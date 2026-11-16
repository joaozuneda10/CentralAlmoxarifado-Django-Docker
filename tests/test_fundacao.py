import re
from pathlib import Path

import pytest
from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.urls import reverse

FONTES = [
    "geist-sans-latin-600-normal.woff2",
    "geist-sans-latin-700-normal.woff2",
    "dm-sans-latin-400-normal.woff2",
    "dm-sans-latin-500-normal.woff2",
    "dm-sans-latin-600-normal.woff2",
    "geist-mono-latin-400-normal.woff2",
    "geist-mono-latin-500-normal.woff2",
]


def css(nome):
    return Path(finders.find(f"interface/css/{nome}")).read_text(encoding="utf-8")


@pytest.mark.parametrize("arquivo", FONTES)
def test_fontes_locais_existem_e_tem_font_face(arquivo):
    assert finders.find(f"interface/fonts/{arquivo}")
    assert f"../fonts/{arquivo}" in css("fundacao.css")


def test_licencas_das_fontes():
    for nome in ("OFL-Geist.txt", "OFL-DMSans.txt", "OFL-GeistMono.txt"):
        assert finders.find(f"interface/fonts/{nome}")


def test_tokens_da_fundacao():
    # Spec 015: os valores de specs/015-design-system-m3/contracts/tokens.md.
    texto = css("fundacao.css")
    for valor in (
        "--fundo: #ffffff",
        "--superficie: #f5f6fa",
        "--superficie-media: #eef0f5",
        "--superficie-alta: #e8eaf0",
        "--superficie-maxima: #e1e4eb",
        "--texto: #1a1c21",
        "--texto-secundario: #4a4d57",
        "--texto-suave: #666975",
        "--borda: #e2e4ea",
        "--contorno: #7a7d88",
        "--destaque: #2563eb",
        "--destaque-hover: #1d4ed8",
        "--destaque-superficie: #dce6ff",
        "--destaque-superficie-texto: #0f2a6b",
        "--secundario-superficie: #e2e7f3",
        "--secundario-superficie-texto: #1b2540",
        "--erro-forte: #b3261e",
        "--raio-campo: 4px",
        "--raio-selo: 6px",
        "--raio-cartao: 16px",
        "--raio-bloco: 28px",
        "--altura-campo: 56px",
        "--transicao: 0.15s ease",
        "font-display: swap",
        ":focus-visible",
        "prefers-reduced-motion",
    ):
        assert valor in texto.lower()
    for proibido in ("system-ui", "Inter", "Roboto", "Arial", "gradient"):
        assert proibido not in texto


def test_fundacao_antiga_removida():
    for nome in ("tokens.css", "base.css", "components.css", "publico.css"):
        assert finders.find(f"interface/css/{nome}") is None


def test_icone_conhecido_e_desconhecido():
    svg = render_to_string("interface/_icone.html", {"nome": "busca"})
    assert '<svg class="icone"' in svg and 'aria-hidden="true"' in svg
    assert 'stroke-width="1.5"' in svg
    assert svg.startswith("<svg")
    assert render_to_string("interface/_icone.html", {"nome": "xyz"}).strip() == ""


def test_componentes_carregados_e_com_o_vocabulario():
    html = render_to_string("interface/base.html", {})
    assert "interface/css/componentes.css" in html.split("</head>")[0]
    texto = css("componentes.css")
    for classe in (
        ".botao-primario",
        ".campo-entrada",
        ".cartao",
        ".selo-ok",
        ".aviso-erro",
        ".tabela-rolagem",
        ".paginacao-atual",
        ".passo-numero",
        ".quantidade",
        ".carrinho",
        ".vazio",
        ".dados",
    ):
        assert classe in texto


def test_paginacao_no_vocabulario_novo(rf):
    from django.core.paginator import Paginator

    pagina = Paginator(list(range(100)), 10).get_page(3)
    html = render_to_string(
        "interface/_paginacao.html",
        {"pagina": pagina, "parametro": "pagina", "rotulo": "Paginação"},
        request=rf.get("/"),
    )
    assert 'class="paginacao"' in html and "paginacao-atual" in html
    assert 'aria-current="page"' in html and "pagination" not in html


def test_layouts_carregados_e_com_impressao():
    html = render_to_string("interface/base.html", {})
    assert "interface/css/layouts.css" in html.split("</head>")[0]
    texto = css("layouts.css")
    impressao = texto[texto.index("@media print") :]
    for seletor in (".app-lateral", ".pagina-cabecalho", ".mensagens", ".nao-imprimir", ".so-tela"):
        assert seletor in impressao


def test_cabecalho_publico_vazio_sem_espaco(rf):
    html = render_to_string("interface/base_publico.html", {}, request=rf.get("/"))
    assert '<p class="rotulo-secao"></p>' in html
    assert '<p class="publico-sub"></p>' in html
    assert 'class="ritmo-publico"' in html


@pytest.mark.django_db
def test_menu_com_icone_e_botao_acessivel(admin_client):
    url = reverse("pedidos:painel")
    html = admin_client.get(url).text
    assert 'class="ritmo-almox"' in html
    assert 'data-menu-toggle aria-expanded="false" aria-controls="menu-lateral"' in html
    assert f'<a class="app-menu-item" href="{url}" aria-current="page"><svg class="icone"' in html


def test_itens_do_menu_tem_icone():
    from interface.navegacao import ITENS_MENU

    assert all(item.icone for item in ITENS_MENU)


