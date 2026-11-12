"""O registro oficial das entradas (`compras.extracao`) e o comando `conciliar_entradas` (PR 3)."""

import gzip
import hashlib
from datetime import date, timedelta

import pytest
from django.core.management import CommandError, call_command
from django.db import IntegrityError, transaction
from django.utils import timezone

from automacoes.historico import linha_de_importacao
from catalogo.models import Importacao
from compras.extracao import extrair
from compras.models import (
    ExtracaoEntradas,
    ItemEntradaOficial,
    Recebimento,
    RequisicaoEntradaOficial,
)
from pedidos.models import ExecucaoRobo
from scpi.execucao import ImportacaoEmAndamento
from scpi.leitura import NadaAExibir
from tests.compras_cenario import pedido_padrao, preparar, usuario_recebedor
from tests.relacao_entradas import EntradaCSV, ItemEntradaCSV, csv_entradas

pytestmark = pytest.mark.django_db

DIA = date(2026, 10, 23)
PERIODO = (date(2026, 10, 22), date(2026, 10, 24))


def _csv(*numeros, **campos):
    return csv_entradas([EntradaCSV(f"{n:06d}/26", n + 100, DIA, **campos) for n in numeros])


def _extrair(conteudo, motivo=ExtracaoEntradas.Motivo.MANUAL, **opcoes):
    return extrair(motivo, PERIODO, lambda: conteudo, **opcoes)


def test_sucesso_guarda_bruto_impressao_e_requisicoes():
    conteudo = _csv(
        3492,
        3494,
        observacoes="Central Almoxarifado RC-0042",
        itens=[ItemEntradaCSV("006.011.020", "2"), ItemEntradaCSV("023.003.004", "1")],
    )
    extracao = _extrair(conteudo)
    extracao.refresh_from_db()
    imp = extracao.importacao
    assert (imp.tipo, imp.situacao, imp.linhas) == ("ENTRADAS", "SUCESSO", 2)
    assert (imp.periodo_de, imp.periodo_ate) == PERIODO
    assert gzip.decompress(bytes(extracao.arquivo)) == conteudo
    assert extracao.impressao == hashlib.sha256(conteudo).hexdigest()
    assert (extracao.requisicoes, extracao.maior_requisicao) == (2, "003494/26")
    req = RequisicaoEntradaOficial.objects.get(extracao=extracao, requisicao="003492/26")
    assert (req.ano, req.numero, req.id_requi, req.recebimento_observado) == (
        2026,
        3492,
        3592,
        "RC-0042",
    )
    assert (req.fornecedor_codigo, req.nf, req.pedido_ano, req.pedido_numero) == (
        "19502",
        "501",
        2026,
        514,
    )
    assert (req.data_entrada, req.data_requisicao, req.com_saida) == (DIA, DIA, False)
    assert list(req.itens.values_list("ordem", "codigo")) == [
        (1, "006.011.020"),
        (2, "023.003.004"),
    ]


def test_a_falha_nao_grava_requisicoes_e_deixa_o_maior_nulo():
    texto = _csv(3492, 3493).decode("utf-8-sig").rstrip("\r\n")
    cortado = texto[: texto.rindex("ENTRADA")].encode("utf-8-sig")
    extracao = _extrair(cortado)
    extracao.refresh_from_db()
    assert extracao.importacao.situacao == "FALHA" and not extracao.bem_sucedida
    assert (extracao.requisicoes, extracao.maior_requisicao) == (0, None)
    assert not RequisicaoEntradaOficial.objects.exists() and not ItemEntradaOficial.objects.exists()
    assert gzip.decompress(bytes(extracao.arquivo)) == cortado


def test_falha_no_download_registra_a_extracao_sem_bruto():
    def baixar():
        raise RuntimeError("SCPI fora do ar")

    extracao = extrair(ExtracaoEntradas.Motivo.MANUAL, PERIODO, baixar)
    extracao.refresh_from_db()
    assert extracao.importacao.erro == "Falha inesperada: SCPI fora do ar"
    assert (extracao.impressao, extracao.arquivo, extracao.maior_requisicao) == ("", None, None)


