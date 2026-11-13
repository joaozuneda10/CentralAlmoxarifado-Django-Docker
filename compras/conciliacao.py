"""A conciliação das entradas com o registro oficial do SCPI (spec 014, PR 5 e PR 6).

Espelha `conciliacao.servicos`. Neste PR: a conferência dos recebimentos em verificação (o
intervalo e as candidatas, R15). Roda depois de toda extração de entradas bem-sucedida (a de
depois do robô e a do `conciliar_entradas`), sob uma trava própria. Nunca muda um recebimento: só
grava `ConferenciaRecebimento` e `CandidataEntrada`.
"""

import logging
from contextlib import contextmanager

from django.db import Error, connection, transaction

from catalogo.models import Importacao
from compras import regras
from compras.models import (
    CandidataEntrada,
    ConferenciaRecebimento,
    ExtracaoEntradas,
    Recebimento,
    TentativaEntrada,
)
from conciliacao import regras as regras_saidas

logger = logging.getLogger("scpi.lancamento_entradas")

# Uma conciliação de entradas por vez entre processos (`GET_LOCK`), como a das saídas.
TRAVA_CONCILIACAO_ENTRADAS = "almoxarifado:conciliacao_entradas"
ESPERA_TRAVA_S = 30
EM_VERIFICACAO = (Recebimento.Status.VERIFICAR, Recebimento.Status.EM_LANCAMENTO)


class ConciliacaoEmAndamento(Exception):
    """Outra conciliação de entradas segura a trava."""


@contextmanager
def trava_conciliacao(espera: int | None = None):
    """Uma conciliação por vez (`GET_LOCK`, com espera): duas ao mesmo tempo poderiam gravar, cada
    uma, a conferência do mesmo recebimento. `espera` em segundos; sem ela, `ESPERA_TRAVA_S`."""
    espera = ESPERA_TRAVA_S if espera is None else espera
    with connection.cursor() as cursor:
        cursor.execute("SELECT GET_LOCK(%s, %s)", [TRAVA_CONCILIACAO_ENTRADAS, espera])
        obtida = cursor.fetchone()[0] == 1
    if not obtida:
        raise ConciliacaoEmAndamento("Outra conciliação de entradas com o SCPI está em andamento.")
    try:
        yield
    finally:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT RELEASE_LOCK(%s)", [TRAVA_CONCILIACAO_ENTRADAS])
        except Error:
            logger.warning("Não foi possível liberar a trava da conciliação.", exc_info=True)


def ultima_tentativa(recebimento: Recebimento) -> TentativaEntrada | None:
    """A tentativa mais recente que chegou ao Salvar (`VERIFICAR` ou `LANCADA`): é a que a
    verificação investiga. A que não passou pelo Salvar (`ERRO`, `IGNORADA`) não conta."""
    return (
        TentativaEntrada.objects.filter(
            recebimento=recebimento,
            resultado__in=(
                TentativaEntrada.Resultado.VERIFICAR,
                TentativaEntrada.Resultado.LANCADA,
            ),
        )
        .select_related("execucao")
        .order_by("-momento", "-pk")
        .first()
    )


def piso(execucao) -> str | None:
    """O maior número de requisição de entrada que já existia quando a execução começou: o da
    extração de antes; sem ela (uma execução histórica), o maior número lançado pelo robô antes do
    início."""
    antes = (
        ExtracaoEntradas.objects.filter(
            execucao=execucao,
            motivo=ExtracaoEntradas.Motivo.ANTES,
            importacao__situacao=Importacao.Situacao.SUCESSO,
        )
        .order_by("-pk")
        .first()
    )
    if antes is not None:
        return antes.maior_requisicao
    numeros = (
        Recebimento.objects.filter(lancado_em__lt=execucao.inicio)
        .exclude(requisicao_scpi="")
        .values_list("requisicao_scpi", flat=True)
        .distinct()
    )
    return regras_saidas.maior_requisicao(
        n for n in numeros if regras_saidas.RE_REQUISICAO.match(n)
    )


def _resumo(requisicao) -> regras.RequisicaoEntradaResumo:
    return regras.RequisicaoEntradaResumo(
        requisicao=requisicao.requisicao,
        recebimento_observado=requisicao.recebimento_observado,
        fornecedor_codigo=requisicao.fornecedor_codigo,
        nf=requisicao.nf,
        pedido_ano=requisicao.pedido_ano,
        pedido_numero=requisicao.pedido_numero,
        itens=tuple((item.codigo, item.quantidade) for item in requisicao.itens.all()),
    )


