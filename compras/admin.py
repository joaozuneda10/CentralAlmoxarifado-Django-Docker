from django.contrib import admin

from catalogo.admin import SoLeituraAdmin

from .models import (
    ExtracaoEntradas,
    ItemEntradaOficial,
    ItemPedidoCompra,
    PedidoCompra,
    RequisicaoEntradaOficial,
)


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


@admin.register(ExtracaoEntradas)
class ExtracaoEntradasAdmin(SoLeituraAdmin):
    list_display = ("importacao", "motivo", "execucao", "requisicoes", "maior_requisicao")
    list_filter = ("motivo",)
    list_select_related = ("importacao", "execucao")
    exclude = ("arquivo",)


class ItemEntradaOficialInline(admin.TabularInline):
    model = ItemEntradaOficial
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(RequisicaoEntradaOficial)
class RequisicaoEntradaOficialAdmin(SoLeituraAdmin):
    list_display = (
        "requisicao",
        "data_entrada",
        "fornecedor_codigo",
        "nf",
        "recebimento_observado",
        "extracao",
    )
    search_fields = ("requisicao", "nf", "recebimento_observado", "fornecedor_codigo")
    list_select_related = ("extracao__importacao",)
    inlines = [ItemEntradaOficialInline]
