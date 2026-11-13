"""A aba Entradas no SCPI de Automações (spec 014, PR 4): a fila, os bloqueados, as recusas e a
atualização a cada 3 s só com o robô de entradas rodando."""

import re
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from compras.models import Recebimento, TravaPedido
from pedidos.models import ExecucaoRobo
from tests.compras_cenario import pedido_padrao, preparar, usuario_recebedor
from tests.papeis import usuario_com

pytestmark = pytest.mark.django_db

PAGINA = reverse("automacoes:pagina")
ENTRADAS = PAGINA + "?aba=entradas"
LANCAR = reverse("automacoes:lancar_entradas")


@pytest.fixture
def usuario():
    return usuario_recebedor()


@pytest.fixture
def logado(client, usuario):
    client.force_login(usuario)
    return usuario


@pytest.fixture
def pedido():
    return pedido_padrao()


def _regiao(client):
    return client.get(PAGINA, HTTP_HX_REQUEST="true", HTTP_HX_TARGET="section#entradas-no-scpi")


def test_a_aba_existe_depois_do_lancamento_e_exige_automacoes(client, logado):
    texto = client.get(ENTRADAS).text
    ids = re.findall(r'data-aba="([^"]+)"', texto)
    assert ids.index("entradas") == ids.index("lancamento") + 1
    assert "Entradas no SCPI" in texto and 'id="painel-entradas"' in texto
    client.force_login(usuario_com(username="40003"))  # sem papel algum
    assert client.get(ENTRADAS).status_code == 403


def test_a_fila_lista_os_preparados_com_caixa_e_os_bloqueados_com_o_motivo(client, logado, pedido):
    pronto = preparar(pedido, logado, {1: "10"}, nf="501")
    bloqueado = preparar(pedido, logado, {1: "5"}, nf="502")
    TravaPedido.objects.create(pedido=pedido, motivo="TELA")
    texto = client.get(ENTRADAS).text
    assert f'value="{pronto.rotulo}"' not in texto  # o pedido está travado: os dois bloqueados
    assert f'value="{bloqueado.rotulo}"' not in texto
    assert "Bloqueado" in texto and "O pedido está travado." in texto
    assert "Nenhum recebimento aguardando o robô." in texto
    TravaPedido.objects.all().delete()
    texto = client.get(ENTRADAS).text
    assert f'name="recebimentos" value="{pronto.rotulo}"' in texto
    assert f'name="recebimentos" value="{bloqueado.rotulo}"' in texto
    assert "2 recebimentos aguardando o robô" in texto
    assert reverse("compras:recebimento", args=[pronto.pk]) in texto
    assert reverse("compras:pedido", args=[pedido.pk]) in texto


def test_so_o_recebimento_preparado_entra_na_fila(client, logado, pedido):
    r = preparar(pedido, logado, {1: "10"})
    Recebimento.objects.filter(pk=r.pk).update(status="VERIFICAR")
    texto = client.get(ENTRADAS).text
    assert f'value="{r.rotulo}"' not in texto and "Nenhum recebimento aguardando" in texto


def test_botoes_com_o_lancamento_real_liberado_e_a_confirmacao(client, logado, pedido, settings):
    settings.LANCAMENTO_REAL = True
    preparar(pedido, logado, {1: "10"})
    texto = client.get(ENTRADAS).text
    assert "data-confirmar-lancamento" in texto and 'id="dialogo-lancar-entradas"' in texto
    assert 'data-fila-dialogo="dialogo-lancar-entradas"' in texto
    assert 'name="recebimentos"' in texto


def test_com_o_lancamento_real_bloqueado_so_a_simulacao(client, logado, pedido, settings):
    settings.LANCAMENTO_REAL = False
    preparar(pedido, logado, {1: "10"})
    texto = client.get(ENTRADAS).text
    assert "Lançamento real bloqueado neste ambiente" in texto
    assert "data-confirmar-lancamento" not in texto
    assert 'id="dialogo-lancar-entradas"' not in texto


