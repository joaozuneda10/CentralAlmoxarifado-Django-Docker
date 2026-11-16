"""A consulta pública (spec 011) não abre pedido feito com conta (spec 013, US2, FR-022)."""

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from pedidos.regras import LIMPEZA
from pedidos.views.publico import MENSAGEM_CONSULTA_NAO_ACHADA
from tests.cenario import envio_limpeza, montar_cenario, registrar
from tests.solicitantes import criar_solicitante

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def cenario():
    montar_cenario()
    cache.clear()
    yield
    cache.clear()


def consultar(numero, nome):
    return Client().post(reverse("pedidos:consulta"), {"numero": numero, "nome": nome})


def test_pedido_com_conta_responde_como_numero_inexistente():
    conta = criar_solicitante()
    pedido = registrar(LIMPEZA, envio_limpeza(solicitante="Maria da Silva"), conta=conta).pedido
    com_conta = consultar(pedido.numero, "Maria")
    inexistente = consultar("P-999999", "Maria")
    assert MENSAGEM_CONSULTA_NAO_ACHADA in com_conta.text
    assert com_conta.status_code == inexistente.status_code == 200
    assert "resultado" not in com_conta.context or not com_conta.context.get("resultado")


def test_pedido_anonimo_continua_abrindo():
    pedido = registrar(LIMPEZA, envio_limpeza(solicitante="Ana Souza")).pedido
    r = consultar(pedido.numero, "Ana")
    assert r.context["resultado"]["numero"] == pedido.numero


def test_a_tentativa_com_conta_conta_no_limite_por_origem(settings):
    settings.PEDIDOS_CONSULTA_LIMITE_IP_10_MIN = 1
    conta = criar_solicitante()
    pedido = registrar(LIMPEZA, envio_limpeza(solicitante="Maria da Silva"), conta=conta).pedido
    consultar(pedido.numero, "Maria")
    assert consultar(pedido.numero, "Maria").status_code == 429
