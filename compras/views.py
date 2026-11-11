"""As telas das compras (spec 014): a lista de pedidos, o pedido, o recebimento e as ações.

A view só lê e chama `compras.servicos`, a porta única de gravação. Quem abre é decidido pela
tabela de rotas (`contas.acesso.REGRAS_POR_ROTA`, permissão `contas.receber_compras`).
"""

import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from catalogo.models import Material
from compras import consultas, servicos
from compras.forms import FormularioCancelamento, FormularioRecebimento
from compras.models import ItemPedidoCompra, PedidoCompra, Recebimento, TravaPedido

POR_PAGINA = 50
RE_NUMERO_PEDIDO = re.compile(r"^(\d{1,5})(?:/(\d{2}))?$")
ABERTOS = ("PREPARADO", "ERRO", "EM_LANCAMENTO", "VERIFICAR")
FILTROS = [("", "Todos"), ("aberto", "Com recebimento aberto"), ("travados", "Travados")]


def _busca(consulta, texto: str):
    texto = texto.strip()
    if not texto:
        return consulta
    condicao = Q(fornecedor_codigo__iexact=texto) | Q(fornecedor_nome__icontains=texto)
    condicao |= Q(itens__codigo__icontains=texto)
    casou = RE_NUMERO_PEDIDO.match(texto)
    if casou:
        condicao |= Q(numero=int(casou.group(1)))
        if casou.group(2):
            condicao &= Q(ano=2000 + int(casou.group(2)))
    return consulta.filter(condicao).distinct()


@login_required
def pedidos(request):
    """Os pedidos do exercício com item com saldo ou recebimento aberto."""
    abertos = Recebimento.objects.filter(pedido=OuterRef("pk"), status__in=ABERTOS)
    # Item disponível, como a `regras.disponibilidade` (as 3 casas ficam para o detalhe): controle
    # por quantidade, saldo > 0, presente e com o código no cadastro, visível.
    com_saldo = ItemPedidoCompra.objects.filter(
        pedido=OuterRef("pk"),
        controle="Q",
        saldo_scpi__gt=0,
        ausente_desde__isnull=True,
    ).filter(Exists(Material.objects.filter(codigo=OuterRef("codigo"), oculto=False)))
    travas = TravaPedido.objects.filter(pedido=OuterRef("pk"), destravada_em__isnull=True)
    consulta = (
        PedidoCompra.objects.filter(exercicio=timezone.localdate().year)
        .annotate(tem_aberto=Exists(abertos), tem_saldo=Exists(com_saldo), tem_trava=Exists(travas))
        .filter(Q(tem_aberto=True) | Q(tem_saldo=True, ausente_desde__isnull=True))
    )
    filtro = request.GET.get("filtro", "")
    if filtro == "aberto":
        consulta = consulta.filter(tem_aberto=True)
    elif filtro == "travados":
        consulta = consulta.filter(tem_trava=True)
    busca = request.GET.get("q", "")
    consulta = _busca(consulta, busca)
    pagina = Paginator(consulta.order_by("-ano", "-numero"), POR_PAGINA).get_page(
        request.GET.get("pagina")
    )
    estados = consultas.estados_dos_pedidos(list(pagina.object_list))
    for pedido in pagina.object_list:
        pedido.estado = estados[pedido.pk]
        pedido.estado_texto = consultas.ESTADOS[pedido.estado]
    return render(
        request,
        "compras/pedidos.html",
        {
            "pagina": pagina,
            "busca": busca,
            "filtro": filtro,
            "filtros": FILTROS,
            "ultima_importacao": consultas.ultima_importacao_pedidos(),
        },
    )


def _pedido_com_saldos(pk: int, *, ignorar: int | None = None):
    pedido = get_object_or_404(PedidoCompra.objects.select_related("atualizado_por"), pk=pk)
    linhas = consultas.saldos_do_pedido(pedido, ignorar=ignorar)
    estado = consultas.estado_do_pedido(pedido, linhas)
    return pedido, linhas, estado


@login_required
@never_cache
def pedido(request, pk):
    pedido, linhas, estado = _pedido_com_saldos(pk)
    return render(
        request,
        "compras/pedido.html",
        {
            "pedido": pedido,
            "linhas": linhas,
            "estado": estado,
            "estado_texto": consultas.ESTADOS[estado],
            "recusa": consultas.recusa_do_pedido(estado),
            "recebimentos": pedido.recebimentos.select_related("preparado_por"),
            "travas": consultas.travas_abertas(pedido),
            "ultima_importacao": consultas.ultima_importacao_pedidos(),
            "pode_receber": estado in ("disponivel", "precisa_conferencia")
            and any(linha.motivo is None and linha.saldo_livre > 0 for linha in linhas),
        },
    )


