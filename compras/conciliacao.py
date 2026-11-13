"""A conciliação das entradas com o registro oficial do SCPI (spec 014, PR 5 e PR 6).

Espelha `conciliacao.servicos`. Neste PR: a conferência dos recebimentos em verificação (o
intervalo e as candidatas, R15). Roda depois de toda extração de entradas bem-sucedida (a de
depois do robô e a do `conciliar_entradas`), sob uma trava própria. Nunca muda um recebimento: só
grava `ConferenciaRecebimento` e `CandidataEntrada`.
"""

import logging
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

from django.db import Error, connection, transaction

from catalogo.models import Importacao
from compras import consultas, regras
from compras.models import (
    CandidataEntrada,
    ConferenciaRecebimento,
    EntradaForaDoCentral,
    ExtracaoEntradas,
    PedidoCompra,
    Recebimento,
    TentativaEntrada,
    TravaPedido,
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


def _oficial(requisicao) -> regras.EntradaOficial:
    return regras.EntradaOficial(
        requisicao=requisicao.requisicao,
        recebimento_observado=requisicao.recebimento_observado,
        fornecedor_codigo=requisicao.fornecedor_codigo,
        nf=requisicao.nf,
        pedido_ano=requisicao.pedido_ano,
        pedido_numero=requisicao.pedido_numero,
        data_entrada=requisicao.data_entrada,
        itens=tuple((i.codigo, i.quantidade) for i in requisicao.itens.all()),
    )


def _entrega(recebimento: Recebimento, tentativa) -> regras.EntregaEntrada:
    """O que o recebimento deveria ter feito no SCPI: a foto da tentativa (o que o robô digitou) ou,
    sem ela, o próprio recebimento (um lançado à mão ou de antes da conciliação)."""
    foto = tentativa.foto if tentativa and tentativa.foto else None
    pedido = recebimento.pedido
    if foto:
        itens = tuple((i["codigo"], Decimal(str(i["quantidade"]))) for i in foto["itens"])
        dia = date.fromisoformat(foto["data"])
    else:
        itens = tuple(
            (linha.item.codigo, linha.quantidade)
            for linha in recebimento.itens.select_related("item")
        )
        dia = recebimento.data_recebimento
    return regras.EntregaEntrada(
        fornecedor_codigo=recebimento.fornecedor_codigo,
        nf=recebimento.nf,
        pedido_ano=pedido.ano,
        pedido_numero=pedido.numero,
        data=dia,
        itens=itens,
    )


def _primeira_conclusiva(recebimento):
    from compras.consultas import _conclusivas

    return (
        _conclusivas(recebimento).select_related("requisicao").order_by("criada_em", "pk").first()
    )


def _ja_achou_a_requisicao(recebimento) -> bool:
    """Se alguma conferência anterior (conclusiva ou não) já ligou o recebimento a uma requisição:
    a primeira conclusiva pode ter sido um Não encontrado, e a requisição achada depois não deixa
    de existir se sumir numa terceira extração."""
    from compras.models import ConferenciaRecebimento

    return ConferenciaRecebimento.objects.filter(
        recebimento=recebimento,
        tipo__in=(ConferenciaRecebimento.Tipo.LANCAMENTO, ConferenciaRecebimento.Tipo.REVISAO),
        requisicao__isnull=False,
    ).exists()


def conciliar_lancados(
    extracao: ExtracaoEntradas, falhas: list[str] | None = None
) -> dict[str, int]:
    """Grava o veredito de cada recebimento lançado coberto pela extração (R17).

    Só conta a extração bem-sucedida que começou depois do lançamento do recebimento. Enquanto ele
    não tem conferência conclusiva, a conferência é do tipo `LANCAMENTO` (as `AGUARDANDO` são
    provisórias); depois da primeira conclusiva, as seguintes são `REVISAO`, com o "alterado no
    SCPI depois do lançamento" contra a requisição daquela. Devolve a contagem por veredito. Nunca
    muda o recebimento (FR-027). Com `falhas`, o que quebra vai para a lista e os seguintes
    continuam; sem ela, sobe."""
    contagem: dict[str, int] = {}
    if not extracao.bem_sucedida:
        return contagem
    imp = extracao.importacao
    oficiais = [
        _oficial(requisicao) for requisicao in extracao.requisicoes_lidas.prefetch_related("itens")
    ]
    pk_por_numero = dict(extracao.requisicoes_lidas.values_list("requisicao", "pk"))
    lancados = Recebimento.objects.filter(
        status=Recebimento.Status.LANCADO,
        data_recebimento__range=(imp.periodo_de, imp.periodo_ate),
    ).select_related("pedido")
    for recebimento in lancados.order_by("pk"):
        try:
            lancado = recebimento.lancado_em
            if lancado is None or imp.inicio <= lancado:
                continue  # a extração começou antes do lançamento: não pode trazê-lo
            if ConferenciaRecebimento.objects.filter(
                recebimento=recebimento,
                extracao=extracao,
                tipo__in=(
                    ConferenciaRecebimento.Tipo.LANCAMENTO,
                    ConferenciaRecebimento.Tipo.REVISAO,
                ),
            ).exists():
                continue
            primeira = _primeira_conclusiva(recebimento)
            if primeira is not None and extracao.motivo == ExtracaoEntradas.Motivo.ARQUIVO:
                continue  # um arquivo antigo não revisa um veredito: não se sabe quando saiu
            tentativa = (
                TentativaEntrada.objects.filter(
                    recebimento=recebimento,
                    foto__isnull=False,
                    resultado__in=(
                        TentativaEntrada.Resultado.LANCADA,
                        TentativaEntrada.Resultado.VERIFICAR,
                    ),
                )
                .order_by("-momento", "-pk")
                .first()
            )
            em_outro = (
                Recebimento.objects.filter(requisicao_scpi=recebimento.requisicao_scpi)
                .exclude(pk=recebimento.pk)
                .exclude(status=Recebimento.Status.CANCELADO)
                .exists()
            )
            resultado = regras.veredito_entrada(
                recebimento.rotulo,
                recebimento.requisicao_scpi,
                oficiais,
                _entrega(recebimento, tentativa),
                fornecedor=recebimento.fornecedor_codigo,
                nf=recebimento.nf,
                maior=extracao.maior_requisicao,
                numero_em_outro_recebimento=em_outro,
                ja_vista=_ja_achou_a_requisicao(recebimento),
            )
            tipo = (
                ConferenciaRecebimento.Tipo.REVISAO
                if primeira
                else ConferenciaRecebimento.Tipo.LANCAMENTO
            )
            alterado = False
            diferencas = list(resultado.diferencas)
            if primeira is not None and primeira.requisicao:
                if resultado.requisicao:
                    mudou = regras.alteracoes_entrada(
                        _oficial(primeira.requisicao), resultado.requisicao
                    )
                else:  # a requisição conferida no lançamento sumiu do relatório (excluída)
                    mudou = [
                        {
                            "campo": "requisição",
                            "antes": primeira.requisicao.requisicao,
                            "agora": "(ausente no relatório)",
                        }
                    ]
                alterado = bool(mudou)
                diferencas += [
                    {
                        "campo": m["campo"],
                        "esperado": m["antes"],
                        "oficial": m["agora"],
                        "alteracao": True,
                    }
                    for m in mudou
                ]
            ConferenciaRecebimento.objects.create(
                recebimento=recebimento,
                extracao=extracao,
                tipo=tipo,
                veredito=resultado.veredito,
                requisicao_id=pk_por_numero.get(resultado.requisicao.requisicao)
                if resultado.requisicao
                else None,
                outra_requisicao_id=pk_por_numero.get(resultado.outra.requisicao)
                if resultado.outra
                else None,
                vinculos=list(resultado.vinculos),
                diferencas=diferencas,
                notas=list(resultado.notas),
                alterado_depois=alterado,
                tentativa=tentativa,
            )
            contagem[resultado.veredito] = contagem.get(resultado.veredito, 0) + 1
        except Exception as exc:
            if falhas is None:
                raise
            logger.exception("⚠ não foi possível conferir o recebimento %s (lançado)", recebimento)
            falhas.append(f"recebimento {recebimento.rotulo} (lançado): {exc}")
    return contagem


def conciliar_fora(extracao: ExtracaoEntradas, falhas: list[str] | None = None) -> dict[str, int]:
    """As entradas por pedido feitas direto no SCPI (R18): a requisição de um pedido conhecido,
    sem a marca do Central, ainda não ligada e com número acima do marco.

    Com um recebimento aberto do mesmo pedido, NF e fornecedor, ele é ligado à requisição como
    lançado à mão; senão vira uma `EntradaForaDoCentral`, que reserva o saldo e trava o pedido. A
    marca de um recebimento que não está lançado nem em verificação trava o pedido. Um arquivo
    (`ARQUIVO`) não entra: a hora real da entrada é desconhecida. Devolve as contagens."""
    contagem: dict[str, int] = {}
    if not extracao.bem_sucedida or extracao.motivo == ExtracaoEntradas.Motivo.ARQUIVO:
        return contagem
    marco = consultas.marco()
    if marco is None:
        return contagem
    for requisicao in extracao.requisicoes_lidas.prefetch_related("itens").order_by(
        "ano", "numero"
    ):
        try:
            if regras_saidas.chave(requisicao.requisicao) <= regras_saidas.chave(marco):
                continue  # história anterior ao Central: já está no "Já Entrou" da base
            resultado = _entrada_de_fora(extracao, requisicao)
            if resultado:
                contagem[resultado] = contagem.get(resultado, 0) + 1
        except Exception as exc:
            if falhas is None:
                raise
            logger.exception("⚠ não foi possível conferir a entrada %s", requisicao.requisicao)
            falhas.append(f"entrada {requisicao.requisicao} (fora do Central): {exc}")
    return contagem


def _entrada_de_fora(extracao, requisicao) -> str:
    """Trata uma requisição acima do marco; devolve o que fez (vazio: nada)."""
    from compras.servicos import travar_pedido

    pedido = (
        PedidoCompra.objects.filter(ano=requisicao.pedido_ano, numero=requisicao.pedido_numero)
        .order_by("-exercicio")
        .first()
        if requisicao.pedido_numero
        else None
    )
    if pedido is None:
        return ""  # entrada sem pedido, ou de um pedido que o Central não conhece
    marca = requisicao.recebimento_observado
    if marca:
        dono = Recebimento.objects.filter(
            pk=int(marca.split("-")[1]) if marca.split("-")[1].isdigit() else 0
        ).first()
        if dono is not None and dono.status in (
            Recebimento.Status.LANCADO,
            Recebimento.Status.VERIFICAR,
            Recebimento.Status.EM_LANCAMENTO,
        ):
            return ""  # entrada do próprio Central: o veredito dela é de outra etapa
        detalhe = (
            f"A requisição {requisicao.requisicao} tem a marca {marca}, mas o recebimento "
            + ("não está lançado." if dono else "não existe.")
        )
        # Uma trava aberta igual já diz isso: outra passagem pela mesma requisição (a mesma
        # extração conciliada de novo, ou uma posterior que ainda a lista) não a repete.
        if not TravaPedido.objects.filter(
            pedido=pedido,
            motivo=TravaPedido.Motivo.MARCA_SEM_LANCAMENTO,
            detalhe=detalhe,
            destravada_em__isnull=True,
        ).exists():
            travar_pedido(
                pedido.pk,
                TravaPedido.Motivo.MARCA_SEM_LANCAMENTO,
                detalhe,
                extracao=extracao,
                recebimento=dono,
            )
        return "MARCA_SEM_LANCAMENTO"
    numero = requisicao.requisicao
    with transaction.atomic():
        return _ligar_ou_registrar(extracao, requisicao, pedido, numero)


def _ligar_ou_registrar(extracao, requisicao, pedido, numero: str) -> str:
    """Liga a requisição ao recebimento aberto da mesma NF ou a registra como entrada fora do
    Central, com a trava do pedido. Numa transação só, com o pedido travado: o registro sem a
    trava (uma falha entre os dois) nunca mais seria refeito, porque a entrada já existiria."""
    from compras.servicos import ligar_a_mao, travar_pedido

    PedidoCompra.objects.select_for_update().get(pk=pedido.pk)
    if (
        Recebimento.objects.filter(requisicao_scpi=numero)
        .exclude(status=Recebimento.Status.CANCELADO)
        .exists()
        or EntradaForaDoCentral.objects.filter(
            ano=requisicao.ano, numero=requisicao.numero
        ).exists()
    ):
        return ""  # já ligada
    aberto = (
        Recebimento.objects.filter(
            pedido=pedido,
            nf=requisicao.nf,
            fornecedor_codigo=requisicao.fornecedor_codigo,
            status__in=(
                Recebimento.Status.PREPARADO,
                Recebimento.Status.ERRO,
                Recebimento.Status.VERIFICAR,
            ),
        )
        .order_by("pk")
        .first()
        if requisicao.nf
        else None
    )
    if aberto is not None:
        resposta = ligar_a_mao(aberto.pk, requisicao.requisicao, extracao.importacao.inicio)
        return "LIGADO_A_MAO" if resposta.ok else ""
    EntradaForaDoCentral.objects.create(
        pedido=pedido,
        requisicao=requisicao,
        ano=requisicao.ano,
        numero=requisicao.numero,
        visivel_desde=extracao.importacao.inicio,
        itens=[
            {"codigo": i.codigo, "quantidade": format(i.quantidade.normalize(), "f")}
            for i in requisicao.itens.all()
        ],
    )
    travar_pedido(
        pedido.pk,
        TravaPedido.Motivo.FORA_DO_CENTRAL,
        f"A requisição {numero} (NF {requisicao.nf or 'sem NF'}) foi feita direto no SCPI.",
        extracao=extracao,
    )
    return "FORA_DO_CENTRAL"


class ConciliacaoIncompleta(Exception):
    """Alguma etapa ou algum recebimento falhou: o que deu certo ficou gravado (`contagem`)."""

    def __init__(self, contagem: dict[str, int], falhas: list[str]):
        self.contagem = contagem
        self.falhas = falhas
        super().__init__("Conciliação das entradas incompleta: " + "; ".join(falhas))


def conciliar(extracao: ExtracaoEntradas) -> dict[str, int]:
    """Toda a conciliação de uma extração, sob a trava: primeiro os recebimentos em verificação
    (a que protege contra lançar duas vezes), depois as entradas fora do Central e os lançados. Uma
    falha não impede as outras etapas, mas não fica escondida: no fim, `ConciliacaoIncompleta`
    leva a contagem do que ficou gravado e o que falhou."""
    contagem: dict[str, int] = {}
    falhas: list[str] = []
    etapas = (
        ("VERIFICAR", "recebimentos em verificação", conciliar_verificar, True),
        ("fora", "entradas fora do Central", conciliar_fora, False),
        ("lancados", "recebimentos lançados", conciliar_lancados, False),
    )
    with trava_conciliacao():
        for chave_etapa, nome, etapa, e_inteiro in etapas:
            try:
                resultado = etapa(extracao, falhas)
            except Exception as exc:
                logger.exception("⚠ não foi possível conferir: %s", nome)
                falhas.append(f"{nome}: {exc}")
                continue
            if e_inteiro:
                if resultado:
                    contagem[chave_etapa] = resultado
            else:
                contagem = {**resultado, **contagem}
    if falhas:
        raise ConciliacaoIncompleta(contagem, falhas)
    return contagem
