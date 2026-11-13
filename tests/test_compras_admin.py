"""O admin dos pedidos de compra é só leitura (as gravações vêm do robô e do serviço)."""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from catalogo.models import Importacao
from compras.models import ItemPedidoCompra, PedidoCompra

pytestmark = pytest.mark.django_db


@pytest.fixture
def pedido():
    imp = Importacao.objects.create(tipo=Importacao.Tipo.PEDIDOS_COMPRA)
    p = PedidoCompra.objects.create(
        exercicio=2026,
        ano=2026,
        numero=514,
        data=date(2026, 3, 2),
        fornecedor_codigo="19502",
        fornecedor_nome="FORNECEDOR SINTÉTICO",
        atualizado_por=imp,
    )
    ItemPedidoCompra.objects.create(
        pedido=p,
        item=1,
        codigo="006.011.020",
        controle="Q",
        quantidade=10,
        anulado=0,
        ja_entrou=0,
        pedida=0,
        saldo_scpi=10,
        preco=1,
    )
    return p


@pytest.fixture
def admin_logado(client):
    admin = get_user_model().objects.create_superuser(username="9999", password="x")
    client.force_login(admin)
    return admin


def test_a_lista_abre_e_o_detalhe_mostra_os_itens(client, admin_logado, pedido):
    r = client.get(reverse("admin:compras_pedidocompra_changelist"))
    assert r.status_code == 200 and "00514/26" in r.text
    r = client.get(reverse("admin:compras_pedidocompra_change", args=[pedido.pk]))
    assert r.status_code == 200 and "006.011.020" in r.text


def test_adicionar_alterar_e_apagar_sao_recusados(client, admin_logado, pedido):
    assert client.get(reverse("admin:compras_pedidocompra_add")).status_code == 403
    alterar = reverse("admin:compras_pedidocompra_change", args=[pedido.pk])
    assert client.post(alterar, {"fornecedor_nome": "OUTRO"}).status_code == 403
    apagar = reverse("admin:compras_pedidocompra_delete", args=[pedido.pk])
    assert client.post(apagar, {"post": "yes"}).status_code == 403
    pedido.refresh_from_db()
    assert pedido.fornecedor_nome == "FORNECEDOR SINTÉTICO"


# --- O registro oficial das entradas (PR 3) ---------------------------------------------------


@pytest.fixture
def extracao_com_requisicao():
    from compras.extracao import extrair
    from compras.models import ExtracaoEntradas
    from tests.relacao_entradas import EntradaCSV, csv_entradas

    dia = date(2026, 11, 10)
    return extrair(
        ExtracaoEntradas.Motivo.MANUAL,
        (dia, dia),
        lambda: csv_entradas(
            [EntradaCSV("003492/26", 9001, dia, observacoes="Central Almoxarifado RC-0042")]
        ),
    )


def test_a_extracao_de_entradas_abre_sem_o_bruto(client, admin_logado, extracao_com_requisicao):
    lista = client.get(reverse("admin:compras_extracaoentradas_changelist"))
    assert lista.status_code == 200 and "003492/26" in lista.text
    detalhe = client.get(
        reverse("admin:compras_extracaoentradas_change", args=[extracao_com_requisicao.pk])
    )
    assert detalhe.status_code == 200 and "arquivo bruto" not in detalhe.text


def test_a_requisicao_de_entrada_mostra_os_itens_e_a_marca(
    client, admin_logado, extracao_com_requisicao
):
    requisicao = extracao_com_requisicao.requisicoes_lidas.get()
    lista = client.get(reverse("admin:compras_requisicaoentradaoficial_changelist"))
    assert lista.status_code == 200 and "RC-0042" in lista.text
    detalhe = client.get(
        reverse("admin:compras_requisicaoentradaoficial_change", args=[requisicao.pk])
    )
    assert detalhe.status_code == 200 and "006.011.020" in detalhe.text


def test_extracao_e_requisicao_de_entrada_sao_so_leitura(
    client, admin_logado, extracao_com_requisicao
):
    requisicao = extracao_com_requisicao.requisicoes_lidas.get()
    for modelo, pk in (
        ("extracaoentradas", extracao_com_requisicao.pk),
        ("requisicaoentradaoficial", requisicao.pk),
    ):
        assert client.get(reverse(f"admin:compras_{modelo}_add")).status_code == 403
        assert (
            client.post(reverse(f"admin:compras_{modelo}_change", args=[pk]), {}).status_code == 403
        )
        assert (
            client.post(
                reverse(f"admin:compras_{modelo}_delete", args=[pk]), {"post": "yes"}
            ).status_code
            == 403
        )