def test_base_sem_tema_e_com_css_novo():
    html = render_to_string("interface/base.html", {})
    head = html.split("</head>")[0]
    assert "interface/css/fundacao.css" in head
    assert "almox-tema" not in html and "data-theme" not in html
    assert 'src="/static/interface/js/shell.js" defer' in head
    assert '<meta name="htmx-config"' in head


RAIZ = Path(__file__).resolve().parent.parent
ANTIGAS = re.compile(
    r'class="[^"]*\b(btn|card|page-section|field|field-label|field-hint|error-box|alert|badge'
    r"|text-muted|table-wrapper|empty-state|filter-bar|form-actions|side|meta-env)\b"
)


def test_nenhum_template_usa_classe_da_fundacao_antiga():
    sujos = []
    for caminho in RAIZ.glob("*/templates/**/*.html"):
        if "admin" in caminho.parts:
            continue
        if ANTIGAS.search(caminho.read_text(encoding="utf-8")):
            sujos.append(str(caminho.relative_to(RAIZ)))
    assert sujos == []


def test_nenhum_emoji_nos_templates():
    emoji = re.compile("[\U0001f300-\U0001faff☀-➿]")
    for caminho in RAIZ.glob("*/templates/**/*.html"):
        assert not emoji.search(caminho.read_text(encoding="utf-8")), caminho


def _regra(texto, seletor):
    inicio = texto.index(seletor + " {")
    return texto[inicio : texto.index("}", inicio)]


def test_grades_nao_crescem_com_a_tabela():
    # Trilha implícita `auto` cresce até a largura mínima da tabela e a página rola de lado;
    # com minmax(0, 1fr) quem rola é só o .tabela-rolagem.
    for arquivo, seletor in (
        ("fundacao.css", ".pilha"),
        ("fundacao.css", ".pilha-larga"),
        ("layouts.css", ".publico-conteudo"),
        ("layouts.css", ".app-principal"),
    ):
        assert "grid-template-columns: minmax(0, 1fr)" in _regra(css(arquivo), seletor), seletor


def test_nenhuma_grade_com_1fr_sem_minimo_zero():
    for caminho in RAIZ.glob("*/static/**/css/*.css"):
        assert "grid-template-columns: 1fr" not in caminho.read_text(encoding="utf-8"), caminho


def test_botao_quebra_texto_e_campo_nao_cresce():
    # Texto longo de botão ("Quem recebe é o solicitante (nome completo)") com nowrap alargava
    # o .campo e a página, até no desktop.
    componentes = css("componentes.css")
    assert "nowrap" not in _regra(componentes, ".botao")
    assert "grid-template-columns: minmax(0, 1fr)" in _regra(componentes, ".campo")


def test_impressao_em_texto_preto():
    texto = css("layouts.css")
    impressao = texto[texto.index("@media print") :]
    for seletor in (".rotulo-secao", ".dados dt", ".texto-suave", ".texto-secundario"):
        assert seletor in impressao
    assert "color: #000000" in impressao


# Spec 015 (entrega 1): ícone do selo pelo tom, no CSS (research R12), e ícones novos.
def _regras(texto, seletor):
    """Todas as declarações das regras que começam exatamente com o seletor."""
    return [texto[i : texto.index("}", i)] for i in _posicoes(texto, seletor + " {")]


def _posicoes(texto, trecho):
    inicio = 0
    while (i := texto.find(trecho, inicio)) != -1:
        yield i
        inicio = i + 1


@pytest.mark.parametrize("tom", ["selo-ok", "selo-aviso", "selo-erro", "selo-info"])
def test_selo_com_icone_pelo_tom(tom):
    regras = " ".join(_regras(css("componentes.css"), f".{tom}::before"))
    assert 'mask-image: url("data:image/svg+xml' in regras
    assert '-webkit-mask-image: url("data:image/svg+xml' in regras


def test_selo_neutro_sem_icone_e_selo_com_svg_sem_o_segundo():
    texto = css("componentes.css")
    assert ".selo-neutro::before" not in texto
    assert "display: none" in _regra(texto, ".selo:has(svg)::before")
    base = _regra(texto, ".selo::before")
    assert "background: currentColor" in base and "width: 14px" in base


def test_aba_selo_mostra_o_proprio_icone_em_toda_largura():
    texto = css("componentes.css")
    for regra in _regras(texto, ".aba-selo .icone"):
        assert "display: none" not in regra


def test_selo_sem_icone_na_impressao():
    for arquivo in ("layouts.css", "componentes.css"):
        texto = css(arquivo)
        if "@media print" in texto:
            impressao = texto[texto.index("@media print") :]
            if ".selo::before" in impressao:
                assert "display: none" in _regra(impressao, ".selo::before")
                return
    pytest.fail("nenhum @media print esconde o ícone dos selos")


def test_botao_icone_tem_a_area_de_toque_do_controle():
    regra = _regra(css("componentes.css"), ".botao-icone")
    assert "width: var(--altura-controle)" in regra
    assert "height: var(--altura-controle)" in regra


@pytest.mark.parametrize("nome", ["kebab", "calendario", "documento", "caminhao"])
def test_icones_novos(nome):
    svg = render_to_string("interface/_icone.html", {"nome": nome})
    assert svg.startswith('<svg class="icone"') and 'stroke-width="1.5"' in svg
    assert "<path" in svg or "<circle" in svg or "<rect" in svg
