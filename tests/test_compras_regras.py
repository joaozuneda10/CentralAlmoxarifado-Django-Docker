"""Regras puras de `compras/regras.py` (sem banco)."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from compras import regras
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


# --- US1: NF, saldo livre e validação -------------------------------------------------------


@pytest.mark.parametrize(
    "texto, esperado",
    [("000000000501", "501"), ("501", "501"), (" 0501 ", "501"), ("123456789012", "123456789012")],
)
def test_nf_normalizada_tira_os_zeros_a_esquerda(texto, esperado):
    assert regras.nf_normalizada(texto) == esperado


@pytest.mark.parametrize("texto", ["", "  ", "0", "0000", "50a", "5-01", "1234567890123", "1,5"])
def test_nf_invalida_levanta_value_error(texto):
    with pytest.raises(ValueError):
        regras.nf_normalizada(texto)


def test_chave_nf_junta_fornecedor_e_numero():
    assert regras.chave_nf("19502", "501") == "19502:501"


T0 = datetime(2026, 11, 11, 10, 0)


def test_reserva_por_estado():
    for status in ("PREPARADO", "ERRO", "EM_LANCAMENTO", "VERIFICAR"):
        assert regras.reserva_de(status, visivel_desde=None, inicio_ultima_importacao=T0)
    assert not regras.reserva_de("CANCELADO", visivel_desde=None, inicio_ultima_importacao=T0)


def test_lancado_reserva_ate_uma_importacao_comecada_depois_do_visivel_desde():
    visivel = T0
    assert regras.reserva_de("LANCADO", visivel_desde=visivel, inicio_ultima_importacao=None)
    assert regras.reserva_de(
        "LANCADO", visivel_desde=visivel, inicio_ultima_importacao=visivel - timedelta(minutes=1)
    )
    assert regras.reserva_de("LANCADO", visivel_desde=visivel, inicio_ultima_importacao=visivel)
    assert not regras.reserva_de(
        "LANCADO", visivel_desde=visivel, inicio_ultima_importacao=visivel + timedelta(seconds=1)
    )


def test_lancado_sem_visivel_desde_reserva_pelo_lado_seguro():
    assert regras.reserva_de("LANCADO", visivel_desde=None, inicio_ultima_importacao=T0)


def test_saldo_livre_100_30_20():
    assert regras.saldo_livre(Decimal("100"), []) == Decimal("100")
    assert regras.saldo_livre(Decimal("100"), [Decimal("30")]) == Decimal("70")
    assert regras.saldo_livre(Decimal("100"), [Decimal("30"), Decimal("20")]) == Decimal("50")


def test_saldo_livre_nunca_e_negativo():
    assert regras.saldo_livre(Decimal("10"), [Decimal("30")]) == Decimal("0")


def _linha(item_id, numero, livre, motivo=None):
    return SimpleNamespace(
        item_id=item_id, numero=numero, saldo_livre=Decimal(livre), motivo=motivo
    )


def test_sugestao_total_e_o_saldo_livre_de_cada_item_disponivel():
    linhas = [
        _linha(1, 1, "50"),
        _linha(2, 2, "0"),
        _linha(3, 3, "7.5", motivo="o material está oculto no cadastro"),
        _linha(4, 4, "1.25"),
    ]
    assert regras.sugestao_total(linhas) == {1: Decimal("50"), 4: Decimal("1.25")}


HOJE = date(2026, 11, 11)
DATA_PEDIDO = date(2026, 8, 5)


def _validar(**campos):
    padrao = dict(
        nf="501",
        data_recebimento=HOJE,
        data_pedido=DATA_PEDIDO,
        hoje=HOJE,
        itens={1: "10"},
        linhas={1: _linha(1, 13, "50")},
        nf_usada_por=None,
        recusa_do_pedido=None,
    )
    padrao.update(campos)
    return regras.validar_recebimento(**padrao)


def test_recebimento_valido_nao_tem_erros():
    assert _validar() == []


def test_nf_invalida_e_nf_ja_usada():
    (erro,) = _validar(nf="abc")
    assert erro.campo == "nf" and "Informe o número da nota fiscal" in erro.mensagem
    (erro,) = _validar(nf_usada_por="RC-0007")
    assert (
        erro.campo == "nf"
        and erro.mensagem == "A NF 501 deste fornecedor já está no recebimento RC-0007."
    )


def test_datas():
    (erro,) = _validar(data_recebimento=HOJE + timedelta(days=1))
    assert erro.campo == "data_recebimento" and "depois de hoje" in erro.mensagem
    (erro,) = _validar(data_recebimento=DATA_PEDIDO - timedelta(days=1))
    assert "antes da data do pedido (05/08/2026)" in erro.mensagem
    (erro,) = _validar(data_recebimento=None)
    assert "Informe a data" in erro.mensagem


def test_nenhum_item_marcado():
    (erro,) = _validar(itens={})
    assert erro.campo == "itens" and erro.mensagem == "Marque ao menos um item."


@pytest.mark.parametrize("texto", ["1.5", "abc", "0", "-1", "1,2345"])
def test_quantidade_ilegivel_ou_fora_do_formato(texto):
    (erro,) = _validar(itens={1: texto})
    assert erro.item == 1 and erro.campo == "item-1"


def test_quantidade_com_virgula_e_ate_tres_casas_vale():
    assert _validar(itens={1: "1,5"}) == []
    assert _validar(itens={1: "0,001"}) == []


def test_acima_do_saldo_livre_traz_o_valor_na_mensagem():
    (erro,) = _validar(itens={1: "50,001"})
    assert erro.mensagem == "Item 13: o saldo livre é 50; informe até 50."
    assert _validar(itens={1: "50"}) == []


def test_item_de_outro_pedido_e_item_indisponivel():
    (erro,) = _validar(itens={99: "1"})
    assert "não é deste pedido" in erro.mensagem
    linhas = {1: _linha(1, 13, "50", motivo="o material está oculto no cadastro")}
    (erro,) = _validar(linhas=linhas)
    assert "Item 13" in erro.mensagem and "oculto" in erro.mensagem


def test_pedido_que_nao_aceita_recebimento():
    erros = _validar(recusa_do_pedido="o pedido está travado")
    assert erros[0].campo == "pedido"
    assert erros[0].mensagem == "Este pedido não aceita recebimento: o pedido está travado."


def test_os_erros_sao_juntados():
    erros = _validar(nf="", data_recebimento=HOJE + timedelta(days=2), itens={1: "999"})
    assert {e.campo for e in erros} == {"nf", "data_recebimento", "item-1"}
