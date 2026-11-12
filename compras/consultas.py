"""Consultas das compras (spec 014): saldos, reservas e estado do pedido. Só leem."""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from catalogo.models import Importacao, Material
from compras import regras
from compras.models import ItemPedidoCompra, ItemRecebimento, PedidoCompra, TravaPedido
from pedidos.regras import norm_u

ESTADOS = {
    "disponivel": "Disponível",
    "travado": "Travado",
    "precisa_conferencia": "Precisa de conferência",
    "ausente": "Ausente da última importação",
    "fora_do_exercicio": "De outro exercício",
}


def ultima_importacao_pedidos(exercicio: int | None = None) -> Importacao | None:
    """A última importação de pedidos de compra que deu certo. Com `exercicio`, só as desse
    exercício: uma importação de outro (um CSV de outro ano) não atualiza o saldo dos pedidos
    deste e não pode liberar as reservas dele. As de antes do registro do exercício (sem ele)
    valem para qualquer um."""
    importacoes = Importacao.objects.filter(
        tipo=Importacao.Tipo.PEDIDOS_COMPRA, situacao=Importacao.Situacao.SUCESSO
    )
    if exercicio is not None:
        importacoes = importacoes.filter(Q(exercicio=exercicio) | Q(exercicio__isnull=True))
    return importacoes.order_by("-inicio").first()


def reservado_por_item(
    pedido: PedidoCompra, *, ignorar: int | None = None
) -> dict[int, list[Decimal]]:
    """As quantidades que cada item do pedido tem reservadas (R5), uma consulta por tabela:
    {id do item → lista de quantidades}. Cancelado não reserva; lançado reserva até uma importação
    começada depois do `visivel_desde`. `ignorar` é o id de um recebimento que não conta (o que
    está sendo editado)."""
    ultima = ultima_importacao_pedidos(pedido.exercicio)
    inicio = ultima.inicio if ultima else None
    reservado: dict[int, list[Decimal]] = defaultdict(list)
    linhas = ItemRecebimento.objects.filter(recebimento__pedido=pedido).select_related(
        "recebimento"
    )
    if ignorar is not None:
        linhas = linhas.exclude(recebimento_id=ignorar)
    for linha in linhas:
        recebimento = linha.recebimento
        if regras.reserva_de(
            recebimento.status,
            visivel_desde=recebimento.visivel_desde,
            inicio_ultima_importacao=inicio,
        ):
            reservado[linha.item_id].append(linha.quantidade)
    return reservado


@dataclass(frozen=True)
class LinhaSaldo:
    item: ItemPedidoCompra
    material: Material | None
    motivo: str | None  # `regras.disponibilidade`: None se o item pode ser recebido
    reservado: Decimal
    saldo_livre: Decimal

    @property
    def item_id(self) -> int:
        return self.item.pk

    @property
    def campo_erro(self) -> str:
        """O nome do campo nos erros do formulário (`regras.Erro.campo`)."""
        return f"item-{self.item.pk}"

    @property
    def numero(self) -> int:
        return self.item.item

    @property
    def saldo_scpi(self) -> Decimal:
        return self.item.saldo_scpi

    @property
    def precisa_conferencia(self) -> bool:
        return self.reservado > self.item.saldo_scpi


def saldos_do_pedido(pedido: PedidoCompra, *, ignorar: int | None = None) -> list[LinhaSaldo]:
    """Os itens do pedido, com o material do cadastro, a disponibilidade, o reservado e o saldo
    livre. O pedido (ou o item) ausente, de outro exercício ou travado é visto pelo
    `estado_do_pedido`; aqui cada item diz o seu motivo. `ignorar`: veja `reservado_por_item`."""
    itens = list(pedido.itens.all())
    materiais = {
        norm_u(m.codigo): m for m in Material.objects.filter(codigo__in=[i.codigo for i in itens])
    }
    reservado = reservado_por_item(pedido, ignorar=ignorar)
    exercicio = timezone.localdate().year
    linhas = []
    for item in itens:
        material = materiais.get(norm_u(item.codigo))
        visivel = None if material is None else not material.oculto
        # O `pedido` do item é o objeto que já temos (evita uma consulta por item).
        item.pedido = pedido
        motivo = regras.disponibilidade(item, material_visivel=visivel, exercicio_atual=exercicio)
        reservas = reservado.get(item.pk, [])
        linhas.append(
            LinhaSaldo(
                item=item,
                material=material,
                motivo=motivo,
                reservado=sum(reservas, Decimal(0)),
                saldo_livre=regras.saldo_livre(item.saldo_scpi, reservas),
            )
        )
    return linhas


