"""Resolver um recebimento em verificação (US3, PR 5): as candidatas, o "É esta" e as três provas
da liberação, com o SCPI simulado e as extrações e importações reais."""

import uuid
from decimal import Decimal

import pytest
from django.utils import timezone

from compras import consultas, importacao, servicos
from compras.models import (
    CandidataEntrada,
    ConferenciaRecebimento,
    ExtracaoEntradas,
    Recebimento,
    TentativaEntrada,
)
from pedidos.models import ExecucaoRobo
from scpi.lancamento_entradas import executar_lancamento_entradas
from tests.compras_cenario import pedido_padrao, preparar, usuario_recebedor
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
def scpi(pedido):
    simulado = SCPIEntradasSimulado()
    simulado.pedido(
        pedido.ano, pedido.numero, {1: ("006.011.020", "100"), 2: ("023.003.004", "20")}
    )
    simulado.pedidos[(pedido.ano, pedido.numero)][1]["ja_entrou"] = Decimal("50")
    return simulado


def _rodar(rotulos, scpi, extrair=None):
    execucao = ExecucaoRobo.objects.create(robo="ENTRADAS")
    executar_lancamento_entradas(
        execucao,
        scpi.abrir,
        recebimentos=list(rotulos),
        extrair=extrair or scpi.relatorio_entradas,
    )
    return execucao


def _importar_pedidos(scpi):
    imp = importacao.importar(scpi.relatorio_pedidos, forcar=True)
    assert imp.situacao == "SUCESSO", imp.erro


def _em_verificacao(pedido, usuario, scpi, *, salvou: bool, nf="501", itens=None):
    """Um recebimento em verificação: o Salvar perdeu a resposta, e o SCPI salvou ou não."""
    r = preparar(pedido, usuario, itens or {1: "10"}, nf=nf)
    (scpi.salva_e_falha if salvou else scpi.falha_salvar).add(r.rotulo)
    _rodar([r.rotulo], scpi)
    r.refresh_from_db()
    assert r.status == "VERIFICAR"
    return r


def _candidatas(r):
    return list(
        CandidataEntrada.objects.filter(conferencia__recebimento=r).values_list(
            "requisicao__requisicao", "e_esta"
        )
    )


# --- cenário 1: a candidata com a marca é "é esta" e liga ---------------------------------------


def test_extracao_posterior_traz_a_candidata_com_a_marca_e_e_esta_liga_como_lancado(
    pedido, usuario, scpi
):
    r = _em_verificacao(pedido, usuario, scpi, salvou=True)
    (conferencia,) = ConferenciaRecebimento.objects.filter(recebimento=r)
    assert conferencia.tipo == "VERIFICAR" and conferencia.veredito == "COM_CANDIDATAS"
    assert _candidatas(r) == [("003492/26", True)]
    candidata = CandidataEntrada.objects.get()
    resposta = servicos.resolver_recebimento(
        r.pk, usuario, acao="e_esta", requisicao_id=candidata.requisicao_id
    )
    assert resposta.ok, resposta.mensagem
    r.refresh_from_db()
    assert (r.status, r.requisicao_scpi, r.via) == ("LANCADO", "003492/26", "ROBO")
    assert r.visivel_desde == conferencia.extracao.importacao.inicio
    assert TentativaEntrada.objects.get().resultado == "LANCADA"
    assert TentativaEntrada.objects.get().requisicao == "003492/26"


def test_e_esta_tambem_acha_pela_nf_e_o_fornecedor_com_a_marca_perdida(pedido, usuario, scpi):
    r = preparar(pedido, usuario, {1: "10"}, nf="501")
    scpi.salva_e_falha.add(r.rotulo)
    scpi.perde_observacoes.add(r.rotulo)  # o SCPI gravou sem a marca
    _rodar([r.rotulo], scpi)
    assert _candidatas(r) == [("003492/26", True)]  # pela NF 501 e o fornecedor 19502


def test_e_esta_recusa_requisicao_que_nao_e_candidata_ou_ja_esta_ligada_a_outro(
    pedido, usuario, scpi
):
    r = _em_verificacao(pedido, usuario, scpi, salvou=True)
    candidata = CandidataEntrada.objects.get()
    assert (
        servicos.resolver_recebimento(r.pk, usuario, acao="e_esta", requisicao_id=999999).motivo
        == "candidata"
    )
    assert servicos.resolver_recebimento(r.pk, usuario, acao="e_esta").motivo == "candidata"
    outro = preparar(pedido, usuario, {2: "5"}, nf="777")
    Recebimento.objects.filter(pk=outro.pk).update(
        status="LANCADO", requisicao_scpi="003492/26", via="MANUAL"
    )
    resposta = servicos.resolver_recebimento(
        r.pk, usuario, acao="e_esta", requisicao_id=candidata.requisicao_id
    )
    assert not resposta.ok and resposta.motivo == "ligada" and outro.rotulo in resposta.mensagem
    r.refresh_from_db()
    assert r.status == "VERIFICAR"


