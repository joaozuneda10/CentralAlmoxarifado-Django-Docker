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


@pytest.mark.parametrize(
    "texto",
    ["", "  ", "0", "0000", "50a", "5-01", "1234567890123", "1,5", "٠٥٠١", "５０１"],
)
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


# --- A marca do recebimento nas Observações ------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Central Almoxarifado RC-0042", "RC-0042"),
        ("central   almoxarifado rc-0042\nObs.: x", "RC-0042"),
        ("Central Almoxarifado RC-123456789 extra", "RC-123456789"),
        ("Central Almoxarifado P-000123", ""),  # a marca das saídas não é a deste
        ("RC-0042 sem a frase do robô", ""),
        ("Central Almoxarifado RC-1234567890", ""),  # mais de 9 dígitos: não é marca
        ("", ""),
    ],
)
def test_recebimento_observado(texto, esperado):
    assert regras.recebimento_observado(texto) == esperado


def test_texto_observacoes_com_e_sem_observacao():
    assert regras.texto_observacoes("RC-0042") == "Central Almoxarifado RC-0042"
    assert (
        regras.texto_observacoes("RC-0042", "  portaria;  volume 3 ")
        == "Central Almoxarifado RC-0042\nObs.: portaria, volume 3"
    )
    # a marca que o robô escreve é a que a leitura reconhece
    assert regras.recebimento_observado(regras.texto_observacoes("RC-0042", "x")) == "RC-0042"


# --- A conferência da tela do SCPI antes do Salvar (PR 4) ----------------------------------


def _esperado(item=1, codigo="006.011.020", quantidade="10", ja_entrou="50", saldo="50"):
    return regras.EsperadoItem(
        item, codigo, Decimal(quantidade), Decimal(ja_entrou), Decimal(saldo)
    )


def _tela_do_scpi(*linhas):
    return regras.TelaItens(tuple(linhas))


def _linha_da_tela(item=1, codigo="006.011.020", ja_entrou="50", saldo="50", quantidade="100"):
    return regras.LinhaTela(
        item, codigo, Decimal(quantidade), Decimal(ja_entrou), Decimal(0), Decimal(saldo)
    )


def test_a_tela_igual_ao_esperado_nao_diverge():
    assert (
        regras.conferir_tela(
            [_esperado()], _tela_do_scpi(_linha_da_tela(), _linha_da_tela(2, "023.003.004"))
        )
        == []
    )


def test_ja_entrou_maior_na_tela_diverge_com_a_mensagem_do_item():
    divergencias = regras.conferir_tela(
        [_esperado(item=13, ja_entrou="1")],
        _tela_do_scpi(_linha_da_tela(13, ja_entrou="2", saldo="50")),
    )
    assert divergencias == ["O SCPI mudou: item 13, Já Entrou 2 na tela, esperado 1."]


def test_saldo_menor_na_tela_diverge():
    divergencias = regras.conferir_tela([_esperado()], _tela_do_scpi(_linha_da_tela(saldo="30")))
    assert "O SCPI mudou: item 1, saldo 30 na tela, esperado 50." in divergencias


def test_item_ausente_na_tela_diverge():
    assert regras.conferir_tela([_esperado(item=3)], _tela_do_scpi(_linha_da_tela(1))) == [
        "O SCPI mudou: o item 3 não está na tela."
    ]


def test_codigo_diferente_no_mesmo_numero_diverge():
    divergencias = regras.conferir_tela(
        [_esperado()], _tela_do_scpi(_linha_da_tela(codigo="999.999.999"))
    )
    assert divergencias == [
        "O SCPI mudou: item 1, código 999.999.999 na tela, esperado 006.011.020."
    ]


def test_o_codigo_se_compara_pela_chave_do_sistema():
    assert (
        regras.conferir_tela(
            [_esperado(codigo="006.011.020")], _tela_do_scpi(_linha_da_tela(codigo=" 006.011.020 "))
        )
        == []
    )


def test_quantidade_acima_do_saldo_da_tela_diverge():
    divergencias = regras.conferir_tela(
        [_esperado(quantidade="60", saldo="50")], _tela_do_scpi(_linha_da_tela(saldo="50"))
    )
    assert divergencias == ["O SCPI mudou: item 1, a quantidade 60 passa do saldo 50 na tela."]