def _cobre(extracao: ExtracaoEntradas, data) -> bool:
    imp = extracao.importacao
    return imp.periodo_de is not None and imp.periodo_de <= data <= imp.periodo_ate


def conciliar_verificar(extracao: ExtracaoEntradas, falhas: list[str] | None = None) -> int:
    """Grava, para cada recebimento em verificação coberto pela extração, a conferência com o
    intervalo e as candidatas (R15). Só vale a extração bem-sucedida que começou depois da
    tentativa; um recebimento sem tentativa registrada ganha `SEM_TENTATIVA`. Devolve quantas
    gravou. Com `falhas`, o recebimento que quebra vai para a lista e os seguintes continuam; sem
    ela, sobe."""
    if not extracao.bem_sucedida or extracao.motivo == ExtracaoEntradas.Motivo.ARQUIVO:
        # Um arquivo exportado antes do Salvar perdido não traria a requisição: se contasse, o
        # intervalo sairia vazio e o recebimento seria relançado (Princípio III).
        return 0
    lidas = {
        requisicao.pk: _resumo(requisicao)
        for requisicao in extracao.requisicoes_lidas.prefetch_related("itens")
    }
    por_numero = {resumo.requisicao: pk for pk, resumo in lidas.items()}
    gravadas = 0
    abertos = Recebimento.objects.filter(status__in=EM_VERIFICACAO).select_related("pedido")
    for recebimento in abertos.order_by("pk"):
        try:
            if not _cobre(extracao, recebimento.data_recebimento):
                continue
            if ConferenciaRecebimento.objects.filter(
                recebimento=recebimento,
                extracao=extracao,
                tipo=ConferenciaRecebimento.Tipo.VERIFICAR,
            ).exists():
                continue
            tentativa = ultima_tentativa(recebimento)
            if tentativa is None:
                ConferenciaRecebimento.objects.create(
                    recebimento=recebimento,
                    extracao=extracao,
                    tipo=ConferenciaRecebimento.Tipo.VERIFICAR,
                    veredito=ConferenciaRecebimento.Veredito.SEM_TENTATIVA,
                )
                gravadas += 1
                continue
            if extracao.importacao.inicio <= tentativa.momento:
                continue  # a extração não é posterior à tentativa: não prova nada sobre ela
            tentativas = [
                regras_saidas.TentativaResumo(t.ordem, t.recebimento.rotulo, t.requisicao)
                for t in tentativa.execucao.tentativas_entradas.select_related("recebimento")
            ]
            de, ate = regras_saidas.intervalo(
                tentativas, piso(tentativa.execucao), recebimento.rotulo
            )
            achadas = regras.candidatas(
                lidas.values(),
                rotulo=recebimento.rotulo,
                fornecedor=recebimento.fornecedor_codigo,
                nf=recebimento.nf,
                pedido=(recebimento.pedido.ano, recebimento.pedido.numero),
                de=de,
                ate=ate,
                foto=tentativa.foto,
            )
            with transaction.atomic():
                conferencia = ConferenciaRecebimento.objects.create(
                    recebimento=recebimento,
                    extracao=extracao,
                    tipo=ConferenciaRecebimento.Tipo.VERIFICAR,
                    veredito=ConferenciaRecebimento.Veredito.COM_CANDIDATAS
                    if achadas
                    else ConferenciaRecebimento.Veredito.INTERVALO_VAZIO,
                    intervalo_de=de or "",
                    intervalo_ate=ate or "",
                    tentativa=tentativa,
                )
                CandidataEntrada.objects.bulk_create(
                    CandidataEntrada(
                        conferencia=conferencia,
                        requisicao_id=por_numero[resumo.requisicao],
                        e_esta=e_esta,
                        ordem=ordem,
                    )
                    for ordem, (resumo, e_esta) in enumerate(achadas, start=1)
                )
            gravadas += 1
            logger.info(
                "  %s em verificação: intervalo %s a %s, %d candidata(s)",
                recebimento.rotulo,
                de or "(aberto)",
                ate or "(aberto)",
                len(achadas),
            )
        except Exception as exc:
            if falhas is None:
                raise
            logger.exception("⚠ não foi possível conferir o recebimento %s", recebimento.rotulo)
            falhas.append(f"recebimento {recebimento.rotulo} (em verificação): {exc}")
    return gravadas


def conciliar(extracao: ExtracaoEntradas) -> dict[str, int]:
    """O que se concilia depois de uma extração de entradas bem-sucedida: neste PR, os
    recebimentos em verificação. Devolve as contagens (para o resumo do comando e o log)."""
    with trava_conciliacao():
        verificar = conciliar_verificar(extracao)
    return {"VERIFICAR": verificar} if verificar else {}
