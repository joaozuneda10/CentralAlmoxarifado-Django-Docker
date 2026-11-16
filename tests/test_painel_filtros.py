"""Spec 015 (entrega 2): os filtros do painel em chips (FR-014, FR-016)."""

import re

import pytest
from django.urls import reverse

from pedidos.consultas import OPCOES_SITUACAO, filtrar_situacao
from pedidos.models import Pedido
from tests.cenario import criar_pedido

pytestmark = pytest.mark.django_db

PAINEL = reverse("pedidos:painel")


def _formulario(html):
    inicio = html.index('<form id="filtros-painel"')
    return html[inicio : html.index("</form>", inicio)]


def _numeros(html):
    return set(re.findall(r'class="mono numero-pedido">([^<]+)<', html))


@pytest.fixture
def tres():
    return [
        criar_pedido(),
        criar_pedido(atendido=True, entregues=["1"]),
        criar_pedido(atendido=True),
    ]


def test_situacao_e_um_grupo_de_radios_com_legenda(client, usuario_logado):
    form = _formulario(client.get(PAINEL).text)
    grupo = form[form.index('<fieldset class="chips"') : form.index("</fieldset>")]
    assert '<legend class="visually-hidden">Situação</legend>' in grupo
    valores = re.findall(r'<input type="radio" name="situacao" value="([^"]*)"', grupo)
    assert valores == [""] + [valor for valor, _ in OPCOES_SITUACAO]
    assert grupo.count('class="chip-entrada"') == len(valores)
    assert grupo.count('class="chip-texto"') == len(valores)
    assert "Todas" in grupo


@pytest.mark.parametrize("valor", ["", *[v for v, _ in OPCOES_SITUACAO]])
def test_o_radio_marcado_e_o_da_url(client, usuario_logado, valor):
    form = _formulario(client.get(PAINEL, {"situacao": valor}).text)
    marcados = re.findall(
        r'<input type="radio" name="situacao" value="([^"]*)"[^>]*\bchecked\b', form
    )
    assert marcados == [valor]


@pytest.mark.parametrize("valor", [v for v, _ in OPCOES_SITUACAO])
@pytest.mark.parametrize("htmx", [True, False])
def test_cada_situacao_devolve_o_mesmo_de_hoje(client, usuario_logado, tres, valor, htmx):
    extra = {"HTTP_HX_REQUEST": "true"} if htmx else {}
    html = client.get(PAINEL, {"situacao": valor}, **extra).text
    esperado = {p.numero for p in filtrar_situacao(Pedido.objects.all(), valor)}
    assert _numeros(html) == esperado


def test_o_rotulo_do_chip_com_lista_mostra_o_valor(client, usuario_logado):
    form = _formulario(client.get(PAINEL, {"origem": "AB"}).text)
    assert re.search(r'<span class="chip-menu-rotulo"[^>]*>Origem: Materiais AB</span>', form)
    sem = _formulario(client.get(PAINEL).text)
    assert re.search(r'<span class="chip-menu-rotulo"[^>]*>Origem</span>', sem)


def test_os_chips_com_lista_levam_os_campos_de_hoje(client, usuario_logado):
    form = _formulario(client.get(PAINEL).text)
    for nome in ("origem", "scpi", "recibo", "autorizacao", "de", "ate"):
        assert f'name="{nome}"' in form, nome
    assert form.count('<details class="chip-menu" data-menu>') == 5
    assert "Período" in form


@pytest.mark.parametrize(
    ("parametros", "cartao"),
    [({"situacao": "aguardando"}, "atendimento"), ({"recibo": "pendente"}, "recibos")],
)
def test_o_indicador_do_filtro_aplicado_sai_com_aria_current(
    client, usuario_logado, parametros, cartao
):
    html = client.get(PAINEL, parametros).text
    atuais = re.findall(
        r'data-indicador="([a-z]+)"[^>]*>\s*<a class="indicador-link"[^>]*aria-current="true"', html
    )
    assert atuais == [cartao]
    sem = client.get(PAINEL).text
    assert (
        'aria-current="true"'
        not in sem[sem.index('class="indicadores"') : sem.index('id="filtros-painel"')]
    )


def test_a_busca_fica_fora_do_formulario_e_ligada_a_ele(client, usuario_logado):
    html = client.get(PAINEL).text
    form = _formulario(html)
    assert 'name="q"' not in form
    busca = re.search(r'<input[^>]*name="q"[^>]*>', html).group(0)
    assert 'form="filtros-painel"' in busca and 'id="id_q"' in busca
    assert html.index('name="q"') < html.index('class="indicadores"')


def test_o_gatilho_do_htmx_escuta_a_busca_de_fora(client, usuario_logado):
    html = client.get(PAINEL).text
    abertura = re.search(r'<form id="filtros-painel"[^>]*>', html, re.S).group(0)
    assert "input delay:400ms from:#id_q" in abertura
    assert 'hx-target="#lista-pedidos"' in abertura and 'hx-push-url="true"' in abertura
    assert f'hx-get="{PAINEL}"' in abertura and 'method="get"' in abertura


def test_o_primeiro_botao_de_envio_e_o_filtrar_sem_name(client, usuario_logado):
    form = _formulario(client.get(PAINEL).text)
    primeiro = re.search(r'<button type="submit"[^>]*>(.*?)</button>', form, re.S)
    assert "Filtrar" in primeiro.group(1)
    assert "name=" not in primeiro.group(0)
    assert f'href="{PAINEL}"' in form  # "Limpar filtros"


def test_o_lancar_no_scpi_nao_fica_dentro_do_formulario_de_filtros(client, usuario_logado):
    criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    html = client.get(PAINEL).text
    form = _formulario(html)
    assert reverse("automacoes:lancar") not in form
    assert reverse("automacoes:lancar") in html


def test_a_busca_e_o_material_combinam_como_hoje(client, usuario_logado):
    ana = criar_pedido(solicitante="Ana Souza")
    criar_pedido(solicitante="Bruno Lima")
    html = client.get(PAINEL, {"q": "Ana", "situacao": "aguardando"}).text
    assert _numeros(html) == {ana.numero}
