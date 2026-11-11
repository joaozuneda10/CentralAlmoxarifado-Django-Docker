"""Avisos de saúde das compras (spec 014): entram na lista curta do painel e nos avisos da visão
geral de Automações, pelo `catalogo.saude._demais`."""

from datetime import datetime

from catalogo.models import Importacao
from catalogo.saude import ItemSaude, _quando, resumo_do_erro
from conciliacao.saude import um_dia_util_depois


def avisos(agora: datetime) -> list[ItemSaude]:
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
