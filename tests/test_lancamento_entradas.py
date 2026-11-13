"""O robô de entradas com o SCPI simulado: uma linha por garantia de
`specs/014-entrada-por-pedido/contracts/robo-entradas.md`."""

import json
from decimal import Decimal

import pytest
from django.db import DatabaseError
from django.db.models import F
from django.db.models.query import QuerySet

from compras import regras
from compras.models import (
    ExtracaoEntradas,
    Recebimento,
    TentativaEntrada,
    TravaPedido,
)
from pedidos.models import ExecucaoRobo
from scpi import lancamento_entradas
from scpi.lancamento import LancamentoEmAndamento
from scpi.lancamento_entradas import executar_lancamento_entradas
from scpi.requisicoes import FalhaCritica
from tests.compras_cenario import pedido_padrao, preparar, usuario_recebedor
from tests.scpi_entradas_simulado import SCPIEntradasSimulado

pytestmark = pytest.mark.django_db


@pytest.fixture
def usuario():
    return usuario_recebedor()


@pytest.fixture
def pedido():
    return pedido_padrao()


@pytest.fixture
def scpi(pedido):
    """O SCPI com o pedido do cenário como a importação o viu: item 1 com 50 já entregues."""
    simulado = SCPIEntradasSimulado()
    simulado.pedido(
        pedido.ano, pedido.numero, {1: ("006.011.020", "100"), 2: ("023.003.004", "20")}
    )
    simulado.pedidos[(pedido.ano, pedido.numero)][1]["ja_entrou"] = Decimal("50")
    return simulado


@pytest.fixture(autouse=True)
def _log_na_pasta_temporaria(journal):
    return journal


def _rodar(rotulos, scpi, *, simulacao=False, extrair=None):
    execucao = ExecucaoRobo.objects.create(robo=ExecucaoRobo.Robo.ENTRADAS, simulacao=simulacao)
    executar_lancamento_entradas(
        execucao,
        scpi.abrir,
        recebimentos=list(rotulos),
        extrair=extrair or scpi.relatorio_entradas,
    )
    execucao.refresh_from_db()
    return execucao


def _chamadas(scpi, nome):
    return [c for c in scpi.chamadas if c[0] == nome]


def _journal(pasta):
    arquivo = pasta / lancamento_entradas.JOURNAL
    return [json.loads(linha) for linha in arquivo.read_text("utf-8").splitlines()]


# --- sucesso -----------------------------------------------------------------------------------


def test_sucesso_grava_o_numero_a_via_o_visivel_desde_e_a_tentativa(pedido, usuario, scpi, journal):
    r = preparar(pedido, usuario, {1: "10"}, observacao="portaria; volume 3")
    execucao = _rodar([r.rotulo], scpi)
    assert execucao.situacao == "SUCESSO"
    assert (execucao.resumo["lancadas"], execucao.resumo["falhas"]) == (1, 0)
    r.refresh_from_db()
    assert (r.status, r.requisicao_scpi, r.via, r.mensagem) == ("LANCADO", "003492/26", "ROBO", "")
    assert r.lancado_em is not None and r.visivel_desde == r.lancado_em
    (tentativa,) = TentativaEntrada.objects.all()
    assert (tentativa.resultado, tentativa.requisicao, tentativa.versao) == (
        "LANCADA",
        "003492/26",
        r.versao,
    )
    assert tentativa.foto["nf"] == "501" and tentativa.foto["tela"][0]["ja_entrou"] == "50"
    (salva,) = scpi.salvas
    assert salva.nf == "501" and salva.observacoes.startswith(f"Central Almoxarifado {r.rotulo}")
    assert "Obs.: portaria, volume 3" in salva.observacoes
    assert [e["evento"] for e in _journal(journal)] == ["em_lancamento", "lancada"]
    assert _journal(journal)[-1]["requisicao"] == "003492/26"
    # a extração de antes e a de depois, as duas ligadas à execução
    assert sorted(ExtracaoEntradas.objects.values_list("motivo", flat=True)) == ["ANTES", "DEPOIS"]
    assert scpi.abertas == 1


