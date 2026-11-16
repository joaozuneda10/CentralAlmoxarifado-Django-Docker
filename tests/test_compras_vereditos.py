"""Conferir cada lançamento com o registro oficial (US4, PR 6): os vereditos com o SCPI simulado e
o `conciliar_entradas`."""

from datetime import date
from decimal import Decimal

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from compras import conciliacao
from compras.models import ConferenciaRecebimento, ExtracaoEntradas, Recebimento
from pedidos.models import ExecucaoRobo
from scpi import relatorios
from scpi.lancamento_entradas import executar_lancamento_entradas
from tests.compras_cenario import pedido_padrao, preparar, usuario_recebedor
from tests.relacao_entradas import EntradaCSV, csv_entradas
from tests.scpi_entradas_simulado import SCPIEntradasSimulado

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _log_na_pasta_temporaria(journal):
    return journal


@pytest.fixture
def usuario():
    return usuario_recebedor()


@pytest.fixture
def pedido():
    return pedido_padrao()


@pytest.fixture
def scpi(pedido, monkeypatch):
    simulado = SCPIEntradasSimulado()
    simulado.pedido(
        pedido.ano, pedido.numero, {1: ("006.011.020", "100"), 2: ("023.003.004", "20")}
    )
    simulado.pedidos[(pedido.ano, pedido.numero)][1]["ja_entrou"] = Decimal("50")
    monkeypatch.setattr(relatorios, "baixar_entradas", simulado.relatorio_entradas)
    return simulado


def _lancar(pedido, usuario, scpi, itens=None, nf="501"):
    r = preparar(pedido, usuario, itens or {1: "10"}, nf=nf)
    execucao = ExecucaoRobo.objects.create(robo="ENTRADAS")
    executar_lancamento_entradas(
        execucao, scpi.abrir, recebimentos=[r.rotulo], extrair=scpi.relatorio_entradas
    )
    r.refresh_from_db()
    assert r.status == "LANCADO"
    return r


def _conferencias(r):
    return list(r.conferencias.order_by("pk"))


# --- cenário: o veredito depois da execução ---------------------------------------------------


def test_depois_do_lancamento_o_recebimento_fica_comprovado_com_os_tres_vinculos(
    pedido, usuario, scpi
):
    r = _lancar(pedido, usuario, scpi)
    (c,) = _conferencias(r)
    assert (c.tipo, c.veredito, c.alterado_depois) == ("LANCAMENTO", "COMPROVADO", False)
    assert set(c.vinculos) == {"numero", "marca", "nf"}
    assert c.requisicao.requisicao == "003492/26" and c.diferencas == []
    assert c.tentativa is not None and c.tentativa.resultado == "LANCADA"


def test_o_recebimento_lancado_nunca_muda_com_a_conferencia(pedido, usuario, scpi):
    r = _lancar(pedido, usuario, scpi)
    antes = Recebimento.objects.values().get(pk=r.pk)
    call_command("conciliar_entradas")
    scpi.salvas[0].nf = "999"
    call_command("conciliar_entradas")
    assert Recebimento.objects.values().get(pk=r.pk) == antes  # FR-027


def test_conferencia_depois_da_primeira_e_revisao_com_o_que_mudou_no_scpi(pedido, usuario, scpi):
    r = _lancar(pedido, usuario, scpi)
    scpi.salvas[0].itens = [("006.011.020", Decimal("12"))]  # editada à mão depois do lançamento
    call_command("conciliar_entradas")
    primeira, revisao = _conferencias(r)
    assert primeira.tipo == "LANCAMENTO" and revisao.tipo == "REVISAO"
    assert revisao.veredito == "DIVERGENTE" and revisao.alterado_depois
    campos = {(d["campo"], d.get("alteracao", False)) for d in revisao.diferencas}
    assert ("itens", False) in campos and ("itens", True) in campos
    atual = conciliacao_veredito(r)
    assert atual == revisao


def conciliacao_veredito(r):
    from compras.consultas import veredito_atual

    return veredito_atual(r)


def test_requisicao_excluida_no_scpi_aparece_como_alteracao_e_nao_encontrado(pedido, usuario, scpi):
    r = _lancar(pedido, usuario, scpi)
    scpi.salvas.clear()
    scpi.entrada_manual((pedido.ano, pedido.numero), {2: "1"}, data=timezone.localdate(), nf="777")
    call_command("conciliar_entradas")
    revisao = _conferencias(r)[-1]
    assert (
        revisao.tipo == "REVISAO"
        and revisao.veredito == "NAO_ENCONTRADO"
        and revisao.alterado_depois
    )
    assert any(d["campo"] == "requisição" for d in revisao.diferencas)


# --- aguardando, não encontrado, duplicado, conflito -----------------------------------------


def test_sem_requisicao_e_sem_numero_maior_fica_aguardando_e_nao_vira_conclusiva(
    pedido, usuario, scpi
):
    r = _lancar(pedido, usuario, scpi)
    ConferenciaRecebimento.objects.all().delete()
    scpi.salvas.clear()  # o relatório não traz nada e nem há número maior
    scpi.entrada_manual((pedido.ano, pedido.numero), {2: "1"}, data=timezone.localdate(), nf="777")
    scpi.salvas[0].requisicao = "003400/26"  # número menor que o do recebimento
    call_command("conciliar_entradas")
    (c,) = _conferencias(r)
    assert c.veredito == "AGUARDANDO" and c.tipo == "LANCAMENTO"
    from compras.consultas import veredito_atual

    assert veredito_atual(r) is None  # a AGUARDANDO é provisória


