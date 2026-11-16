"""O formulário público com a conta do solicitante (spec 013, US3 e US4;
contracts/formulario-com-conta.md): o token leva a conta, o nome é o da conta, o destino vem do
último pedido, o pedido sai ligado à conta, e a sessão que termina no meio nunca o deixa anônimo."""

import re
import time

import pytest
from django.core import signing
from django.test import Client
from django.urls import reverse

from catalogo.models import CentroCusto
from contas.acesso import GRUPO_ATENDIMENTO
from pedidos import servicos
from pedidos.models import AutorizacaoPedido, Pedido, Sequencia
from pedidos.protecao import (
    MENSAGEM_RAPIDO,
    MENSAGEM_RECUSA,
    MENSAGEM_SESSAO_TERMINOU,
    SALT,
    emitir,
    ler,
)
from pedidos.regras import EPIS, LIMPEZA, EnvioPedido, ItemEnviado
from tests.cenario import envio_limpeza, montar_cenario, registrar
from tests.papeis import usuario_com
from tests.solicitantes import SENHA, cliente_de, criar_solicitante, postar, token

pytestmark = pytest.mark.django_db

NOME = "Maria da Silva"


@pytest.fixture(autouse=True)
def cenario(monkeypatch):
    montar_cenario()
    monkeypatch.setattr(servicos, "notificar_pedido", lambda pedido, url_painel="": "enviado")
    monkeypatch.setattr(
        servicos, "notificar_autorizacao_pendente", lambda pedido, url_painel="": "enviado"
    )


def _abrir(c, fluxo="limpeza"):
    return c.get(reverse("pedidos:formulario", args=[fluxo])).text


def _token_da_pagina(html):
    return ler(re.search(r'name="token" value="([^"]+)"', html).group(1))


def _valor(html, campo):
    return re.search(rf'<input id="{campo}"[^>]*value="([^"]*)"', html).group(1)


# --- Abrir o formulário (T023) -------------------------------------------------------------------


def test_solicitante_abre_com_o_nome_da_conta_travado():
    u = criar_solicitante(nome=" Maria ", sobrenome="da  Silva")
    html = _abrir(cliente_de(u))
    assert _valor(html, "solicitante") == NOME
    assert re.search(r'<input id="solicitante"[^>]*readonly', html)
    assert "data-com-conta" in html
    assert 'data-limpar-campo="solicitante"' not in html
    assert _token_da_pagina(html).conta == u.pk


@pytest.mark.parametrize("quem", ["anonimo", "equipe"])
def test_anonimo_e_equipe_abrem_sem_conta(quem):
    c = Client() if quem == "anonimo" else cliente_de(usuario_com(GRUPO_ATENDIMENTO))
    html = _abrir(c)
    assert "data-com-conta" not in html
    assert _token_da_pagina(html).conta is None
    assert not re.search(r'<input id="solicitante"[^>]*readonly', html)


def test_destino_sugerido_pelo_ultimo_pedido_da_conta_no_formulario():
    u = criar_solicitante()
    registrar(LIMPEZA, envio_limpeza(solicitante=NOME, destino="ETA II"), conta=u)
    c = cliente_de(u)
    assert _valor(_abrir(c, "limpeza"), "destino") == "ETA II"
    assert _valor(_abrir(c, "ab"), "destino") == ""


def test_destino_que_deixou_de_existir_nao_e_sugerido():
    u = criar_solicitante()
    registrar(LIMPEZA, envio_limpeza(solicitante=NOME, destino="ETA II"), conta=u)
    CentroCusto.objects.filter(descricao="ETA II").update(ativo=False)
    assert _valor(_abrir(cliente_de(u)), "destino") == ""


# --- Enviar (T023, T024) ------------------------------------------------------------------------


def test_pedido_sai_com_a_conta_e_o_nome_dela_mesmo_com_outro_nome():
    u = criar_solicitante()
    r = postar(cliente_de(u), token(u), solicitante="Outra Pessoa")
    assert r.status_code == 200
    pedido = Pedido.objects.get()
    assert pedido.conta == u and pedido.solicitante == NOME


