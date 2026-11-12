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


# --- a região "Em verificação e com erro" e a ação de resolver ---------------------------------


@pytest.fixture
def scpi_simulado(pedido):
    from decimal import Decimal

    from tests.scpi_entradas_simulado import SCPIEntradasSimulado

    simulado = SCPIEntradasSimulado()
    simulado.pedido(
        pedido.ano, pedido.numero, {1: ("006.011.020", "100"), 2: ("023.003.004", "20")}
    )
    simulado.pedidos[(pedido.ano, pedido.numero)][1]["ja_entrou"] = Decimal("50")
    return simulado


def _verificar(pedido, logado, scpi_simulado, *, salvou):
    from pedidos.models import ExecucaoRobo
    from scpi.lancamento_entradas import executar_lancamento_entradas

    r = preparar(pedido, logado, {1: "10"})
    (scpi_simulado.salva_e_falha if salvou else scpi_simulado.falha_salvar).add(r.rotulo)
    execucao = ExecucaoRobo.objects.create(robo="ENTRADAS")
    executar_lancamento_entradas(
        execucao,
        scpi_simulado.abrir,
        recebimentos=[r.rotulo],
        extrair=scpi_simulado.relatorio_entradas,
    )
    r.refresh_from_db()
    return r


def test_a_regiao_mostra_o_recebimento_em_verificacao_com_a_candidata_e_o_e_esta(
    client, logado, pedido, scpi_simulado
):
    r = _verificar(pedido, logado, scpi_simulado, salvou=True)
    texto = client.get(ENTRADAS).text
    assert 'id="travas-entradas"' in texto and r.rotulo in texto
    assert "003492/26" in texto and "Provavelmente esta" in texto
    assert f'action="{reverse("automacoes:resolver_entrada", args=[r.pk])}"' in texto
    assert 'name="acao" value="e_esta"' in texto
    assert "Para liberar ou cancelar ainda falta:" in texto
    assert "Há requisição candidata no intervalo: 003492/26." in texto


def test_e_esta_pela_aba_liga_o_recebimento(client, logado, pedido, scpi_simulado):
    from compras.models import CandidataEntrada

    r = _verificar(pedido, logado, scpi_simulado, salvou=True)
    candidata = CandidataEntrada.objects.get()
    resposta = client.post(
        reverse("automacoes:resolver_entrada", args=[r.pk]),
        {"acao": "e_esta", "requisicao_id": candidata.requisicao_id},
        follow=True,
    )
    assert f"{r.rotulo}: requisição 003492/26 registrada." in resposta.text
    r.refresh_from_db()
    assert r.status == "LANCADO" and r.requisicao_scpi == "003492/26"


def test_liberar_sem_as_provas_volta_a_aba_com_a_falta(client, logado, pedido, scpi_simulado):
    r = _verificar(pedido, logado, scpi_simulado, salvou=False)
    resposta = client.post(
        reverse("automacoes:resolver_entrada", args=[r.pk]),
        {"acao": "liberar", "conferi": "1"},
        follow=True,
    )
    assert "não foi conferido depois da tentativa: atualize os pedidos." in resposta.text
    r.refresh_from_db()
    assert r.status == "VERIFICAR"


def test_com_as_tres_provas_a_aba_libera_e_o_botao_fica_habilitado(
    client, logado, pedido, scpi_simulado
):
    from compras import importacao

    r = _verificar(pedido, logado, scpi_simulado, salvou=False)
    importacao.importar(scpi_simulado.relatorio_pedidos, forcar=True)
    texto = client.get(ENTRADAS).text
    assert "Para liberar ou cancelar ainda falta:" not in texto
    botao = re.search(r"<button[^>]*>Liberar para relançar", texto).group(0)
    assert " disabled" not in botao
    resposta = client.post(
        reverse("automacoes:resolver_entrada", args=[r.pk]),
        {"acao": "liberar", "conferi": "1"},
        follow=True,
    )
    assert f"{r.rotulo} liberado para o próximo lançamento." in resposta.text
    r.refresh_from_db()
    assert r.status == "PREPARADO"


