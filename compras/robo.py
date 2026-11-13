"""O que o robô de entradas faz pelo recebimento (spec 014, PR 4): a seleção, o esperado da tela,
as extrações antes e depois e o registro de cada tentativa.

Nada aqui muda a ordem das gravações que impede lançar duas vezes (Princípio III): a extração de
antes só acrescenta uma condição para começar, e a tentativa é gravada na mesma transação que
confirma o `EM_LANCAMENTO`, antes do Salvar (`scpi.lancamento_entradas`).
"""

import logging
import re
from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from catalogo.models import Importacao
from compras import consultas, regras
from compras.extracao import extrair
from compras.models import (
    ExtracaoEntradas,
    ItemRecebimento,
    Recebimento,
    RequisicaoEntradaOficial,
    TentativaEntrada,
)
from conciliacao import robo as robo_saidas
from conciliacao.regras import periodo as periodo_do_relatorio
from scpi.execucao import ImportacaoEmAndamento
from scpi.leitura import ErroImportacao

logger = logging.getLogger("scpi.lancamento_entradas")

Extrair = Callable[[date, date], bytes]
RE_ROTULO = re.compile(r"^RC-(\d+)$", re.IGNORECASE)
EM_ABERTO = (Recebimento.Status.EM_LANCAMENTO, Recebimento.Status.VERIFICAR)


class ExtracaoAntesFalhou(ErroImportacao):
    """A extração de antes não deu certo em nenhuma tentativa: a execução não lança nada."""


@dataclass
class Selecao:
    """O resultado da seleção: os recebimentos que o robô pode lançar (na ordem escolhida) e os
    bloqueados, cada um com o motivo em português."""

    aptos: list[regras.RecebimentoParaLancar] = field(default_factory=list)
    bloqueados: list[tuple[str, str]] = field(default_factory=list)


def _id_do_rotulo(rotulo: str) -> int | None:
    casou = RE_ROTULO.match((rotulo or "").strip())
    return int(casou.group(1)) if casou else None


def motivo_de_bloqueio(recebimento: Recebimento, hoje: date | None = None) -> str:
    """Por que o recebimento não pode ir ao SCPI agora (vazio: pode). Vale na seleção e de novo
    imediatamente antes de abrir o pedido: o robô nunca confia só na seleção."""
    hoje = hoje or timezone.localdate()
    if recebimento.status != Recebimento.Status.PREPARADO:
        return f"o recebimento está {recebimento.get_status_display().lower()}, não preparado"
    pedido = recebimento.pedido
    if pedido.exercicio != hoje.year:
        return "o pedido é de outro exercício"
    if pedido.ausente_desde_id is not None:
        return "o pedido não veio na última importação"
    if pedido.travas.filter(destravada_em__isnull=True).exists():
        return "o pedido está travado"
    outro = (
        Recebimento.objects.filter(pedido=pedido, status__in=EM_ABERTO)
        .exclude(pk=recebimento.pk)
        .first()
    )
    if outro is not None:
        situacao = (
            "em verificação" if outro.status == Recebimento.Status.VERIFICAR else "em lançamento"
        )
        return f"o pedido tem um recebimento {situacao}"
    return ""


def _nao_refletido(item_id: int, exercicio: int) -> Decimal:
    """O que os recebimentos lançados do Central já tiraram do saldo de um item e a última
    importação de pedidos ainda não mostra (R5): a mesma condição da reserva do lançado."""
    ultima = consultas.ultima_importacao_pedidos(exercicio)
    inicio = ultima.inicio if ultima else None
    total = Decimal(0)
    for linha in ItemRecebimento.objects.filter(
        item_id=item_id, recebimento__status=Recebimento.Status.LANCADO
    ).select_related("recebimento"):
        if regras.reserva_de(
            "LANCADO",
            visivel_desde=linha.recebimento.visivel_desde,
            inicio_ultima_importacao=inicio,
        ):
            total += linha.quantidade
    return total


def para_lancar(recebimento: Recebimento) -> regras.RecebimentoParaLancar:
    """O recebimento como o robô o recebe: dado puro, com o texto das Observações já montado e o
    esperado da tela para cada item (R11)."""
    pedido = recebimento.pedido
    linhas = list(recebimento.itens.select_related("item").order_by("item__item"))
    itens = tuple(
        regras.ItemParaLancar(linha.item.item, linha.item.codigo, linha.quantidade)
        for linha in linhas
    )
    esperado = []
    for linha in linhas:
        ja_entrou, saldo = regras.esperado_do_item(
            ja_entrou=linha.item.ja_entrou,
            saldo=linha.item.saldo_scpi,
            nao_refletido=_nao_refletido(linha.item_id, pedido.exercicio),
        )
        esperado.append(
            regras.EsperadoItem(
                linha.item.item, linha.item.codigo, linha.quantidade, ja_entrou, saldo
            )
        )
    return regras.RecebimentoParaLancar(
        id=recebimento.pk,
        rotulo=recebimento.rotulo,
        versao=recebimento.versao,
        pedido_id=pedido.pk,
        pedido_ano=pedido.ano,
        pedido_numero=pedido.numero,
        pedido_rotulo=pedido.rotulo,
        fornecedor_codigo=recebimento.fornecedor_codigo,
        nf=recebimento.nf,
        data=recebimento.data_recebimento,
        observacoes=regras.texto_observacao_item(recebimento.rotulo, recebimento.observacao),
        itens=itens,
        esperado=tuple(esperado),
    )


