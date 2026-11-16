"""Quem é solicitante e o que ele abre (spec 013, contracts/rotas-e-acesso.md): `eh_solicitante`,
`ponto_de_partida`, as categorias `SOLICITANTE` e `LOGADO` da tabela de rotas, a recusa no layout
público e o topo do layout público (Entrar, Meus pedidos e Sair)."""

import re
import subprocess

import pytest
from django.contrib.auth.models import AnonymousUser, Group
from django.test import Client
from django.urls import reverse

from contas.acesso import (
    GRUPO_ATENDIMENTO,
    GRUPO_GESTAO,
    GRUPO_SEGURANCA_TRABALHO,
    LOGADO,
    PUBLICA,
    REGRAS_POR_ROTA,
    SOLICITANTE,
    Regra,
    eh_solicitante,
    ponto_de_partida,
    sem_papel,
)
from pedidos.models import ExecucaoRobo
from tests.cenario import montar_cenario
from tests.papeis import usuario_com
from tests.rotas import rotas_nomeadas
from tests.solicitantes import cliente_de, criar_solicitante

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def sem_processos(monkeypatch):
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("subiu processo"))


def _novo(usuario):
    """Um objeto novo do usuário: `eh_solicitante` guarda o resultado no objeto."""
    return type(usuario).objects.get(pk=usuario.pk)


# --- eh_solicitante, ponto_de_partida e sem_papel (T007) ----------------------------------------


def test_solicitante_comum():
    u = criar_solicitante()
    assert eh_solicitante(u)
    assert ponto_de_partida(u) == "pedidos:meus_pedidos"
    assert not sem_papel(u)


@pytest.mark.parametrize(
    "ajuste",
    [
        {"is_staff": True},
        {"is_superuser": True},
        {"is_active": False},
        {"grupo": GRUPO_ATENDIMENTO},
        {"grupo": GRUPO_GESTAO},
        {"grupo": GRUPO_SEGURANCA_TRABALHO},
    ],
)
def test_no_grupo_com_algo_da_equipe_nao_e_solicitante(ajuste):
    u = criar_solicitante()
    if "grupo" in ajuste:
        u.groups.add(Group.objects.get_or_create(name=ajuste.pop("grupo"))[0])
    for campo, valor in ajuste.items():
        setattr(u, campo, valor)
    u.save()
    assert not eh_solicitante(_novo(u))


def test_anonimo_e_equipe_nao_sao_solicitantes():
    assert not eh_solicitante(AnonymousUser())
    assert not eh_solicitante(None)
    equipe = usuario_com(GRUPO_ATENDIMENTO, username="1")
    assert not eh_solicitante(equipe)
    assert ponto_de_partida(equipe) == "pedidos:painel"
    seguranca = usuario_com(GRUPO_SEGURANCA_TRABALHO, username="2")
    assert ponto_de_partida(seguranca) == "pedidos:autorizacoes"


def test_rotas_novas_na_tabela():
    assert REGRAS_POR_ROTA["pedidos:meus_pedidos"] == SOLICITANTE
    assert REGRAS_POR_ROTA["pedidos:meu_pedido"] == SOLICITANTE
    assert REGRAS_POR_ROTA["trocar_senha"] == LOGADO


# --- Meus pedidos para cada um (T042) ------------------------------------------------------------


def test_anonimo_vai_ao_login_e_volta_a_lista():
    criar_solicitante()
    c = Client()
    r = c.get(reverse("pedidos:meus_pedidos"))
    assert r.status_code == 302 and reverse("login") in r["Location"]
    entrar = c.post(r["Location"], {"username": "90001", "password": "senha-do-solicitante-123"})
    assert entrar.status_code == 302 and entrar["Location"] == reverse("pedidos:meus_pedidos")


