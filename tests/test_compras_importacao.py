"""Importação dos pedidos de compra (`compras.importacao`) e o comando `importar_pedidos_compra`."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from catalogo.models import Importacao
from compras import importacao
from compras.models import ItemPedidoCompra, PedidoCompra
from scpi.execucao import ImportacaoEmAndamento
from tests.relacao_pedidos_compra import ItemPedidoCSV, csv_pedidos

pytestmark = pytest.mark.django_db

ANO = timezone.localdate().year


def _item(numped="00514/26", item=1, codigo="006.011.020", **campos):
    return ItemPedidoCSV(numped, item, codigo, **campos)


def _importar(itens, **opcoes):
    return importacao.importar(lambda: csv_pedidos(itens), **opcoes)


def _item_db(pedido_numero, item):
    return ItemPedidoCompra.objects.get(pedido__numero=pedido_numero, item=item)


def test_a_primeira_importacao_cria_pedidos_e_itens_com_a_base_nula():
    imp = _importar(
        [
            _item(item=1, quantidade="100", ja_entrou="30"),
            _item(item=2, codigo="023.003.004"),
            _item("00515/26", 1, "008.001.002", fornecedor="777", nome="OUTRO FORNECEDOR"),
        ]
    )
    assert (imp.tipo, imp.situacao, imp.linhas) == ("PEDIDOS_COMPRA", "SUCESSO", 3)
    pedido = PedidoCompra.objects.get(numero=514)
    assert (pedido.exercicio, pedido.ano, pedido.data) == (ANO, 2026, date(2026, 3, 2))
    assert (pedido.fornecedor_codigo, pedido.rotulo) == ("19502", "00514/26")
    assert (pedido.atualizado_por, pedido.ausente_desde) == (imp, None)
    assert PedidoCompra.objects.count() == 2 and ItemPedidoCompra.objects.count() == 3
    item = _item_db(514, 1)
    assert (item.ja_entrou, item.saldo_scpi, item.ja_entrou_anterior) == (
        Decimal("30"),
        Decimal("70"),
        None,
    )


def test_a_segunda_importacao_atualiza_e_guarda_o_ja_entrou_anterior():
    _importar([_item(quantidade="100", ja_entrou="30"), _item(item=2, codigo="023.003.004")])
    segunda = _importar(
        [_item(quantidade="100", ja_entrou="45"), _item(item=2, codigo="023.003.004")]
    )
    item = _item_db(514, 1)
    assert (item.ja_entrou, item.ja_entrou_anterior, item.saldo_scpi) == (
        Decimal("45"),
        Decimal("30"),
        Decimal("55"),
    )
    assert PedidoCompra.objects.get().atualizado_por == segunda
    assert ItemPedidoCompra.objects.count() == 2


def test_item_e_pedido_que_somem_ficam_ausentes_e_nada_e_apagado():
    _importar(
        [_item(item=n, codigo=f"006.011.0{n:02d}") for n in range(1, 11)]
        + [_item("00515/26", 1, "008.001.002")]
    )
    # O pedido 515 some inteiro e o item 10 do 514 também: 2 de 11 itens, abaixo dos 20%.
    segunda = _importar([_item(item=n, codigo=f"006.011.0{n:02d}") for n in range(1, 10)])
    assert _item_db(514, 10).ausente_desde == segunda
    assert _item_db(515, 1).ausente_desde == segunda
    assert PedidoCompra.objects.get(numero=515).ausente_desde == segunda
    assert PedidoCompra.objects.get(numero=514).ausente_desde is None
    assert ItemPedidoCompra.objects.count() == 11


def test_o_que_reaparece_limpa_o_ausente_desde():
    _importar([_item(item=n, codigo=f"006.011.0{n:02d}") for n in range(1, 11)])
    _importar([_item(item=n, codigo=f"006.011.0{n:02d}") for n in range(1, 10)])
    assert _item_db(514, 10).ausente_desde is not None
    terceira = _importar([_item(item=n, codigo=f"006.011.0{n:02d}") for n in range(1, 11)])
    item = _item_db(514, 10)
    assert item.ausente_desde is None
    assert PedidoCompra.objects.get().atualizado_por == terceira


def test_o_ausente_mantem_a_primeira_importacao_em_que_sumiu():
    _importar([_item(item=n, codigo=f"006.011.0{n:02d}") for n in range(1, 11)])
    segunda = _importar([_item(item=n, codigo=f"006.011.0{n:02d}") for n in range(1, 10)])
    _importar([_item(item=n, codigo=f"006.011.0{n:02d}") for n in range(1, 10)])
    assert _item_db(514, 10).ausente_desde == segunda


def test_sumir_mais_de_20_por_cento_dos_itens_presentes_aborta_sem_forcar():
    _importar([_item(item=n, codigo=f"006.011.0{n:02d}") for n in range(1, 11)])
    cortada = _importar([_item(item=n, codigo=f"006.011.0{n:02d}") for n in range(1, 8)])
    assert cortada.situacao == Importacao.Situacao.FALHA
    assert "20%" in cortada.erro and "--forcar" in cortada.erro
    assert not ItemPedidoCompra.objects.filter(ausente_desde__isnull=False).exists()

    forcada = _importar(
        [_item(item=n, codigo=f"006.011.0{n:02d}") for n in range(1, 8)], forcar=True
    )
    assert forcada.situacao == Importacao.Situacao.SUCESSO
    assert ItemPedidoCompra.objects.filter(ausente_desde=forcada).count() == 3


def test_o_exercicio_vem_do_ano_corrente_e_o_mesmo_numero_em_outro_exercicio_e_outro_pedido():
    antigo = PedidoCompra.objects.create(
        exercicio=ANO - 1,
        ano=2026,
        numero=514,
        data=date(2026, 3, 2),
        fornecedor_codigo="19502",
        atualizado_por=Importacao.objects.create(tipo=Importacao.Tipo.PEDIDOS_COMPRA),
    )
    _importar([_item()])
    assert PedidoCompra.objects.count() == 2
    novo = PedidoCompra.objects.exclude(pk=antigo.pk).get()
    assert novo.exercicio == ANO
    antigo.refresh_from_db()
    assert antigo.ausente_desde is None  # outro exercício não é tocado


def test_a_falha_de_leitura_deixa_a_importacao_com_falha_sem_mudar_nada():
    _importar([_item(quantidade="100", ja_entrou="30")])
    falha = importacao.importar(lambda: b"GRUPO;NUMPED\r\n01/01/2026;lixo\r\n")
    assert falha.situacao == Importacao.Situacao.FALHA and falha.erro
    assert _item_db(514, 1).ja_entrou == Decimal("30")
    assert Importacao.objects.filter(tipo="PEDIDOS_COMPRA").count() == 2


def test_a_trava_do_tipo_ocupada_levanta_importacao_em_andamento(trava_importacao_ocupada):
    trava_importacao_ocupada("PEDIDOS_COMPRA")
    with pytest.raises(ImportacaoEmAndamento):
        importacao.importar(lambda: pytest.fail("não deveria baixar"))
    assert not Importacao.objects.exists()


def test_texto_maior_que_o_campo_e_cortado_com_aviso():
    imp = _importar([_item(codigo="006.011.020", nome="N" * 250)])
    assert PedidoCompra.objects.get().fornecedor_nome == "N" * 200
    assert any("cortado" in aviso for aviso in imp.avisos)


def test_aviso_diz_quantos_itens_e_pedidos_sumiram():
    _importar([_item(item=n, codigo=f"006.011.0{n:02d}") for n in range(1, 11)])
    segunda = _importar([_item(item=n, codigo=f"006.011.0{n:02d}") for n in range(1, 10)])
    assert any("1 item" in aviso for aviso in segunda.avisos)


# --- o comando -------------------------------------------------------------------------------


def _csv(tmp_path: Path, itens):
    arquivo = tmp_path / "pedidos.csv"
    arquivo.write_bytes(csv_pedidos(itens))
    return arquivo


def test_comando_com_arquivo_importa_e_conta(tmp_path, capsys):
    arquivo = _csv(tmp_path, [_item(), _item(item=2, codigo="023.003.004")])
    call_command("importar_pedidos_compra", arquivo=str(arquivo))
    assert ItemPedidoCompra.objects.count() == 2
    saida = capsys.readouterr().out
    assert "1 pedido" in saida and "2 itens" in saida


def test_comando_apaga_o_arquivo_enviado_ao_terminar(tmp_path):
    arquivo = _csv(tmp_path, [_item()])
    call_command("importar_pedidos_compra", arquivo=str(arquivo), apagar_arquivo=True)
    assert not arquivo.exists()


def test_comando_apaga_o_arquivo_mesmo_quando_falha(tmp_path):
    arquivo = tmp_path / "ruim.csv"
    arquivo.write_bytes(b"isto nao e o relatorio")
    with pytest.raises(CommandError):
        call_command("importar_pedidos_compra", arquivo=str(arquivo), apagar_arquivo=True)
    assert not arquivo.exists()


def test_comando_forcar_aceita_o_que_o_corte_de_20_por_cento_recusaria(tmp_path):
    _importar([_item(item=n, codigo=f"006.011.0{n:02d}") for n in range(1, 11)])
    arquivo = _csv(tmp_path, [_item(item=n, codigo=f"006.011.0{n:02d}") for n in range(1, 8)])
    with pytest.raises(CommandError, match="20%"):
        call_command("importar_pedidos_compra", arquivo=str(arquivo))
    call_command("importar_pedidos_compra", arquivo=str(arquivo), forcar=True)
    assert ItemPedidoCompra.objects.filter(ausente_desde__isnull=False).count() == 3


def test_comando_com_a_trava_ocupada_recusa(tmp_path, trava_importacao_ocupada):
    arquivo = _csv(tmp_path, [_item()])
    trava_importacao_ocupada("PEDIDOS_COMPRA")
    with pytest.raises(CommandError, match="em andamento"):
        call_command("importar_pedidos_compra", arquivo=str(arquivo))
