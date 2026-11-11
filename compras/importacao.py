"""Importação dos pedidos de compra (07.13, spec 014): grava os pedidos e os itens do SCPI.

Nada é apagado: o pedido e o item que somem do relatório ficam com `ausente_desde`, e o que volta
a aparecer o limpa (FR-005, Princípio IV). A gravação roda dentro da transação que a
`scpi.execucao.executar` abre; um `ErroImportacao` desfaz tudo.
"""

from collections.abc import Callable

from django.utils import timezone

from catalogo.models import Importacao
from compras.models import ItemPedidoCompra, PedidoCompra
from scpi.execucao import Resultado, executar
from scpi.leitura import ErroImportacao, LinhaPedidoCompra, ler_pedidos_compra

# Fração máxima dos itens presentes na importação anterior que pode sumir de uma vez; acima disso o
# relatório provavelmente veio cortado e a importação aborta (salvo `forcar`), como o cadastro.
LIMITE_SUMIDOS = 0.2
LOTE = 1000

CAMPOS_ITEM = (
    "codigo",
    "unidade",
    "controle",
    "quantidade",
    "anulado",
    "ja_entrou",
    "ja_entrou_anterior",
    "pedida",
    "saldo_scpi",
    "preco",
    "ausente_desde",
)
CAMPOS_PEDIDO = ("data", "fornecedor_codigo", "fornecedor_nome", "atualizado_por", "ausente_desde")


def _max(modelo, campo: str) -> int:
    return modelo._meta.get_field(campo).max_length


def _cortar(texto: str, limite: int, descricao: str, avisos: list[str]) -> str:
    if len(texto) > limite:
        avisos.append(f"Texto cortado em {descricao} ({limite} caracteres): {texto[:30]}…")
        return texto[:limite]
    return texto


