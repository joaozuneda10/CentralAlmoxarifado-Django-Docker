"""A reversão da `compras/0002` recusa o que o arredondamento a 4 casas estragaria."""

from datetime import date
from decimal import Decimal
from importlib import import_module

import pytest
from django.apps import apps
from django.db.migrations.exceptions import IrreversibleError

from catalogo.models import Importacao
from compras.models import ItemPedidoCompra, PedidoCompra

pytestmark = pytest.mark.django_db

migracao = import_module("compras.migrations.0002_quantidades_com_6_casas")


def _item(quantidade: str) -> ItemPedidoCompra:
    imp = Importacao.objects.create(tipo=Importacao.Tipo.PEDIDOS_COMPRA)
    pedido = PedidoCompra.objects.create(
        exercicio=2026,
        ano=2026,
        numero=514,
        data=date(2026, 3, 2),
        fornecedor_codigo="19502",
        atualizado_por=imp,
    )
    q = Decimal(quantidade)
    return ItemPedidoCompra.objects.create(
        pedido=pedido,
        item=1,
        codigo="006.011.020",
        controle="Q",
        quantidade=q,
        anulado=0,
        ja_entrou=0,
        pedida=0,
        saldo_scpi=q,
        preco=1,
    )


def test_reversao_com_valor_de_5_casas_e_recusada():
    _item("1.66651")
    with pytest.raises(IrreversibleError, match=r"quantidade.*1\.66651"):
        migracao.recusar_reversao_que_arredonda(apps, None)


def test_reversao_com_valor_que_nao_cabe_nos_14_digitos_e_recusada():
    _item("10000000000.000000")
    with pytest.raises(IrreversibleError, match="não cabe nos 14 dígitos"):
        migracao.recusar_reversao_que_arredonda(apps, None)


def test_reversao_com_o_maior_valor_que_cabe_passa():
    _item("9999999999.9999")
    migracao.recusar_reversao_que_arredonda(apps, None)


def test_reversao_sem_valor_que_arredonde_passa():
    _item("1.5")
    migracao.recusar_reversao_que_arredonda(apps, None)