def test_cancelar_pela_aba_em_dois_passos(client, logado, pedido, scpi_simulado):
    from compras import importacao

    r = _verificar(pedido, logado, scpi_simulado, salvou=False)
    importacao.importar(scpi_simulado.relatorio_pedidos, forcar=True)
    url = reverse("automacoes:resolver_entrada", args=[r.pk])
    sem = client.post(url, {"acao": "cancelar", "motivo": "NF devolvida"}, follow=True)
    assert "Confirme antes de cancelar." in sem.text
    com = client.post(
        url, {"acao": "cancelar", "motivo": "NF devolvida", "confirmado": "1"}, follow=True
    )
    assert "cancelado; a NF continua reservada." in com.text
    r.refresh_from_db()
    assert r.status == "CANCELADO"


def test_com_robo_rodando_a_regiao_diz_que_a_resolucao_espera(
    client, logado, pedido, scpi_simulado
):
    _verificar(pedido, logado, scpi_simulado, salvou=False)
    ExecucaoRobo.objects.create(robo="SAIDAS")
    texto = client.get(ENTRADAS).text
    assert "A resolução fica disponível quando o lançamento terminar." in texto
    assert 'name="acao" value="liberar"' not in texto


def test_recebimento_com_erro_aparece_sem_acoes_de_verificacao(client, logado, pedido):
    r = preparar(pedido, logado, {1: "10"})
    Recebimento.objects.filter(pk=r.pk).update(status="ERRO", mensagem="O SCPI mudou: item 1")
    texto = client.get(ENTRADAS).text
    assert r.rotulo in texto and "O SCPI mudou: item 1" in texto
    assert "O robô parou antes do Salvar" in texto and 'name="acao" value="e_esta"' not in texto


def test_resolver_entrada_exige_login_e_operar_automacoes(client, logado, pedido):
    r = preparar(pedido, logado, {1: "10"})
    url = reverse("automacoes:resolver_entrada", args=[r.pk])
    client.logout()
    assert client.post(url, {"acao": "liberar"}).status_code == 302
    client.force_login(usuario_com(username="40012"))
    assert client.post(url, {"acao": "liberar"}).status_code == 403
    assert client.get(url).status_code == 403


# --- a região "Conferência", "Pedidos travados" e as ações novas -------------------------------


def _lancado(pedido, logado, scpi_simulado):
    from pedidos.models import ExecucaoRobo
    from scpi.lancamento_entradas import executar_lancamento_entradas

    r = preparar(pedido, logado, {1: "10"})
    execucao = ExecucaoRobo.objects.create(robo="ENTRADAS")
    executar_lancamento_entradas(
        execucao,
        scpi_simulado.abrir,
        recebimentos=[r.rotulo],
        extrair=scpi_simulado.relatorio_entradas,
    )
    r.refresh_from_db()
    return r


def test_conferencia_mostra_a_ultima_extracao_e_o_veredito_com_o_filtro(
    client, logado, pedido, scpi_simulado
):
    r = _lancado(pedido, logado, scpi_simulado)
    texto = client.get(ENTRADAS + "&veredito_entradas=todos").text
    assert 'id="conferencia-entradas"' in texto and "Última extração:" in texto
    assert r.rotulo in texto and "Comprovado" in texto and "003492/26" in texto
    padrao = client.get(ENTRADAS).text  # o filtro padrão são as divergências: nenhuma
    assert "Nenhum recebimento lançado neste filtro." in padrao
    comprovados = client.get(ENTRADAS + "&veredito_entradas=comprovados").text
    assert r.rotulo in comprovados
    assert 'aria-current="true"' in comprovados


def test_conferencia_mostra_as_diferencas_em_texto(
    client, logado, pedido, scpi_simulado, monkeypatch
):
    from decimal import Decimal

    from django.core.management import call_command

    from scpi import relatorios

    r = _lancado(pedido, logado, scpi_simulado)
    monkeypatch.setattr(relatorios, "baixar_entradas", scpi_simulado.relatorio_entradas)
    scpi_simulado.salvas[0].itens = [("006.011.020", Decimal("12"))]
    call_command("conciliar_entradas")
    texto = client.get(ENTRADAS).text
    assert r.rotulo in texto and "Divergente" in texto and "Alterado no SCPI depois" in texto
    assert "Itens: no Central, 006.011.020 × 10; no SCPI, 006.011.020 × 12." in texto