def test_nada_a_exibir_sem_recebimento_lancado_no_periodo_e_extracao_vazia():
    def nada():
        raise NadaAExibir("Entradas do SCPI: nada a exibir.")

    extracao = extrair(ExtracaoEntradas.Motivo.MANUAL, PERIODO, nada)
    assert extracao.bem_sucedida
    assert (extracao.requisicoes, extracao.maior_requisicao) == (0, None)


def test_nada_a_exibir_com_recebimento_lancado_no_periodo_e_falha():
    pedido = pedido_padrao()
    recebimento = preparar(pedido, usuario_recebedor(), {1: "5"})
    Recebimento.objects.filter(pk=recebimento.pk).update(
        status="LANCADO", requisicao_scpi="003492/26", data_recebimento=DIA
    )

    def nada():
        raise NadaAExibir("Entradas do SCPI: nada a exibir.")

    extracao = extrair(ExtracaoEntradas.Motivo.MANUAL, PERIODO, nada)
    assert not extracao.bem_sucedida
    assert "há recebimentos lançados nesse período" in extracao.importacao.erro


def test_bytes_vazios_sem_o_aviso_do_scpi_sao_falha():
    extracao = _extrair(b"")
    assert not extracao.bem_sucedida and "arquivo veio vazio" in extracao.importacao.erro


def test_mesma_impressao_aponta_para_a_extracao_que_guarda_o_bruto():
    conteudo = _csv(3492)
    origem = _extrair(conteudo)
    repetida = _extrair(conteudo)
    repetida.refresh_from_db()
    assert repetida.arquivo is None and repetida.mesmo_arquivo_que == origem
    assert repetida.requisicoes == 1  # as requisições são lidas de novo, uma foto por extração


def test_mesma_impressao_de_uma_origem_sem_bytes_guarda_o_seu():
    conteudo = _csv(3492)
    origem = _extrair(conteudo)
    ExtracaoEntradas.objects.filter(pk=origem.pk).update(
        arquivo=None, arquivo_apagado_em=timezone.now()
    )
    nova = _extrair(conteudo)
    nova.refresh_from_db()
    assert gzip.decompress(bytes(nova.arquivo)) == conteudo and nova.mesmo_arquivo_que is None


def test_trava_ocupada_nao_cria_registro(trava_importacao_ocupada):
    trava_importacao_ocupada("ENTRADAS")
    with pytest.raises(ImportacaoEmAndamento):
        _extrair(_csv(3492))
    assert not Importacao.objects.exists() and not ExtracaoEntradas.objects.exists()


@pytest.mark.parametrize("motivo", ["ANTES", "DEPOIS"])
def test_antes_e_depois_sem_execucao_sao_recusados(motivo):
    with pytest.raises(ValueError, match="sem a execução"):
        _extrair(_csv(3492), motivo)
    assert not Importacao.objects.exists()


def test_banco_recusa_extracao_de_antes_sem_execucao():
    imp = Importacao.objects.create(tipo="ENTRADAS")
    with pytest.raises(IntegrityError), transaction.atomic():
        ExtracaoEntradas.objects.create(importacao=imp, motivo="ANTES")


def test_extracao_ligada_a_execucao_do_robo():
    execucao = ExecucaoRobo.objects.create()
    extracao = _extrair(_csv(3492), ExtracaoEntradas.Motivo.ANTES, execucao=execucao)
    assert (extracao.motivo, extracao.execucao) == ("ANTES", execucao)


def test_data_de_entrada_fora_do_periodo_faz_a_extracao_falhar():
    conteudo = csv_entradas([EntradaCSV("003492/26", 1, date(2026, 10, 25))])
    extracao = _extrair(conteudo)
    extracao.refresh_from_db()
    assert not extracao.bem_sucedida
    assert "fora do período 22/10/2026 a 24/10/2026" in extracao.importacao.erro
    assert not RequisicaoEntradaOficial.objects.exists()


def test_data_de_entrada_nas_pontas_do_periodo_vale():
    for numero, dia in ((3492, date(2026, 10, 22)), (3493, date(2026, 10, 24))):
        extracao = _extrair(csv_entradas([EntradaCSV(f"{numero:06d}/26", numero, dia)]))
        assert extracao.bem_sucedida


