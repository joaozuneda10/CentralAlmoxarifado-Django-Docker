"""Regras puras da spec 013: o nome da conta no pedido e a conta no token do formulário."""

import time

from pedidos.protecao import emitir, ler
from pedidos.regras import nome_da_conta


def test_nome_da_conta_normaliza_os_espacos():
    assert nome_da_conta("  Maria ", "da  Silva") == "Maria da Silva"
    assert nome_da_conta("Maria", "") == "Maria"
    assert nome_da_conta("", "") == ""


def test_token_leva_a_conta():
    assert ler(emitir(conta_id=7).token).conta == 7
    assert ler(emitir().token).conta is None


def test_token_com_conta_mantem_o_id_e_o_momento():
    antes = emitir(aberto_em=time.time() - 30, conta_id=3)
    lido = ler(antes.token)
    assert (lido.id, lido.aberto_em, lido.conta) == (antes.id, antes.aberto_em, 3)
