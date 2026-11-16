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
from compras.models import (
    IncertoConsumido,
    ItemRecebimento,
    PedidoCompra,
    Recebimento,
    TentativaEntrada,
    TravaPedido,
)
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
    não edita nem cancela sem as provas da verificação. Vale o estado (lado seguro) ou uma
    `TentativaEntrada` `LANCADA` ou `VERIFICAR`; a tentativa `ERRO` ou `IGNORADA` não passou pelo
    Salvar e não conta (R6)."""
    return (
        recebimento.status in COM_TENTATIVA
        or TentativaEntrada.objects.filter(
            recebimento=recebimento,
            resultado__in=(
                TentativaEntrada.Resultado.LANCADA,
                TentativaEntrada.Resultado.VERIFICAR,
            ),
        ).exists()
    )


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
            if existente.status == Recebimento.Status.CANCELADO:
                return Resposta(
                    False,
                    f"{existente.rotulo} foi cancelado: nada foi preparado de novo. "
                    "Faça um recebimento novo se ainda for preciso.",
                    recebimento=existente,
                    divergente=True,
                    motivo="cancelado",
                )
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
        nova_chave = regras.chave_nf(pedido.fornecedor_codigo, numero_nf)
        if nova_chave != recebimento.chave_nf and _ja_foi_ao_salvar(recebimento):
            # A NF já passou pelo Salvar do robô: trocar a chave aqui (a NF, ou o fornecedor que
            # uma reimportação mudou no pedido) soltaria a reserva da original, que outro
            # recebimento poderia usar.
            texto = (
                f"A NF {recebimento.nf} não pode ser trocada: o robô já tentou lançar este "
                "recebimento. Para outra NF, cancele este e prepare um novo."
                if numero_nf != recebimento.nf
                else "O fornecedor do pedido mudou depois que o robô tentou lançar este "
                "recebimento, e a NF reservada não pode mudar de fornecedor. Cancele este e "
                "prepare um novo."
            )
            return Resposta(
                False, erros=[regras.Erro("nf", texto)], recebimento=recebimento, motivo="erros"
            )
        try:
            with transaction.atomic():
                recebimento.nf = numero_nf
                recebimento.chave_nf = nova_chave
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


def _ja_foi_ao_salvar(recebimento: Recebimento) -> bool:
    """Se alguma tentativa do recebimento chegou ao `EM_LANCAMENTO` e depois foi liberada para
    relançar. A liberação tira a trava da edição (as três provas dizem que nada foi salvo), mas
    o fato fica na foto da tentativa, e a NF de quem passou por ele nunca volta a ficar livre."""
    return any(
        "liberada" in (foto or {})
        for foto in TentativaEntrada.objects.filter(recebimento=recebimento).values_list(
            "foto", flat=True
        )
    )


def cancelar_recebimento(recebimento_id: int, usuario, *, motivo: str) -> Resposta:
    """Cancela um recebimento sem tentativa do robô e libera a NF (`chave_nf` nula). O que já foi
    ao Salvar e foi liberado para relançar também se cancela aqui, mas a NF continua reservada,
    como no cancelamento da verificação."""
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
        reservada = _ja_foi_ao_salvar(recebimento)
        recebimento.status = Recebimento.Status.CANCELADO
        if not reservada:
            recebimento.chave_nf = None
        recebimento.motivo_cancelamento = motivo[:limite]
        recebimento.versao += 1
        recebimento.alterado_por = usuario
        recebimento.alterado_em = timezone.now()
        recebimento.save()
    final = f"{recebimento.rotulo} cancelado"
    final += "; a NF continua reservada (o robô já tentou lançá-lo)." if reservada else "."
    return Resposta(True, final, recebimento=recebimento)


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
        ultima = consultas.ultima_importacao_pedidos(pedido.exercicio)
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


# --- Resolver um recebimento em verificação (PR 5) -----------------------------------------------

ACOES_DE_VERIFICACAO = ("e_esta", "liberar", "cancelar")
MENSAGEM_LANCAMENTO_EM_ANDAMENTO = "Há um lançamento em andamento. Resolva quando ele terminar."


def resolver_recebimento(
    recebimento_id: int,
    usuario,
    *,
    acao: str,
    requisicao_id: int | None = None,
    conferi: bool = False,
    motivo: str = "",
    confirmado: bool = False,
    agora=None,
) -> Resposta:
    """Resolve um recebimento que o robô deixou em verificação (ou em lançamento): "É esta" liga a
    requisição candidata como lançada; "Liberar para relançar" e "Cancelar" exigem as três provas
    (`consultas.liberacao`, R16). Corre sob a `TRAVA_LANCAMENTO` (recusa com um robô rodando) e
    trava o pedido e o recebimento."""
    from pedidos.models import TRAVA_LANCAMENTO, ExecucaoRobo
    from scpi.execucao import trava

    if acao not in ACOES_DE_VERIFICACAO:
        return Resposta(False, "Ação desconhecida.", motivo="acao")
    agora = agora or timezone.now()
    if ExecucaoRobo.em_andamento(agora).exists():
        return Resposta(False, MENSAGEM_LANCAMENTO_EM_ANDAMENTO, motivo="andamento")
    # A trava do lançamento fica com a resolução do começo ao fim: um robô que comece agora não
    # pega o recebimento que esta resolução está liberando.
    with trava(TRAVA_LANCAMENTO) as obtida:
        if not obtida:
            return Resposta(False, MENSAGEM_LANCAMENTO_EM_ANDAMENTO, motivo="andamento")
        with transaction.atomic():
            return _resolver(
                recebimento_id, usuario, acao, requisicao_id, conferi, motivo, confirmado, agora
            )


def _resolver(recebimento_id, usuario, acao, requisicao_id, conferi, motivo, confirmado, agora):
    travados = _travar_recebimento(recebimento_id)
    if travados is None:
        return Resposta(False, "Recebimento não encontrado.", motivo="nao_encontrado")
    pedido, recebimento = travados
    if recebimento.status not in (
        Recebimento.Status.VERIFICAR,
        Recebimento.Status.EM_LANCAMENTO,
    ):
        return Resposta(
            False,
            f"O {recebimento.rotulo} está {recebimento.get_status_display().lower()}: "
            "só um recebimento em verificação se resolve aqui.",
            recebimento=recebimento,
            motivo="estado",
        )
    quem = f"por {usuario.username} em {timezone.localtime(agora):%d/%m/%Y %H:%M}"
    if acao == "e_esta":
        return _e_esta(recebimento, requisicao_id, quem, agora)
    motivo = (motivo or "").strip()
    if acao == "liberar" and not conferi:
        return Resposta(
            False,
            "Antes de liberar, confira no SCPI que a entrada não foi gravada e marque a "
            "confirmação.",
            recebimento=recebimento,
            motivo="conferi",
        )
    if acao == "cancelar":
        if not motivo:
            return Resposta(
                False, "Informe o motivo do cancelamento.", recebimento=recebimento, motivo="motivo"
            )
        if not confirmado:
            return Resposta(
                False, "Confirme antes de cancelar.", recebimento=recebimento, motivo="confirmacao"
            )
    faltas = consultas.liberacao(recebimento)
    if faltas:
        return Resposta(False, " ".join(faltas), recebimento=recebimento, motivo="provas")
    if acao == "liberar":
        recebimento.status = Recebimento.Status.PREPARADO
        recebimento.mensagem = f"Liberado para relançar {quem}."
        recebimento.requisicao_scpi = ""
        recebimento.lancado_em = None
        recebimento.visivel_desde = None
        recebimento.via = ""
        # A tentativa estava a verificar: as três provas dizem que nada foi salvo. Daí em diante
        # ela não trava a edição nem o cancelamento do recebimento, que voltou à fila.
        ultima = TentativaEntrada.objects.filter(
            recebimento=recebimento, resultado=TentativaEntrada.Resultado.VERIFICAR
        )
        for tentativa in ultima:
            tentativa.resultado = TentativaEntrada.Resultado.IGNORADA
            tentativa.foto = {**(tentativa.foto or {}), "liberada": quem}
            tentativa.save(update_fields=["resultado", "foto"])
        # O consumo era da tentativa que acabou de ser descartada: a nova, se for a verificar,
        # volta a poder explicar um aumento do "Já Entrou" (R19).
        IncertoConsumido.objects.filter(recebimento=recebimento).delete()
        final = f"{recebimento.rotulo} liberado para o próximo lançamento."
    else:
        limite = Recebimento._meta.get_field("motivo_cancelamento").max_length
        recebimento.status = Recebimento.Status.CANCELADO
        recebimento.motivo_cancelamento = motivo[:limite]
        # A NF continua reservada (`chave_nf`): houve tentativa do robô.
        final = f"{recebimento.rotulo} cancelado; a NF continua reservada."
    recebimento.versao += 1
    recebimento.alterado_por = usuario
    recebimento.alterado_em = agora
    recebimento.save()
    return Resposta(True, final, recebimento=recebimento)


def _e_esta(recebimento, requisicao_id, quem, agora) -> Resposta:
    """Liga ao recebimento a requisição que é uma candidata dele e que não é de outro."""
    from compras.models import CandidataEntrada

    candidata = (
        CandidataEntrada.objects.filter(
            conferencia__recebimento=recebimento, requisicao_id=requisicao_id
        )
        .select_related("requisicao", "conferencia__extracao__importacao")
        .order_by("-conferencia__criada_em")
        .first()
        if requisicao_id
        else None
    )
    if candidata is None:
        return Resposta(
            False,
            "Escolha uma das requisições candidatas deste recebimento.",
            recebimento=recebimento,
            motivo="candidata",
        )
    numero = candidata.requisicao.requisicao
    outro = (
        Recebimento.objects.filter(requisicao_scpi=numero)
        .exclude(pk=recebimento.pk)
        .exclude(status=Recebimento.Status.CANCELADO)
        .first()
    )
    if outro is not None:
        return Resposta(
            False,
            f"A requisição {numero} já está ligada ao {outro.rotulo}.",
            recebimento=recebimento,
            motivo="ligada",
        )
    inicio = candidata.conferencia.extracao.importacao.inicio
    recebimento.status = Recebimento.Status.LANCADO
    recebimento.requisicao_scpi = numero
    # `lancado_em` é o momento da resolução, não o da entrada (o Salvar incerto foi antes, numa
    # hora que ninguém sabe): diferente do `visivel_desde`, é o que marca a hora incerta para a
    # explicação do "Já Entrou" (`importacao._explicar_ja_entrou`).
    recebimento.lancado_em = agora
    recebimento.via = Recebimento.Via.ROBO
    recebimento.visivel_desde = inicio
    recebimento.mensagem = f"Requisição {numero} informada {quem}."
    recebimento.versao += 1
    recebimento.save()
    TentativaEntrada.objects.filter(
        recebimento=recebimento, resultado=TentativaEntrada.Resultado.VERIFICAR
    ).update(resultado=TentativaEntrada.Resultado.LANCADA, requisicao=numero)
    return Resposta(
        True, f"{recebimento.rotulo}: requisição {numero} registrada.", recebimento=recebimento
    )


def ligar_a_mao(recebimento_id: int, requisicao: str, visivel_desde) -> Resposta:
    """Liga a um recebimento aberto (preparado, com erro ou em verificação) a requisição que alguém
    fez à mão no SCPI com a mesma NF e o mesmo fornecedor (R18): ele passa a lançado, com
    `via=MANUAL`, o número e o `visivel_desde` (o início da extração que a viu), e sai da fila do
    robô. Um recebimento em lançamento nunca é ligado: a conciliação não roda com robô rodando."""
    with transaction.atomic():
        travados = _travar_recebimento(recebimento_id)
        if travados is None:
            return Resposta(False, "Recebimento não encontrado.", motivo="nao_encontrado")
        _, recebimento = travados
        if recebimento.status not in (
            Recebimento.Status.PREPARADO,
            Recebimento.Status.ERRO,
            Recebimento.Status.VERIFICAR,
        ):
            return Resposta(
                False, "O recebimento não está aberto.", recebimento=recebimento, motivo="estado"
            )
        agora = timezone.now()
        recebimento.status = Recebimento.Status.LANCADO
        recebimento.requisicao_scpi = requisicao
        recebimento.lancado_em = agora
        recebimento.via = Recebimento.Via.MANUAL
        recebimento.visivel_desde = visivel_desde
        recebimento.mensagem = f"Entrada {requisicao} feita à mão no SCPI, ligada pela NF."
        recebimento.versao += 1
        recebimento.save()
        TentativaEntrada.objects.filter(
            recebimento=recebimento, resultado=TentativaEntrada.Resultado.VERIFICAR
        ).update(resultado=TentativaEntrada.Resultado.LANCADA, requisicao=requisicao)
    return Resposta(
        True, f"{recebimento.rotulo} ligado à requisição {requisicao}.", recebimento=recebimento
    )
