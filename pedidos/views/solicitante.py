"""A página Meus pedidos (spec 013): o solicitante logado acompanha os pedidos que fez com a conta.

Quem abre é decidido pela tabela de rotas (`contas.acesso`, categoria `SOLICITANTE`): aqui o
usuário já é um solicitante. Toda busca filtra pela conta logada, e o template só recebe o que
`pedidos.minhas` monta, nunca o `Pedido` (spec, FR-020).
"""

from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from pedidos.minhas import POR_PAGINA, apresentar, linha_da_lista
from pedidos.models import Pedido


@never_cache
@require_GET
def meus_pedidos(request):
    """A lista dos pedidos da conta, do mais novo, em páginas de `POR_PAGINA`."""
    pedidos = (
        Pedido.objects.filter(conta=request.user)
        .select_related("atendimento", "autorizacao")
        .prefetch_related("itens")
        .order_by("-criado_em")
    )
    pagina = Paginator(pedidos, POR_PAGINA).get_page(request.GET.get("pagina"))
    return render(
        request,
        "pedidos/meus_pedidos.html",
        {"pagina": pagina, "linhas": [linha_da_lista(p) for p in pagina]},
    )


@never_cache
@require_GET
def meu_pedido(request, numero):
    """Um pedido da conta. De outra conta, anônimo ou inexistente: a mesma resposta 404."""
    pedido = get_object_or_404(
        Pedido.objects.select_related("atendimento", "autorizacao").prefetch_related("itens"),
        numero=numero,
        conta=request.user,
    )
    return render(request, "pedidos/meu_pedido.html", {"pedido": apresentar(pedido)})