def test_o_segundo_recebimento_do_pedido_espera_o_ja_entrou_do_primeiro(pedido, usuario, scpi):
    um = preparar(pedido, usuario, {1: "10"}, nf="501")
    dois = preparar(pedido, usuario, {1: "5"}, nf="502")
    execucao = _rodar([um.rotulo, dois.rotulo], scpi)
    assert execucao.resumo["lancadas"] == 2
    assert [r.status for r in Recebimento.objects.order_by("pk")] == ["LANCADO", "LANCADO"]
    assert scpi.pedidos[(pedido.ano, pedido.numero)][1]["ja_entrou"] == Decimal("65")


# --- falhas antes do Salvar --------------------------------------------------------------------


@pytest.mark.parametrize("onde", ["abrir", "preencher"])
def test_falha_antes_do_salvar_vai_a_erro_sem_salvar(pedido, usuario, scpi, onde):
    r = preparar(pedido, usuario, {1: "10"})
    scpi.falha_antes.add(onde)
    execucao = _rodar([r.rotulo], scpi)
    assert execucao.situacao == "ATENCAO" and execucao.resumo["falhas"] == 1
    r.refresh_from_db()
    assert r.status == "ERRO" and r.mensagem
    assert scpi.salvas == [] and not _chamadas(scpi, "salvar")
    assert _chamadas(scpi, "descartar")
    (tentativa,) = TentativaEntrada.objects.all()
    assert tentativa.resultado == "ERRO"


def test_a_tela_diferente_do_esperado_da_erro_trava_o_pedido_e_nao_salva(pedido, usuario, scpi):
    r = preparar(pedido, usuario, {1: "10"})
    scpi.tela_mudou[1] = Decimal("55")  # alguém lançou 5 à mão depois da importação
    execucao = _rodar([r.rotulo], scpi)
    r.refresh_from_db()
    assert (
        r.status == "ERRO"
        and "O SCPI mudou: item 1, Já Entrou 55 na tela, esperado 50" in r.mensagem
    )
    assert scpi.salvas == [] and not _chamadas(scpi, "preencher")
    (trava,) = TravaPedido.objects.all()
    assert (trava.pedido, trava.motivo, trava.execucao, trava.recebimento) == (
        pedido,
        "TELA",
        execucao,
        r,
    )
    assert "Já Entrou 55" in trava.detalhe and trava.aberta
    assert TentativaEntrada.objects.get().resultado == "ERRO"
    assert execucao.situacao == "ATENCAO"


# --- depois do clique --------------------------------------------------------------------------


def test_salvou_e_perdeu_a_resposta_vai_a_verificar_e_nao_volta_a_fila(
    pedido, usuario, scpi, journal
):
    r = preparar(pedido, usuario, {1: "10"})
    scpi.salva_e_falha.add(r.rotulo)
    execucao = _rodar([r.rotulo], scpi)
    r.refresh_from_db()
    assert r.status == "VERIFICAR" and r.mensagem.startswith("Resultado incerto:")
    assert len(scpi.salvas) == 1  # o simulado tem a requisição
    assert TentativaEntrada.objects.get().resultado == "VERIFICAR"
    assert _chamadas(scpi, "reiniciar")
    assert [e["evento"] for e in _journal(journal)] == ["em_lancamento", "incerto"]
    assert execucao.situacao == "ATENCAO" and execucao.resumo["verificar"] == 1
    # rodar de novo não relança: o recebimento não está mais preparado
    outra = _rodar([r.rotulo], scpi)
    assert outra.resumo["lancadas"] == 0 and len(scpi.salvas) == 1


