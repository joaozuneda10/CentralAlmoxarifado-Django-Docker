"""A conta criada e mantida pelo almoxarifado (spec 013, US5; contracts/login-senha-admin.md).

O admin liga a troca obrigatória e recusa as combinações proibidas; o solicitante troca a senha
antes de usar o sistema; cada um cai no seu ponto de partida depois de entrar."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse

from contas.acesso import GRUPO_ATENDIMENTO, GRUPO_GESTAO, GRUPO_SEGURANCA_TRABALHO
from contas.forms import MENSAGEM_SOLICITANTE_COM_PAPEL, MENSAGEM_SOLICITANTE_SEM_NOME
from tests.cenario import montar_cenario
from tests.papeis import usuario_com
from tests.solicitantes import SENHA, cliente_de, criar_solicitante, garantir_grupo

pytestmark = pytest.mark.django_db

NOVA = "outra-senha-bem-forte-456"


@pytest.fixture
def admin(admin_client):
    return admin_client


def _grupo(nome):
    return Group.objects.get_or_create(name=nome)[0]


def _dados_de_edicao(usuario, **mudancas):
    dados = {
        "username": usuario.username,
        "first_name": usuario.first_name,
        "last_name": usuario.last_name,
        "email": "",
        "is_active": "on",
        "groups": [g.pk for g in usuario.groups.all()],
        "trocar_senha": "on" if usuario.trocar_senha else "",
        "date_joined_0": "2026-11-09",
        "date_joined_1": "10:00:00",
    }
    dados.update(mudancas)
    return {k: v for k, v in dados.items() if v not in ("", None)}


# --- Admin (T013) --------------------------------------------------------------------------------


def test_criar_usuario_no_admin_liga_a_troca(admin):
    r = admin.post(
        reverse("admin:contas_usuario_add"),
        {"username": "90010", "password1": SENHA, "password2": SENHA, "usable_password": "true"},
    )
    assert r.status_code == 302, r.context["adminform"].form.errors if r.context else r
    assert get_user_model().objects.get(username="90010").trocar_senha


def test_definir_a_senha_no_admin_liga_a_troca_de_novo(admin):
    u = criar_solicitante()
    assert not u.trocar_senha
    r = admin.post(
        # O `UserAdmin` nomeia a rota assim, seja qual for o modelo de usuário.
        reverse("admin:auth_user_password_change", args=[u.pk]),
        {"password1": NOVA, "password2": NOVA, "usable_password": "true"},
    )
    assert r.status_code == 302
    u.refresh_from_db()
    assert u.trocar_senha and u.check_password(NOVA)


@pytest.mark.parametrize(
    "mudanca",
    [
        {"grupo": GRUPO_ATENDIMENTO},
        {"grupo": GRUPO_GESTAO},
        {"grupo": GRUPO_SEGURANCA_TRABALHO},
        {"is_staff": "on"},
        {"is_superuser": "on"},
    ],
)
def test_admin_recusa_solicitante_com_papel_da_equipe(admin, mudanca):
    u = criar_solicitante()
    grupos = [garantir_grupo().pk]
    if "grupo" in mudanca:
        grupos.append(_grupo(mudanca.pop("grupo")).pk)
    r = admin.post(
        reverse("admin:contas_usuario_change", args=[u.pk]),
        _dados_de_edicao(u, groups=grupos, **mudanca),
    )
    assert r.status_code == 200
    assert MENSAGEM_SOLICITANTE_COM_PAPEL in r.text
    u.refresh_from_db()
    assert list(u.groups.values_list("name", flat=True)) == ["Solicitante"]
    assert not u.is_staff and not u.is_superuser


def test_admin_recusa_solicitante_sem_nome_completo(admin):
    u = criar_solicitante()
    r = admin.post(
        reverse("admin:contas_usuario_change", args=[u.pk]), _dados_de_edicao(u, last_name="")
    )
    assert r.status_code == 200 and MENSAGEM_SOLICITANTE_SEM_NOME in r.text


def test_admin_salva_a_equipe_como_antes(admin):
    u = usuario_com(GRUPO_ATENDIMENTO, username="70")
    r = admin.post(
        reverse("admin:contas_usuario_change", args=[u.pk]), _dados_de_edicao(u, is_staff="on")
    )
    assert r.status_code == 302
    u.refresh_from_db()
    assert u.is_staff


# --- Troca obrigatória (T014) --------------------------------------------------------------------


def test_com_a_troca_pendente_so_abre_a_troca_e_o_sair():
    montar_cenario()
    c = cliente_de(criar_solicitante(trocar_senha=True))
    for url in (
        reverse("pedidos:meus_pedidos"),
        reverse("pedidos:inicio"),
        reverse("pedidos:formulario", args=["limpeza"]),
    ):
        r = c.get(url)
        assert r.status_code == 302 and r["Location"] == reverse("trocar_senha"), url
    assert c.post(reverse("pedidos:formulario", args=["limpeza"])).status_code == 403
    pagina = c.get(reverse("trocar_senha"))
    assert pagina.status_code == 200
    assert "Antes de continuar, troque a senha que o almoxarifado entregou." in pagina.text
    assert c.post(reverse("logout")).status_code == 302


def test_troca_recusa_senha_fraca_e_a_mesma_senha():
    u = criar_solicitante(trocar_senha=True)
    c = cliente_de(u)
    fraca = c.post(
        reverse("trocar_senha"),
        {"old_password": SENHA, "new_password1": "123", "new_password2": "123"},
    )
    assert fraca.status_code == 200
    mesma = c.post(
        reverse("trocar_senha"),
        {"old_password": SENHA, "new_password1": SENHA, "new_password2": SENHA},
    )
    assert "A senha nova precisa ser diferente da atual." in mesma.text
    u.refresh_from_db()
    assert u.trocar_senha and u.check_password(SENHA)


def test_troca_valida_desliga_a_marca_mantem_a_sessao_e_vai_a_meus_pedidos():
    u = criar_solicitante(trocar_senha=True)
    c = cliente_de(u)
    r = c.post(
        reverse("trocar_senha"),
        {"old_password": SENHA, "new_password1": NOVA, "new_password2": NOVA},
    )
    assert r.status_code == 302 and r["Location"] == reverse("pedidos:meus_pedidos")
    u.refresh_from_db()
    assert not u.trocar_senha and u.check_password(NOVA)
    assert c.get(reverse("pedidos:meus_pedidos")).status_code == 200


def test_equipe_com_a_marca_nao_e_obrigada_a_trocar():
    montar_cenario()
    equipe = usuario_com(GRUPO_ATENDIMENTO, GRUPO_GESTAO, username="70", trocar_senha=True)
    assert cliente_de(equipe).get(reverse("pedidos:painel")).status_code == 200


def test_contas_criadas_sem_a_marca_continuam_sem_ela():
    """A migration `contas/0005_trocar_senha` entra com `default=False` (FR-007)."""
    campo = get_user_model()._meta.get_field("trocar_senha")
    assert campo.default is False
    assert not get_user_model().objects.create_user(username="1", password=SENHA).trocar_senha


# --- Depois de entrar (T015) ---------------------------------------------------------------------


def _equipe(*grupos, username):
    u = usuario_com(*grupos, username=username)
    u.set_password(SENHA)
    u.save()
    return u


def _entrar(c, usuario, next_=None):
    url = reverse("login") + (f"?next={next_}" if next_ else "")
    return c.post(url, {"username": usuario.username, "password": SENHA})


@pytest.mark.parametrize(
    ("fabrica", "destino"),
    [
        (lambda: criar_solicitante(), "pedidos:meus_pedidos"),
        (lambda: _equipe(GRUPO_ATENDIMENTO, username="70"), "pedidos:painel"),
    ],
)
def test_cada_um_vai_ao_seu_ponto_de_partida(fabrica, destino):
    r = _entrar(Client(), fabrica())
    assert r.status_code == 302 and r["Location"] == reverse(destino)


def test_seguranca_do_trabalho_vai_a_fila():
    u = _equipe(GRUPO_SEGURANCA_TRABALHO, username="71")
    c = Client()
    r = _entrar(c, u)
    assert c.get(r["Location"])["Location"] == reverse("pedidos:autorizacoes")


def test_next_do_mesmo_site_e_respeitado():
    montar_cenario()
    u = criar_solicitante()
    alvo = reverse("pedidos:formulario", args=["limpeza"])
    r = _entrar(Client(), u, next_=alvo)
    assert r["Location"] == alvo


def test_solicitante_logado_que_abre_a_entrada_vai_a_meus_pedidos():
    c = cliente_de(criar_solicitante())
    r = c.get(reverse("login"))
    assert r.status_code == 302 and r["Location"] == reverse("pedidos:meus_pedidos")