def test_varios_itens_acumulam_as_divergencias():
    divergencias = regras.conferir_tela(
        [_esperado(1), _esperado(2, "023.003.004", "5", "0", "20")],
        _tela_do_scpi(
            _linha_da_tela(1, ja_entrou="55"),
            _linha_da_tela(2, "023.003.004", ja_entrou="0", saldo="20"),
        ),
    )
    assert len(divergencias) == 1 and "item 1, Já Entrou 55" in divergencias[0]


def test_o_esperado_soma_o_lancado_ainda_nao_refletido():
    assert regras.esperado_do_item(ja_entrou=Decimal("50"), saldo=Decimal("50")) == (50, 50)
    ja_entrou, saldo = regras.esperado_do_item(
        ja_entrou=Decimal("50"), saldo=Decimal("50"), nao_refletido=Decimal("10")
    )
    assert (ja_entrou, saldo) == (60, 40)
    assert (
        regras.conferir_tela(
            [_esperado(ja_entrou="60", saldo="40", quantidade="5")],
            _tela_do_scpi(_linha_da_tela(ja_entrou="60", saldo="40")),
        )
        == []
    )


def test_a_foto_guarda_o_que_o_robo_digita_e_o_que_a_tela_mostrou():
    rec = regras.RecebimentoParaLancar(
        id=7,
        rotulo="RC-0007",
        versao=2,
        pedido_id=1,
        pedido_ano=2026,
        pedido_numero=514,
        pedido_rotulo="00514/26",
        fornecedor_codigo="19502",
        nf="501",
        data=date(2026, 11, 10),
        observacoes="Central Almoxarifado RC-0007",
        itens=(regras.ItemParaLancar(1, "006.011.020", Decimal("10")),),
        esperado=(_esperado(),),
    )
    foto = regras.foto(
        rec, _tela_do_scpi(_linha_da_tela(ja_entrou="50", saldo="50"), _linha_da_tela(2))
    )
    assert foto == {
        "pedido": "00514/26",
        "fornecedor": "19502",
        "nf": "501",
        "data": "2026-11-10",
        "observacoes": "Central Almoxarifado RC-0007",
        "itens": [{"item": 1, "codigo": "006.011.020", "quantidade": "10"}],
        "tela": [{"item": 1, "ja_entrou": "50", "saldo": "50"}],
    }
    assert regras.foto(rec)["tela"] == []


# --- Recebimento em verificação: intervalo, candidatas e as três provas (PR 5) -----------------


def _req(numero, marca="", fornecedor="19502", nf="501", pedido=(2026, 514), itens=()):
    return regras.RequisicaoEntradaResumo(
        numero, marca, fornecedor, nf, pedido[0], pedido[1], tuple(itens)
    )


def _candidatas(requisicoes, de=None, ate=None, **campos):
    dados = {
        "rotulo": "RC-0042",
        "fornecedor": "19502",
        "nf": "501",
        "pedido": (2026, 514),
        "de": de,
        "ate": ate,
    } | campos
    return regras.candidatas(requisicoes, **dados)


def test_o_intervalo_usa_as_tentativas_de_entrada():
    from conciliacao.regras import TentativaResumo, intervalo

    tentativas = [
        TentativaResumo(1, "RC-0040", "003500/26"),
        TentativaResumo(2, "RC-0042", ""),
        TentativaResumo(3, "RC-0043", "003504/26"),
    ]
    assert intervalo(tentativas, "003490/26", "RC-0042") == ("003500/26", "003504/26")
    assert intervalo(tentativas, "003490/26", "RC-0040") == ("003490/26", "003504/26")


def test_e_esta_pela_marca_e_pela_nf_com_o_fornecedor_mesmo_fora_do_intervalo():
    pela_marca = _req("009999/26", marca="RC-0042", nf="", pedido=(2026, 1))
    pela_nf = _req("009998/26", nf="501", pedido=(2026, 1))
    outra_nf = _req("003501/26", nf="777")
    achadas = _candidatas([outra_nf, pela_nf, pela_marca], "003500/26", "003504/26")
    assert [(r.requisicao, e) for r, e in achadas] == [
        ("009998/26", True),
        ("009999/26", True),
        ("003501/26", False),
    ]