def test_numero_maior_no_relatorio_sem_a_requisicao_do_recebimento_e_nao_encontrado(
    pedido, usuario, scpi
):
    r = _lancar(pedido, usuario, scpi)
    ConferenciaRecebimento.objects.all().delete()
    scpi.salvas.clear()
    scpi.proximo_numero = 3600
    scpi.entrada_manual((pedido.ano, pedido.numero), {2: "1"}, data=timezone.localdate(), nf="777")
    call_command("conciliar_entradas")
    (c,) = _conferencias(r)
    assert c.veredito == "NAO_ENCONTRADO"


def test_duplicado_pela_nf_mesmo_sem_a_marca_do_central(pedido, usuario, scpi):
    r = _lancar(pedido, usuario, scpi)
    scpi.salvas[0].observacoes = ""  # a marca se perdeu
    scpi.entrada_manual(
        (pedido.ano, pedido.numero), {1: "10"}, data=timezone.localdate(), nf="501"
    )  # outra com a mesma NF e o mesmo fornecedor
    call_command("conciliar_entradas")
    ultima = _conferencias(r)[-1]
    assert ultima.veredito == "DUPLICADO" and ultima.outra_requisicao is not None


def test_conflito_quando_o_numero_e_a_nf_apontam_para_requisicoes_diferentes(pedido, usuario, scpi):
    r = _lancar(pedido, usuario, scpi)
    scpi.salvas[0].nf = "888"  # o número gravado leva a uma NF diferente
    scpi.entrada_manual((pedido.ano, pedido.numero), {1: "10"}, data=timezone.localdate(), nf="501")
    scpi.salvas[1].observacoes = ""
    call_command("conciliar_entradas")
    assert _conferencias(r)[-1].veredito in {"CONFLITO", "DUPLICADO"}


def test_a_requisicao_achada_numa_conferencia_anterior_nao_some_calada(pedido, usuario, scpi):
    r = _lancar(pedido, usuario, scpi)
    primeira = _conferencias(r)[0]
    # a primeira conclusiva não achou nada; uma segunda achou a requisição (COMPROVADO)
    ConferenciaRecebimento.objects.filter(pk=primeira.pk).update(
        veredito="NAO_ENCONTRADO", requisicao=None
    )
    ConferenciaRecebimento.objects.create(
        recebimento=r,
        extracao=primeira.extracao,
        tipo="REVISAO",
        veredito="COMPROVADO",
        requisicao=primeira.requisicao,
        tentativa=primeira.tentativa,
    )
    scpi.salvas.clear()  # agora a requisição sumiu e não há número maior no relatório
    scpi.entrada_manual((pedido.ano, pedido.numero), {2: "1"}, data=timezone.localdate(), nf="777")
    scpi.salvas[0].requisicao = "003400/26"
    call_command("conciliar_entradas")
    ultima = _conferencias(r)[-1]
    assert ultima.veredito == "NAO_ENCONTRADO"  # e não AGUARDANDO, que esconderia o sumiço


def test_a_lista_de_vereditos_filtra_e_pagina_o_veredito_atual(pedido, usuario, scpi):
    from compras.consultas import vereditos

    r = _lancar(pedido, usuario, scpi)
    comprovados = vereditos("comprovados")
    (linha,) = list(comprovados)
    assert linha["recebimento"] == r and linha["veredito"] == "COMPROVADO"
    assert linha["conferencia"] == _conferencias(r)[-1]
    assert list(vereditos("divergencias")) == []
    assert list(vereditos("aguardando")) == []
    ConferenciaRecebimento.objects.all().delete()
    (sem,) = list(vereditos("aguardando"))
    assert sem["conferencia"] is None and sem["veredito"] == "AGUARDANDO"
    assert [x["recebimento"] for x in vereditos("todos")] == [r]


# --- --arquivo, incompleta -------------------------------------------------------------------


def test_arquivo_so_da_o_primeiro_veredito_e_nunca_revisa(pedido, usuario, scpi, tmp_path):
    r = _lancar(pedido, usuario, scpi)
    ConferenciaRecebimento.objects.all().delete()
    hoje = timezone.localdate()
    arquivo = tmp_path / "entradas.csv"
    arquivo.write_bytes(scpi.relatorio_entradas(date(hoje.year, 1, 1), hoje))
    call_command("conciliar_entradas", arquivo=str(arquivo))
    (primeira,) = _conferencias(r)
    assert primeira.tipo == "LANCAMENTO" and primeira.extracao.motivo == "ARQUIVO"
    call_command("conciliar_entradas", arquivo=str(arquivo))
    assert len(_conferencias(r)) == 1  # o arquivo não revisa um veredito


def test_conciliacao_incompleta_sai_com_erro_e_a_contagem_parcial(
    pedido, usuario, scpi, monkeypatch
):
    _lancar(pedido, usuario, scpi)

    def quebrar(extracao, falhas=None):
        raise RuntimeError("banco fora")

    monkeypatch.setattr(conciliacao, "conciliar_lancados", quebrar)
    with pytest.raises(CommandError, match="incompleta.*banco fora"):
        call_command("conciliar_entradas")


def test_a_extracao_do_robo_ja_confere_o_que_ele_lancou(pedido, usuario, scpi):
    r = _lancar(pedido, usuario, scpi)
    assert ExtracaoEntradas.objects.filter(motivo="DEPOIS").count() == 1
    assert _conferencias(r)[0].extracao.motivo == "DEPOIS"
    assert csv_entradas and EntradaCSV