@pytest.mark.parametrize(
    ("grupos", "destino"),
    [
        ((GRUPO_ATENDIMENTO,), "pedidos:painel"),
        ((GRUPO_ATENDIMENTO, GRUPO_GESTAO), "pedidos:painel"),
        ((GRUPO_SEGURANCA_TRABALHO,), "pedidos:autorizacoes"),
    ],
)
def test_equipe_que_abre_meus_pedidos_vai_ao_seu_ponto_de_partida(grupos, destino):
    c = cliente_de(usuario_com(*grupos))
    for url in (reverse("pedidos:meus_pedidos"), reverse("pedidos:meu_pedido", args=["P-1"])):
        r = c.get(url)
        assert r.status_code == 302 and r["Location"] == reverse(destino), (url, r.status_code)


@pytest.mark.parametrize(
    "nome", sorted(n for n, r in REGRAS_POR_ROTA.items() if isinstance(r, Regra))
)
def test_solicitante_e_recusado_na_area_interna(nome, caplog):
    montar_cenario()
    c = Client(raise_request_exception=False)
    c.force_login(criar_solicitante())
    url = rotas_nomeadas()[nome]
    for metodo in (c.get, c.post):
        r = metodo(url)
        assert r.status_code == 403, (nome, metodo.__name__)
        assert "interface/acesso_negado_publico.html" in [t.name for t in r.templates]
        assert reverse("pedidos:meus_pedidos") in r.text
        assert "no-store" in r["Cache-Control"]
    assert not ExecucaoRobo.objects.exists()


def test_recusa_do_solicitante_vai_ao_log(caplog):
    import logging

    logger = logging.getLogger("contas.acesso")
    logger.addHandler(caplog.handler)
    try:
        cliente_de(criar_solicitante()).get(reverse("pedidos:painel"))
    finally:
        logger.removeHandler(caplog.handler)
    assert [r.getMessage() for r in caplog.records if r.name == "contas.acesso"] == [
        "Acesso recusado: matricula=90001 rota=pedidos:painel metodo=GET "
        "falta=contas.atender_pedidos"
    ]


def test_nenhuma_rota_publica_cria_usuario():
    """Sem cadastro aberto (FR-003): conta só se cria no admin."""
    for nome, url in rotas_nomeadas().items():
        if REGRAS_POR_ROTA.get(nome) != PUBLICA:
            continue
        for palavra in ("cadastr", "registr", "signup", "sign-up", "conta/nova"):
            assert palavra not in nome.casefold() and palavra not in url.casefold(), nome


# --- Topo do layout público (T052) --------------------------------------------------------------


def _topo(html):
    return html[html.index('<header class="publico-topo">') : html.index("</header>")]


def test_topo_publico_para_anonimo_solicitante_e_equipe():
    montar_cenario()
    inicio = reverse("pedidos:inicio")
    anonimo = _topo(Client().get(inicio).text)
    assert "Entrar" in anonimo and "Meus pedidos" not in anonimo and "Sair" not in anonimo

    solicitante = _topo(cliente_de(criar_solicitante()).get(inicio).text)
    assert "Meus pedidos" in solicitante and "Sair" in solicitante and "Entrar" not in solicitante

    equipe = _topo(cliente_de(usuario_com(GRUPO_ATENDIMENTO, username="1")).get(inicio).text)
    assert "Entrar" not in equipe and "Meus pedidos" not in equipe and "Sair" not in equipe


def test_um_so_formulario_de_saida_em_cada_pagina_do_solicitante(settings):
    from pedidos.regras import LIMPEZA
    from tests.cenario import envio_limpeza, registrar

    montar_cenario()
    conta = criar_solicitante()
    numero = registrar(LIMPEZA, envio_limpeza(solicitante="Maria da Silva"), conta=conta).numero
    c = Client(raise_request_exception=False)
    c.force_login(conta)
    paginas = {
        "inicio": c.get(reverse("pedidos:inicio")),
        "formulario": c.get(reverse("pedidos:formulario", args=["limpeza"])),
        "lista": c.get(reverse("pedidos:meus_pedidos")),
        "pedido": c.get(reverse("pedidos:meu_pedido", args=[numero])),
        "troca": c.get(reverse("trocar_senha")),
        "recusa": c.get(reverse("pedidos:painel")),
    }
    acao = f'action="{reverse("logout")}"'
    for nome, r in paginas.items():
        assert len(re.findall(re.escape(acao), r.text)) == 1, nome