def test_com_o_robo_de_saidas_rodando_os_botoes_ficam_desabilitados_com_a_dica(
    client, logado, pedido
):
    preparar(pedido, logado, {1: "10"})
    ExecucaoRobo.objects.create(robo="SAIDAS")
    r = client.get(ENTRADAS)
    assert r.context["pode_executar_entradas"] is False and r.context["saidas_lancando"] is True
    assert "O robô de saídas está lançando." in r.text
    assert re.search(r'name="modo" value="simular"[^>]* disabled', r.text)


def test_atualiza_a_cada_3_s_so_com_o_robo_de_entradas_rodando(client, logado):
    assert 'hx-trigger="every 3s"' not in _regiao(client).text
    ExecucaoRobo.objects.create(robo="ENTRADAS")
    regiao = _regiao(client).text
    assert 'id="entradas-no-scpi"' in regiao and 'hx-trigger="every 3s"' in regiao


def test_a_regiao_recarregada_nao_traz_a_pagina_inteira(client, logado):
    regiao = _regiao(client).text
    assert "<html" not in regiao and 'id="entradas-no-scpi"' in regiao


def test_o_andamento_das_entradas_fala_recebimento(client, logado):
    agora = timezone.now()
    ExecucaoRobo.objects.create(
        robo="ENTRADAS",
        situacao="SUCESSO",
        inicio=agora - timedelta(minutes=2),
        fim=agora - timedelta(minutes=1),
        resumo={
            "requisicoes": 1,
            "lancadas": 1,
            "processadas": 1,
            "fase": "lancando",
            "lotes": [
                {
                    "lote": "RC-0001",
                    "recebedor": "NF 501",
                    "centro": "00514/26",
                    "itens": 1,
                    "resultado": "lancada",
                    "requisicao": "003492/26",
                    "mensagem": "",
                    "inicio": (agora - timedelta(minutes=2)).isoformat(),
                    "fim": (agora - timedelta(minutes=1)).isoformat(),
                }
            ],
        },
    )
    texto = client.get(ENTRADAS).text
    assert "O recebimento foi lançado no SCPI." in texto and "RC-0001" in texto
    assert "003492/26" in texto


# --- a ação -----------------------------------------------------------------------------------


@pytest.fixture
def disparos(monkeypatch):
    from scpi import disparo

    chamadas = []
    monkeypatch.setattr(
        disparo, "_iniciar_comando", lambda args, log, titulo: chamadas.append((args, log))
    )
    return chamadas


def test_post_valido_inicia_o_robo_de_entradas(
    client, logado, pedido, disparos, settings, tmp_path
):
    settings.LOG_DIR = tmp_path
    r1 = preparar(pedido, logado, {1: "10"}, nf="501")
    r2 = preparar(pedido, logado, {1: "5"}, nf="502")
    resposta = client.post(LANCAR, {"modo": "simular", "recebimentos": [r1.rotulo, r2.rotulo]})
    assert resposta.status_code == 302 and resposta.url == ENTRADAS
    ((argumentos, log),) = disparos
    assert argumentos[0] == "lancar_entradas" and "--dry-run" in argumentos
    assert argumentos.count("--recebimento") == 2 and r1.rotulo in argumentos
    assert log == "lancar_entradas.log"
    execucao = ExecucaoRobo.objects.get()
    assert execucao.robo == "ENTRADAS" and execucao.simulacao and execucao.iniciada_por == logado


def test_post_sem_marcar_nada_e_recusado(client, logado, pedido, disparos):
    preparar(pedido, logado, {1: "10"})
    resposta = client.post(LANCAR, {"modo": "simular"}, follow=True)
    assert "Marque ao menos um recebimento da fila." in resposta.text
    assert disparos == [] and not ExecucaoRobo.objects.exists()


def test_post_com_recebimento_que_saiu_da_fila_ou_esta_bloqueado_e_recusado(
    client, logado, pedido, disparos
):
    r = preparar(pedido, logado, {1: "10"})
    TravaPedido.objects.create(pedido=pedido, motivo="TELA")
    resposta = client.post(LANCAR, {"modo": "simular", "recebimentos": [r.rotulo]}, follow=True)
    assert f"O recebimento {r.rotulo} não está mais na fila do robô." in resposta.text
    assert disparos == []


