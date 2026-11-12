from django.contrib import admin

from catalogo.admin import SoLeituraAdmin

from .models import ItemPedidoCompra, PedidoCompra


class ItemPedidoCompraInline(admin.TabularInline):
    model = ItemPedidoCompra
    extra = 0
    can_delete = False
    fields = (
        "item",
        "codigo",
        "unidade",
        "controle",
        "quantidade",
        "anulado",
        "ja_entrou",
        "pedida",
        "saldo_scpi",
        "ausente_desde",
    )

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PedidoCompra)
class PedidoCompraAdmin(SoLeituraAdmin):
    list_display = (
        "rotulo",
        "data",
        "fornecedor_codigo",
        "fornecedor_nome",
        "exercicio",
        "ausente_desde",
    )
    list_filter = ("exercicio",)
    search_fields = ("numero", "fornecedor_codigo", "fornecedor_nome", "itens__codigo")
    list_select_related = ("ausente_desde",)
    inlines = [ItemPedidoCompraInline]