def test_equipe_logada_pede_anonimo():
    equipe = usuario_com(GRUPO_ATENDIMENTO)
    postar(cliente_de(equipe), token(), solicitante="Ana")
    pedido = Pedido.objects.get()
    assert pedido.conta is None and pedido.solicitante == "Ana"


def test_anonimo_como_hoje():
    r = postar(Client(), token(), solicitante="Ana")
    assert "data-lembrar-solicitante" in r.text and "Guarde o número" in r.text
    assert Pedido.objects.get().conta is None


def test_sucesso_com_conta_leva_a_meus_pedidos():
    u = criar_solicitante()
    r = postar(cliente_de(u), token(u))
    numero = Pedido.objects.get().numero
    assert reverse("pedidos:meu_pedido", args=[numero]) in r.text
    assert "Ver em Meus pedidos" in r.text
    assert "data-lembrar-" not in r.text
    assert "Guarde o número" not in r.text
    assert reverse("pedidos:consulta") not in r.text


def test_reenvio_com_a_mesma_conta_confirma_e_com_outra_e_divergente():
    a = criar_solicitante("90001")
    b = criar_solicitante("90002", "Bia", "Souza")
    envio = emitir(aberto_em=time.time() - 60, conta_id=a.pk)
    postar(cliente_de(a), envio.token)
    de_novo = postar(cliente_de(a), envio.token)
    assert "Pedido já estava registrado" in de_novo.text
    outra = emitir(envio_id=envio.id, aberto_em=envio.aberto_em, conta_id=b.pk).token
    r = postar(cliente_de(b), outra, solicitante="Bia Souza")
    assert Pedido.objects.count() == 1
    assert servicos.mensagem_divergente(Pedido.objects.get().numero) in r.text


def test_token_de_antes_da_spec_vale_como_anonimo():
    antigo = signing.dumps(
        {"id": "6f1c1b3e-0000-4000-8000-000000000001", "aberto_em": time.time() - 60}, salt=SALT
    )
    assert ler(antigo).conta is None
    postar(Client(), antigo)
    assert Pedido.objects.get().conta is None


def test_pedido_de_epi_com_conta_aguarda_a_seguranca():
    from tests.epis_cenario import LUVA, montar_epis

    montar_epis()
    u = criar_solicitante()
    envio = EnvioPedido(solicitante=NOME, destino="ETA I", itens=(ItemEnviado(LUVA, "2"),))
    r = registrar(EPIS, envio, conta=u)
    assert r.ok, r.mensagem
    assert r.pedido.conta == u
    assert r.pedido.autorizacao.situacao == AutorizacaoPedido.Situacao.AGUARDANDO


def test_protecoes_continuam_valendo_com_conta(settings):
    """FR-017: isca, tempo mínimo e os limites por nome (o da conta) e por IP."""
    u = criar_solicitante()
    c = cliente_de(u)
    assert MENSAGEM_RECUSA in postar(c, token(u), isca="robô").text
    rapido = emitir(conta_id=u.pk).token
    assert MENSAGEM_RAPIDO in postar(c, rapido).text
    assert not Pedido.objects.exists()

    settings.PEDIDOS_LIMITE_SOLICITANTE_DIA = 1
    settings.PEDIDOS_LIMITE_IP_10_MIN = 99
    settings.PEDIDOS_LIMITE_IP_DIA = 99
    postar(c, token(u), solicitante="Um Nome")
    segundo = postar(c, token(u), solicitante="Outro Nome")
    # O limite conta pelo nome da conta, não pelo que veio no POST.
    assert Pedido.objects.count() == 1
    assert "limite" in segundo.text.casefold() or "muitos pedidos" in segundo.text.casefold()

    settings.PEDIDOS_LIMITE_SOLICITANTE_DIA = 99
    settings.PEDIDOS_LIMITE_IP_10_MIN = 1
    postar(c, token(u))
    assert Pedido.objects.count() == 1


# --- Sessão que termina no meio (T044, T045) -----------------------------------------------------


