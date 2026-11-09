"""Contas de solicitante nos testes (spec 013).

O grupo `Solicitante` vem da migration `contas/0006_solicitante`; o teste `transaction=True` esvazia
o banco no fim, e `garantir_grupo` o recria, como o `tests/papeis.py` faz com os papéis da 012.
"""

import time

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse

from contas.acesso import GRUPO_SOLICITANTE
from pedidos.protecao import emitir

SENHA = "senha-do-solicitante-123"
LIMPEZA_ITENS = [("023.001.002", "2"), ("008.001.002", "1,5")]


def garantir_grupo() -> Group:
    return Group.objects.get_or_create(name=GRUPO_SOLICITANTE)[0]


def criar_solicitante(
    username="90001", nome="Maria", sobrenome="da Silva", *, senha=SENHA, **campos
):
    """Uma conta de solicitante com nome completo, no grupo `Solicitante`."""
    usuario = get_user_model().objects.create_user(
        username=username, password=senha, first_name=nome, last_name=sobrenome, **campos
    )
    usuario.groups.add(garantir_grupo())
    return usuario


def cliente_de(usuario, **kw) -> Client:
    c = Client(**kw)
    c.force_login(usuario)
    return c


def token(conta=None) -> str:
    """O token de um formulário aberto há um minuto (passa do tempo mínimo), com ou sem conta."""
    return emitir(aberto_em=time.time() - 60, conta_id=conta.pk if conta else None).token


def postar(
    client,
    tok,
    *,
    fluxo="limpeza",
    solicitante="Ana",
    destino="ETA II",
    obs="",
    ocorrencia="",
    itens=LIMPEZA_ITENS,
    isca="",
    extra=None,
):
    dados = {
        "token": tok,
        "solicitante": solicitante,
        "destino": destino,
        "obs": obs,
        "ocorrencia": ocorrencia,
        "confirmacao_extra": isca,
        "item_codigo": [c for c, _ in itens],
        "item_qtd": [q for _, q in itens],
        **(extra or {}),
    }
    return client.post(reverse("pedidos:formulario", args=[fluxo]), dados, HTTP_HX_REQUEST="true")