def test_o_historico_mostra_o_periodo_da_extracao():
    extracao = _extrair(_csv(3492))
    linha = linha_de_importacao(extracao.importacao, set())
    assert linha.robo == "Entradas do SCPI" and linha.modo == "Período 22/10 a 24/10"


# --- o comando ------------------------------------------------------------------------------


def _arquivo(tmp_path, conteudo):
    arquivo = tmp_path / "entradas.csv"
    arquivo.write_bytes(conteudo)
    return str(arquivo)


def test_comando_com_arquivo_extrai_com_o_periodo_do_arquivo(tmp_path, capsys):
    call_command("conciliar_entradas", arquivo=_arquivo(tmp_path, _csv(3492, 3493)))
    assert "23/10/2026 a 23/10/2026): 2 requisições, a maior 003493/26" in capsys.readouterr().out
    assert ExtracaoEntradas.objects.get().motivo == "ARQUIVO"


def test_comando_com_periodo_informado(tmp_path, capsys):
    call_command(
        "conciliar_entradas",
        arquivo=_arquivo(tmp_path, _csv(3492)),
        desde="22/10/2026",
        ate="24/10/2026",
    )
    assert "22/10/2026 a 24/10/2026" in capsys.readouterr().out


def test_comando_diaria_e_manual_escolhem_o_motivo(tmp_path, monkeypatch):
    from scpi import relatorios

    monkeypatch.setattr(relatorios, "baixar_entradas", lambda de, ate: _csv(3492))
    hoje = timezone.localdate()
    csv = csv_entradas([EntradaCSV("003492/26", 1, hoje)])
    monkeypatch.setattr(relatorios, "baixar_entradas", lambda de, ate: csv)
    call_command("conciliar_entradas", diaria=True)
    call_command("conciliar_entradas")
    assert list(ExtracaoEntradas.objects.order_by("pk").values_list("motivo", flat=True)) == [
        "DIARIA",
        "MANUAL",
    ]


def test_comando_com_falha_sai_com_erro(tmp_path):
    with pytest.raises(CommandError, match="nenhuma entrada"):
        call_command(
            "conciliar_entradas",
            arquivo=_arquivo(tmp_path, csv_entradas([])),
            desde="22/10/2026",
            ate="24/10/2026",
        )


def test_comando_recusa_so_uma_das_datas():
    with pytest.raises(CommandError, match="--desde e --ate juntos"):
        call_command("conciliar_entradas", desde="22/10/2026")


def test_comando_recusa_periodo_invertido():
    with pytest.raises(CommandError, match="depois do fim"):
        call_command("conciliar_entradas", desde="24/10/2026", ate="22/10/2026")


def test_comando_recusa_com_lancamento_em_andamento():
    ExecucaoRobo.objects.create()  # sem fim e recém-criada: em andamento
    with pytest.raises(CommandError, match="lançamento ou importação em andamento"):
        call_command("conciliar_entradas", desde="22/10/2026", ate="24/10/2026")


def test_comando_recusa_com_importacao_em_andamento(trava_importacao_ocupada):
    trava_importacao_ocupada("PEDIDOS_COMPRA")
    Importacao.objects.create(tipo="PEDIDOS_COMPRA")
    with pytest.raises(CommandError, match="lançamento ou importação em andamento"):
        call_command("conciliar_entradas", desde="22/10/2026", ate="24/10/2026")


def test_periodo_padrao_volta_9_dias_e_cobre_lancados_recentes_e_em_verificacao():
    from compras.management.commands.conciliar_entradas import periodo_padrao

    agora = timezone.now()
    hoje = timezone.localtime(agora).date()
    assert periodo_padrao(agora) == (hoje - timedelta(days=10), hoje + timedelta(days=1))

    pedido = pedido_padrao()
    r = preparar(pedido, usuario_recebedor(), {1: "5"})
    antigo = hoje - timedelta(days=30)
    Recebimento.objects.filter(pk=r.pk).update(
        status="VERIFICAR", data_recebimento=antigo, chave_nf="19502:501"
    )
    assert periodo_padrao(agora)[0] == antigo - timedelta(days=1)