def test_processo_que_morre_depois_do_travar_deixa_em_lancamento_com_tentativa_a_verificar(
    pedido, usuario, scpi, monkeypatch
):
    r = preparar(pedido, usuario, {1: "10"})

    def morrer(*args, **kwargs):
        raise KeyboardInterrupt  # não é `Exception`: o processo some entre o `_travar` e o Salvar

    monkeypatch.setattr(lancamento_entradas, "_journal", morrer)
    with pytest.raises(KeyboardInterrupt):
        _rodar([r.rotulo], scpi)
    r.refresh_from_db()
    assert r.status == "EM_LANCAMENTO"
    assert TentativaEntrada.objects.get().resultado == "VERIFICAR"
    assert scpi.salvas == [] and not _chamadas(scpi, "salvar")


def test_recebimento_editado_entre_a_selecao_e_o_travar_e_ignorado(pedido, usuario, scpi):
    r = preparar(pedido, usuario, {1: "10"})
    scpi.ao_preencher = lambda rec: Recebimento.objects.filter(pk=r.pk).update(
        versao=F("versao") + 1
    )
    execucao = _rodar([r.rotulo], scpi)
    r.refresh_from_db()
    assert r.status == "PREPARADO" and scpi.salvas == []
    assert execucao.resumo["ignoradas"] == 1
    assert TentativaEntrada.objects.get().resultado == "IGNORADA"
    assert _chamadas(scpi, "descartar")


def test_banco_que_recusa_o_numero_interrompe_e_o_journal_tem_o_numero(
    pedido, usuario, scpi, journal, monkeypatch
):
    r = preparar(pedido, usuario, {1: "10"})
    original = QuerySet.update

    def quebrar(self, **kwargs):
        if kwargs.get("status") == "LANCADO":
            raise DatabaseError("MySQL server has gone away")
        return original(self, **kwargs)

    monkeypatch.setattr(QuerySet, "update", quebrar)
    execucao = ExecucaoRobo.objects.create(robo="ENTRADAS")
    with pytest.raises(FalhaCritica):
        executar_lancamento_entradas(
            execucao, scpi.abrir, recebimentos=[r.rotulo], extrair=scpi.relatorio_entradas
        )
    execucao.refresh_from_db()
    assert execucao.situacao == "FALHA" and "gone away" in execucao.erro
    r.refresh_from_db()
    assert r.status == "EM_LANCAMENTO"  # travado para conferência
    eventos = _journal(journal)
    assert eventos[-2]["evento"] == "lancada" and eventos[-2]["requisicao"] == "003492/26"
    assert eventos[-1]["evento"] == "falha_banco" and eventos[-1]["execucao"] == execucao.pk


def test_nf_que_a_extracao_de_antes_ja_achou_no_scpi_nao_e_lancada(pedido, usuario, scpi):
    """Alguém lançou a mesma NF à mão por outro item do pedido: o "Já Entrou" do item do
    recebimento não muda e a tela confere, mas a extração de antes já tem a NF."""
    r = preparar(pedido, usuario, {1: "10"})
    manual = scpi.entrada_manual(
        (pedido.ano, pedido.numero), {2: "10"}, data=r.data_recebimento, nf="501"
    )
    execucao = _rodar([r.rotulo], scpi)
    assert execucao.situacao == "ATENCAO"
    assert (execucao.resumo["lancadas"], execucao.resumo["falhas"]) == (0, 1)
    assert execucao.resumo["lotes"][0]["resultado"] == "erro"
    r.refresh_from_db()
    assert r.status == "ERRO" and manual in r.mensagem
    assert [s.requisicao for s in scpi.salvas] == [manual]  # nada salvo pelo robô
    assert not _chamadas(scpi, "abrir_pedido")
    assert TentativaEntrada.objects.get().resultado == "ERRO"


