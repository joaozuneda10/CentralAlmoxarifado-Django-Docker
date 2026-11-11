"""A porta única de gravação dos recebimentos e das travas de pedido (spec 014, Princípio II).

Cada operação roda numa transação e trava o `PedidoCompra` (`select_for_update`) antes de refazer o
saldo livre, então duas pessoas nunca reservam o mesmo saldo. O reenvio igual não duplica: o
`envio` decide. Fora daqui, só o robô de entradas grava em recebimentos, e só `status`,
`requisicao_scpi`, `lancado_em`, `mensagem`, `via` e `visivel_desde`.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

from compras import consultas, regras
from compras.models import ItemRecebimento, PedidoCompra, Recebimento, TravaPedido
from pedidos.regras import interpretar_quantidade

MENSAGEM_VERSAO = "Outra pessoa alterou este recebimento. Recarregue a página."
MENSAGEM_TENTATIVA = (
    "O robô já tentou lançar este recebimento: resolva em Automações › Entradas no SCPI."
)
ABERTOS_PARA_EDITAR = (Recebimento.Status.PREPARADO, Recebimento.Status.ERRO)
COM_TENTATIVA = (
    Recebimento.Status.EM_LANCAMENTO,
    Recebimento.Status.VERIFICAR,
    Recebimento.Status.LANCADO,
)


@dataclass
class Resposta:
    ok: bool
    mensagem: str = ""
    erros: list[regras.Erro] = field(default_factory=list)
    recebimento: Recebimento | None = None
    trava: TravaPedido | None = None
    reenvio: bool = False
    divergente: bool = False
    # Por que foi recusada, além dos erros de campo: "nao_encontrado", "versao", "tentativa",
    # "estado", "divergente", "motivo" ou "importacao".
    motivo: str = ""


def tem_tentativa(recebimento: Recebimento) -> bool:
    """Se o robô já tentou lançar o recebimento (chegou ao `EM_LANCAMENTO`): daí em diante o Central
    não edita nem cancela sem as provas da verificação."""
    return recebimento.status in COM_TENTATIVA


def _quantidades(itens: dict[int, str]) -> dict[int, Decimal] | None:
    """As quantidades lidas, ou None se alguma é ilegível."""
    lidas = {}
    for item_id, texto in itens.items():
        valor, _ = interpretar_quantidade(texto, True)
        if valor is None:
            return None
        lidas[item_id] = valor
    return lidas


def _mesmo_conteudo(
    recebimento: Recebimento, *, nf, data_recebimento, observacao, itens, pedido_id=None
) -> bool:
    try:
        nf_lida = regras.nf_normalizada(nf)
    except ValueError:
        return False
    lidas = _quantidades(itens)
    if lidas is None:
        return False
    gravados = {i.item_id: i.quantidade for i in recebimento.itens.all()}
    return (
        recebimento.nf == nf_lida
        and recebimento.data_recebimento == data_recebimento
        and recebimento.observacao == (observacao or "").strip()
        and gravados == lidas
        and (pedido_id is None or recebimento.pedido_id == pedido_id)
    )


def _nf_usada_por(pedido: PedidoCompra, nf: str, *, ignorar: int | None = None) -> str | None:
    try:
        chave = regras.chave_nf(pedido.fornecedor_codigo, regras.nf_normalizada(nf))
    except ValueError:
        return None
    usada = Recebimento.objects.filter(chave_nf=chave)
    if ignorar is not None:
        usada = usada.exclude(pk=ignorar)
    primeiro = usada.first()
    return primeiro.rotulo if primeiro else None


def _validar(pedido, usuario_hoje, *, nf, data_recebimento, observacao, itens, ignorar=None):
    linhas = consultas.saldos_do_pedido(pedido, ignorar=ignorar)
    estado = consultas.estado_do_pedido(pedido, linhas)
    erros = regras.validar_recebimento(
        nf=nf,
        data_recebimento=data_recebimento,
        data_pedido=pedido.data,
        hoje=usuario_hoje,
        itens=itens,
        linhas={linha.item_id: linha for linha in linhas},
        nf_usada_por=_nf_usada_por(pedido, nf, ignorar=ignorar),
        recusa_do_pedido=consultas.recusa_do_pedido(estado),
    )
    if len((observacao or "").strip()) > Recebimento._meta.get_field("observacao").max_length:
        erros.append(regras.Erro("observacao", "A observação passa de 500 caracteres."))
    return erros


def _gravar_itens(recebimento: Recebimento, itens: dict[int, str]) -> None:
    ItemRecebimento.objects.bulk_create(
        [
            ItemRecebimento(recebimento=recebimento, item_id=item_id, quantidade=quantidade)
            for item_id, quantidade in _quantidades(itens).items()
        ]
    )


def preparar_recebimento(
    pedido_id: int,
    usuario,
    *,
    envio: UUID,
    nf: str,
    data_recebimento: date | None,
    observacao: str = "",
    itens: dict[int, str],
    hoje: date | None = None,
) -> Resposta:
    """Grava um recebimento `PREPARADO`. `itens` é {id do item do pedido → quantidade digitada}."""
    hoje = hoje or timezone.localdate()
    with transaction.atomic():
        try:
            pedido = PedidoCompra.objects.select_for_update().get(pk=pedido_id)
        except PedidoCompra.DoesNotExist:
            return Resposta(False, "Pedido não encontrado.", motivo="nao_encontrado")

        existente = Recebimento.objects.filter(envio=envio).first()
        if existente is not None:
            if _mesmo_conteudo(
                existente,
                nf=nf,
                data_recebimento=data_recebimento,
                observacao=observacao,
                itens=itens,
                pedido_id=pedido.pk,
            ):
                return Resposta(
                    True,
                    f"{existente.rotulo} já estava preparado.",
                    recebimento=existente,
                    reenvio=True,
                )
            return Resposta(
                False,
                "Este recebimento já foi gravado com outros dados. "
                f"Abra o {existente.rotulo} para conferir.",
                recebimento=existente,
                divergente=True,
                motivo="divergente",
            )

        erros = _validar(
            pedido,
            hoje,
            nf=nf,
            data_recebimento=data_recebimento,
            observacao=observacao,
            itens=itens,
        )
        if erros:
            return Resposta(False, erros=erros, motivo="erros")

        numero_nf = regras.nf_normalizada(nf)
        try:
            with transaction.atomic():
                recebimento = Recebimento.objects.create(
                    envio=envio,
                    pedido=pedido,
                    nf=numero_nf,
                    fornecedor_codigo=pedido.fornecedor_codigo,
                    chave_nf=regras.chave_nf(pedido.fornecedor_codigo, numero_nf),
                    data_recebimento=data_recebimento,
                    observacao=(observacao or "").strip(),
                    preparado_por=usuario,
                )
        except IntegrityError:
            # A última barreira: outro pedido do mesmo fornecedor gravou a mesma NF ao mesmo tempo.
            usada = _nf_usada_por(pedido, nf)
            texto = (
                f"A NF {numero_nf} deste fornecedor já está no recebimento {usada}."
                if usada
                else f"A NF {numero_nf} deste fornecedor já foi usada."
            )
            return Resposta(False, erros=[regras.Erro("nf", texto)], motivo="erros")
        _gravar_itens(recebimento, itens)
    return Resposta(
        True, f"{recebimento.rotulo} preparado: vai para a fila do robô.", recebimento=recebimento
    )


def _travar_recebimento(recebimento_id: int) -> tuple[PedidoCompra, Recebimento] | None:
    """Trava o pedido e depois o recebimento (sempre nesta ordem) e devolve os dois."""
    bruto = (
        Recebimento.objects.filter(pk=recebimento_id).values_list("pedido_id", flat=True).first()
    )
    if bruto is None:
        return None
    pedido = PedidoCompra.objects.select_for_update().get(pk=bruto)
    return pedido, Recebimento.objects.select_for_update().get(pk=recebimento_id)


def editar_recebimento(
    recebimento_id: int,
    usuario,
    *,
    versao: int,
    nf: str,
    data_recebimento: date | None,
    observacao: str = "",
    itens: dict[int, str],
    hoje: date | None = None,
) -> Resposta:
    """Edita um recebimento ainda sem tentativa do robô: recria os itens e soma 1 na versão."""
    hoje = hoje or timezone.localdate()
    with transaction.atomic():
        travados = _travar_recebimento(recebimento_id)
        if travados is None:
            return Resposta(False, "Recebimento não encontrado.", motivo="nao_encontrado")
        pedido, recebimento = travados
        if tem_tentativa(recebimento):
            return Resposta(False, MENSAGEM_TENTATIVA, recebimento=recebimento, motivo="tentativa")
        if recebimento.status not in ABERTOS_PARA_EDITAR:
            return Resposta(
                False,
                f"O {recebimento.rotulo} está {recebimento.get_status_display().lower()} e "
                "não pode ser editado.",
                recebimento=recebimento,
                motivo="estado",
            )
        if versao != recebimento.versao:
            if _mesmo_conteudo(
                recebimento,
                nf=nf,
                data_recebimento=data_recebimento,
                observacao=observacao,
                itens=itens,
            ):
                return Resposta(
                    True,
                    f"{recebimento.rotulo} já estava salvo.",
                    recebimento=recebimento,
                    reenvio=True,
                )
            return Resposta(False, MENSAGEM_VERSAO, recebimento=recebimento, motivo="versao")

        erros = _validar(
            pedido,
            hoje,
            nf=nf,
            data_recebimento=data_recebimento,
            observacao=observacao,
            itens=itens,
            ignorar=recebimento.pk,
        )
        if erros:
            return Resposta(False, erros=erros, recebimento=recebimento, motivo="erros")

        numero_nf = regras.nf_normalizada(nf)
        try:
            with transaction.atomic():
                recebimento.nf = numero_nf
                recebimento.chave_nf = regras.chave_nf(pedido.fornecedor_codigo, numero_nf)
                recebimento.data_recebimento = data_recebimento
                recebimento.observacao = (observacao or "").strip()
                recebimento.status = Recebimento.Status.PREPARADO  # o erro volta à fila
                recebimento.mensagem = ""
                recebimento.versao += 1
                recebimento.alterado_por = usuario
                recebimento.alterado_em = timezone.now()
                recebimento.save()
        except IntegrityError:
            usada = _nf_usada_por(pedido, nf, ignorar=recebimento.pk) or "outro recebimento"
            texto = f"A NF {numero_nf} deste fornecedor já está no recebimento {usada}."
            return Resposta(False, erros=[regras.Erro("nf", texto)], motivo="erros")
        recebimento.itens.all().delete()
        _gravar_itens(recebimento, itens)
    return Resposta(True, f"{recebimento.rotulo} salvo.", recebimento=recebimento)


def cancelar_recebimento(recebimento_id: int, usuario, *, motivo: str) -> Resposta:
    """Cancela um recebimento sem tentativa do robô e libera a NF (`chave_nf` nula)."""
    motivo = (motivo or "").strip()
    with transaction.atomic():
        travados = _travar_recebimento(recebimento_id)
        if travados is None:
            return Resposta(False, "Recebimento não encontrado.", motivo="nao_encontrado")
        _, recebimento = travados
        if tem_tentativa(recebimento):
            return Resposta(False, MENSAGEM_TENTATIVA, recebimento=recebimento, motivo="tentativa")
        if recebimento.status not in ABERTOS_PARA_EDITAR:
            return Resposta(
                False,
                f"O {recebimento.rotulo} está {recebimento.get_status_display().lower()} e "
                "não pode ser cancelado.",
                recebimento=recebimento,
                motivo="estado",
            )
        if not motivo:
            return Resposta(
                False, "Informe o motivo do cancelamento.", recebimento=recebimento, motivo="motivo"
            )
        limite = Recebimento._meta.get_field("motivo_cancelamento").max_length
        recebimento.status = Recebimento.Status.CANCELADO
        recebimento.chave_nf = None
        recebimento.motivo_cancelamento = motivo[:limite]
        recebimento.versao += 1
        recebimento.alterado_por = usuario
        recebimento.alterado_em = timezone.now()
        recebimento.save()
    return Resposta(True, f"{recebimento.rotulo} cancelado.", recebimento=recebimento)


def travar_pedido(pedido_id: int, motivo: str, detalhe: str = "", **origem) -> TravaPedido:
    """Abre uma trava no pedido. `origem` pode trazer `execucao`, `importacao`, `extracao` e
    `recebimento`. Quem chama (o robô, a importação) não muda o resto do pedido."""
    with transaction.atomic():
        PedidoCompra.objects.select_for_update().get(pk=pedido_id)
        return TravaPedido.objects.create(
            pedido_id=pedido_id, motivo=motivo, detalhe=detalhe, **origem
        )


def destravar_pedido(pedido_id: int, usuario, *, motivo: str) -> Resposta:
    """Fecha todas as travas abertas do pedido. Exige o motivo e uma importação de pedidos
    bem-sucedida começada depois da trava aberta mais recente (R20)."""
    motivo = (motivo or "").strip()
    with transaction.atomic():
        try:
            pedido = PedidoCompra.objects.select_for_update().get(pk=pedido_id)
        except PedidoCompra.DoesNotExist:
            return Resposta(False, "Pedido não encontrado.", motivo="nao_encontrado")
        abertas = list(pedido.travas.filter(destravada_em__isnull=True).select_for_update())
        if not abertas:
            return Resposta(False, "Este pedido não tem trava aberta.", motivo="estado")
        if not motivo:
            return Resposta(False, "Informe o motivo do destravamento.", motivo="motivo")
        mais_recente = max(t.criada_em for t in abertas)
        ultima = consultas.ultima_importacao_pedidos()
        if ultima is None or ultima.inicio <= mais_recente:
            return Resposta(
                False,
                "Atualize os pedidos antes: a última importação é de antes da trava.",
                motivo="importacao",
            )
        agora = timezone.now()
        limite = TravaPedido._meta.get_field("motivo_destrave").max_length
        for trava in abertas:
            trava.destravada_em = agora
            trava.destravada_por = usuario
            trava.motivo_destrave = motivo[:limite]
            trava.save(update_fields=["destravada_em", "destravada_por", "motivo_destrave"])
    return Resposta(True, f"Pedido {pedido.rotulo} destravado.")