def test_aberto_com_a_conta_e_enviado_sem_sessao_e_recusado_com_o_carrinho():
    u = criar_solicitante()
    numeracao = list(Sequencia.objects.values())
    r = postar(Client(), token(u))
    assert MENSAGEM_SESSAO_TERMINOU in r.text
    assert 'target="_blank"' in r.text and 'rel="noopener"' in r.text
    assert "023.001.002" in r.text and "008.001.002" in r.text
    assert not Pedido.objects.exists()
    assert list(Sequencia.objects.values()) == numeracao


def test_aberto_com_uma_conta_e_enviado_com_outra_e_recusado():
    a = criar_solicitante("90001")
    b = criar_solicitante("90002", "Bia", "Souza")
    r = postar(cliente_de(b), token(a))
    assert MENSAGEM_SESSAO_TERMINOU in r.text
    assert not Pedido.objects.exists()


def test_aberto_sem_conta_e_enviado_logado_sai_anonimo_com_o_aviso():
    u = criar_solicitante()
    r = postar(cliente_de(u), token(), solicitante="Ana")
    assert Pedido.objects.get().conta is None
    assert "não aparece em Meus pedidos" in r.text


def _csrf(html):
    return re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html).group(1)


def _entrar(c):
    t = _csrf(c.get(reverse("login")).text)
    c.post(
        reverse("login"),
        {"username": "90001", "password": SENHA, "csrfmiddlewaretoken": t},
    )


def test_entrar_de_novo_e_reenviar_com_o_csrf_do_cookie_registra_com_a_conta():
    """O que o `pedidos.js` faz (research R3a): o login troca o segredo do CSRF, e a aba antiga só
    envia com o do cookie."""
    u = criar_solicitante()
    c = Client(enforce_csrf_checks=True)
    _entrar(c)
    pagina = _abrir(c)
    antigo = _csrf(pagina)
    tok = _token_da_pagina(pagina)
    tok = emitir(envio_id=tok.id, aberto_em=time.time() - 60, conta_id=u.pk).token
    c.post(reverse("logout"), {"csrfmiddlewaretoken": antigo})

    sem_sessao = postar(c, tok, extra={"csrfmiddlewaretoken": antigo})
    assert MENSAGEM_SESSAO_TERMINOU in sem_sessao.text

    _entrar(c)  # na outra aba
    com_o_antigo = postar(c, tok, extra={"csrfmiddlewaretoken": _csrf(sem_sessao.text)})
    assert com_o_antigo.status_code == 403  # o motivo do R3a
    com_o_cookie = postar(c, tok, extra={"csrfmiddlewaretoken": c.cookies["csrftoken"].value})
    assert com_o_cookie.status_code == 200
    pedido = Pedido.objects.get()
    assert pedido.conta == u and pedido.solicitante == NOME


# --- Token inválido numa página aberta com conta (revisão do PR) --------------------------------


def test_pagina_com_conta_leva_a_marca_com_conta():
    u = criar_solicitante()
    assert 'name="com_conta" value="1"' in _abrir(cliente_de(u))
    assert 'name="com_conta"' not in _abrir(Client())


def test_token_invalido_numa_pagina_com_conta_e_sem_sessao_nao_vira_anonimo():
    """O token quebrado leva junto a conta de origem; a marca `com_conta` garante que o pedido
    não sai anônimo: recusa com a sessão terminada, nada gravado, a marca mantida."""
    r = postar(Client(), "token-quebrado", extra={"com_conta": "1"})
    assert MENSAGEM_SESSAO_TERMINOU in r.text
    assert 'name="com_conta" value="1"' in r.text
    assert not Pedido.objects.exists()
    # O token novo (sem conta), reenviado ainda sem sessão depois do tempo mínimo, continua
    # recusado pela marca.
    assert MENSAGEM_SESSAO_TERMINOU in postar(Client(), token(), extra={"com_conta": "1"}).text
    assert not Pedido.objects.exists()


def test_marca_com_conta_e_token_sem_conta_com_solicitante_logado_grava_na_conta():
    u = criar_solicitante()
    postar(cliente_de(u), token(), solicitante="Outro Nome", extra={"com_conta": "1"})
    pedido = Pedido.objects.get()
    assert pedido.conta == u and pedido.solicitante == NOME
