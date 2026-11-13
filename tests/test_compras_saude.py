"""Avisos de saúde das compras (`compras.saude`) e a ligação com o `catalogo.saude`."""

from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from catalogo.models import Importacao
from catalogo.saude import saude_do_catalogo
from compras import saude

pytestmark = pytest.mark.django_db

TIPO = Importacao.Tipo.PEDIDOS_COMPRA
# Uma quarta-feira ao meio-dia (UTC; o fuso local do projeto é -03).
QUARTA = datetime(2026, 11, 11, 15, 0, tzinfo=UTC)


def _imp(situacao, inicio, erro=""):
    return Importacao.objects.create(
        tipo=TIPO, situacao=situacao, inicio=inicio, fim=inicio, erro=erro
    )


def test_sem_nenhuma_importacao_nao_avisa_nada():
    assert saude.avisos(QUARTA) == []


def test_importacao_recente_com_sucesso_nao_avisa():
    _imp(Importacao.Situacao.SUCESSO, QUARTA - timedelta(hours=3))
    assert saude.avisos(QUARTA) == []


def test_ultima_com_falha_e_erro_e_diz_o_motivo():
    _imp(Importacao.Situacao.SUCESSO, QUARTA - timedelta(hours=5))
    _imp(
        Importacao.Situacao.FALHA,
        QUARTA - timedelta(hours=1),
        "Pedidos de compra: relatório cortado.",
    )
    (aviso,) = saude.avisos(QUARTA)
    assert aviso.nivel == "erro" and "falhou" in aviso.texto and "cortado" in aviso.texto


def test_sem_sucesso_ha_mais_de_um_dia_util_avisa():
    _imp(Importacao.Situacao.SUCESSO, QUARTA - timedelta(days=2))
    (aviso,) = saude.avisos(QUARTA)
    assert aviso.nivel == "aviso" and "um dia útil" in aviso.texto


def test_sexta_com_sucesso_vale_ate_a_segunda():
    sexta = datetime(2026, 11, 13, 15, 0, tzinfo=UTC)
    _imp(Importacao.Situacao.SUCESSO, sexta)
    assert saude.avisos(sexta + timedelta(days=2, hours=23)) == []
    assert saude.avisos(sexta + timedelta(days=3, hours=1))


def test_importacao_interrompida_avisa(monkeypatch):
    _imp(Importacao.Situacao.SUCESSO, QUARTA - timedelta(hours=5))
    Importacao.objects.create(
        tipo=TIPO, situacao=Importacao.Situacao.ANDAMENTO, inicio=QUARTA - timedelta(hours=2)
    )
    monkeypatch.setattr(Importacao, "trava_ocupada", classmethod(lambda cls, tipo: False))
    (aviso,) = saude.avisos(QUARTA)
    assert aviso.nivel == "aviso" and "não terminou" in aviso.texto


def test_importacao_em_andamento_de_verdade_nao_avisa(monkeypatch):
    _imp(Importacao.Situacao.SUCESSO, QUARTA - timedelta(hours=5))
    Importacao.objects.create(
        tipo=TIPO, situacao=Importacao.Situacao.ANDAMENTO, inicio=QUARTA - timedelta(hours=2)
    )
    monkeypatch.setattr(Importacao, "trava_ocupada", classmethod(lambda cls, tipo: True))
    assert saude.avisos(QUARTA) == []


def test_so_falhas_avisa_a_falha_e_a_falta_de_sucesso():
    _imp(Importacao.Situacao.FALHA, QUARTA - timedelta(hours=1), "x")
    textos = [a.texto for a in saude.avisos(QUARTA)]
    assert len(textos) == 2


def test_os_avisos_entram_na_saude_do_catalogo():
    _imp(Importacao.Situacao.FALHA, timezone.now() - timedelta(hours=1), "Pedidos de compra: x")
    textos = [i.texto for i in saude_do_catalogo()]
    assert any(t.startswith("Pedidos de compra: a última importação falhou") for t in textos)