def test_journal_que_falha_antes_do_salvar_interrompe_sem_salvar(
    pedido, usuario, scpi, monkeypatch
):
    r = preparar(pedido, usuario, {1: "10"})

    def sem_disco(*args, **kwargs):
        raise OSError("disco cheio")

    monkeypatch.setattr(lancamento_entradas, "open", sem_disco, raising=False)
    execucao = ExecucaoRobo.objects.create(robo="ENTRADAS")
    with pytest.raises(FalhaCritica):
        executar_lancamento_entradas(
            execucao, scpi.abrir, recebimentos=[r.rotulo], extrair=scpi.relatorio_entradas
        )
    execucao.refresh_from_db()
    assert execucao.situacao == "FALHA" and "disco cheio" in execucao.erro
    assert not scpi.salvas
    r.refresh_from_db()
    assert r.status == "EM_LANCAMENTO"  # travado para conferência
    assert TentativaEntrada.objects.get().resultado == "VERIFICAR"


def test_journal_que_falha_com_o_numero_obtido_grava_no_banco_e_interrompe(
    pedido, usuario, scpi, monkeypatch
):
    um = preparar(pedido, usuario, {1: "10"}, nf="501")
    dois = preparar(pedido, usuario, {1: "5"}, nf="502")
    chamadas = []

    def falha_na_segunda(*args, **kwargs):
        chamadas.append(args)
        if len(chamadas) == 2:  # a primeira é o em_lancamento; a segunda, o número
            raise OSError("disco cheio")
        return open(*args, **kwargs)

    monkeypatch.setattr(lancamento_entradas, "open", falha_na_segunda, raising=False)
    execucao = ExecucaoRobo.objects.create(robo="ENTRADAS")
    with pytest.raises(FalhaCritica):
        executar_lancamento_entradas(
            execucao,
            scpi.abrir,
            recebimentos=[um.rotulo, dois.rotulo],
            extrair=scpi.relatorio_entradas,
        )
    execucao.refresh_from_db()
    assert execucao.situacao == "FALHA"
    um.refresh_from_db()
    dois.refresh_from_db()
    assert (um.status, um.requisicao_scpi) == ("LANCADO", "003492/26")
    assert dois.status == "PREPARADO" and len(scpi.salvas) == 1  # a execução parou


def test_falha_antes_do_salvar_nao_desfaz_o_que_mudou_durante_o_preenchimento(
    pedido, usuario, scpi, monkeypatch
):
    """Enquanto o robô preenche, o recebimento é ligado a uma entrada feita à mão (lançado): a
    falha do preenchimento não o devolve a erro."""
    r = preparar(pedido, usuario, {1: "10"})

    def preencher(rec):
        Recebimento.objects.filter(pk=r.pk).update(
            status="LANCADO", requisicao_scpi="003400/26", versao=F("versao") + 1
        )
        raise RuntimeError("a grade não respondeu")

    monkeypatch.setattr(scpi, "preencher", preencher)
    execucao = _rodar([r.rotulo], scpi)
    assert (execucao.resumo["falhas"], execucao.resumo["ignoradas"]) == (0, 1)
    r.refresh_from_db()
    assert (r.status, r.requisicao_scpi) == ("LANCADO", "003400/26")
    assert TentativaEntrada.objects.get().resultado == "IGNORADA"
    assert not scpi.salvas


def test_banco_que_recusa_o_erro_de_antes_do_salvar_conta_como_falha(
    pedido, usuario, scpi, monkeypatch
):
    """A falha do preenchimento que o banco não deixa gravar não é um recebimento que mudou: a
    execução termina com atenção, e não como se nada tivesse acontecido."""
    r = preparar(pedido, usuario, {1: "10"})
    scpi.falha_antes.add("preencher")
    original = QuerySet.update

    def quebrar(self, **kwargs):
        if kwargs.get("status") == "ERRO":
            raise DatabaseError("MySQL server has gone away")
        return original(self, **kwargs)

    monkeypatch.setattr(QuerySet, "update", quebrar)
    execucao = _rodar([r.rotulo], scpi)
    assert execucao.situacao == "ATENCAO"
    assert (execucao.resumo["falhas"], execucao.resumo["ignoradas"]) == (1, 0)
    assert execucao.resumo["lotes"][0]["resultado"] == "erro"


