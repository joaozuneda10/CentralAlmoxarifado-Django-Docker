"""Quem abre a área Compras (spec 014, permissão `contas.receber_compras`)."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import Client
from django.urls import reverse

from contas.acesso import GRUPO_ATENDIMENTO, GRUPO_GESTAO, GRUPO_SEGURANCA_TRABALHO
from tests.compras_cenario import pedido_padrao, preparar, usuario_recebedor
from tests.papeis import dar_papeis, usuario_com
from tests.solicitantes import criar_solicitante

pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario():
    pedido = pedido_padrao()
    recebimento = preparar(pedido, usuario_recebedor("40001"), {1: "5"})
    return pedido, recebimento


def _rotas(pedido, recebimento):
    return [
        ("get", reverse("compras:pedidos")),
        ("get", reverse("compras:pedido", args=[pedido.pk])),
        ("get", reverse("compras:receber", args=[pedido.pk])),
        ("get", reverse("compras:recebimento", args=[recebimento.pk])),
        ("get", reverse("compras:editar_recebimento", args=[recebimento.pk])),
        ("post", reverse("compras:cancelar_recebimento", args=[recebimento.pk])),
    ]


def _cliente(usuario):
    c = Client(raise_request_exception=False)
    c.force_login(usuario)
    return c


def test_usuario_sem_papel_recebe_403_nas_seis_rotas(cenario):
    c = _cliente(usuario_com(username="50001"))
    for metodo, url in _rotas(*cenario):
        r = getattr(c, metodo)(url)
        assert r.status_code == 403, url
        assert "Seu usuário ainda não tem acesso" in r.text


@pytest.mark.parametrize("grupo", [GRUPO_ATENDIMENTO, GRUPO_GESTAO])
def test_atendimento_e_gestao_abrem(cenario, grupo):
    c = _cliente(usuario_com(grupo, username="50002"))
    for metodo, url in _rotas(*cenario):
        if metodo == "get":
            assert c.get(url).status_code == 200, url
    # A recusa do POST do cancelamento (sem confirmação) é da view, não do acesso.
    assert c.post(_rotas(*cenario)[-1][1]).status_code == 302


def test_anonimo_vai_ao_login(cenario, client):
    for metodo, url in _rotas(*cenario):
        r = getattr(client, metodo)(url)
        assert r.status_code == 302 and reverse("login") in r.url, url


def test_solicitante_recebe_a_recusa_publica(cenario):
    c = _cliente(criar_solicitante())
    for metodo, url in _rotas(*cenario):
        r = getattr(c, metodo)(url)
        assert r.status_code == 403, url
        assert "interface/acesso_negado_publico.html" in [t.name for t in r.templates]


def test_seguranca_do_trabalho_e_bloqueada_pelo_middleware(cenario):
    seguranca = get_user_model().objects.create_user(username="60001", password="x")
    seguranca.groups.add(Group.objects.get_or_create(name=GRUPO_SEGURANCA_TRABALHO)[0])
    c = _cliente(seguranca)
    for metodo, url in _rotas(*cenario):
        r = getattr(c, metodo)(url)
        assert r.status_code in (302, 403), url
        if r.status_code == 302:
            assert reverse("pedidos:autorizacoes") in r.url


def test_so_a_permissao_receber_compras_basta(cenario):
    usuario = usuario_com(username="50003")
    usuario.user_permissions.add(Permission.objects.get(codename="receber_compras"))
    assert _cliente(usuario).get(reverse("compras:pedidos")).status_code == 200


def test_item_compras_do_menu_so_para_quem_tem_a_permissao():
    com = _cliente(dar_papeis(usuario_com(username="50004")))
    sem = _cliente(
        usuario_com(username="50005")
    )  # sem papel algum: a recusa também traz o menu, sem o item
    texto = com.get(reverse("pedidos:painel")).text
    assert "<span>Compras</span>" in texto and reverse("compras:pedidos") in texto
    atendimento_so_painel = usuario_com(GRUPO_ATENDIMENTO, username="50006")
    atendimento_so_painel.groups.clear()
    atendimento_so_painel.user_permissions.add(Permission.objects.get(codename="atender_pedidos"))
    texto = _cliente(atendimento_so_painel).get(reverse("pedidos:painel")).text
    assert "<span>Compras</span>" not in texto
    assert "<span>Compras</span>" not in sem.get(reverse("pedidos:painel")).text


def test_a_migration_deu_receber_compras_aos_grupos_atendimento_e_gestao():
    dar_papeis(usuario_com(username="50007"))  # garante os grupos (também no banco de teste)
    for nome in (GRUPO_ATENDIMENTO, GRUPO_GESTAO):
        grupo = Group.objects.get(name=nome)
        assert grupo.permissions.filter(codename="receber_compras").exists(), nome
