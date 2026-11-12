"""Regras puras de `compras/regras.py` (sem banco)."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from compras.regras import chave_pedido, disponibilidade, rotulo_pedido

# --- Fundação: chave, rótulo e disponibilidade ----------------------------------------------


def test_chave_pedido_traz_o_ano_de_origem_e_o_numero():
    assert chave_pedido("00514/26") == (2026, 514)
    assert chave_pedido(" 00001/25 ") == (2025, 1)


@pytest.mark.parametrize("texto", ["", "514/26", "003588/26", "00514-26", "00514/2026", "abc"])
def test_chave_pedido_invalida_levanta_value_error(texto):
    with pytest.raises(ValueError):
        chave_pedido(texto)


def test_rotulo_pedido_tem_5_digitos_e_o_ano_em_2():
    assert rotulo_pedido(2026, 514) == "00514/26"
    assert rotulo_pedido(2025, 1) == "00001/25"


def _item(**campos):
    pedido = SimpleNamespace(
        exercicio=campos.pop("exercicio", 2026), ausente_desde_id=campos.pop("pedido_ausente", None)
    )
    padrao = dict(
        controle="Q",
        quantidade=Decimal("100"),
        anulado=Decimal("0"),
        ja_entrou=Decimal("50"),
        pedida=Decimal("0"),
        saldo_scpi=Decimal("50"),
        ausente_desde_id=None,
        pedido=pedido,
    )
    padrao.update(campos)
    return SimpleNamespace(**padrao)


def _disp(item, *, visivel=True, exercicio=2026):
    return disponibilidade(item, material_visivel=visivel, exercicio_atual=exercicio)


def test_item_disponivel_nao_tem_motivo():
    assert _disp(_item()) is None


def test_saldo_controlado_por_valor_nao_e_disponivel():
    assert "valor" in _disp(_item(controle="T"))


def test_codigo_fora_do_cadastro_e_material_oculto_tem_motivos_diferentes():
    fora = _disp(_item(), visivel=None)
    oculto = _disp(_item(), visivel=False)
    assert "cadastro" in fora and "oculto" in oculto and fora != oculto


def test_pedido_de_outro_exercicio_ausente_e_item_ausente():
    assert "exercício" in _disp(_item(exercicio=2025))
    assert "pedido não veio" in _disp(_item(pedido_ausente=7))
    assert "item não veio" in _disp(_item(ausente_desde_id=7))


def test_quantidade_com_quatro_casas_nao_e_disponivel():
    assert "3 casas" in _disp(_item(saldo_scpi=Decimal("0.0005")))
    assert "3 casas" in _disp(_item(quantidade=Decimal("100.1234")))


def test_quantidade_com_tres_casas_e_zeros_a_direita_e_disponivel():
    assert _disp(_item(saldo_scpi=Decimal("50.1230"))) is None


def test_saldo_zero_nao_e_disponivel():
    assert "saldo" in _disp(_item(saldo_scpi=Decimal("0")))
