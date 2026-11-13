"""A rotina diária das entradas e a retenção de 60 dias (PR 7, R22)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from catalogo.models import Importacao
from compras import limpeza
from compras.limpeza import RETENCAO, limpar
from compras.management.commands.conciliar_entradas import periodo_padrao
from compras.models import (
    CandidataEntrada,
    ConferenciaRecebimento,
    EntradaForaDoCentral,
    ExtracaoEntradas,
    Recebimento,
    RequisicaoEntradaOficial,
)
from scpi import relatorios
from tests.compras_cenario import pedido_padrao, preparar, usuario_recebedor
from tests.relacao_entradas import EntradaCSV, csv_entradas
from tests.scpi_entradas_simulado import SCPIEntradasSimulado

pytestmark = pytest.mark.django_db

ATUALIZAR = "scpi.management.commands.atualizar_catalogo.call_command"


# --- o atualizar_catalogo ---------------------------------------------------------------------


def test_atualizar_roda_as_entradas_e_depois_os_pedidos_na_mesma_sessao(monkeypatch):
    feitos = []
    monkeypatch.setattr(ATUALIZAR, lambda nome, *a, **k: feitos.append((nome, k)))
    call_command("atualizar_catalogo")
    nomes = [nome for nome, _ in feitos]
    assert nomes[-2:] == ["conciliar_entradas", "importar_pedidos_compra"]
    assert dict(feitos)["conciliar_entradas"]["diaria"] is True


def test_um_passo_que_falha_nao_desfaz_os_anteriores_nem_impede_o_seguinte(monkeypatch, capsys):
    feitos = []

    def falso(nome, *args, **kwargs):
        feitos.append(nome)
        if nome == "conciliar_entradas":
            raise CommandError("Entradas do SCPI: fora do ar.")

    monkeypatch.setattr(ATUALIZAR, falso)
    with pytest.raises(CommandError, match=r"^Falharam: conciliar_entradas\.$"):
        call_command("atualizar_catalogo")
    assert feitos[-1] == "importar_pedidos_compra"  # o seguinte rodou
    assert "conciliar_entradas: Entradas do SCPI: fora do ar." in capsys.readouterr().err


def test_a_carga_inicial_roda_os_dois_passos_novos(monkeypatch):
    feitos = []
    monkeypatch.setattr(ATUALIZAR, lambda nome, *a, **k: feitos.append(nome))
    call_command("atualizar_catalogo", carga_inicial=True)
    assert feitos[-2:] == ["conciliar_entradas", "importar_pedidos_compra"]


# --- o período diário --------------------------------------------------------------------------


def test_o_periodo_diario_cobre_o_lancado_de_hoje_com_data_antiga_e_o_em_verificacao_aberto():
    pedido = pedido_padrao()
    usuario = usuario_recebedor()
    agora = timezone.now()
    hoje = timezone.localtime(agora).date()
    antigo = hoje - timedelta(days=20)
    lancado = preparar(pedido, usuario, {1: "5"}, nf="501", data=hoje)
    Recebimento.objects.filter(pk=lancado.pk).update(
        status="LANCADO", lancado_em=agora, data_recebimento=antigo, requisicao_scpi="003492/26"
    )
    assert periodo_padrao(agora) == (antigo - timedelta(days=1), hoje + timedelta(days=1))
    # sem lançamento recente, só o em verificação aberto com data antiga estende o período
    Recebimento.objects.filter(pk=lancado.pk).update(
        status="VERIFICAR",
        lancado_em=None,
        requisicao_scpi="",
        data_recebimento=antigo - timedelta(days=5),
    )
    assert periodo_padrao(agora)[0] == antigo - timedelta(days=6)


# --- a limpeza ---------------------------------------------------------------------------------


@pytest.fixture
def scpi(monkeypatch):
    simulado = SCPIEntradasSimulado()
    monkeypatch.setattr(relatorios, "baixar_entradas", simulado.relatorio_entradas)
    return simulado


def _extracao(dias_atras: int, numeros=(3492,), motivo="MANUAL", **campos):
    """Uma extração gravada pelo caminho de verdade, recuada `dias_atras` dias."""
    from compras.extracao import extrair

    hoje = timezone.localdate()
    conteudo = csv_entradas([EntradaCSV(f"{n:06d}/26", n, hoje) for n in numeros])
    extracao = extrair(
        motivo, (hoje - timedelta(days=1), hoje + timedelta(days=1)), lambda: conteudo
    )
    recuo = timezone.now() - timedelta(days=dias_atras)
    Importacao.objects.filter(pk=extracao.importacao_id).update(inicio=recuo, fim=recuo)
    extracao.refresh_from_db()
    return extracao


def test_a_limpeza_esvazia_o_bruto_de_mais_de_60_dias_e_o_de_quem_aponta_para_ele():
    velha = _extracao(70)
    repete = _extracao(0)  # o mesmo arquivo: aponta para a velha, que ainda tem os bytes
    outra = _extracao(0, numeros=(3500,))
    assert repete.mesmo_arquivo_que == velha and repete.arquivo is None
    # a velha tem uma extração recente apontando para ela: o bruto fica
    assert limpar().brutos == 0
    velha.refresh_from_db()
    assert velha.arquivo is not None
    # quando a que aponta também passa dos 60 dias, o bruto da velha é esvaziado
    recuo = timezone.now() - timedelta(days=65)
    Importacao.objects.filter(pk=repete.importacao_id).update(inicio=recuo, fim=recuo)
    assert limpar().brutos == 1
    velha.refresh_from_db()
    assert velha.arquivo is None and velha.arquivo_apagado_em is not None and velha.impressao
    outra.refresh_from_db()
    assert outra.arquivo is not None  # a de hoje não é tocada


def test_a_limpeza_apaga_as_requisicoes_sem_ligacao_e_guarda_as_ligadas():
    velha = _extracao(70, numeros=(3492, 3493, 3494, 3495))
    por_numero = {r.numero: r for r in velha.requisicoes_lidas.all()}
    pedido = pedido_padrao()
    usuario = usuario_recebedor()
    r = preparar(pedido, usuario, {1: "5"}, nf="501")
    conferencia = ConferenciaRecebimento.objects.create(
        recebimento=r, extracao=velha, tipo="VERIFICAR", veredito="COM_CANDIDATAS"
    )
    CandidataEntrada.objects.create(
        conferencia=conferencia, requisicao=por_numero[3493], e_esta=False, ordem=1
    )
    ConferenciaRecebimento.objects.create(
        recebimento=r,
        extracao=velha,
        tipo="LANCAMENTO",
        veredito="COMPROVADO",
        requisicao=por_numero[3492],
    )
    EntradaForaDoCentral.objects.create(
        pedido=pedido,
        requisicao=por_numero[3494],
        ano=2026,
        numero=3494,
        visivel_desde=timezone.now(),
    )
    resultado = limpar()
    assert resultado.requisicoes == 1  # só a 3495: sem conferência, candidata nem entrada de fora
    assert sorted(RequisicaoEntradaOficial.objects.values_list("numero", flat=True)) == [
        3492,
        3493,
        3494,
    ]
    assert "1 requisição sem ligação de entrada com mais de 60 dias apagados" in resultado.resumo


def test_a_limpeza_de_nada_a_apagar_diz_isso():
    _extracao(1)
    resultado = limpar()
    assert (resultado.brutos, resultado.requisicoes) == (0, 0)
    assert resultado.resumo == "nada com mais de 60 dias a apagar"


def test_a_limpeza_com_a_trava_ocupada_fica_para_a_proxima(trava_importacao_ocupada):
    _extracao(70)
    trava_importacao_ocupada("ENTRADAS")
    assert limpar() is None
    assert ExtracaoEntradas.objects.get().arquivo is not None


def test_a_retencao_e_de_60_dias():
    assert RETENCAO == timedelta(days=60) and limpeza.LOTE_DE_APAGAR == 500


# --- o comando chama a limpeza ----------------------------------------------------------------


def test_o_comando_roda_a_limpeza_no_fim_e_sem_limpeza_nao(scpi, capsys):
    hoje = timezone.localdate()
    scpi.pedido(2026, 514, {1: ("006.011.020", "100")})
    scpi.entrada_manual((2026, 514), {1: "1"}, data=hoje, nf="111")
    call_command("conciliar_entradas")
    assert "Limpeza: nada com mais de 60 dias a apagar." in capsys.readouterr().out
    call_command("conciliar_entradas", sem_limpeza=True)
    assert "Limpeza:" not in capsys.readouterr().out


def test_a_limpeza_nao_impede_o_comando_de_falhar_pela_conciliacao(scpi, monkeypatch):
    from compras import conciliacao

    scpi.pedido(2026, 514, {1: ("006.011.020", "100")})
    scpi.entrada_manual((2026, 514), {1: "1"}, data=timezone.localdate(), nf="111")

    def quebrar(extracao):
        raise conciliacao.ConciliacaoIncompleta({}, ["algo quebrou"])

    monkeypatch.setattr("compras.management.commands.conciliar_entradas.conciliar", quebrar)
    chamadas = []
    monkeypatch.setattr(
        "compras.management.commands.conciliar_entradas.limpar", lambda: chamadas.append(1)
    )
    with pytest.raises(CommandError, match="incompleta.*algo quebrou"):
        call_command("conciliar_entradas")
    assert chamadas == [1]  # a limpeza rodou mesmo assim
    assert Decimal(0) == 0
