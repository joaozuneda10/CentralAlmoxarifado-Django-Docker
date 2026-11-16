"""O robô de entradas não mexe na aba e nos serviços das saídas (spec 014, R9)."""

from datetime import timedelta

import pytest
from django.core.management import CommandError, call_command
from django.urls import reverse
from django.utils import timezone

from pedidos.models import ExecucaoRobo
from scpi import disparo

pytestmark = pytest.mark.django_db

LANCAMENTO = reverse("automacoes:pagina") + "?aba=lancamento"


def _painel_das_saidas(texto: str) -> str:
    """Só o painel da aba Lançamento no SCPI (a página tem também o das entradas)."""
    inicio = texto.index('id="painel-lancamento"')
    return texto[inicio : texto.index('role="tabpanel"', inicio + 1)]


@pytest.fixture
def duas_execucoes():
    """Uma execução de saídas concluída e uma de entradas em andamento (a mais recente)."""
    agora = timezone.now()
    saidas = ExecucaoRobo.objects.create(
        robo="SAIDAS",
        inicio=agora - timedelta(minutes=30),
        fim=agora - timedelta(minutes=25),
        situacao="SUCESSO",
        resumo={"requisicoes": 1, "lancadas": 1, "lotes": []},
    )
    entradas = ExecucaoRobo.objects.create(robo="ENTRADAS", inicio=agora - timedelta(seconds=5))
    return saidas, entradas


def test_a_aba_das_saidas_mostra_so_a_ultima_execucao_de_saidas(
    client, usuario_logado, duas_execucoes
):
    saidas, _ = duas_execucoes
    r = client.get(LANCAMENTO)
    assert r.context["execucao"] == saidas
    assert r.context["lancamento_em_andamento"] is False  # as saídas não estão rodando
    painel = _painel_das_saidas(r.text)
    assert 'hx-trigger="every 3s"' not in painel  # não acompanha a execução de entradas


def test_os_botoes_das_saidas_ficam_desabilitados_com_a_dica_das_entradas(
    client, usuario_logado, duas_execucoes
):
    r = client.get(LANCAMENTO)
    assert r.context["entradas_lancando"] is True and r.context["pode_executar"] is False
    painel = _painel_das_saidas(r.text)
    assert "O robô de entradas está lançando." in painel
    assert "Há uma execução em andamento." not in painel


def test_sem_entradas_rodando_nao_tem_a_dica(client, usuario_logado):
    ExecucaoRobo.objects.create(robo="SAIDAS", situacao="SUCESSO", fim=timezone.now())
    r = client.get(LANCAMENTO)
    assert r.context["entradas_lancando"] is False
    assert "O robô de entradas está lançando." not in _painel_das_saidas(r.text)


def test_com_as_saidas_rodando_a_dica_e_a_das_saidas(client, usuario_logado):
    ExecucaoRobo.objects.create(robo="SAIDAS")
    r = client.get(LANCAMENTO)
    assert r.context["entradas_lancando"] is False and r.context["lancamento_em_andamento"] is True
    assert "Há uma execução em andamento." in _painel_das_saidas(r.text)


def test_iniciar_lancamento_das_saidas_recusa_com_o_robo_de_entradas_rodando(
    usuario_logado, duas_execucoes, monkeypatch
):
    from django.contrib.auth import get_user_model

    monkeypatch.setattr(disparo, "_iniciar_comando", lambda *a: pytest.fail("não deveria iniciar"))
    usuario = get_user_model().objects.get(username="12345")
    assert disparo.iniciar_lancamento(usuario, simulacao=True, lotes=["P-000001"]) is None


def test_o_historico_mostra_o_robo_de_entradas(client, usuario_logado, duas_execucoes):
    r = client.get(
        reverse("automacoes:pagina"), HTTP_HX_REQUEST="true", HTTP_HX_TARGET="div#historico"
    )
    assert "Entradas no SCPI" in r.text and "Lançamento no SCPI" in r.text


def test_robos_em_andamento_sai_com_erro_com_o_robo_de_entradas(duas_execucoes):
    with pytest.raises(CommandError, match="Lançamento de entradas #"):
        call_command("robos_em_andamento")


def test_a_visao_geral_das_saidas_nao_considera_a_execucao_de_entradas(
    client, usuario_logado, duas_execucoes
):
    saidas, _ = duas_execucoes
    r = client.get(reverse("automacoes:pagina"), {"aba": "visao-geral"})
    assert r.context["linha_lancamento"].selo != "Em andamento"
    assert r.context["acompanhar_lancamento"] is False
