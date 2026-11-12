"""Consultas das compras (spec 014): saldos, reservas e estado do pedido. Só leem."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Count, Q
from django.utils import timezone

from catalogo.models import Importacao, Material
from compras import regras
from compras.models import (
    ItemPedidoCompra,
    ItemRecebimento,
    PedidoCompra,
    Recebimento,
    TravaPedido,
)
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
    _reserva_das_entradas_fora_do_central(pedido, inicio, reservado)
    return reservado


def _reserva_das_entradas_fora_do_central(pedido, inicio, reservado) -> None:
    """As entradas feitas direto no SCPI reservam o saldo, por **código**, até uma importação de
    pedidos começada depois do `visivel_desde` (a mesma regra do lançado). Com o código repetido
    no pedido, reservam em cada item."""
    from compras.models import EntradaForaDoCentral

    entradas = list(EntradaForaDoCentral.objects.filter(pedido=pedido))
    if not entradas:
        return
    por_codigo: dict[str, list[ItemPedidoCompra]] = defaultdict(list)
    for item in pedido.itens.all():
        por_codigo[norm_u(item.codigo)].append(item)
    for entrada in entradas:
        if not regras.reserva_de(
            "LANCADO", visivel_desde=entrada.visivel_desde, inicio_ultima_importacao=inicio
        ):
            continue
        for linha in entrada.itens:
            for item in por_codigo.get(norm_u(linha["codigo"]), []):
                reservado[item.pk].append(Decimal(str(linha["quantidade"])))


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


@dataclass(frozen=True)
class LinhaFilaEntradas:
    """Um recebimento preparado na fila do robô de entradas, com o motivo se está bloqueado."""

    rotulo: str
    pk: int
    pedido_pk: int
    pedido_rotulo: str
    fornecedor: str
    nf: str
    data: date
    itens: int
    motivo: str  # vazio: o robô pode lançar

    @property
    def apto(self) -> bool:
        return not self.motivo


@dataclass(frozen=True)
class FilaEntradas:
    linhas: list[LinhaFilaEntradas]

    @property
    def aptos(self) -> int:
        return sum(1 for linha in self.linhas if linha.apto)

    @property
    def total(self) -> int:
        return len(self.linhas)


def fila_entradas() -> FilaEntradas:
    """Os recebimentos preparados, na ordem em que o robô os percorre (a da preparação): os
    aptos com caixa de marcar e os bloqueados com o motivo. Usa a mesma regra do robô
    (`compras.robo.motivo_de_bloqueio`), que o robô confere de novo ao abrir cada pedido."""
    from compras.robo import motivo_de_bloqueio

    hoje = timezone.localdate()
    recebimentos = (
        Recebimento.objects.filter(status=Recebimento.Status.PREPARADO)
        .select_related("pedido")
        .annotate(n_itens=Count("itens"))
        .order_by("pk")
    )
    return FilaEntradas(
        [
            LinhaFilaEntradas(
                rotulo=r.rotulo,
                pk=r.pk,
                pedido_pk=r.pedido_id,
                pedido_rotulo=r.pedido.rotulo,
                fornecedor=r.pedido.fornecedor_nome or r.fornecedor_codigo,
                nf=r.nf,
                data=r.data_recebimento,
                itens=r.n_itens,
                motivo=motivo_de_bloqueio(r, hoje),
            )
            for r in recebimentos
        ]
    )


def liberacao(recebimento: Recebimento) -> list[str]:
    """As faltas das três provas para liberar (ou cancelar) um recebimento em verificação (R16);
    vazia quando pode. Só lê: `regras.tres_provas` decide, com o que o banco tem:

    - a extração posterior é uma conferência de verificação da tentativa mais recente, feita por
      uma extração bem-sucedida que não é de arquivo (`conciliar_verificar` só grava essas);
    - as candidatas são as de todas as conferências da tentativa;
    - o "Já Entrou" da tela antes do Salvar está na foto da tentativa; a importação posterior é a
      última importação de pedidos bem-sucedida do exercício, começada depois dela."""
    from compras.conciliacao import ultima_tentativa
    from compras.models import CandidataEntrada, ConferenciaRecebimento

    tentativa = ultima_tentativa(recebimento)
    if tentativa is None:
        return ["Não há tentativa registrada deste recebimento: confira a entrada no SCPI."]
    conferencias = ConferenciaRecebimento.objects.filter(
        recebimento=recebimento, tipo=ConferenciaRecebimento.Tipo.VERIFICAR, tentativa=tentativa
    )
    numeros = CandidataEntrada.objects.filter(conferencia__in=conferencias).values_list(
        "requisicao__requisicao", flat=True
    )
    importacao = ultima_importacao_pedidos(recebimento.pedido.exercicio)
    posterior = importacao is not None and importacao.inicio > tentativa.momento
    antes_da_tela = {i["item"]: i["ja_entrou"] for i in (tentativa.foto or {}).get("tela", [])}
    atuais = {
        i.item: i
        for i in ItemPedidoCompra.objects.filter(
            pedido=recebimento.pedido, item__in=antes_da_tela or [0]
        )
    }
    itens = []
    for linha in (tentativa.foto or {}).get("itens", []):
        numero = linha["item"]
        if numero not in antes_da_tela:
            # Sem a tela registrada antes do Salvar não há o que comparar: lado seguro.
            return [
                f"A tela do SCPI não foi registrada antes do Salvar (item {numero}): "
                "não dá para provar o 'Já Entrou'."
            ]
        atual = atuais.get(numero)
        itens.append(
            regras.ItemDaProva(
                item=numero,
                antes=Decimal(antes_da_tela[numero]),
                presente=atual is not None and atual.ausente_desde_id is None,
                depois=atual.ja_entrou if atual is not None else None,
            )
        )
    return regras.tres_provas(
        momento=timezone.localtime(tentativa.momento),
        extracao_posterior=conferencias.exists(),
        candidatas=list(numeros),
        importacao_posterior=posterior,
        itens=itens,
    )


@dataclass(frozen=True)
class RecebimentoParaResolver:
    """Um recebimento que o robô deixou em verificação ou com erro, com o que a aba mostra: as
    candidatas (com "É esta") e, só nos em verificação, as faltas das três provas."""

    recebimento: Recebimento
    em_verificacao: bool
    candidatas: list  # `CandidataEntrada`, da conferência mais recente, na ordem
    faltas: list[str]

    @property
    def pode_liberar(self) -> bool:
        return self.em_verificacao and not self.faltas


def verificacoes_entradas() -> list[RecebimentoParaResolver]:
    """Os recebimentos em verificação (ou em lançamento sem robô) e com erro, na ordem do número,
    para a região "Em verificação e com erro" da aba Entradas no SCPI."""
    from compras.models import CandidataEntrada, ConferenciaRecebimento

    abertos = (
        Recebimento.objects.filter(
            status__in=(
                Recebimento.Status.VERIFICAR,
                Recebimento.Status.EM_LANCAMENTO,
                Recebimento.Status.ERRO,
            )
        )
        .select_related("pedido")
        .order_by("pk")
    )
    resultado = []
    for recebimento in abertos:
        em_verificacao = recebimento.status != Recebimento.Status.ERRO
        candidatas = []
        faltas = []
        if em_verificacao:
            faltas = liberacao(recebimento)
            ultima = (
                ConferenciaRecebimento.objects.filter(
                    recebimento=recebimento, tipo=ConferenciaRecebimento.Tipo.VERIFICAR
                )
                .order_by("-criada_em", "-pk")
                .first()
            )
            if ultima is not None:
                candidatas = list(
                    CandidataEntrada.objects.filter(conferencia=ultima)
                    .select_related("requisicao")
                    .order_by("ordem")
                )
        resultado.append(RecebimentoParaResolver(recebimento, em_verificacao, candidatas, faltas))
    return resultado


def marco() -> str | None:
    """O `maior_requisicao` da primeira extração de entradas bem-sucedida: o que tem número até ele
    é história anterior ao Central (R18). None sem nenhuma extração ainda."""
    from compras.models import ExtracaoEntradas

    primeira = (
        ExtracaoEntradas.objects.filter(importacao__situacao=Importacao.Situacao.SUCESSO)
        .exclude(maior_requisicao__isnull=True)
        .order_by("importacao__inicio", "pk")
        .first()
    )
    return primeira.maior_requisicao if primeira else None


def _conclusivas(recebimento):
    from compras.models import ConferenciaRecebimento

    return ConferenciaRecebimento.objects.filter(
        recebimento=recebimento,
        tipo__in=(
            ConferenciaRecebimento.Tipo.LANCAMENTO,
            ConferenciaRecebimento.Tipo.REVISAO,
        ),
    ).exclude(veredito=ConferenciaRecebimento.Veredito.AGUARDANDO)


def veredito_atual(recebimento):
    """A última conferência conclusiva do recebimento lançado (o veredito atual); None é
    "Aguardando"."""
    return _conclusivas(recebimento).order_by("-criada_em", "-pk").first()


FILTROS_VEREDITO = (
    ("divergencias", "Divergências"),
    ("aguardando", "Aguardando"),
    ("comprovados", "Comprovados"),
    ("todos", "Todos"),
)
POR_PAGINA_VEREDITOS = 50
PROBLEMAS = ("DIVERGENTE", "NAO_ENCONTRADO", "DUPLICADO", "CONFLITO")


def vereditos(filtro: str = "divergencias", pagina: int | str = 1):
    """Os recebimentos lançados com o veredito atual, filtrados e paginados (50 por página)."""
    from django.core.paginator import Paginator

    lancados = (
        Recebimento.objects.filter(status=Recebimento.Status.LANCADO)
        .select_related("pedido")
        .order_by("-lancado_em", "-pk")
    )
    linhas = []
    for recebimento in lancados:
        atual = veredito_atual(recebimento)
        veredito = atual.veredito if atual else "AGUARDANDO"
        if (
            filtro == "divergencias"
            and veredito not in PROBLEMAS
            or filtro == "aguardando"
            and veredito != "AGUARDANDO"
            or filtro == "comprovados"
            and veredito != "COMPROVADO"
        ):
            continue
        linhas.append({"recebimento": recebimento, "conferencia": atual, "veredito": veredito})
    return Paginator(linhas, POR_PAGINA_VEREDITOS).get_page(pagina)


def ultima_extracao_entradas():
    from compras.models import ExtracaoEntradas

    return (
        ExtracaoEntradas.objects.select_related("importacao")
        .order_by("-importacao__inicio", "-pk")
        .first()
    )
