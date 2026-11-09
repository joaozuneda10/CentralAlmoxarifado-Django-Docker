"""Meus pedidos e a privacidade do pedido com conta (spec 013, US1 e US2;
contracts/meus-pedidos.md): a lista e a página do pedido mostram só o que é do solicitante, e o
pedido de outra conta tem a mesma resposta de um número que não existe."""

import re
import uuid
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from pedidos.minhas import apresentar
from pedidos.models import Pedido
from pedidos.regras import EPIS, LIMPEZA, Adicionado, EnvioPedido, ItemEnviado
from pedidos.servicos import catalogo_de, confirmar_atendimento, decidir_autorizacao
from tests.cenario import dar_saldo, envio_limpeza, montar_cenario, registrar, saida
from tests.papeis import dar_papeis
from tests.solicitantes import cliente_de, criar_solicitante

pytestmark = pytest.mark.django_db

NOME = "Maria da Silva"
HOJE = date(2026, 10, 9)


@pytest.fixture(autouse=True)
def cenario():
    montar_cenario()


@pytest.fixture
def conta():
    return criar_solicitante()


@pytest.fixture
def atendente():
    return dar_papeis(
        get_user_model().objects.create_user(username="70777", password="x", first_name="Ateno")
    )


def pedir(conta, **extra):
    return registrar(LIMPEZA, envio_limpeza(solicitante=NOME, **extra), conta=conta).pedido


def _livres(pedido):
    no_pedido = {i.codigo for i in pedido.itens.all()}
    from pedidos.regras import AVULSA

    return [i.codigo for i in catalogo_de(AVULSA) if i.codigo not in no_pedido]


def atender_parcial_com_troca_e_acrescimo(pedido, atendente):
    """023.001.002: 1 de 2 (parcial); 008.001.002 trocado por um material; outro acrescentado."""
    dar_saldo("023.001.002", "008.001.002", "013.006.001", "016.005.010")
    troca, acrescimo = _livres(pedido)[:2]
    r = confirmar_atendimento(
        pedido.id,
        uuid.uuid4(),
        saida(centro_custo="PICKUP 01", placa="ABC1D23", recebedor="Zeca Recebedor"),
        {"023.001.002": "1", "008.001.002": "0", troca: "1", acrescimo: "2"},
        nao_lancar=False,
        usuario=atendente,
        hoje=HOJE,
        adicionados=[Adicionado(troca, "008.001.002"), Adicionado(acrescimo, "")],
    )
    assert r.ok, [e.texto for e in r.erros]
    nomes = {i.codigo: i.material for i in pedido.itens.all()}
    return nomes[troca], nomes[acrescimo]


# --- Lista (T032) ---------------------------------------------------------------------------------


def test_lista_so_os_pedidos_da_conta_do_mais_novo(conta):
    antigo = pedir(conta)
    novo = pedir(conta)
    Pedido.objects.filter(pk=antigo.pk).update(criado_em=timezone.now() - timedelta(days=2))
    pedir(criar_solicitante("90002", "Bia", "Souza"))
    registrar(LIMPEZA, envio_limpeza(solicitante=NOME))  # anônimo, da mesma pessoa
    r = cliente_de(conta).get(reverse("pedidos:meus_pedidos"))
    assert r.status_code == 200
    numeros = re.findall(r'<span class="mono">([^<]+)</span>', r.text)
    assert numeros == [novo.numero, antigo.numero]
    assert "Aguardando atendimento" in r.text
    assert "Limpeza" in r.text
    assert "no-store" in r["Cache-Control"]


def test_paginas_de_20(conta, settings):
    settings.PEDIDOS_LIMITE_SOLICITANTE_DIA = 99  # 21 pedidos com o mesmo nome no mesmo dia
    for _ in range(21):
        pedir(conta)
    c = cliente_de(conta)
    primeira = c.get(reverse("pedidos:meus_pedidos")).text
    segunda = c.get(reverse("pedidos:meus_pedidos") + "?pagina=2").text
    assert len(re.findall(r'class="cartao meus-pedidos-linha"', primeira)) == 20
    assert len(re.findall(r'class="cartao meus-pedidos-linha"', segunda)) == 1


def test_lista_vazia(conta):
    r = cliente_de(conta).get(reverse("pedidos:meus_pedidos"))
    assert "Você ainda não fez pedidos com a conta." in r.text
    assert reverse("pedidos:inicio") in r.text