def test_a_nf_so_vale_com_o_mesmo_fornecedor_e_nao_vazia():
    outro_fornecedor = _req("003501/26", fornecedor="777", nf="501", pedido=(2026, 1))
    sem_nf = _req("003502/26", nf="", pedido=(2026, 1))
    assert _candidatas([outro_fornecedor, sem_nf], "003500/26", "003504/26") == []
    assert _candidatas([_req("003503/26", nf="", pedido=(2026, 1))], nf="") == []


def test_outro_pedido_no_intervalo_nao_entra_e_o_mesmo_pedido_entra():
    outro = _req("003501/26", nf="900", pedido=(2026, 999))
    mesmo = _req("003502/26", nf="901", pedido=(2026, 514))
    achadas = _candidatas([outro, mesmo], "003500/26", "003504/26")
    assert [(r.requisicao, e) for r, e in achadas] == [("003502/26", False)]


def test_a_marca_de_outro_recebimento_nao_entra():
    de_outro = _req("003501/26", marca="RC-0099", nf="501")
    assert _candidatas([de_outro], "003500/26", "003504/26") == []


def test_fora_do_intervalo_e_do_mesmo_pedido_sem_marca_nem_nf_nao_entra():
    assert _candidatas([_req("003600/26", nf="900")], "003500/26", "003504/26") == []


def test_as_candidatas_se_ordenam_pela_semelhanca_com_a_foto():
    foto = {"itens": [{"item": 1, "codigo": "006.011.020", "quantidade": "10"}]}
    parecida = _req("003503/26", nf="900", itens=[("006.011.020", Decimal("10"))])
    mesmos_codigos = _req("003501/26", nf="901", itens=[("006.011.020", Decimal("3"))])
    diferente = _req("003502/26", nf="902", itens=[("999.000.000", Decimal("1"))])
    achadas = _candidatas(
        [mesmos_codigos, diferente, parecida], "003500/26", "003504/26", foto=foto
    )
    assert [r.requisicao for r, _ in achadas] == ["003503/26", "003501/26", "003502/26"]


def _prova(**campos):
    dados = {
        "momento": datetime(2026, 11, 11, 10, 42),
        "extracao_posterior": True,
        "candidatas": [],
        "importacao_posterior": True,
        "itens": [regras.ItemDaProva(13, Decimal("30"), True, Decimal("30"))],
    } | campos
    return regras.tres_provas(**dados)


def test_tudo_certo_nao_tem_falta():
    assert _prova() == []


def test_sem_extracao_posterior():
    assert _prova(extracao_posterior=False) == [
        "Ainda não houve extração de entradas depois da tentativa de 11/11/2026 10:42."
    ]


def test_com_candidata_numa_conferencia_antiga_continua_bloqueando():
    assert _prova(candidatas=["003901/26"]) == ["Há requisição candidata no intervalo: 003901/26."]
    assert _prova(candidatas=["003902/26", "003901/26", "003901/26"]) == [
        "Há requisições candidatas no intervalo: 003901/26, 003902/26."
    ]


def test_ja_entrou_diferente_da_foto_ou_item_ausente_ou_importacao_anterior():
    assert _prova(itens=[regras.ItemDaProva(13, Decimal("30"), True, Decimal("50"))]) == [
        "O 'Já Entrou' do item 13 mudou de 30 para 50 depois da tentativa: "
        "a requisição pode existir."
    ]
    assert _prova(itens=[regras.ItemDaProva(13, Decimal("30"), False, None)]) == [
        "O item 13 não veio na importação de pedidos depois da tentativa: "
        "a requisição pode existir."
    ]
    assert _prova(importacao_posterior=False) == [
        "O 'Já Entrou' do item 13 não foi conferido depois da tentativa: atualize os pedidos."
    ]


def test_a_extracao_de_arquivo_nao_e_extracao_posterior_e_a_lacuna_nao_entra_na_conta():
    # tres_provas só recebe o booleano da extração: o arquivo nunca o torna verdadeiro
    # (compras.conciliacao.conciliar_verificar o ignora) e a numeração nem é um parâmetro.
    import inspect

    assert "lacuna" not in inspect.signature(regras.tres_provas).parameters
    assert _prova(extracao_posterior=False, importacao_posterior=False)[0].startswith("Ainda não")