def test_post_de_lancamento_real_bloqueado_e_recusado(client, logado, pedido, disparos, settings):
    settings.LANCAMENTO_REAL = False
    r = preparar(pedido, logado, {1: "10"})
    resposta = client.post(LANCAR, {"modo": "lancar", "recebimentos": [r.rotulo]}, follow=True)
    assert "bloqueado" in resposta.text and disparos == []


def test_post_com_qualquer_robo_rodando_avisa(client, logado, pedido, disparos):
    r = preparar(pedido, logado, {1: "10"})
    ExecucaoRobo.objects.create(robo="SAIDAS")
    resposta = client.post(LANCAR, {"modo": "simular", "recebimentos": [r.rotulo]}, follow=True)
    assert "Já há um lançamento em andamento" in resposta.text and disparos == []


def test_a_acao_exige_login_e_operar_automacoes(client, pedido, disparos):
    r = preparar(pedido, usuario_recebedor("40010"), {1: "10"})
    dados = {"modo": "simular", "recebimentos": [r.rotulo]}
    assert client.post(LANCAR, dados).status_code == 302  # sem login
    client.force_login(usuario_com(username="40011"))
    assert client.post(LANCAR, dados).status_code == 403
    assert client.get(LANCAR).status_code == 403  # recusa antes do método
    assert disparos == [] and not ExecucaoRobo.objects.exists()


def test_com_o_robo_de_saidas_rodando_a_regiao_se_atualiza_ate_os_botoes_voltarem(client, logado):
    saidas = ExecucaoRobo.objects.create(robo="SAIDAS")
    assert 'hx-trigger="every 3s"' in _regiao(client).text
    saidas.situacao = "SUCESSO"
    saidas.fim = saidas.inicio
    saidas.save()
    assert 'hx-trigger="every 3s"' not in _regiao(client).text


def test_a_execucao_em_andamento_vem_antes_da_tentativa_recusada(client, logado):
    """Um comando disparado durante o lançamento cria outra execução, que termina em falha: o
    cartão continua mostrando a que está rodando."""
    rodando = ExecucaoRobo.objects.create(robo="ENTRADAS")
    ExecucaoRobo.objects.create(
        robo="ENTRADAS", situacao="FALHA", fim=rodando.inicio, erro="Há um lançamento em andamento."
    )
    contexto = client.get(ENTRADAS).context
    assert contexto["execucao_entradas"] == rodando and contexto["entradas_em_andamento"]


def test_o_cartao_das_entradas_nao_aponta_para_as_travas_das_saidas(client, logado):
    ExecucaoRobo.objects.create(
        robo="ENTRADAS",
        situacao="ATENCAO",
        fim=timezone.now(),
        resumo={
            "fase": "depois",
            "verificar": 1,
            "lotes": [{"lote": "RC-0001", "resultado": "verificar"}],
        },
    )
    assert 'href="#travas"' not in client.get(ENTRADAS).text


def test_execucao_antiga_interrompida_nao_esconde_a_que_tem_a_trava(client, logado, trava_ocupada):
    """Uma execução que morreu sem registrar o fim volta a contar como em andamento quando outra
    ocupa a trava: o cartão mostra a nova."""
    antiga = ExecucaoRobo.objects.create(robo="ENTRADAS")
    ExecucaoRobo.objects.filter(pk=antiga.pk).update(inicio=timezone.now() - timedelta(hours=3))
    nova = ExecucaoRobo.objects.create(robo="ENTRADAS")
    assert client.get(ENTRADAS).context["execucao_entradas"] == nova


def test_sem_a_trava_propria_das_entradas_so_a_simulacao(
    client, logado, pedido, disparos, settings
):
    settings.LANCAMENTO_REAL = True
    settings.LANCAMENTO_REAL_ENTRADAS = False
    r = preparar(pedido, logado, {1: "10"})
    texto = _regiao(client).text  # só a aba das entradas: a das saídas continua liberada
    assert 'name="modo" value="lancar"' not in texto and "LANCAMENTO_REAL_ENTRADAS" in texto
    client.post(
        reverse("automacoes:lancar_entradas"), {"modo": "lancar", "recebimentos": [r.rotulo]}
    )
    assert not disparos and not ExecucaoRobo.objects.exists()
