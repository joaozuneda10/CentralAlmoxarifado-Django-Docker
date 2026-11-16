"""O lançador de entradas só se exercita no SCPI real: aqui, a estrutura e a leitura pura."""

import ast
from pathlib import Path

import pytest

from compras.regras import TelaItens
from scpi import lancador_entradas
from scpi.lancamento_entradas import SCPIEntradas
from scpi.requisicoes import ErroSCPI


def test_navegador_implementa_o_protocolo_das_entradas():
    for metodo in (
        "abrir_pedido",
        "preencher",
        "salvar",
        "depois_de_salvar",
        "encerrar_simulacao",
        "descartar",
        "reiniciar",
    ):
        assert callable(getattr(lancador_entradas.NavegadorEntradas, metodo))
        assert hasattr(SCPIEntradas, metodo)


def test_o_modulo_nao_importa_o_playwright_no_topo():
    arvore = ast.parse(Path(lancador_entradas.__file__).read_text("utf-8"))
    topo = {
        alvo.name.split(".")[0]
        for no in arvore.body
        if isinstance(no, ast.Import)
        for alvo in no.names
    } | {
        no.module.split(".")[0]
        for no in arvore.body
        if isinstance(no, ast.ImportFrom) and no.module
    }
    assert "playwright" not in topo


CABECALHOS = [
    "?", "Item", "Código", "Descrição do Produto/Serviço", "Unidade", "Qtd.", "Valor Unitário",
    "Valor Total", "Qtd. Já Entrou", "Qtd. Já Pedida", "Qtd. Saldo",
]  # fmt: skip


def _linha(item, codigo, qtd, entrou, pedida, saldo):
    return [
        "",
        str(item),
        codigo,
        "DESCRIÇÃO",
        "PC",
        qtd,
        "304,08",
        "3.648,96",
        entrou,
        pedida,
        saldo,
    ]


def test_a_leitura_da_escolha_dos_itens_pelos_cabecalhos():
    tela = lancador_entradas.ler_escolha_dos_itens(
        {
            "cabecalhos": CABECALHOS,
            "linhas": [
                _linha(1, "006.011.020", "100", "50", "0", "50"),
                _linha(13, "023.003.004", "20", "0", "0", "20"),
            ],
        }
    )
    assert isinstance(tela, TelaItens) and [linha.item for linha in tela.linhas] == [1, 13]
    assert tela.linhas[0].quantidade == 100 and tela.linhas[0].ja_entrou == 50
    assert tela.linhas[0].saldo == 50 and tela.linhas[1].codigo == "023.003.004"


def test_o_prefixo_qtd_nao_confunde_as_colunas():
    # "Qtd." é exato: "Qtd. Já Entrou" não pode ser lido como a quantidade
    tela = lancador_entradas.ler_escolha_dos_itens(
        {"cabecalhos": CABECALHOS, "linhas": [_linha(1, "x", "12", "3", "0", "9")]}
    )
    assert (tela.linhas[0].quantidade, tela.linhas[0].ja_entrou) == (12, 3)


@pytest.mark.parametrize(
    "dados",
    [
        None,
        {},
        {"cabecalhos": CABECALHOS, "linhas": []},
        {"cabecalhos": CABECALHOS, "linhas": [_linha(1, "x", "abc", "0", "0", "0")]},
        {"cabecalhos": ["Item", "Código"], "linhas": [["1", "x"]]},  # faltam as colunas
    ],
)
def test_leitura_vazia_ilegivel_ou_sem_coluna_e_erro_do_scpi(dados):
    with pytest.raises(ErroSCPI):
        lancador_entradas.ler_escolha_dos_itens(dados)


def test_a_falta_de_coluna_lista_os_cabecalhos_vistos():
    with pytest.raises(ErroSCPI, match="Qtd. Saldo.*cabeçalhos: Item, Código"):
        lancador_entradas.ler_escolha_dos_itens(
            {
                "cabecalhos": ["Item", "Código", "Qtd.", "Qtd. Já Entrou", "Qtd. Já Pedida"],
                "linhas": [["1"] * 5],
            }
        )


def test_o_numero_do_pedido_vai_com_5_digitos_e_o_ano():
    from compras.regras import RecebimentoParaLancar

    rec = RecebimentoParaLancar(
        1,
        "RC-0001",
        1,
        1,
        2026,
        514,
        "00514/26",
        "19502",
        "501",
        __import__("datetime").date(2026, 11, 10),
        "",
        (),
        (),
    )
    assert lancador_entradas._numero_pedido(rec) == ("00514", "2026")