# --- cenário 2: sem candidata e com o "Já Entrou" esperado, libera o mesmo recebimento ----------


def test_sem_candidata_e_com_o_ja_entrou_esperado_libera_o_mesmo_recebimento(pedido, usuario, scpi):
    r = _em_verificacao(pedido, usuario, scpi, salvou=False)
    assert ConferenciaRecebimento.objects.get().veredito == "INTERVALO_VAZIO"
    assert consultas.liberacao(r) == [
        "O 'Já Entrou' do item 1 não foi conferido depois da tentativa: atualize os pedidos."
    ]
    _importar_pedidos(scpi)  # o SCPI não salvou: o "Já Entrou" continua 50
    assert consultas.liberacao(r) == []
    versao, chave = r.versao, r.chave_nf
    resposta = servicos.resolver_recebimento(r.pk, usuario, acao="liberar", conferi=True)
    assert resposta.ok, resposta.mensagem
    r.refresh_from_db()
    assert (r.status, r.versao, r.chave_nf) == ("PREPARADO", versao + 1, chave)
    assert (r.requisicao_scpi, r.lancado_em, r.visivel_desde) == ("", None, None)
    assert "Liberado para relançar por 12345" in r.mensagem
    # voltou à fila e o robô o lança de verdade, e a tentativa antiga não trava mais nada
    assert not servicos.tem_tentativa(r)
    scpi.falha_salvar.clear()  # desta vez o SCPI responde
    execucao = _rodar([r.rotulo], scpi)
    r.refresh_from_db()
    assert r.status == "LANCADO" and execucao.resumo["lancadas"] == 1
    assert len(scpi.salvas) == 1


def test_liberar_exige_a_confirmacao_de_que_conferiu_no_scpi(pedido, usuario, scpi):
    r = _em_verificacao(pedido, usuario, scpi, salvou=False)
    _importar_pedidos(scpi)
    resposta = servicos.resolver_recebimento(r.pk, usuario, acao="liberar")
    assert not resposta.ok and resposta.motivo == "conferi"
    r.refresh_from_db()
    assert r.status == "VERIFICAR"


# --- cenário 3: sem extração posterior, a liberação é recusada ----------------------------------


def test_sem_extracao_posterior_a_liberacao_e_recusada(pedido, usuario, scpi):
    r = preparar(pedido, usuario, {1: "10"})
    scpi.falha_salvar.add(r.rotulo)
    chamadas = []

    def extrair(de, ate):
        chamadas.append((de, ate))
        if len(chamadas) == 1:
            return scpi.relatorio_entradas(de, ate)
        raise RuntimeError("SCPI fora do ar")  # a extração de depois falha

    _rodar([r.rotulo], scpi, extrair)
    _importar_pedidos(scpi)
    assert not ConferenciaRecebimento.objects.exists()
    (falta,) = consultas.liberacao(r)
    assert falta.startswith("Ainda não houve extração de entradas depois da tentativa de ")
    resposta = servicos.resolver_recebimento(r.pk, usuario, acao="liberar", conferi=True)
    assert not resposta.ok and resposta.motivo == "provas" and falta in resposta.mensagem


def test_extracao_de_arquivo_nunca_confere_nem_libera(pedido, usuario, scpi, tmp_path):
    from django.core.management import call_command
    from django.utils import timezone

    from tests.relacao_entradas import EntradaCSV, csv_entradas

    r = _em_verificacao(pedido, usuario, scpi, salvou=False)
    ConferenciaRecebimento.objects.all().delete()
    arquivo = tmp_path / "entradas.csv"
    arquivo.write_bytes(csv_entradas([EntradaCSV("000001/26", 1, timezone.localdate())]))
    call_command("conciliar_entradas", arquivo=str(arquivo))
    assert ExtracaoEntradas.objects.filter(motivo="ARQUIVO").exists()
    assert not ConferenciaRecebimento.objects.exists()  # o arquivo nunca confere
    assert consultas.liberacao(r)  # continua com faltas


# --- cenário 4: a candidata que sumiu continua bloqueando ----------------------------------------


def test_candidata_que_apareceu_e_sumiu_continua_bloqueando_a_liberacao(
    pedido, usuario, scpi, monkeypatch
):
    from django.core.management import call_command

    from scpi import relatorios

    monkeypatch.setattr(relatorios, "baixar_entradas", scpi.relatorio_entradas)

    r = _em_verificacao(pedido, usuario, scpi, salvou=True)
    assert _candidatas(r) == [("003492/26", True)]
    scpi.salvas.clear()  # a requisição some do relatório seguinte
    scpi.pedidos[(pedido.ano, pedido.numero)][1]["ja_entrou"] = Decimal("50")
    call_command("conciliar_entradas")
    assert ConferenciaRecebimento.objects.filter(recebimento=r).count() == 2
    _importar_pedidos(scpi)
    faltas = consultas.liberacao(r)
    assert faltas == ["Há requisição candidata no intervalo: 003492/26."]
    assert not servicos.resolver_recebimento(r.pk, usuario, acao="liberar", conferi=True).ok


