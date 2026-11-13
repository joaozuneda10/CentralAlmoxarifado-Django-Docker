"""Avisos de saúde das compras (spec 014): entram na lista curta do painel e nos avisos da visão
geral de Automações, pelo `catalogo.saude._demais`."""

from datetime import datetime, timedelta

from catalogo.models import Importacao
from catalogo.saude import ItemSaude, _quando, resumo_do_erro
from compras.models import EntradaForaDoCentral, Recebimento, TravaPedido
from conciliacao.saude import um_dia_util_depois


def _pedidos(agora: datetime) -> list[ItemSaude]:
    """A importação de pedidos: falha, interrupção e atraso."""
    saude = []
    tipo = Importacao.Tipo.PEDIDOS_COMPRA
    ultima = Importacao.objects.filter(tipo=tipo).order_by("-inicio").first()
    if ultima is None:
        return saude  # a importação ainda não foi usada: nada a avisar
    if ultima.situacao == Importacao.Situacao.FALHA:
        saude.append(
            ItemSaude(
                "erro",
                "Pedidos de compra: a última importação falhou em "
                f"{_quando(ultima.fim or ultima.inicio)}: {resumo_do_erro(ultima.erro)}",
            )
        )
    elif ultima.esta_interrompida(agora):
        saude.append(
            ItemSaude(
                "aviso",
                "Pedidos de compra: a importação iniciada em "
                f"{_quando(ultima.inicio)} não terminou (interrompida).",
            )
        )
    sucesso = (
        Importacao.objects.filter(tipo=tipo, situacao=Importacao.Situacao.SUCESSO)
        .order_by("-inicio")
        .first()
    )
    if sucesso is None or agora > um_dia_util_depois(sucesso.inicio):
        quando = f"desde {_quando(sucesso.inicio)}" if sucesso else "ainda"
        saude.append(
            ItemSaude(
                "aviso",
                f"Pedidos de compra: sem importação bem-sucedida há mais de um dia útil "
                f"({quando}); o saldo livre pode estar desatualizado.",
            )
        )
    return saude


def avisos(agora: datetime) -> list[ItemSaude]:
    """Os avisos das compras: a importação de pedidos, os recebimentos em verificação ou com erro,
    a extração de entradas, os pedidos travados e as entradas feitas fora do Central."""
    return [
        *_pedidos(agora),
        *_recebimentos(),
        *_extracao_de_entradas(),
        *_pedidos_travados(),
        *_entradas_fora_do_central(agora),
    ]


def _recebimentos() -> list[ItemSaude]:
    """Recebimentos que pedem ação: em verificação (o robô não sabe se o SCPI salvou) e com erro."""
    saude = []
    verificar = Recebimento.objects.filter(
        status__in=(Recebimento.Status.VERIFICAR, Recebimento.Status.EM_LANCAMENTO)
    ).count()
    if verificar:
        saude.append(
            ItemSaude(
                "erro",
                f"Entradas: {verificar} {'recebimento' if verificar == 1 else 'recebimentos'} em "
                "verificação: o robô não sabe se o SCPI gravou. Resolva em Automações › Entradas "
                "no SCPI.",
            )
        )
    com_erro = Recebimento.objects.filter(status=Recebimento.Status.ERRO).count()
    if com_erro:
        saude.append(
            ItemSaude(
                "aviso",
                f"Entradas: {com_erro} {'recebimento' if com_erro == 1 else 'recebimentos'} com "
                "erro (nada foi gravado no SCPI): corrija e libere o recebimento.",
            )
        )
    return saude


def _extracao_de_entradas() -> list[ItemSaude]:
    ultima = Importacao.objects.filter(tipo=Importacao.Tipo.ENTRADAS).order_by("-inicio").first()
    if ultima is None or ultima.situacao != Importacao.Situacao.FALHA:
        return []
    return [
        ItemSaude(
            "erro",
            "Entradas: a última extração do SCPI falhou em "
            f"{_quando(ultima.fim or ultima.inicio)}: {resumo_do_erro(ultima.erro)}",
        )
    ]


def _pedidos_travados() -> list[ItemSaude]:
    """Um aviso por pedido travado, com o motivo (o detalhe fica na aba e no pedido)."""
    saude = []
    abertas = TravaPedido.objects.filter(destravada_em__isnull=True).select_related("pedido")
    por_pedido: dict[int, list[TravaPedido]] = {}
    for trava in abertas.order_by("pedido_id", "-criada_em"):
        por_pedido.setdefault(trava.pedido_id, []).append(trava)
    for travas in por_pedido.values():
        motivos = ", ".join(sorted({t.get_motivo_display().lower() for t in travas}))
        saude.append(
            ItemSaude(
                "aviso",
                f"Pedido {travas[0].pedido.rotulo} travado: {motivos}. Confira no SCPI e destrave "
                "em Automações › Entradas no SCPI.",
            )
        )
    return saude


def _entradas_fora_do_central(agora: datetime) -> list[ItemSaude]:
    recentes = EntradaForaDoCentral.objects.filter(
        visivel_desde__gte=agora - timedelta(days=30)
    ).count()
    if not recentes:
        return []
    return [
        ItemSaude(
            "aviso",
            f"Entradas: {recentes} {'entrada feita' if recentes == 1 else 'entradas feitas'} "
            "direto no SCPI, sem o Central, nos últimos 30 dias.",
        )
    ]