# --- simulação ---------------------------------------------------------------------------------


def test_simulacao_nao_grava_tentativa_estado_nem_extracao(pedido, usuario, scpi):
    r = preparar(pedido, usuario, {1: "10"})
    execucao = _rodar([r.rotulo], scpi, simulacao=True)
    assert execucao.situacao == "SUCESSO" and execucao.resumo["simuladas"] == 1
    r.refresh_from_db()
    assert (r.status, r.mensagem) == ("PREPARADO", "")
    assert not TentativaEntrada.objects.exists() and not ExtracaoEntradas.objects.exists()
    assert scpi.salvas == [] and not _chamadas(scpi, "salvar") and scpi.relatorios == []
    assert _chamadas(scpi, "simulacao")


def test_a_divergencia_da_tela_numa_simulacao_so_entra_no_resumo(pedido, usuario, scpi):
    r = preparar(pedido, usuario, {1: "10"})
    scpi.tela_mudou[1] = Decimal("55")
    execucao = _rodar([r.rotulo], scpi, simulacao=True)
    r.refresh_from_db()
    assert r.status == "PREPARADO" and not TravaPedido.objects.exists()
    assert not TentativaEntrada.objects.exists()
    (item,) = execucao.resumo["lotes"]
    assert item["resultado"] == "erro" and "O SCPI mudou" in item["mensagem"]


# --- travas ------------------------------------------------------------------------------------


def test_trava_do_lancamento_ocupada_falha_sem_mudar_nada(pedido, usuario, scpi, trava_ocupada):
    r = preparar(pedido, usuario, {1: "10"})
    execucao = ExecucaoRobo.objects.create(robo="ENTRADAS")
    with pytest.raises(LancamentoEmAndamento, match="Outro lançamento"):
        executar_lancamento_entradas(
            execucao, scpi.abrir, recebimentos=[r.rotulo], extrair=scpi.relatorio_entradas
        )
    execucao.refresh_from_db()
    assert (
        execucao.situacao == "FALHA" and execucao.erro == "Outro lançamento já está em andamento."
    )
    r.refresh_from_db()
    assert r.status == "PREPARADO" and scpi.abertas == 0


def test_importacao_de_pedidos_em_andamento_falha_sem_mudar_nada(
    pedido, usuario, scpi, trava_importacao_ocupada
):
    r = preparar(pedido, usuario, {1: "10"})
    trava_importacao_ocupada("PEDIDOS_COMPRA")
    execucao = ExecucaoRobo.objects.create(robo="ENTRADAS")
    with pytest.raises(LancamentoEmAndamento, match="importação de pedidos"):
        executar_lancamento_entradas(
            execucao, scpi.abrir, recebimentos=[r.rotulo], extrair=scpi.relatorio_entradas
        )
    execucao.refresh_from_db()
    assert execucao.erro == "A importação de pedidos está em andamento."
    r.refresh_from_db()
    assert r.status == "PREPARADO" and scpi.abertas == 0


# --- a seleção e o pedido com recebimento em verificação -----------------------------------


def test_segundo_recebimento_do_pedido_com_o_primeiro_em_verificar_e_ignorado(
    pedido, usuario, scpi
):
    primeiro = preparar(pedido, usuario, {1: "10"}, nf="501")
    segundo = preparar(pedido, usuario, {1: "5"}, nf="502")
    Recebimento.objects.filter(pk=primeiro.pk).update(status="VERIFICAR")
    execucao = _rodar([segundo.rotulo], scpi)
    segundo.refresh_from_db()
    assert segundo.status == "PREPARADO" and scpi.salvas == []
    (item,) = execucao.resumo["lotes"]
    assert item["resultado"] == "ignorada" and "em verificação" in item["mensagem"]