# --- cenário 5: lacuna na numeração e entrada manual de outro pedido -----------------------------


def test_lacuna_na_numeracao_e_entrada_de_outro_pedido_nao_bloqueiam_nem_provam(
    pedido, usuario, scpi
):
    scpi.pedido(2026, 999, {1: ("006.011.020", "100")})
    r = preparar(pedido, usuario, {1: "10"})
    scpi.falha_salvar.add(r.rotulo)
    # uma entrada à mão de OUTRO pedido, no meio do intervalo, e um número que ninguém usou
    scpi.entrada_manual((2026, 999), {1: "5"}, data=timezone.localdate())
    scpi.proximo_numero += 3  # a lacuna
    _rodar([r.rotulo], scpi)
    assert _candidatas(r) == []  # o outro pedido não entra, e a lacuna não é candidata
    _importar_pedidos(scpi)
    assert consultas.liberacao(r) == []


# --- cancelar ---------------------------------------------------------------------------------


def test_cancelar_sem_as_provas_e_recusado_e_com_elas_cancela_sem_liberar_a_nf(
    pedido, usuario, scpi
):
    r = _em_verificacao(pedido, usuario, scpi, salvou=False)
    sem = servicos.resolver_recebimento(
        r.pk, usuario, acao="cancelar", motivo="NF devolvida", confirmado=True
    )
    assert not sem.ok and sem.motivo == "provas"
    _importar_pedidos(scpi)
    assert (
        servicos.resolver_recebimento(r.pk, usuario, acao="cancelar", confirmado=True).motivo
        == "motivo"
    )
    assert (
        servicos.resolver_recebimento(r.pk, usuario, acao="cancelar", motivo="x").motivo
        == "confirmacao"
    )
    com = servicos.resolver_recebimento(
        r.pk, usuario, acao="cancelar", motivo="NF devolvida", confirmado=True
    )
    assert com.ok, com.mensagem
    r.refresh_from_db()
    assert r.status == "CANCELADO" and r.chave_nf == "19502:501"  # a NF continua reservada
    assert r.motivo_cancelamento == "NF devolvida"


def test_a_nf_do_cancelado_apos_tentativa_nao_pode_ser_reusada(pedido, usuario, scpi):
    r = _em_verificacao(pedido, usuario, scpi, salvou=False)
    _importar_pedidos(scpi)
    servicos.resolver_recebimento(r.pk, usuario, acao="cancelar", motivo="x", confirmado=True)
    resposta = servicos.preparar_recebimento(
        pedido.pk,
        usuario,
        envio=uuid.uuid4(),
        nf="501",
        data_recebimento=timezone.localdate(),
        itens={i.pk: "5" for i in pedido.itens.filter(item=1)},
    )
    assert not resposta.ok and any("501" in e.mensagem for e in resposta.erros)


# --- recusas ------------------------------------------------------------------------------------


def test_resolver_com_execucao_em_andamento_e_recusado(pedido, usuario, scpi):
    r = _em_verificacao(pedido, usuario, scpi, salvou=False)
    ExecucaoRobo.objects.create(robo="SAIDAS")
    resposta = servicos.resolver_recebimento(r.pk, usuario, acao="liberar", conferi=True)
    assert not resposta.ok and resposta.motivo == "andamento"


def test_so_o_recebimento_em_verificacao_se_resolve(pedido, usuario):
    r = preparar(pedido, usuario, {1: "10"})
    resposta = servicos.resolver_recebimento(r.pk, usuario, acao="liberar", conferi=True)
    assert not resposta.ok and resposta.motivo == "estado"
    assert servicos.resolver_recebimento(r.pk, usuario, acao="x").motivo == "acao"
    assert servicos.resolver_recebimento(999999, usuario, acao="liberar").motivo == "nao_encontrado"


def test_sem_tentativa_registrada_a_liberacao_e_recusada(pedido, usuario):
    r = preparar(pedido, usuario, {1: "10"})
    Recebimento.objects.filter(pk=r.pk).update(status="VERIFICAR")
    (falta,) = consultas.liberacao(r)
    assert "Não há tentativa registrada" in falta


def test_o_ja_entrou_que_mudou_depois_da_tentativa_bloqueia_a_liberacao(pedido, usuario, scpi):
    r = _em_verificacao(pedido, usuario, scpi, salvou=True)
    CandidataEntrada.objects.all().delete()  # (a candidata não é o ponto deste teste)
    ConferenciaRecebimento.objects.all().update(veredito="INTERVALO_VAZIO")
    _importar_pedidos(scpi)  # o SCPI salvou: o "Já Entrou" subiu de 50 para 60
    (falta,) = consultas.liberacao(r)
    assert falta == (
        "O 'Já Entrou' do item 1 mudou de 50 para 60 depois da tentativa: "
        "a requisição pode existir."
    )
