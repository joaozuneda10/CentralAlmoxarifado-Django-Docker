"""Spec 015 (entrega 2): o menu ⋮ de cada linha da lista do painel (FR-018a)."""

import re

import pytest
from django.urls import reverse

from pedidos.models import AutorizacaoPedido
from pedidos.regras import AVULSA, EPIS
from tests.cenario import criar_pedido

pytestmark = pytest.mark.django_db

PAINEL = reverse("pedidos:painel")


def menu_de(html, numero):
    """O `<details class="menu-acoes...">` da linha do pedido `numero`."""
    achado = re.search(
        r'<details class="(menu-acoes[^"]*)" data-menu>\s*<summary[^>]*aria-label="Ações do pedido '
        + re.escape(numero)
        + r'"[^>]*>.*?</details>',
        html,
        re.S,
    )
    assert achado, numero
    return achado.group(1), achado.group(0)


def itens(menu):
    return re.findall(
        r'<a class="menu-acoes-item" href="([^"]+)"[^>]*>.*?<span>([^<]+)</span>', menu, re.S
    )


def _lista(client):
    return client.get(PAINEL, HTTP_HX_REQUEST="true").text


def test_pedido_aguardando_so_abre(client, usuario_logado):
    p = criar_pedido()
    _, menu = menu_de(_lista(client), p.numero)
    assert itens(menu) == [(reverse("pedidos:detalhe", args=[p.numero]), "Abrir pedido")]


def test_atendido_com_lote_pendente_imprime_e_edita(client, usuario_logado):
    p = criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    _, menu = menu_de(_lista(client), p.numero)
    detalhe = reverse("pedidos:detalhe", args=[p.numero])
    assert itens(menu) == [
        (detalhe, "Abrir pedido"),
        (f"{detalhe}?imprimir=1", "Imprimir recibo"),
        (reverse("pedidos:editar", args=[p.numero]), "Editar atendimento"),
    ]


def test_atendido_e_lancado_nao_edita(client, usuario_logado):
    p = criar_pedido(atendido=True, linhas=[("LANCADA", "003354/26")])
    _, menu = menu_de(_lista(client), p.numero)
    assert [rotulo for _, rotulo in itens(menu)] == ["Abrir pedido", "Imprimir recibo"]


def test_atendido_em_verificacao_nao_edita(client, usuario_logado):
    p = criar_pedido(atendido=True, linhas=[("VERIFICAR", "")])
    _, menu = menu_de(_lista(client), p.numero)
    assert "Editar atendimento" not in menu


def test_epi_aguardando_autorizacao_so_abre(client, usuario_logado):
    p = criar_pedido(origem=EPIS)
    AutorizacaoPedido.objects.create(pedido=p, situacao="AGUARDANDO")
    _, menu = menu_de(_lista(client), p.numero)
    assert [rotulo for _, rotulo in itens(menu)] == ["Abrir pedido"]


def test_saida_avulsa_edita_a_saida(client, usuario_logado):
    p = criar_pedido(
        origem=AVULSA, atendido=True, linhas=[("PENDENTE", "")], usuario=usuario_logado
    )
    _, menu = menu_de(_lista(client), p.numero)
    assert [rotulo for _, rotulo in itens(menu)] == [
        "Abrir pedido",
        "Imprimir recibo",
        "Editar saída",
    ]


def test_com_cinco_linhas_ou_mais_as_duas_ultimas_abrem_para_cima(client, usuario_logado):
    pedidos = [criar_pedido() for _ in range(6)]
    html = _lista(client)
    # A lista é dos mais recentes primeiro: as duas últimas linhas são os dois mais antigos.
    classes = [menu_de(html, p.numero)[0] for p in reversed(pedidos)]
    assert [("menu-acoes-acima" in c) for c in classes] == [False, False, False, False, True, True]
    assert "tabela-rolagem-curta" not in html


def test_com_menos_de_cinco_linhas_todo_menu_abre_para_baixo(client, usuario_logado):
    pedidos = [criar_pedido() for _ in range(4)]
    html = _lista(client)
    assert all("menu-acoes-acima" not in menu_de(html, p.numero)[0] for p in pedidos)
    assert '<div class="tabela-rolagem tabela-rolagem-curta">' in html


def test_uma_linha_so_tambem_abre_para_baixo(client, usuario_logado):
    p = criar_pedido()
    html = _lista(client)
    assert "menu-acoes-acima" not in menu_de(html, p.numero)[0]
    assert "tabela-rolagem-curta" in html


def test_o_resumo_do_menu_e_um_botao_com_rotulo(client, usuario_logado):
    p = criar_pedido()
    _, menu = menu_de(_lista(client), p.numero)
    resumo = '<summary class="botao botao-icone menu-acoes-botao" aria-label="Ações do pedido '
    assert f'{resumo}{p.numero}">' in menu
    assert '<svg class="icone"' in menu  # o ícone kebab


def test_o_menu_nao_acrescenta_consulta_por_linha(
    client, usuario_logado, django_assert_max_num_queries
):
    for _ in range(25):
        criar_pedido(atendido=True, linhas=[("PENDENTE", ""), ("LANCADA", "1/26")])
    with django_assert_max_num_queries(12):
        r = client.get(PAINEL, HTTP_HX_REQUEST="true")
    # Abrir e imprimir em cada linha (o lote parcialmente lançado não edita).
    assert r.text.count('class="menu-acoes-item"') == 25 * 2


def test_situacao_e_scpi_em_colunas_separadas_e_recibo_nao_impresso_na_linha(
    client, usuario_logado
):
    criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    html = _lista(client)
    cabecalho = html[html.index("<thead>") : html.index("</thead>")]
    assert re.findall(r'<th scope="col"[^>]*>([^<]*)</th>', cabecalho) == [
        "Nº / origem",
        "Enviado em",
        "Pessoa",
        "Destino / centro de custo",
        "Situação",
        "SCPI",
        "",
    ]
    assert "Recibo não impresso" in html
    assert 'class="recibo-pendente' in html


def test_recibo_impresso_nao_aparece_na_linha(client, usuario_logado):
    from django.utils import timezone

    from pedidos.models import Atendimento

    criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    Atendimento.objects.update(recibo_impresso_em=timezone.now())
    assert "Recibo não impresso" not in _lista(client)