@pytest.mark.parametrize(
    ("preparo", "motivo"),
    [
        (
            lambda r, p: Recebimento.objects.filter(pk=r.pk).update(status="CANCELADO"),
            "não preparado",
        ),
        (
            lambda r, p: p.__class__.objects.filter(pk=p.pk).update(exercicio=p.exercicio - 1),
            "outro exercício",
        ),
        (
            lambda r, p: TravaPedido.objects.create(pedido=p, motivo="TELA"),
            "está travado",
        ),
    ],
)
def test_recebimentos_bloqueados_entram_no_resumo_como_ignorados(
    pedido, usuario, scpi, preparo, motivo
):
    r = preparar(pedido, usuario, {1: "10"})
    preparo(r, pedido)
    execucao = _rodar([r.rotulo], scpi)
    (item,) = execucao.resumo["lotes"]
    assert item["resultado"] == "ignorada" and motivo in item["mensagem"]
    assert scpi.abertas == 0 and execucao.resumo["lancadas"] == 0


def test_rotulo_que_nao_existe_ou_invalido_e_ignorado(pedido, usuario, scpi):
    execucao = _rodar(["RC-9999", "X-1"], scpi)
    motivos = {i["lote"]: i["mensagem"] for i in execucao.resumo["lotes"]}
    assert "não existe" in motivos["RC-9999"] and "inválido" in motivos["X-1"]


# --- as extrações -----------------------------------------------------------------------------


def test_extracao_de_antes_que_falha_deixa_tudo_como_estava(pedido, usuario, scpi):
    from scpi.leitura import ErroImportacao

    r = preparar(pedido, usuario, {1: "10"})
    scpi.falhas_relatorio = 3  # as três tentativas
    execucao = ExecucaoRobo.objects.create(robo="ENTRADAS")
    with pytest.raises(ErroImportacao, match="3 tentativas"):
        executar_lancamento_entradas(
            execucao, scpi.abrir, recebimentos=[r.rotulo], extrair=scpi.relatorio_entradas
        )
    execucao.refresh_from_db()
    assert execucao.situacao == "FALHA"
    r.refresh_from_db()
    assert r.status == "PREPARADO" and scpi.abertas == 0
    assert not TentativaEntrada.objects.exists()


def test_extracao_de_antes_que_falha_uma_vez_e_tentada_de_novo(pedido, usuario, scpi):
    r = preparar(pedido, usuario, {1: "10"})
    scpi.falhas_relatorio = 1
    execucao = _rodar([r.rotulo], scpi)
    assert execucao.situacao == "SUCESSO" and execucao.resumo["lancadas"] == 1


def test_extracao_de_depois_que_falha_nao_piora_a_execucao(pedido, usuario, scpi):
    r = preparar(pedido, usuario, {1: "10"})
    chamadas = []

    def extrair(de, ate):
        chamadas.append((de, ate))
        if len(chamadas) == 1:
            return scpi.relatorio_entradas(de, ate)  # a de antes funciona
        raise RuntimeError("SCPI fora do ar")

    execucao = _rodar([r.rotulo], scpi, extrair=extrair)
    assert execucao.situacao == "SUCESSO" and execucao.resumo["lancadas"] == 1
    r.refresh_from_db()
    assert r.status == "LANCADO"
    assert "extração de depois falhou" in execucao.log


def test_o_periodo_da_extracao_cobre_o_dia_anterior_ate_amanha(pedido, usuario, scpi):
    from datetime import timedelta

    from django.utils import timezone

    r = preparar(pedido, usuario, {1: "10"})
    _rodar([r.rotulo], scpi)
    hoje = timezone.localdate()
    assert scpi.relatorios[0] == (hoje - timedelta(days=1), hoje + timedelta(days=1))


