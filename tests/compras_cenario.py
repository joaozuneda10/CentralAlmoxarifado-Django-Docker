"""Cenários das compras (spec 014): pedido importado pelo CSV sintético, recebimento preparado e
usuário com o papel de recebedor."""

import uuid
from datetime import date

from django.utils import timezone

from catalogo.models import Material
from compras import importacao, servicos
from compras.models import ItemPedidoCompra, PedidoCompra, Recebimento
from pedidos.regras import qtd_br
from tests.papeis import usuario_com
from tests.relacao_pedidos_compra import ItemPedidoCSV, csv_pedidos

ANO = timezone.localdate().year
NUMPED = f"00514/{ANO % 100:02d}"
DATA_DO_PEDIDO = date(ANO, 1, 1)  # nunca depois de hoje


def importar_pedido(
    itens: list[dict], *, data=DATA_DO_PEDIDO, fornecedor="19502", numped=NUMPED
) -> PedidoCompra:
    """Importa um pedido pelo CSV do 07.13 e cria o `Material` de cada código (visível, com
    unidade). Cada item é um dict com `item`, `codigo` e, opcionalmente, `quantidade`,
    `ja_entrou`, `anulado`, `pedida` e `controle`. Pode ser chamado de novo para o mesmo pedido
    (a importação é forçada: não interessa o corte de 20%)."""
    csv_itens = []
    for dados in itens:
        csv_itens.append(
            ItemPedidoCSV(numped, dados["item"], dados["codigo"], data=data, fornecedor=fornecedor)
        )
        for campo in ("quantidade", "ja_entrou", "anulado", "pedida", "controle", "unidade"):
            if campo in dados:
                setattr(csv_itens[-1], campo, dados[campo])
        Material.objects.get_or_create(
            codigo=dados["codigo"],
            defaults={"nome": f"MATERIAL {dados['codigo']}", "unidade": "UN"},
        )
    # Os outros pedidos já importados continuam no relatório, como no SCPI (senão, ausentes).
    for existente in ItemPedidoCompra.objects.filter(
        pedido__exercicio=ANO, ausente_desde__isnull=True, pedido__ausente_desde__isnull=True
    ).select_related("pedido"):
        if existente.pedido.rotulo == numped:
            continue
        csv_itens.append(
            ItemPedidoCSV(
                existente.pedido.rotulo,
                existente.item,
                existente.codigo,
                quantidade=qtd_br(existente.quantidade),
                anulado=qtd_br(existente.anulado),
                ja_entrou=qtd_br(existente.ja_entrou),
                pedida=qtd_br(existente.pedida),
                saldo=qtd_br(existente.saldo_scpi),
                unidade=existente.unidade,
                controle=existente.controle,
                data=existente.pedido.data,
                fornecedor=existente.pedido.fornecedor_codigo,
                nome=existente.pedido.fornecedor_nome,
            )
        )
    imp = importacao.importar(lambda: csv_pedidos(csv_itens), forcar=True)
    assert imp.situacao == "SUCESSO", imp.erro
    return PedidoCompra.objects.get(
        exercicio=ANO, ano=2000 + int(numped[-2:]), numero=int(numped[:5])
    )


def pedido_padrao(**kw) -> PedidoCompra:
    """O pedido de dois itens: o 1 com saldo 50 (100 pedido, 50 já entraram) e o 2 com 20."""
    return importar_pedido(
        [
            {"item": 1, "codigo": "006.011.020", "quantidade": "100", "ja_entrou": "50"},
            {"item": 2, "codigo": "023.003.004", "quantidade": "20"},
        ],
        **kw,
    )


def item_do_pedido(pedido: PedidoCompra, numero: int) -> ItemPedidoCompra:
    return ItemPedidoCompra.objects.get(pedido=pedido, item=numero)


def usuario_recebedor(username="12345"):
    """Um usuário com os papéis Atendimento e Gestão (têm `receber_compras`)."""
    from tests.papeis import dar_papeis

    return dar_papeis(usuario_com(username=username))


def preparar(
    pedido: PedidoCompra, usuario, itens: dict[int, str], nf="501", data=None, **kw
) -> Recebimento:
    """Prepara um recebimento pelo serviço. `itens` é {número do item no pedido → quantidade}."""
    por_numero = {i.item: i.pk for i in pedido.itens.all()}
    resposta = servicos.preparar_recebimento(
        pedido.pk,
        usuario,
        envio=kw.pop("envio", uuid.uuid4()),
        nf=nf,
        data_recebimento=data or timezone.localdate(),
        observacao=kw.pop("observacao", ""),
        itens={por_numero[n]: q for n, q in itens.items()},
        **kw,
    )
    assert resposta.ok, [e.mensagem for e in resposta.erros] or resposta.mensagem
    return resposta.recebimento