def gravar(
    linhas: list[LinhaPedidoCompra],
    importacao: Importacao,
    *,
    exercicio: int,
    forcar: bool = False,
) -> Resultado:
    """Cria os pedidos e itens novos, atualiza os presentes (guardando o `ja_entrou_anterior`) e
    marca `ausente_desde` nos que sumiram. Só mexe nos pedidos do `exercicio`."""
    avisos: list[str] = []
    existentes = {(p.ano, p.numero): p for p in PedidoCompra.objects.filter(exercicio=exercicio)}
    itens_antes = {
        (i.pedido_id, i.item): i
        for i in ItemPedidoCompra.objects.filter(pedido__exercicio=exercicio)
    }
    chaves_novas = {(linha.ano, linha.numero, linha.item) for linha in linhas}
    presentes_antes = [i for i in itens_antes.values() if i.ausente_desde_id is None]
    mapa_pedido = {p.pk: (p.ano, p.numero) for p in existentes.values()}
    sumiram = [
        i for i in presentes_antes if (*mapa_pedido[i.pedido_id], i.item) not in chaves_novas
    ]
    if presentes_antes and len(sumiram) > LIMITE_SUMIDOS * len(presentes_antes) and not forcar:
        raise ErroImportacao(
            f"Pedidos de compra: o relatório não traz {len(sumiram)} dos {len(presentes_antes)} "
            "itens presentes na importação anterior (mais de 20%). Nada foi alterado; confira "
            "o relatório do SCPI ou rode com --forcar."
        )

    # Pedidos: um por (ano, número), com os dados do primeiro item (a leitura já garantiu um só
    # fornecedor por pedido).
    por_pedido: dict[tuple[int, int], LinhaPedidoCompra] = {}
    for linha in linhas:
        por_pedido.setdefault((linha.ano, linha.numero), linha)
    criar_pedidos, atualizar_pedidos = [], []
    for chave_pedido, linha in por_pedido.items():
        valores = {
            "data": linha.data,
            "fornecedor_codigo": _cortar(
                linha.fornecedor_codigo,
                _max(PedidoCompra, "fornecedor_codigo"),
                "o fornecedor",
                avisos,
            ),
            "fornecedor_nome": _cortar(
                linha.fornecedor_nome,
                _max(PedidoCompra, "fornecedor_nome"),
                "o nome do fornecedor",
                avisos,
            ),
            "atualizado_por": importacao,
            "ausente_desde": None,
        }
        pedido = existentes.get(chave_pedido)
        if pedido is None:
            criar_pedidos.append(
                PedidoCompra(
                    exercicio=exercicio, ano=chave_pedido[0], numero=chave_pedido[1], **valores
                )
            )
        else:
            for campo, valor in valores.items():
                setattr(pedido, campo, valor)
            atualizar_pedidos.append(pedido)
    PedidoCompra.objects.bulk_create(criar_pedidos, batch_size=LOTE)
    PedidoCompra.objects.bulk_update(atualizar_pedidos, CAMPOS_PEDIDO, batch_size=LOTE)
    pedidos = {(p.ano, p.numero): p for p in PedidoCompra.objects.filter(exercicio=exercicio)}

    # Pedidos ausentes: presentes antes (sem `ausente_desde`) e fora do relatório.
    ausentes = [
        p for k, p in existentes.items() if p.ausente_desde_id is None and k not in por_pedido
    ]
    PedidoCompra.objects.filter(pk__in=[p.pk for p in ausentes]).update(ausente_desde=importacao)

    # Itens.
    criar_itens, atualizar_itens = [], []
    for linha in linhas:
        pedido = pedidos[(linha.ano, linha.numero)]
        valores = {
            "codigo": _cortar(linha.codigo, _max(ItemPedidoCompra, "codigo"), "o código", avisos),
            "unidade": _cortar(
                linha.unidade, _max(ItemPedidoCompra, "unidade"), "a unidade", avisos
            ),
            "controle": linha.controle,
            "quantidade": linha.quantidade,
            "anulado": linha.anulado,
            "ja_entrou": linha.ja_entrou,
            "pedida": linha.pedida,
            "saldo_scpi": linha.saldo,
            "preco": linha.preco,
            "ausente_desde": None,
        }
        antes = itens_antes.get((pedido.pk, linha.item))
        if antes is None:
            criar_itens.append(
                ItemPedidoCompra(pedido=pedido, item=linha.item, ja_entrou_anterior=None, **valores)
            )
        else:
            valores["ja_entrou_anterior"] = antes.ja_entrou
            for campo, valor in valores.items():
                setattr(antes, campo, valor)
            atualizar_itens.append(antes)
    ItemPedidoCompra.objects.bulk_create(criar_itens, batch_size=LOTE)
    ItemPedidoCompra.objects.bulk_update(atualizar_itens, CAMPOS_ITEM, batch_size=LOTE)
    ItemPedidoCompra.objects.filter(pk__in=[i.pk for i in sumiram]).update(ausente_desde=importacao)

    if sumiram or ausentes:
        avisos.append(
            f"{len(sumiram)} {'item' if len(sumiram) == 1 else 'itens'} e "
            f"{len(ausentes)} {'pedido' if len(ausentes) == 1 else 'pedidos'} não vieram no "
            "relatório e ficaram como ausentes (nada foi apagado)."
        )
    return Resultado(len(linhas), avisos)


def importar(obter_csv: Callable[[], bytes], *, forcar: bool = False) -> Importacao:
    """Baixa (ou lê) o relatório e o grava numa `Importacao` do tipo `PEDIDOS_COMPRA`, com a trava
    do tipo. O exercício é o ano corrente."""
    exercicio = timezone.localdate().year
    criada: list[Importacao] = []

    def gravar_csv(conteudo: bytes) -> Resultado:
        leitura = ler_pedidos_compra(conteudo)
        return gravar(leitura.linhas, criada[0], exercicio=exercicio, forcar=forcar)

    return executar(Importacao.Tipo.PEDIDOS_COMPRA, obter_csv, gravar_csv, ao_criar=criada.append)
