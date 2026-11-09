"""Limite de tentativas de login com o django-axes (spec 013, US6; contracts/login-senha-admin.md):
bloqueio da matrícula naquela origem, nas duas portas, com a página em português."""

from datetime import timedelta

import pytest
from axes.models import AccessAttempt, AccessLog
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from tests.solicitantes import SENHA, criar_solicitante

pytestmark = pytest.mark.django_db

BLOQUEIO = "Muitas tentativas. Tente de novo em alguns minutos ou procure o almoxarifado."
RECUSA = "Matrícula ou senha incorretas."


@pytest.fixture(autouse=True)
def limite(settings):
    settings.AXES_FAILURE_LIMIT = 3


def entrar(username, senha, *, origem="10.0.0.1", url=None):
    return Client(REMOTE_ADDR=origem).post(
        url or reverse("login"), {"username": username, "password": senha}
    )


def errar(username, vezes, **kw):
    return [entrar(username, "errada", **kw) for _ in range(vezes)]


def test_antes_do_limite_a_recusa_e_a_de_sempre():
    criar_solicitante()
    for r in errar("90001", 2):
        assert r.status_code == 200 and RECUSA in r.text and BLOQUEIO not in r.text


def test_no_limite_bloqueia_mesmo_com_a_senha_certa():
    criar_solicitante()
    errar("90001", 3)
    r = entrar("90001", SENHA)
    assert r.status_code == 429
    assert BLOQUEIO in r.text
    assert "contas/bloqueado.html" in [t.name for t in r.templates]


def test_matricula_inexistente_tambem_bloqueia_sem_dizer_que_nao_existe():
    rs = errar("99999", 4)
    assert all(RECUSA in r.text for r in rs[:2])
    assert rs[-1].status_code == 429


def test_outra_matricula_e_a_mesma_de_outra_origem_entram():
    criar_solicitante("90001")
    criar_solicitante("90002", "Bia", "Souza")
    errar("90001", 3)
    assert entrar("90002", SENHA).status_code == 302
    assert entrar("90001", SENHA, origem="10.0.0.2").status_code == 302


def test_login_do_admin_bloqueia_do_mesmo_jeito():
    criar_solicitante(is_staff=False)
    url = reverse("admin:login")
    errar("90001", 3, url=url)
    r = entrar("90001", SENHA, url=url)
    assert r.status_code == 429 and BLOQUEIO in r.text


def test_depois_do_tempo_entra_e_zera_as_tentativas():
    criar_solicitante()
    errar("90001", 3)
    AccessAttempt.objects.filter(username="90001").update(
        attempt_time=timezone.now() - timedelta(minutes=16)
    )
    assert entrar("90001", SENHA).status_code == 302
    assert not AccessAttempt.objects.filter(username="90001").exists()


def test_apagar_a_tentativa_desbloqueia_na_hora():
    criar_solicitante()
    errar("90001", 3)
    AccessAttempt.objects.filter(username="90001").delete()
    assert entrar("90001", SENHA).status_code == 302


def test_login_certo_nao_fica_registrado():
    criar_solicitante()
    assert entrar("90001", SENHA).status_code == 302
    assert not AccessLog.objects.exists()
