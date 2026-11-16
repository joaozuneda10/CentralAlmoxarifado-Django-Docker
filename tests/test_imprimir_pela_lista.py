"""Spec 015 (entrega 2): "Imprimir recibo" pelo ⋮ da lista, com `?imprimir=1` (research R8)."""

import re

import pytest
from django.urls import reverse
from django.utils import timezone

from pedidos.models import Atendimento
from tests.cenario import criar_pedido

pytestmark = pytest.mark.django_db


def _detalhe(client, pedido, **params):
    return client.get(reverse("pedidos:detalhe", args=[pedido.numero]), params).text


def _botao(html):
    achado = re.search(r"<button[^>]*data-imprimir[^>]*>", html)
    return achado.group(0) if achado else ""


def test_com_atendimento_e_recibo_nao_impresso_imprime_ao_abrir(client, usuario_logado):
    p = criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    assert "data-imprimir-ao-abrir" in _botao(_detalhe(client, p, imprimir="1"))


def test_sem_o_parametro_nao_imprime_ao_abrir(client, usuario_logado):
    p = criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    html = _detalhe(client, p)
    assert _botao(html) and "data-imprimir-ao-abrir" not in html


def test_recibo_ja_impresso_ignora_o_parametro(client, usuario_logado):
    p = criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    Atendimento.objects.update(recibo_impresso_em=timezone.now())
    assert "data-imprimir-ao-abrir" not in _detalhe(client, p, imprimir="1")


def test_sem_atendimento_o_parametro_e_ignorado(client, usuario_logado):
    p = criar_pedido()
    html = _detalhe(client, p, imprimir="1")
    assert "data-imprimir-ao-abrir" not in html


def test_o_voltar_da_confirmacao_sai_sem_o_parametro(client, usuario_logado):
    p = criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    html = _detalhe(client, p, imprimir="1", aba="x")
    voltar = re.search(r'<input type="hidden" name="voltar" value="([^"]*)"', html).group(1)
    assert "imprimir" not in voltar
    assert voltar.startswith(reverse("pedidos:detalhe", args=[p.numero]))
    assert "aba=x" in voltar  # o resto da URL fica


def test_abrir_com_imprimir_nao_grava_nada(client, usuario_logado):
    p = criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    antes = Atendimento.objects.filter(recibo_impresso_em__isnull=True).count()
    _detalhe(client, p, imprimir="1")
    assert Atendimento.objects.filter(recibo_impresso_em__isnull=True).count() == antes == 1
