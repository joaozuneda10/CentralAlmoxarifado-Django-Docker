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


def test_a_leitura_da_escolha_dos_itens():
    tela = lancador_entradas.ler_escolha_dos_itens(
        [
            ["1", "006.011.020", "100,00", "50,00", "0,00", "50,00"],
            ["13", "023.003.004", "20", "0", "0", "20"],
        ]
    )
    assert isinstance(tela, TelaItens) and [linha.item for linha in tela.linhas] == [1, 13]
    assert tela.linhas[0].saldo == 50 and tela.linhas[1].codigo == "023.003.004"


@pytest.mark.parametrize("linhas", [None, [], [["1", "x", "abc", "0", "0", "0"]]])
def test_leitura_vazia_ou_ilegivel_e_erro_do_scpi(linhas):
    with pytest.raises(ErroSCPI):
        lancador_entradas.ler_escolha_dos_itens(linhas)


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
