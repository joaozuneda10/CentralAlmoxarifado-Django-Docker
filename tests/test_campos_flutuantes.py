"""Campos com rótulo flutuante nas telas públicas (spec 015, entrega 3).

Contrato: contracts/campos-publicos.md.

O rótulo continua antes do campo e com as classes de sempre; entram o modificador `campo-flutuante`,
o `placeholder=" "` (o CSS sabe se o campo está vazio pelo `:placeholder-shown`) e, embaixo, o
`campo-dica` com o texto que era o placeholder. Com erro, a dica sai do HTML e do
`aria-describedby`, e o `campo-erro` toma o lugar dela.
"""

import re
import time

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from contas.forms import FormularioEntrada, FormularioEntradaAdmin, FormularioTrocaSenha
from pedidos.protecao import emitir
from tests.cenario import montar_cenario
from tests.epis_cenario import montar_epis
from tests.oficina_cenario import montar_oficina
from tests.viaturas_cenario import montar_viaturas

pytestmark = pytest.mark.django_db

MONTAR = {
    "limpeza": montar_cenario,
    "ab": montar_cenario,
    "viaturas": montar_viaturas,
    "oficina": montar_oficina,
    "epis": montar_epis,
}

DICA_DESTINO = {
    "limpeza": "Setor ou posto de trabalho",
    "ab": "Setor, posto ou placa",
    "viaturas": "Centro de custo da equipe",
    "oficina": "Oficina mecânica ou placa da viatura",
    "epis": "Setor ou posto de trabalho",
}


def bloco(html: str, campo: str) -> str:
    """O `div.campo` que contém o campo `id=campo`, do rótulo ao fim do bloco."""
    meio = html.index(f'id="{campo}"')
    inicio = html.rindex('<div class="campo', 0, meio)
    fins = [html.find(marca, meio) for marca in ('<div class="campo', "</section>", "</form>")]
    return html[inicio : min(f for f in fins if f != -1)]


def entrada(html: str, campo: str) -> str:
    return re.search(rf'<input[^>]*id="{campo}"[^>]*>', html).group(0)


def confere_flutuante(html: str, campo: str, dica: str) -> None:
    trecho = bloco(html, campo)
    assert trecho.startswith('<div class="campo campo-flutuante')
    assert trecho.index('class="campo-rotulo"') < trecho.index(f'id="{campo}"')
    tag = entrada(html, campo)
    assert 'placeholder=" "' in tag
    assert f'aria-describedby="{campo}-dica"' in tag
    assert f'<p id="{campo}-dica" class="campo-dica">{dica}</p>' in trecho


@pytest.mark.parametrize("fluxo", list(DICA_DESTINO))
def test_destino_com_rotulo_flutuante_e_o_exemplo_embaixo(client, fluxo):
    MONTAR[fluxo]()
    html = client.get(reverse("pedidos:formulario", args=[fluxo])).text
    confere_flutuante(html, "destino", DICA_DESTINO[fluxo])
    # O exemplo saiu do placeholder; a lista de destinos e o "Limpar" continuam no campo.
    tag = entrada(html, "destino")
    assert 'list="destinos"' in tag and DICA_DESTINO[fluxo] not in tag
    assert 'data-limpar-campo="destino"' in bloco(html, "destino")


def test_nome_com_rotulo_flutuante_e_a_dica_do_passo(client):
    # A dica do nome é a frase do cabeçalho do passo (como no protótipo), que o campo cita.
    montar_cenario()
    html = client.get(reverse("pedidos:formulario", args=["limpeza"])).text
    trecho = bloco(html, "solicitante")
    assert trecho.startswith('<div class="campo campo-flutuante')
    tag = entrada(html, "solicitante")
    assert 'placeholder=" "' in tag and 'aria-describedby="solicitante-dica"' in tag
    assert re.search(r'<p id="solicitante-dica"[^>]*>Ficam guardados no seu aparelho', html)
    assert 'data-limpar-campo="solicitante"' in trecho


