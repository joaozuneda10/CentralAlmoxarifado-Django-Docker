"""Leitura da "Relação de Requisições" de Entrada (`ler_entradas`): pura, tudo ou nada."""

from datetime import date
from decimal import Decimal

import pytest

from compras import regras
from conciliacao.regras import lote_observado
from scpi.leitura import ErroImportacao, ler_entradas
from tests.relacao_entradas import COLUNAS, EntradaCSV, ItemEntradaCSV, csv_entradas

DATA = date(2026, 11, 10)


def _entrada(numero="003492/26", id_requi=9001, **campos):
    return EntradaCSV(numero, id_requi, DATA, **campos)


def test_le_uma_entrada_com_pedido_nf_e_itens():
    conteudo = csv_entradas(
        [
            _entrada(
                itens=[
                    ItemEntradaCSV("006.011.020", "10", "UN"),
                    ItemEntradaCSV("023.003.004", "1,5", "KG"),
                ],
                observacoes="Central Almoxarifado RC-0042",
            )
        ]
    )
    leitura = ler_entradas(conteudo)
    (e,) = leitura.linhas
    assert (e.requisicao, e.ano, e.numero, e.id_requi) == ("003492/26", 2026, 3492, 9001)
    assert (e.data_entrada, e.data_requisicao) == (DATA, DATA)
    assert (e.fornecedor_codigo, e.nf, e.pedido_ano, e.pedido_numero) == ("19502", "501", 2026, 514)
    assert (e.com_saida, e.tipo, e.responsavel) == (False, "ENTRADA", "USUARIO DO ROBO")
    assert [(i.codigo, i.quantidade, i.unidade) for i in e.itens] == [
        ("006.011.020", Decimal("10"), "UN"),
        ("023.003.004", Decimal("1.5"), "KG"),
    ]
    assert regras.recebimento_observado(e.observacoes) == "RC-0042"


def test_entrada_sem_pedido_e_sem_nf_e_permitida():
    (e,) = ler_entradas(csv_entradas([_entrada(pedido="", nf="")])).linhas
    assert (e.pedido_ano, e.pedido_numero, e.nf) == (None, None, "")


def test_a_nf_perde_os_zeros_e_o_que_nao_e_numero_fica_como_veio():
    entradas = ler_entradas(
        csv_entradas(
            [
                _entrada("003492/26", 1, nf="000000000501"),
                _entrada("003493/26", 2, nf="0000"),
                _entrada("003494/26", 3, nf="S/N"),
            ]
        )
    ).linhas
    assert [e.nf for e in entradas] == ["501", "", "S/N"]


def test_saida_s_e_lida():
    (e,) = ler_entradas(csv_entradas([_entrada(saida=True)])).linhas
    assert e.com_saida is True


def test_uma_requisicao_por_numero_com_varios_itens():
    conteudo = csv_entradas(
        [
            _entrada(
                "003492/26", 1, itens=[ItemEntradaCSV("006.011.020"), ItemEntradaCSV("023.003.004")]
            ),
            _entrada("003493/26", 2),
        ]
    )
    um, dois = ler_entradas(conteudo).linhas
    assert (um.numero, len(um.itens)) == (3492, 2) and (dois.numero, len(dois.itens)) == (3493, 1)


def test_a_marca_do_recebimento_e_lida_e_a_das_saidas_nao_confunde():
    (e,) = ler_entradas(csv_entradas([_entrada(observacoes="Central Almoxarifado RC-0042")])).linhas
    assert regras.recebimento_observado(e.observacoes) == "RC-0042"
    assert lote_observado(e.observacoes) == ""  # o `RC-` não é lido como lote de saída


def test_registro_quebrado_nas_observacoes_e_recolado():
    conteudo = csv_entradas(
        [_entrada(observacoes="Central Almoxarifado RC-0042\nObs.: portaria, volume 3")]
    )
    (e,) = ler_entradas(conteudo).linhas
    assert regras.recebimento_observado(e.observacoes) == "RC-0042"
    assert "portaria" in e.observacoes and e.nf == "501"


def test_cabecalho_que_varia_dentro_da_requisicao_e_erro():
    um = csv_entradas(
        [_entrada(itens=[ItemEntradaCSV("006.011.020"), ItemEntradaCSV("023.003.004")])]
    )
    texto = um.decode("utf-8-sig").split("\r\n")
    texto[2] = texto[2].replace("000000000501", "000000000777")  # outro DOCUM na 2ª linha
    with pytest.raises(ErroImportacao, match="DOCUM"):
        ler_entradas("\r\n".join(texto).encode("utf-8-sig"))