# --- Página do pedido (T033, T034) --------------------------------------------------------------


def test_parcial_com_troca_mostra_pedida_entregue_e_a_troca_sem_dados_da_equipe(conta, atendente):
    pedido = pedir(conta)
    trocado_por, acrescentado = atender_parcial_com_troca_e_acrescimo(pedido, atendente)
    r = cliente_de(conta).get(reverse("pedidos:meu_pedido", args=[pedido.numero]))
    assert r.status_code == 200
    texto = r.text
    assert "Atendido parcialmente" in texto
    assert "com algum material em quantidade menor que a pedida" in texto
    assert "Pedido: <strong>2" in texto and "Entregue: <strong>1" in texto
    assert f"Trocado por {trocado_por}" in texto
    for proibido in ("Zeca Recebedor", "PICKUP 01", "ABC1D23", "BALCÃO", "70777", "Ateno"):
        assert proibido not in texto, proibido
    assert acrescentado not in texto
    assert "no-store" in r["Cache-Control"]


def test_apresentar_so_tem_as_chaves_do_contrato(conta, atendente):
    pedido = pedir(conta)
    atender_parcial_com_troca_e_acrescimo(pedido, atendente)
    pedido = (
        Pedido.objects.select_related("atendimento", "autorizacao")
        .prefetch_related("itens")
        .get(pk=pedido.pk)
    )
    dados = apresentar(pedido)
    assert set(dados) == {
        "numero",
        "formulario",
        "enviado_em",
        "consulta",
        "destino",
        "obs",
        "ocorrencia",
        "atendido",
        "itens",
    }
    assert [set(i) for i in dados["itens"]] == [
        {"material", "unidade", "qtd_pedida", "qtd_entregue", "trocado_por"}
    ] * 2
    assert [bool(i["trocado_por"]) for i in dados["itens"]].count(True) == 1


def test_antes_do_atendimento_a_entregue_nao_aparece(conta):
    pedido = pedir(conta)
    r = cliente_de(conta).get(reverse("pedidos:meu_pedido", args=[pedido.numero])).text
    assert "Aguardando atendimento" in r and "Entregue:" not in r


def test_destino_observacao_e_ocorrencia_informados(conta):
    pedido = pedir(conta, obs="Para a copa do 2º andar")
    Pedido.objects.filter(pk=pedido.pk).update(ocorrencia="OC-4521")
    r = cliente_de(conta).get(reverse("pedidos:meu_pedido", args=[pedido.numero])).text
    assert "ETA II" in r and "Para a copa do 2º andar" in r and "OC-4521" in r


def test_epi_recusado_mostra_o_motivo_sem_quem_decidiu(conta):
    from tests.epis_cenario import LUVA, montar_epis, usuarios

    montar_epis()
    seguranca = usuarios()["seguranca"]
    envio = EnvioPedido(solicitante=NOME, destino="ETA I", itens=(ItemEnviado(LUVA, "2"),))
    pedido = registrar(EPIS, envio, conta=conta).pedido
    r = decidir_autorizacao(pedido.numero, "recusar", "Já recebeu este mês", seguranca)
    assert r.ok
    texto = cliente_de(conta).get(reverse("pedidos:meu_pedido", args=[pedido.numero])).text
    assert "Recusado" in texto and "Já recebeu este mês" in texto
    assert "Sônia" not in texto and "70001" not in texto


# --- Só o dono vê (T040) ------------------------------------------------------------------------


def _sem_csrf(html):
    return re.sub(r'value="[^"]{40,}"', "", html)


def test_outra_conta_anonimo_e_inexistente_tem_a_mesma_resposta(conta):
    do_a = pedir(conta)
    anonimo = registrar(LIMPEZA, envio_limpeza(solicitante=NOME)).pedido
    b = Client(raise_request_exception=False)
    b.force_login(criar_solicitante("90002", "Bia", "Souza"))
    respostas = [
        b.get(reverse("pedidos:meu_pedido", args=[n]))
        for n in (do_a.numero, anonimo.numero, "P-999999")
    ]
    assert [r.status_code for r in respostas] == [404, 404, 404]
    corpos = {_sem_csrf(r.content.decode()) for r in respostas}
    assert len(corpos) == 1