def selecionar(rotulos: Collection[str], hoje: date | None = None) -> Selecao:
    """Dos recebimentos escolhidos (`RC-0001`), os que o robô pode lançar e os bloqueados, com o
    motivo. A ordem dos aptos é a do número do recebimento (a da preparação)."""
    hoje = hoje or timezone.localdate()
    selecao = Selecao()
    ids = {}
    for rotulo in rotulos:
        pk = _id_do_rotulo(rotulo)
        if pk is None:
            selecao.bloqueados.append((rotulo, "o número do recebimento é inválido"))
        else:
            ids[pk] = rotulo
    achados = {
        r.pk: r
        for r in Recebimento.objects.filter(pk__in=ids).select_related("pedido").order_by("pk")
    }
    for pk in sorted(ids):
        recebimento = achados.get(pk)
        if recebimento is None:
            selecao.bloqueados.append((ids[pk], "o recebimento não existe"))
            continue
        motivo = motivo_de_bloqueio(recebimento, hoje)
        if motivo:
            selecao.bloqueados.append((recebimento.rotulo, motivo))
        else:
            selecao.aptos.append(para_lancar(recebimento))
    return selecao


def periodo_da_execucao(
    recebimentos: Iterable[regras.RecebimentoParaLancar], hoje: date
) -> tuple[date, date]:
    """Do dia anterior à data de recebimento mais antiga envolvida (os da execução e os em
    verificação ainda abertos) até o dia seguinte a hoje."""
    datas = [rec.data for rec in recebimentos]
    datas += Recebimento.objects.filter(status__in=EM_ABERTO).values_list(
        "data_recebimento", flat=True
    )
    return periodo_do_relatorio(datas, hoje)


def _uma_extracao(motivo, periodo, baixar: Extrair, execucao) -> ExtracaoEntradas | None:
    """Uma tentativa: a extração registrada, ou None quando outra extração segurava a trava."""
    de, ate = periodo
    try:
        return extrair(motivo, periodo, lambda: baixar(de, ate), execucao=execucao)
    except ImportacaoEmAndamento:
        logger.warning("⚠ outra extração de entradas do SCPI está em andamento")
        return None


def extrair_antes(execucao, periodo: tuple[date, date], baixar: Extrair) -> ExtracaoEntradas:
    """A extração de antes, com até `TENTATIVAS_EXTRACAO` tentativas. Sem nenhuma bem-sucedida,
    levanta `ExtracaoAntesFalhou` antes de qualquer recebimento mudar."""
    tentativas = robo_saidas.TENTATIVAS_EXTRACAO
    ultimo_erro = "outra extração estava em andamento"
    for tentativa in range(1, tentativas + 1):
        if tentativa > 1:
            robo_saidas._dormir(robo_saidas.PAUSA_EXTRACAO_S)
        logger.info(
            "→ extraindo as entradas do SCPI antes de lançar (%d/%d), %s a %s",
            tentativa,
            tentativas,
            f"{periodo[0]:%d/%m/%Y}",
            f"{periodo[1]:%d/%m/%Y}",
        )
        extracao = _uma_extracao(ExtracaoEntradas.Motivo.ANTES, periodo, baixar, execucao)
        if extracao is not None and extracao.bem_sucedida:
            logger.info(
                "✔ %d requisições de entrada no SCPI; a maior é %s (o piso desta execução)",
                extracao.requisicoes,
                extracao.maior_requisicao or "nenhuma",
            )
            return extracao
        if extracao is not None:
            ultimo_erro = extracao.importacao.erro
            logger.warning("⚠ extração de antes falhou: %s", ultimo_erro)
    raise ExtracaoAntesFalhou(
        "Não foi possível extrair as entradas do SCPI antes de lançar "
        f"({tentativas} tentativas; a última: {ultimo_erro}). Nenhum recebimento foi lançado."
    )


MENSAGEM_REAL_BLOQUEADO = (
    "O lançamento real das entradas está bloqueado neste ambiente "
    "(LANCAMENTO_REAL_ENTRADAS=0 no .env): só a simulação roda."
)


def lancamento_real_liberado() -> bool:
    """Se o robô de entradas pode salvar de verdade no SCPI: a trava geral do lançamento real e
    a própria das entradas, as duas ligadas."""
    return bool(settings.LANCAMENTO_REAL and settings.LANCAMENTO_REAL_ENTRADAS)