def test_relatorio_cortado_e_erro():
    texto = csv_entradas([_entrada()]).decode("utf-8-sig").rstrip("\r\n")
    cortado = texto.rsplit(";", 12)[0]  # perde os últimos campos da última linha
    with pytest.raises(ErroImportacao):
        ler_entradas(cortado.encode("utf-8-sig"))


def test_requi_invalido_e_erro():
    with pytest.raises(ErroImportacao, match="número de requisição inválido"):
        ler_entradas(csv_entradas([_entrada("3492/26")]))


def test_pedido_invalido_e_erro():
    with pytest.raises(ErroImportacao, match="número de pedido inválido"):
        ler_entradas(csv_entradas([_entrada(pedido="514-26")]))


def test_quan1_zero_e_lida_como_dado_do_scpi():
    (e,) = ler_entradas(csv_entradas([_entrada(itens=[ItemEntradaCSV("005.000.001", "0")])])).linhas
    assert e.itens[0].quantidade == 0


@pytest.mark.parametrize("quantidade", ["", "abc", "-1", "0,1234567"])
def test_quan1_ilegivel_negativa_ou_longa_e_erro(quantidade):
    with pytest.raises(ErroImportacao, match="quantidade"):
        ler_entradas(csv_entradas([_entrada(itens=[ItemEntradaCSV("006.011.020", quantidade)])]))


def test_quantidade_com_5_casas_e_lida():
    (e,) = ler_entradas(
        csv_entradas([_entrada(itens=[ItemEntradaCSV("006.011.020", "1,66651")])])
    ).linhas
    assert e.itens[0].quantidade == Decimal("1.66651")


def test_coluna_obrigatoria_faltando_e_erro():
    texto = csv_entradas([_entrada()]).decode("utf-8-sig").replace("QUAN1", "OUTRA", 1)
    with pytest.raises(ErroImportacao, match="QUAN1"):
        ler_entradas(texto.encode("utf-8-sig"))


def test_csv_sem_entradas_e_erro():
    with pytest.raises(ErroImportacao, match="nenhuma entrada"):
        ler_entradas(csv_entradas([]))


def test_o_gerador_segue_o_formato_real():
    assert len(COLUNAS) == 65
    conteudo = csv_entradas([_entrada()])
    assert conteudo.startswith(b"\xef\xbb\xbfGRUPO;GRUPO_1;") and b"\r\n" in conteudo
    cabecalho = conteudo.decode("utf-8-sig").split("\r\n")[0].split(";")
    assert cabecalho[-1] == "" and len(cabecalho) == 66  # 65 colunas e o ";" final


def test_a_marca_na_observacao_do_item_e_lida_e_junta_com_a_do_cabecalho():
    itens = [
        ItemEntradaCSV("006.011.020", obs="Central Almoxarifado RC-0042"),
        ItemEntradaCSV("023.003.004", obs="Central Almoxarifado RC-0042"),
    ]
    (e,) = ler_entradas(
        csv_entradas([_entrada(itens=itens, observacoes="Recebido na portaria")])
    ).linhas
    assert regras.recebimento_observado(e.observacoes) == "RC-0042"
    assert e.observacoes.count("RC-0042") == 1  # a observação repetida nos itens entra uma vez
    assert "Recebido na portaria" in e.observacoes


def test_sem_observacao_de_item_continua_lendo_a_do_cabecalho():
    (e,) = ler_entradas(csv_entradas([_entrada(observacoes="Central Almoxarifado RC-0042")])).linhas
    assert regras.recebimento_observado(e.observacoes) == "RC-0042"


def test_registro_colado_ao_anterior_recusa_a_leitura():
    """Sem o começo que separa os registros (GRUPO vazio), a recolagem junta a segunda requisição
    à primeira: campos a mais que o cabeçalho, e a leitura inteira é recusada (tudo ou nada)."""
    conteudo = csv_entradas([_entrada(), _entrada("003493/26", 9002)]).decode("utf-8-sig")
    linhas = conteudo.split("\r\n")
    posicao = next(i for i, linha in enumerate(linhas) if ";003493/26;" in linha)
    linhas[posicao] = ";" + linhas[posicao].split(";", 1)[1]
    with pytest.raises(ErroImportacao, match="campos"):
        ler_entradas("\r\n".join(linhas).encode("utf-8-sig"))