def test_conferir_agora_inicia_o_comando_e_recusa_com_robo_rodando(client, logado, disparos):
    resposta = client.post(reverse("automacoes:conferir_entradas"), follow=True)
    assert "Conferência iniciada" in resposta.text
    ((argumentos, log),) = disparos
    assert argumentos == ["conciliar_entradas"] and log == "conciliar_entradas.log"
    ExecucaoRobo.objects.create(robo="SAIDAS")
    outra = client.post(reverse("automacoes:conferir_entradas"), follow=True)
    assert "Há um lançamento em andamento" in outra.text and len(disparos) == 1


def test_conferir_agora_fica_desabilitado_com_robo_rodando(client, logado):
    ExecucaoRobo.objects.create(robo="ENTRADAS")
    texto = client.get(ENTRADAS).text
    botao = re.search(r"<button[^>]*>Conferir agora", texto).group(0)
    assert " disabled" in botao
    assert "Há um lançamento em andamento. Confira quando ele terminar." in texto


def test_pedidos_travados_com_o_detalhe_a_ultima_importacao_e_o_destravar(client, logado, pedido):
    from compras import servicos

    servicos.travar_pedido(pedido.pk, "FORA_DO_CENTRAL", "A requisição 003493/26 foi feita à mão.")
    texto = client.get(ENTRADAS).text
    assert 'id="pedidos-travados"' in texto and pedido.rotulo in texto
    assert "Entrada feita fora do Central" in texto and "003493/26 foi feita à mão" in texto
    assert reverse("automacoes:destravar_pedido", args=[pedido.pk]) in texto
    assert "Última importação de pedidos" in texto


def test_destravar_pela_aba_exige_motivo_e_importacao_posterior(client, logado, pedido):
    from compras import servicos

    servicos.travar_pedido(pedido.pk, "TELA", "o SCPI mudou")
    url = reverse("automacoes:destravar_pedido", args=[pedido.pk])
    sem_motivo = client.post(url, {"motivo": ""}, follow=True)
    assert "Informe o motivo do destravamento." in sem_motivo.text
    sem_importacao = client.post(url, {"motivo": "conferi"}, follow=True)
    assert "Atualize os pedidos antes" in sem_importacao.text


def test_destravar_e_conferir_exigem_operar_automacoes(client, pedido, disparos):
    client.force_login(usuario_com(username="40013"))
    assert client.post(reverse("automacoes:destravar_pedido", args=[pedido.pk])).status_code == 403
    assert client.post(reverse("automacoes:conferir_entradas")).status_code == 403
    assert disparos == []


def test_o_pedido_mostra_as_entradas_feitas_fora_do_central(client, logado, pedido):
    from catalogo.models import Importacao
    from compras.models import EntradaForaDoCentral, ExtracaoEntradas, RequisicaoEntradaOficial

    imp = Importacao.objects.create(tipo="ENTRADAS", situacao="SUCESSO")
    extracao = ExtracaoEntradas.objects.create(importacao=imp, motivo="MANUAL")
    requisicao = RequisicaoEntradaOficial.objects.create(
        extracao=extracao,
        requisicao="003493/26",
        ano=2026,
        numero=3493,
        id_requi=1,
        data_entrada=timezone.localdate(),
        data_requisicao=timezone.localdate(),
    )
    EntradaForaDoCentral.objects.create(
        pedido=pedido,
        requisicao=requisicao,
        ano=2026,
        numero=3493,
        visivel_desde=timezone.now(),
        itens=[{"codigo": "006.011.020", "quantidade": "8"}],
    )
    texto = client.get(reverse("compras:pedido", args=[pedido.pk])).text
    assert "Entradas feitas direto no SCPI, sem o Central" in texto and "003493/26" in texto