def test_ocorrencia_das_viaturas_com_rotulo_flutuante(client):
    montar_viaturas()
    html = client.get(reverse("pedidos:formulario", args=["viaturas"])).text
    dica = "Se as peças foram usadas numa ocorrência, o número dela."
    confere_flutuante(html, "ocorrencia", dica)


def test_observacoes_e_busca_ficam_fora_do_rotulo_flutuante(client):
    montar_cenario()
    html = client.get(reverse("pedidos:formulario", args=["limpeza"])).text
    assert 'aria-labelledby="obs-titulo"' in html
    assert "campo-flutuante" not in html[html.index('id="obs-titulo"') :]
    assert 'placeholder="Ex.: detergente, café"' in entrada(html, "busca-q")


def test_com_erro_o_campo_perde_a_dica_e_aponta_so_para_o_erro(client):
    montar_cenario()
    dados = {
        "token": emitir(aberto_em=time.time() - 60).token,
        "solicitante": "Ana",
        "destino": "Portaria",
        "obs": "",
        "confirmacao_extra": "",
        "item_codigo": ["023.001.002"],
        "item_qtd": ["2"],
    }
    html = client.post(
        reverse("pedidos:formulario", args=["limpeza"]), dados, HTTP_HX_REQUEST="true"
    ).text
    trecho = bloco(html, "destino")
    assert trecho.startswith('<div class="campo campo-flutuante campo-com-erro"')
    tag = entrada(html, "destino")
    assert 'aria-invalid="true"' in tag and 'aria-describedby="destino-erro"' in tag
    assert 'id="destino-erro" class="campo-erro"' in trecho
    assert "campo-dica" not in trecho and "destino-dica" not in html


def test_consulta_com_rotulo_flutuante(client):
    html = client.get(reverse("pedidos:consulta")).text
    confere_flutuante(html, "numero", "Ex.: P-000123")
    confere_flutuante(html, "nome", "Como foi escrito no pedido.")


def test_consulta_sem_resultado_aponta_para_o_aviso(client):
    montar_cenario()
    html = client.post(reverse("pedidos:consulta"), {"numero": "P-999999", "nome": "Ana"}).text
    for campo in ("numero", "nome"):
        tag = entrada(html, campo)
        assert 'aria-invalid="true"' in tag and 'aria-describedby="consulta-aviso"' in tag
        assert 'placeholder=" "' in tag
    assert "campo-dica" not in html


def test_widgets_do_login_e_da_troca_de_senha():
    for campo in FormularioEntrada().fields.values():
        assert campo.widget.attrs.get("placeholder") == " "
        assert "campo-entrada" in campo.widget.attrs.get("class", "")
    usuario = get_user_model()(username="x")
    for campo in FormularioTrocaSenha(usuario).fields.values():
        assert campo.widget.attrs.get("placeholder") == " "
        assert "campo-entrada" in campo.widget.attrs.get("class", "")
    # O login do admin não muda.
    for campo in FormularioEntradaAdmin().fields.values():
        assert "placeholder" not in campo.widget.attrs


def test_entrar_com_rotulo_flutuante(client):
    html = client.get(reverse("login")).text
    for campo in ("id_username", "id_password"):
        inicio = html.rindex('<div class="campo', 0, html.index(f'id="{campo}"'))
        assert html[inicio:].startswith('<div class="campo campo-flutuante')
        assert 'placeholder=" "' in entrada(html, campo)


def test_troca_de_senha_com_rotulo_flutuante(client):
    usuario = get_user_model().objects.create_user("troca", password="senha-antiga-bem-longa-1")
    client.force_login(usuario)
    html = client.get(reverse("trocar_senha")).text
    for campo in ("id_old_password", "id_new_password1", "id_new_password2"):
        inicio = html.rindex('<div class="campo', 0, html.index(f'id="{campo}"'))
        assert html[inicio:].startswith('<div class="campo campo-flutuante')
        assert 'placeholder=" "' in entrada(html, campo)
