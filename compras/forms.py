"""Os formulários do recebimento (spec 014): leem o POST sem esconder o que foi digitado.

Não são `django.forms`: o formulário tem uma linha por item do pedido, com uma caixa e uma
quantidade, e o que importa é devolver o que a pessoa digitou quando há erro. A validação é do
serviço (`compras.servicos`), dentro da trava do pedido.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date

from django.utils import timezone

from compras import regras
from compras.models import Recebimento
from pedidos.regras import qtd_br


def _data(texto: str) -> date | None:
    try:
        return date.fromisoformat((texto or "").strip())
    except ValueError:
        return None


@dataclass
class FormularioRecebimento:
    """O que a tela mostra e o que o POST traz: NF, data, observação, o `envio` (e a `versao`, na
    edição) e, por item, a caixa e a quantidade."""

    envio: uuid.UUID
    nf: str = ""
    data_recebimento: date | None = None
    data_texto: str = ""
    observacao: str = ""
    versao: int | None = None
    marcados: dict[int, str] = field(default_factory=dict)  # {id do item → quantidade digitada}
    quantidades: dict[int, str] = field(default_factory=dict)  # tudo o que foi digitado

    @classmethod
    def novo(cls, modo: str, linhas) -> "FormularioRecebimento":
        """O GET: "total" marca todos os itens disponíveis com o saldo livre; "parcial" abre
        vazio."""
        hoje = timezone.localdate()
        formulario = cls(envio=uuid.uuid4(), data_recebimento=hoje, data_texto=hoje.isoformat())
        if modo == "total":
            formulario.marcados = {
                item_id: qtd_br(livre) for item_id, livre in regras.sugestao_total(linhas).items()
            }
            formulario.quantidades = dict(formulario.marcados)
        return formulario

    @classmethod
    def de(cls, recebimento: Recebimento) -> "FormularioRecebimento":
        """A edição: o que está gravado."""
        marcados = {i.item_id: qtd_br(i.quantidade) for i in recebimento.itens.all()}
        return cls(
            envio=recebimento.envio,
            nf=recebimento.nf,
            data_recebimento=recebimento.data_recebimento,
            data_texto=recebimento.data_recebimento.isoformat(),
            observacao=recebimento.observacao,
            versao=recebimento.versao,
            marcados=marcados,
            quantidades=dict(marcados),
        )

    @classmethod
    def do_post(cls, post, linhas) -> "FormularioRecebimento":
        try:
            envio = uuid.UUID(post.get("envio", ""))
        except ValueError:
            envio = uuid.uuid4()
        try:
            versao = int(post.get("versao", ""))
        except ValueError:
            versao = None
        formulario = cls(
            envio=envio,
            nf=(post.get("nf") or "").strip(),
            data_texto=(post.get("data_recebimento") or "").strip(),
            data_recebimento=_data(post.get("data_recebimento", "")),
            observacao=(post.get("observacao") or "").strip(),
            versao=versao,
        )
        for linha in linhas:
            texto = post.get(f"qtd-{linha.item_id}", "").strip()
            if texto:
                formulario.quantidades[linha.item_id] = texto
            if post.get(f"marcar-{linha.item_id}"):
                formulario.marcados[linha.item_id] = texto
        return formulario


@dataclass
class FormularioCancelamento:
    motivo: str = ""
    confirmado: bool = False

    @classmethod
    def do_post(cls, post) -> "FormularioCancelamento":
        return cls(
            motivo=(post.get("motivo") or "").strip(), confirmado=post.get("confirmado") == "1"
        )