def test_a_tela_e_conferida_antes_do_preencher(pedido, usuario, scpi):
    r = preparar(pedido, usuario, {1: "10"})
    _rodar([r.rotulo], scpi)
    ordem = [c[0] for c in scpi.chamadas]
    assert ordem.index("abrir_pedido") < ordem.index("preencher") < ordem.index("salvar")


def test_o_esperado_da_tela_vem_do_recebimento_com_o_lancado_ainda_nao_refletido(pedido, usuario):
    from compras import robo

    um = preparar(pedido, usuario, {1: "10"}, nf="501")
    Recebimento.objects.filter(pk=um.pk).update(
        status="LANCADO", requisicao_scpi="003492/26", visivel_desde=None
    )
    dois = preparar(pedido, usuario, {1: "5"}, nf="502")
    rec = robo.para_lancar(dois)
    (esperado,) = rec.esperado
    # o lançado sem `visivel_desde` conta (lado seguro): 50 + 10 já entraram, saldo 40
    assert (esperado.ja_entrou, esperado.saldo, esperado.quantidade) == (60, 40, 5)
    assert isinstance(rec, regras.RecebimentoParaLancar) and rec.nf == "502"
    assert rec.observacoes == f"Central Almoxarifado {dois.rotulo}"


# --- o comando e o disparo -------------------------------------------------------------------


@pytest.fixture
def comando(monkeypatch, scpi):
    """O comando com o SCPI simulado no lugar do navegador e do relatório."""
    from scpi.management.commands import lancar_entradas

    monkeypatch.setattr(lancar_entradas, "navegador", scpi.abrir)
    monkeypatch.setattr(lancar_entradas, "baixar_entradas", scpi.relatorio_entradas)


def test_comando_sem_recebimento_e_recusado():
    from django.core.management import CommandError, call_command

    with pytest.raises(CommandError, match="--recebimento"):
        call_command("lancar_entradas")


def test_comando_lanca_de_verdade_com_o_lancamento_real_liberado(pedido, usuario, scpi, comando):
    from django.core.management import call_command

    r = preparar(pedido, usuario, {1: "10"})
    call_command("lancar_entradas", recebimento=[r.rotulo])
    r.refresh_from_db()
    assert r.status == "LANCADO"
    execucao = ExecucaoRobo.objects.get()
    assert execucao.robo == "ENTRADAS" and not execucao.simulacao


def test_comando_dry_run_simula(pedido, usuario, scpi, comando, capsys):
    from django.core.management import call_command

    r = preparar(pedido, usuario, {1: "10"})
    call_command("lancar_entradas", dry_run=True, recebimento=[r.rotulo])
    r.refresh_from_db()
    assert r.status == "PREPARADO" and scpi.salvas == []
    assert ExecucaoRobo.objects.get().simulacao is True
    assert "simulados: 1" in capsys.readouterr().out


def test_lancamento_real_bloqueado_recusa_antes_de_criar_a_execucao(
    pedido, usuario, scpi, comando, settings
):
    from django.core.management import CommandError, call_command

    settings.LANCAMENTO_REAL = False
    r = preparar(pedido, usuario, {1: "10"})
    with pytest.raises(CommandError, match="bloqueado"):
        call_command("lancar_entradas", recebimento=[r.rotulo])
    assert not ExecucaoRobo.objects.exists() and scpi.abertas == 0
    # a simulação segue mesmo bloqueado
    call_command("lancar_entradas", dry_run=True, recebimento=[r.rotulo])
    assert ExecucaoRobo.objects.get().simulacao