def _contexto_formulario(
    pedido, linhas, estado, formulario, *, erros=(), recebimento=None, modo=""
):
    por_campo = {}
    for erro in erros:
        por_campo.setdefault(erro.campo, []).append(erro.mensagem)
    return {
        "pedido": pedido,
        "linhas": linhas,
        "estado": estado,
        "estado_texto": consultas.ESTADOS[estado],
        "recusa": consultas.recusa_do_pedido(estado),
        "formulario": formulario,
        "erros": list(erros),
        "erros_por_campo": por_campo,
        "recebimento": recebimento,
        "modo": modo,
        "hoje": timezone.localdate(),
    }


def _itens_do_post(formulario: FormularioRecebimento) -> dict[int, str]:
    return dict(formulario.marcados)


@login_required
@never_cache
def receber(request, pk):
    pedido, linhas, estado = _pedido_com_saldos(pk)
    modo = request.GET.get("modo", "parcial")
    modo = "total" if modo == "total" else "parcial"
    if request.method == "POST":
        formulario = FormularioRecebimento.do_post(request.POST, linhas)
        resposta = servicos.preparar_recebimento(
            pedido.pk,
            request.user,
            envio=formulario.envio,
            nf=formulario.nf,
            data_recebimento=formulario.data_recebimento,
            observacao=formulario.observacao,
            itens=_itens_do_post(formulario),
        )
        if resposta.ok:
            messages.success(request, resposta.mensagem)
            return redirect("compras:recebimento", pk=resposta.recebimento.pk)
        if resposta.divergente:
            messages.error(request, resposta.mensagem)
            return redirect("compras:recebimento", pk=resposta.recebimento.pk)
        if resposta.motivo == "nao_encontrado":
            raise Http404
        pedido, linhas, estado = _pedido_com_saldos(pk)
        contexto = _contexto_formulario(
            pedido, linhas, estado, formulario, erros=resposta.erros, modo=modo
        )
        return render(request, "compras/receber.html", contexto, status=422)
    formulario = FormularioRecebimento.novo(modo, linhas)
    return render(
        request,
        "compras/receber.html",
        _contexto_formulario(pedido, linhas, estado, formulario, modo=modo),
    )


@login_required
@never_cache
def recebimento(request, pk):
    recebimento = get_object_or_404(
        Recebimento.objects.select_related("pedido", "preparado_por", "alterado_por"), pk=pk
    )
    itens = recebimento.itens.select_related("item")
    pode_alterar = (
        recebimento.status in servicos.ABERTOS_PARA_EDITAR
        and not servicos.tem_tentativa(recebimento)
    )
    return render(
        request,
        "compras/recebimento.html",
        {
            "recebimento": recebimento,
            "pedido": recebimento.pedido,
            "itens": itens,
            "pode_alterar": pode_alterar,
        },
    )


@login_required
@never_cache
def editar_recebimento(request, pk):
    recebimento = get_object_or_404(Recebimento.objects.select_related("pedido"), pk=pk)
    pedido, linhas, estado = _pedido_com_saldos(recebimento.pedido_id, ignorar=recebimento.pk)
    if request.method == "POST":
        formulario = FormularioRecebimento.do_post(request.POST, linhas)
        resposta = servicos.editar_recebimento(
            recebimento.pk,
            request.user,
            versao=formulario.versao if formulario.versao is not None else -1,
            nf=formulario.nf,
            data_recebimento=formulario.data_recebimento,
            observacao=formulario.observacao,
            itens=_itens_do_post(formulario),
        )
        if resposta.ok:
            messages.success(request, resposta.mensagem)
            return redirect("compras:recebimento", pk=recebimento.pk)
        if resposta.motivo in ("tentativa", "estado", "versao"):
            messages.error(request, resposta.mensagem)
            return redirect("compras:recebimento", pk=recebimento.pk)
        pedido, linhas, estado = _pedido_com_saldos(pedido.pk, ignorar=recebimento.pk)
        contexto = _contexto_formulario(
            pedido, linhas, estado, formulario, erros=resposta.erros, recebimento=recebimento
        )
        return render(request, "compras/receber.html", contexto, status=422)
    if recebimento.status not in servicos.ABERTOS_PARA_EDITAR or servicos.tem_tentativa(
        recebimento
    ):
        messages.error(request, servicos.MENSAGEM_TENTATIVA)
        return redirect("compras:recebimento", pk=recebimento.pk)
    formulario = FormularioRecebimento.de(recebimento)
    return render(
        request,
        "compras/receber.html",
        _contexto_formulario(pedido, linhas, estado, formulario, recebimento=recebimento),
    )


@login_required
@require_POST
def cancelar_recebimento(request, pk):
    recebimento = get_object_or_404(Recebimento, pk=pk)
    formulario = FormularioCancelamento.do_post(request.POST)
    if not formulario.confirmado:
        messages.error(request, "Confirme o cancelamento antes de continuar.")
        return redirect("compras:recebimento", pk=recebimento.pk)
    resposta = servicos.cancelar_recebimento(recebimento.pk, request.user, motivo=formulario.motivo)
    (messages.success if resposta.ok else messages.error)(request, resposta.mensagem)
    return redirect("compras:recebimento", pk=recebimento.pk)