def motivo_do_bloqueio_real() -> str:
    """A mensagem do bloqueio, pela trava que está desligada (a geral vem primeiro)."""
    from scpi.lancamento import LANCAMENTO_BLOQUEADO

    return LANCAMENTO_BLOQUEADO if not settings.LANCAMENTO_REAL else MENSAGEM_REAL_BLOQUEADO


def ja_no_scpi(extracao: ExtracaoEntradas, aptos) -> dict[int, str]:
    """Dos recebimentos aptos, os que o registro oficial já tem no SCPI, com o número da
    requisição: a que tem a marca dele nas observações ou a NF e o fornecedor dele. A conferência
    da tela não pega este caso quando a entrada foi feita por outro item do pedido com o mesmo
    código: o "Já Entrou" do item do recebimento não muda.

    Vale a extração de antes e, além dela, as extrações já guardadas (60 dias): a entrada feita à
    mão com uma data fora do período desta execução não vem na de antes, mas alguma anterior pode
    tê-la visto. A requisição que só uma extração antiga viu e que sumiu de uma posterior que
    cobre a data dela (excluída no SCPI) não conta."""
    achados: dict[int, str] = {}
    for rec in aptos:
        vistas = (
            RequisicaoEntradaOficial.objects.filter(
                extracao__importacao__situacao=Importacao.Situacao.SUCESSO
            )
            .filter(
                Q(recebimento_observado=rec.rotulo)
                | (Q(fornecedor_codigo=rec.fornecedor_codigo, nf=rec.nf) & ~Q(nf=""))
            )
            .select_related("extracao__importacao")
            .order_by("ano", "numero", "-extracao__importacao__inicio")
        )
        for vista in vistas:
            if vista.extracao_id == extracao.pk or not _sumiu_depois(vista):
                achados[rec.id] = vista.requisicao
                break
    return achados


def _sumiu_depois(vista: RequisicaoEntradaOficial) -> bool:
    """Se uma extração bem-sucedida, lida do SCPI depois da que viu esta requisição e cobrindo a
    data de entrada dela, já não a traz: a entrada foi excluída no SCPI."""
    return (
        ExtracaoEntradas.objects.filter(
            importacao__situacao=Importacao.Situacao.SUCESSO,
            importacao__inicio__gt=vista.extracao.importacao.inicio,
            importacao__periodo_de__lte=vista.data_entrada,
            importacao__periodo_ate__gte=vista.data_entrada,
        )
        .exclude(motivo=ExtracaoEntradas.Motivo.ARQUIVO)
        .exclude(requisicoes_lidas__ano=vista.ano, requisicoes_lidas__numero=vista.numero)
        .exists()
    )


def extrair_depois(execucao, periodo: tuple[date, date], baixar: Extrair) -> None:
    """A extração de depois, uma tentativa. Qualquer falha, inclusive do banco ao registrá-la, só
    vai para o log: os recebimentos já lançados ficam aguardando conferência, e a situação da
    execução não piora."""
    logger.info("→ extraindo as entradas do SCPI depois do lançamento")
    try:
        extracao = _uma_extracao(ExtracaoEntradas.Motivo.DEPOIS, periodo, baixar, execucao)
    except Exception:
        logger.exception(
            "⚠ extração de depois não pôde ser registrada; os recebimentos ficam aguardando "
            "conferência"
        )
        return
    if extracao is None:
        return
    if extracao.importacao.situacao == Importacao.Situacao.SUCESSO:
        logger.info(
            "✔ %d requisições de entrada no SCPI depois do lançamento", extracao.requisicoes
        )
    else:
        logger.warning(
            "⚠ extração de depois falhou (%s); os recebimentos ficam aguardando conferência",
            extracao.importacao.erro,
        )


def registrar_tentativa(
    execucao,
    ordem: int,
    rec: regras.RecebimentoParaLancar,
    resultado: str,
    tela: regras.TelaItens | None = None,
) -> TentativaEntrada:
    """Cria a tentativa. Chamada dentro da transação do `_travar` (resultado `VERIFICAR`, o lado
    seguro se o processo morrer) ou, sem ela, para o recebimento que falhou antes do Salvar."""
    return TentativaEntrada.objects.create(
        execucao=execucao,
        ordem=ordem,
        recebimento_id=rec.id,
        versao=rec.versao,
        momento=timezone.now(),
        resultado=resultado,
        foto=regras.foto(rec, tela),
    )


def tentativa_lancada(execucao, recebimento_id: int, numero: str) -> None:
    """Marca a tentativa como lançada com o número obtido. Falha aqui só vai para o log: o
    recebimento já está gravado e o journal tem o número; sem o número, o intervalo de uma
    verificação seguinte fica mais largo, o que só bloqueia mais (lado seguro)."""
    try:
        TentativaEntrada.objects.filter(execucao=execucao, recebimento_id=recebimento_id).update(
            resultado=TentativaEntrada.Resultado.LANCADA, requisicao=numero
        )
    except Exception:
        logger.exception("Não foi possível registrar o número %s na tentativa.", numero)
