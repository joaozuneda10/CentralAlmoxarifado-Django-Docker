"""O site atrás do Apache em /almoxarifado: nenhum caminho fixo fora do prefixo."""

import json
import re
from wsgiref.util import setup_testing_defaults

import pytest
from django.contrib.auth import get_user_model
from django.core.handlers.wsgi import WSGIHandler
from django.urls import get_script_prefix, reverse, set_script_prefix

from tests.cenario import montar_cenario
from tests.test_config import rodar

PREFIXO = "/almoxarifado"
ATRIBUTOS = re.compile(r'(?:href|src|action|hx-get|hx-post)="(/[^"]*)"')


@pytest.fixture
def prefixo(settings):
    # O que PREFIXO_URL=/almoxarifado produz em config/settings.py (veja o teste de configuração).
    settings.STATIC_URL = PREFIXO + "/static/"
    anterior = get_script_prefix()
    set_script_prefix(PREFIXO + "/")
    yield
    set_script_prefix(anterior)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "rota",
    [
        "pedidos:inicio",
        "login",
        "pedidos:painel",
        "pedidos:avulsa",
        "automacoes:pagina",
    ],
)
def test_nenhum_caminho_fixo_fora_do_prefixo(client, prefixo, rota):
    """Atrás do Apache em /almoxarifado, todo link, formulário e chamada HTMX leva o prefixo."""
    montar_cenario()
    client.force_login(get_user_model().objects.create_user("12345", password="x"))
    url = reverse(rota)  # já com o prefixo
    assert url.startswith(PREFIXO + "/")
    html = client.get(url[len(PREFIXO) :], SCRIPT_NAME=PREFIXO).content.decode()
    fora = [c for c in ATRIBUTOS.findall(html) if not c.startswith(PREFIXO + "/")]
    assert fora == [], fora


@pytest.mark.django_db
@pytest.mark.parametrize("producao", [False, True], ids=["so-script-name", "forma-de-producao"])
def test_estatico_servido_sob_o_prefixo(tmp_path, settings, producao):
    """O waitress com --url-prefix passa SCRIPT_NAME=/almoxarifado; o whitenoise (que olha o
    PATH_INFO) acha o arquivo. O manipulador nasce antes do primeiro pedido, com o prefixo "/",
    como no waitress; o WSGIHandler grava o prefixo da requisição na thread, e o `finally` o
    devolve a "/". Usa um STATIC_ROOT temporário para não depender do collectstatic. A forma de
    produção (PREFIXO_URL=/almoxarifado) também ajusta FORCE_SCRIPT_NAME e STATIC_URL antes de o
    manipulador nascer, como o settings faz na partida."""
    if producao:
        settings.FORCE_SCRIPT_NAME = PREFIXO
        settings.STATIC_URL = PREFIXO + "/static/"
    arquivo = tmp_path / "interface" / "css" / "fundacao.css"
    arquivo.parent.mkdir(parents=True)
    arquivo.write_text("body { color: black; }", encoding="utf-8")
    settings.STATIC_ROOT = tmp_path
    aplicacao = WSGIHandler()
    ambiente = {}
    setup_testing_defaults(ambiente)
    ambiente.update(
        SCRIPT_NAME=PREFIXO,
        PATH_INFO="/static/interface/css/fundacao.css",
        HTTP_HOST="testserver",
    )
    estado = []
    anterior = get_script_prefix()
    try:
        corpo = b"".join(aplicacao(ambiente, lambda status, cabecalhos, *a: estado.append(status)))
    finally:
        set_script_prefix(anterior)
    assert estado[0].startswith("200")
    assert corpo == b"body { color: black; }"


CODIGO = (
    "import django, json;"
    "django.setup();"
    "from django.conf import settings;"
    "from django.templatetags.static import static;"
    "from django.urls import reverse;"
    "print(json.dumps([settings.FORCE_SCRIPT_NAME, settings.STATIC_URL, reverse('login'),"
    " static('interface/css/fundacao.css')]))"
)


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("/almoxarifado", [PREFIXO, PREFIXO + "/static/", PREFIXO + "/painel/entrar/"]),
        (" almoxarifado/ ", [PREFIXO, PREFIXO + "/static/", PREFIXO + "/painel/entrar/"]),
        ("", [None, "/static/", "/painel/entrar/"]),
    ],
)
def test_prefixo_url_ajusta_estaticos_e_rotas(valor, esperado):
    """PREFIXO_URL é o --url-prefix do waitress: o STATIC_URL é lido na partida, antes do
    primeiro pedido, e só por isso precisa do prefixo no settings. Roda o config.settings (o
    settings_test fixa o site na raiz); DEBUG=1 dispensa o manifesto do collectstatic."""
    resultado = rodar(["-c", CODIGO], DEBUG="1", PREFIXO_URL=valor)
    assert resultado.returncode == 0, resultado.stderr
    forcado, estatico, entrar, arquivo = json.loads(resultado.stdout.strip().splitlines()[-1])
    assert [forcado, estatico, entrar] == esperado
    assert arquivo.startswith(estatico)