# --- recebimentos, extração, travas e entradas fora do Central (PR 6) ---------------------------


def _recebimento(status, nf="501"):
    from tests.compras_cenario import pedido_padrao, preparar, usuario_recebedor

    r = preparar(pedido_padrao(), usuario_recebedor(), {1: "5"}, nf=nf)
    from compras.models import Recebimento

    Recebimento.objects.filter(pk=r.pk).update(status=status)
    return r


def test_recebimento_em_verificacao_e_com_erro_geram_avisos():
    _imp(Importacao.Situacao.SUCESSO, QUARTA - timedelta(hours=1))
    _recebimento("VERIFICAR")
    textos = [a.texto for a in saude.avisos(QUARTA)]
    assert any("1 recebimento em verificação" in t for t in textos)
    from compras.models import Recebimento

    Recebimento.objects.update(status="ERRO")
    textos = [a.texto for a in saude.avisos(QUARTA)]
    assert any("1 recebimento com erro" in t for t in textos)


def test_extracao_de_entradas_com_falha_avisa():
    Importacao.objects.create(
        tipo=Importacao.Tipo.ENTRADAS,
        situacao=Importacao.Situacao.FALHA,
        erro="Entradas do SCPI: relatório cortado.",
        inicio=QUARTA,
        fim=QUARTA,
    )
    (aviso,) = [a for a in saude.avisos(QUARTA) if a.texto.startswith("Entradas: a última")]
    assert aviso.nivel == "erro" and "cortado" in aviso.texto


def test_pedido_travado_avisa_com_o_motivo():
    from compras import servicos
    from tests.compras_cenario import pedido_padrao

    pedido = pedido_padrao()
    servicos.travar_pedido(pedido.pk, "JA_ENTROU", "x")
    servicos.travar_pedido(pedido.pk, "TELA", "y")
    (aviso,) = [a for a in saude.avisos(timezone.now()) if "travado" in a.texto]
    assert pedido.rotulo in aviso.texto and "já entrou não explicado" in aviso.texto
    assert "a tela do scpi mudou" in aviso.texto


def test_entradas_fora_do_central_dos_ultimos_30_dias_avisam():
    from compras.models import EntradaForaDoCentral, ExtracaoEntradas, RequisicaoEntradaOficial
    from tests.compras_cenario import pedido_padrao

    pedido = pedido_padrao()
    imp = Importacao.objects.create(tipo="ENTRADAS", situacao="SUCESSO")
    extracao = ExtracaoEntradas.objects.create(importacao=imp, motivo="MANUAL")
    requisicao = RequisicaoEntradaOficial.objects.create(
        extracao=extracao,
        requisicao="003493/26",
        ano=2026,
        numero=3493,
        id_requi=1,
        data_entrada=timezone.localdate(),
        data_requisicao=timezone.localdate(),
    )
    entrada = EntradaForaDoCentral.objects.create(
        pedido=pedido, requisicao=requisicao, ano=2026, numero=3493, visivel_desde=timezone.now()
    )
    agora = timezone.now()
    assert any("1 entrada feita direto no SCPI" in a.texto for a in saude.avisos(agora))
    assert not any("direto no SCPI" in a.texto for a in saude.avisos(agora + timedelta(days=31)))
    assert entrada.pk


def test_as_fontes_novas_entram_na_visao_geral_depois_da_primeira_execucao():
    from catalogo.saude import situacao_do_catalogo

    tipos = [f.tipo for f in situacao_do_catalogo().fontes]
    assert "PEDIDOS_COMPRA" not in tipos and "ENTRADAS" not in tipos
    Importacao.objects.create(tipo="PEDIDOS_COMPRA", situacao="SUCESSO", linhas=5)
    Importacao.objects.create(tipo="ENTRADAS", situacao="SUCESSO", linhas=2)
    fontes = {f.tipo: f for f in situacao_do_catalogo().fontes}
    assert "5 itens" in fontes["PEDIDOS_COMPRA"].resumo
    assert "2 requisições de entrada" in fontes["ENTRADAS"].resumo
