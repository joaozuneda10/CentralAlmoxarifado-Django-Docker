"""Regras puras das entradas por pedido de compra (spec 014). Sem ORM.

Recebem objetos com os atributos que o modelo tem (ou o que o teste montar) e devolvem valores
simples. As quantidades são `Decimal`; os códigos de material se comparam por
`pedidos.regras.norm_u`.
"""

import re
from decimal import Decimal

RE_PEDIDO = re.compile(r"^(\d{5})/(\d{2})$")  # número visível do pedido no SCPI: 00514/26
TRES_CASAS = Decimal("0.001")


def chave_pedido(numped: str) -> tuple[int, int]:
    """`00514/26` → (2026, 514): o ano de origem e o número. Inválido: ValueError."""
    casou = RE_PEDIDO.match((numped or "").strip())
    if not casou:
        raise ValueError(f"número de pedido inválido: {numped!r}")
    return 2000 + int(casou.group(2)), int(casou.group(1))


def rotulo_pedido(ano: int, numero: int) -> str:
    """(2026, 514) → `00514/26`."""
    return f"{numero:05d}/{ano % 100:02d}"


def _cabe_em_tres_casas(valor: Decimal) -> bool:
    return valor == valor.quantize(TRES_CASAS)


def disponibilidade(item, *, material_visivel: bool | None, exercicio_atual: int) -> str | None:
    """Diz se o item pode ser recebido (R4): `None` se pode, senão o motivo em pt-BR.

    `material_visivel`: `True` (no cadastro e visível), `False` (no cadastro, mas oculto) ou
    `None` (o código não está no cadastro). `item` traz `controle`, `quantidade`, `anulado`,
    `ja_entrou`, `pedida`, `saldo_scpi`, `ausente_desde_id` e o `pedido` (com `exercicio` e
    `ausente_desde_id`).
    """
    if item.controle != "Q":
        return "o saldo deste item é controlado por valor, não por quantidade"
    if material_visivel is None:
        return "o código não está no cadastro de materiais"
    if material_visivel is False:
        return "o material está oculto no cadastro"
    if item.pedido.exercicio != exercicio_atual:
        return "o pedido é de outro exercício"
    if item.pedido.ausente_desde_id is not None:
        return "o pedido não veio na última importação"
    if item.ausente_desde_id is not None:
        return "o item não veio na última importação"
    quantidades = (item.quantidade, item.anulado, item.ja_entrou, item.pedida, item.saldo_scpi)
    if not all(_cabe_em_tres_casas(q) for q in quantidades):
        return "as quantidades do item têm mais de 3 casas decimais"
    if item.saldo_scpi <= 0:
        return "o item não tem saldo a entregar no SCPI"
    return None
