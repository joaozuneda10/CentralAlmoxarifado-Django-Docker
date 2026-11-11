"""Leitura do 07.13 (`scpi.leitura.ler_pedidos_compra`): pura, tudo ou nada."""

from datetime import date
from decimal import Decimal

import pytest

from scpi.leitura import ErroImportacao, ler_pedidos_compra
from tests.relacao_pedidos_compra import COLUNAS, ItemPedidoCSV, csv_pedidos

P = "00514/26"


def _item(item=1, codigo="006.011.020", **campos):
    return ItemPedidoCSV(P, item, codigo, **campos)


def test_le_item_de_quantidade_e_item_de_valor():
    conteudo = csv_pedidos(
        [
            _item(1, quantidade="100", ja_entrou="30", anulado="10", pedida="5", preco="8,9948"),
            _item(2, "023.003.004", controle="T", quantidade="1361,32", saldo="900", unidade="SV"),
        ]
    )
    um, dois = ler_pedidos_compra(conteudo).linhas
    assert (um.ano, um.numero, um.data) == (2026, 514, date(2026, 3, 2))
    assert (um.fornecedor_codigo, um.fornecedor_nome) == ("19502", "FORNECEDOR SINTÉTICO LTDA")
    assert (um.item, um.codigo, um.unidade, um.controle) == (1, "006.011.020", "UN", "Q")
    assert (um.quantidade, um.anulado, um.ja_entrou, um.pedida, um.saldo, um.preco) == (
        Decimal("100"),
        Decimal("10"),
        Decimal("30"),
        Decimal("5"),
        Decimal("55"),
        Decimal("8.9948"),
    )
    # No item de valor o QTDFALTA é lido como veio, sem a conta das quantidades.
    assert (dois.controle, dois.quantidade, dois.saldo) == ("T", Decimal("1361.32"), Decimal("900"))


def test_qtdfalta_diferente_da_conta_num_item_q_e_erro():
    conteudo = csv_pedidos([_item(quantidade="100", ja_entrou="30", saldo="71")])
    with pytest.raises(ErroImportacao, match="QTDFALTA"):
        ler_pedidos_compra(conteudo)


def test_relatorio_cortado_e_erro():
    conteudo = csv_pedidos([_item(1), _item(2, "023.003.004")])
    texto = conteudo.decode("utf-8-sig").rstrip("\r\n").rsplit(";", 70)[0]
    with pytest.raises(ErroImportacao, match="cortado"):
        ler_pedidos_compra(texto.encode("utf-8-sig"))


def test_registro_quebrado_em_duas_linhas_e_recolado():
    conteudo = csv_pedidos([_item(1), _item(2, "023.003.004")], quebrar_registro=True)
    assert [linha.item for linha in ler_pedidos_compra(conteudo).linhas] == [1, 2]


def test_item_repetido_no_mesmo_pedido_e_erro():
    with pytest.raises(ErroImportacao, match="repetido"):
        ler_pedidos_compra(csv_pedidos([_item(1), _item(1, "023.003.004")]))


@pytest.mark.parametrize("numped", ["514/26", "003588/26", "00514-26", ""])
def test_numped_fora_do_formato_e_erro(numped):
    conteudo = csv_pedidos([ItemPedidoCSV(numped, 1, "006.011.020")])
    with pytest.raises(ErroImportacao, match="pedido"):
        ler_pedidos_compra(conteudo)


def test_dois_fornecedores_no_mesmo_pedido_e_erro():
    conteudo = csv_pedidos([_item(1), _item(2, "023.003.004", fornecedor="777")])
    with pytest.raises(ErroImportacao, match="fornecedor"):
        ler_pedidos_compra(conteudo)


def test_data_diferente_no_mesmo_pedido_e_erro():
    conteudo = csv_pedidos([_item(1), _item(2, "023.003.004", data=date(2026, 3, 9))])
    with pytest.raises(ErroImportacao, match="data ou nome"):
        ler_pedidos_compra(conteudo)


def test_nome_diferente_no_mesmo_fornecedor_e_erro():
    conteudo = csv_pedidos([_item(1), _item(2, "023.003.004", nome="OUTRO NOME")])
    with pytest.raises(ErroImportacao, match="data ou nome"):
        ler_pedidos_compra(conteudo)


@pytest.mark.parametrize(
    ("campos", "coluna"),
    [({"fornecedor": ""}, "CODIF"), ({"codigo": ""}, "CADPRO"), ({"codigo": "  "}, "CADPRO")],
)
def test_codigo_obrigatorio_vazio_e_erro(campos, coluna):
    codigo = campos.pop("codigo", "006.011.020")
    with pytest.raises(ErroImportacao, match=f"{coluna} vazio"):
        ler_pedidos_compra(csv_pedidos([_item(codigo=codigo, **campos)]))


def test_controle_desconhecido_e_erro():
    with pytest.raises(ErroImportacao, match="TPCONTROLE_SALDO"):
        ler_pedidos_compra(csv_pedidos([_item(controle="X")]))


def test_coluna_obrigatoria_faltando_e_erro():
    texto = csv_pedidos([_item()]).decode("utf-8-sig").replace("QTDPEDIDA", "OUTRA")
    with pytest.raises(ErroImportacao, match="QTDPEDIDA"):
        ler_pedidos_compra(texto.encode("utf-8-sig"))


def test_csv_sem_itens_e_erro():
    with pytest.raises(ErroImportacao, match="nenhum item"):
        ler_pedidos_compra(csv_pedidos([]))


def test_quantidade_com_quatro_casas_e_lida_sem_perda():
    (linha,) = ler_pedidos_compra(csv_pedidos([_item(quantidade="10,1234")])).linhas
    assert linha.quantidade == Decimal("10.1234") and linha.saldo == Decimal("10.1234")


def test_quantidade_com_cinco_casas_e_erro():
    with pytest.raises(ErroImportacao, match="quantidade"):
        ler_pedidos_compra(csv_pedidos([_item(quantidade="10,12345", saldo="10,12345")]))


def test_o_gerador_segue_o_formato_real():
    assert len(COLUNAS) == 79
    conteudo = csv_pedidos([_item()])
    assert conteudo.startswith(b"\xef\xbb\xbfGRUPO;GRUPO_1;")
    assert b"\r\n" in conteudo