def travas_abertas(pedido: PedidoCompra) -> list[TravaPedido]:
    return list(pedido.travas.filter(destravada_em__isnull=True).order_by("criada_em", "id"))


def estado_do_pedido(pedido: PedidoCompra, linhas: list[LinhaSaldo] | None = None) -> str:
    """Um de `ESTADOS`: fora do exercício, ausente, travado, precisa de conferência (algum item com
    o reservado maior que o saldo do SCPI) ou disponível. Calculado, nunca guardado."""
    if pedido.exercicio != timezone.localdate().year:
        return "fora_do_exercicio"
    if pedido.ausente_desde_id is not None:
        return "ausente"
    if pedido.travas.filter(destravada_em__isnull=True).exists():
        return "travado"
    linhas = saldos_do_pedido(pedido) if linhas is None else linhas
    if any(linha.precisa_conferencia for linha in linhas):
        return "precisa_conferencia"
    return "disponivel"


def recusa_do_pedido(estado: str) -> str | None:
    """O motivo de o pedido não aceitar recebimento, pelo estado; `None` se aceita."""
    return {
        "fora_do_exercicio": "o pedido é de outro exercício",
        "ausente": "o pedido não veio na última importação",
        "travado": "o pedido está travado",
    }.get(estado)


def estados_dos_pedidos(pedidos: list[PedidoCompra]) -> dict[int, str]:
    """O estado de cada pedido de uma lista, em poucas consultas (a lista de pedidos). É o mesmo
    cálculo do `estado_do_pedido`: fora do exercício, ausente, travado, precisa de conferência."""
    ids = [p.pk for p in pedidos]
    travados = set(
        TravaPedido.objects.filter(pedido_id__in=ids, destravada_em__isnull=True).values_list(
            "pedido_id", flat=True
        )
    )
    inicio_por_exercicio = {}
    for exercicio_do_pedido in {p.exercicio for p in pedidos}:
        ultima = ultima_importacao_pedidos(exercicio_do_pedido)
        inicio_por_exercicio[exercicio_do_pedido] = ultima.inicio if ultima else None
    exercicio_do_pedido_por_id = {p.pk: p.exercicio for p in pedidos}
    reservado: dict[int, Decimal] = defaultdict(Decimal)
    for linha in ItemRecebimento.objects.filter(recebimento__pedido_id__in=ids).select_related(
        "recebimento"
    ):
        recebimento = linha.recebimento
        if regras.reserva_de(
            recebimento.status,
            visivel_desde=recebimento.visivel_desde,
            inicio_ultima_importacao=inicio_por_exercicio[
                exercicio_do_pedido_por_id[recebimento.pedido_id]
            ],
        ):
            reservado[linha.item_id] += linha.quantidade
    com_conferencia = {
        item.pedido_id
        for item in ItemPedidoCompra.objects.filter(pedido_id__in=ids)
        if reservado.get(item.pk, Decimal(0)) > item.saldo_scpi
    }
    exercicio = timezone.localdate().year
    estados = {}
    for pedido in pedidos:
        if pedido.exercicio != exercicio:
            estados[pedido.pk] = "fora_do_exercicio"
        elif pedido.ausente_desde_id is not None:
            estados[pedido.pk] = "ausente"
        elif pedido.pk in travados:
            estados[pedido.pk] = "travado"
        elif pedido.pk in com_conferencia:
            estados[pedido.pk] = "precisa_conferencia"
        else:
            estados[pedido.pk] = "disponivel"
    return estados
