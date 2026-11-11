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


def test_so_falhas_avisa_a_falha_e_a_falta_de_sucesso():
    _imp(Importacao.Situacao.FALHA, QUARTA - timedelta(hours=1), "x")
    textos = [a.texto for a in saude.avisos(QUARTA)]
    assert len(textos) == 2


def test_os_avisos_entram_na_saude_do_catalogo():
    _imp(Importacao.Situacao.FALHA, timezone.now() - timedelta(hours=1), "Pedidos de compra: x")
    textos = [i.texto for i in saude_do_catalogo()]
    assert any(t.startswith("Pedidos de compra: a última importação falhou") for t in textos)