def test_lancamento_real_bloqueado_com_execucao_do_botao_termina_em_falha(
    pedido, usuario, scpi, comando, settings
):
    from django.core.management import CommandError, call_command

    settings.LANCAMENTO_REAL = False
    r = preparar(pedido, usuario, {1: "10"})
    execucao = ExecucaoRobo.objects.create(robo="ENTRADAS")
    with pytest.raises(CommandError, match="bloqueado"):
        call_command("lancar_entradas", execucao=execucao.pk, recebimento=[r.rotulo])
    execucao.refresh_from_db()
    assert execucao.situacao == "FALHA" and "bloqueado" in execucao.erro


def test_comando_com_pendencia_sai_com_erro(pedido, usuario, scpi, comando):
    from django.core.management import CommandError, call_command

    r = preparar(pedido, usuario, {1: "10"})
    scpi.falha_antes.add("abrir")
    with pytest.raises(CommandError, match="erros ou recebimentos a verificar"):
        call_command("lancar_entradas", recebimento=[r.rotulo])


def test_a_importacao_de_pedidos_recusa_com_lancamento_de_entradas_em_andamento():
    from django.core.management import CommandError, call_command

    ExecucaoRobo.objects.create(robo="ENTRADAS")  # recém-criada e sem fim: em andamento
    with pytest.raises(CommandError, match="lançamento de entradas está em andamento"):
        call_command("importar_pedidos_compra", arquivo="/inexistente.csv")


def test_a_importacao_de_pedidos_nao_recusa_com_o_robo_de_saidas_rodando(tmp_path):
    from django.core.management import CommandError, call_command

    ExecucaoRobo.objects.create(robo="SAIDAS")
    with pytest.raises(CommandError) as erro:
        call_command("importar_pedidos_compra", arquivo=str(tmp_path / "nao-existe.csv"))
    assert "lançamento de entradas" not in str(erro.value)


def test_disparo_cria_a_execucao_de_entradas_e_inicia_o_comando(
    pedido, usuario, monkeypatch, settings, tmp_path
):
    from scpi import disparo

    settings.LOG_DIR = tmp_path
    iniciados = []
    monkeypatch.setattr(
        disparo, "_iniciar_comando", lambda args, log, titulo: iniciados.append((args, log))
    )
    execucao = disparo.iniciar_lancamento_entradas(
        usuario, simulacao=True, recebimentos=["RC-0001", "RC-0002"]
    )
    assert (execucao.robo, execucao.simulacao, execucao.iniciada_por) == ("ENTRADAS", True, usuario)
    ((argumentos, log),) = iniciados
    assert argumentos == [
        "lancar_entradas",
        "--execucao",
        str(execucao.pk),
        "--dry-run",
        "--recebimento",
        "RC-0001",
        "--recebimento",
        "RC-0002",
    ]
    assert log == "lancar_entradas.log"


def test_disparo_recusa_com_qualquer_robo_rodando_e_sem_permissao(usuario, monkeypatch):
    from django.core.exceptions import PermissionDenied

    from scpi import disparo
    from tests.papeis import usuario_com

    monkeypatch.setattr(disparo, "_iniciar_comando", lambda *a: pytest.fail("não deveria iniciar"))
    ExecucaoRobo.objects.create(robo="SAIDAS")
    assert (
        disparo.iniciar_lancamento_entradas(usuario, simulacao=False, recebimentos=["RC-1"]) is None
    )
    with pytest.raises(PermissionDenied):
        disparo.iniciar_lancamento_entradas(
            usuario_com(username="40001"), simulacao=False, recebimentos=["RC-1"]
        )


def test_disparo_que_nao_inicia_o_processo_deixa_a_execucao_em_falha(usuario, monkeypatch):
    from scpi import disparo

    def quebrar(*args):
        raise OSError("sem processo")

    monkeypatch.setattr(disparo, "_iniciar_comando", quebrar)
    with pytest.raises(OSError):
        disparo.iniciar_lancamento_entradas(usuario, simulacao=False, recebimentos=["RC-1"])
    execucao = ExecucaoRobo.objects.get()
    assert execucao.situacao == "FALHA" and execucao.erro == "sem processo"
