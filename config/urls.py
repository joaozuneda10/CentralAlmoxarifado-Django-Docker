from django.contrib import admin
from django.urls import include, path

from contas.forms import FormularioEntradaAdmin

admin.site.site_header = "Central Almoxarifado — cadastros"
admin.site.site_title = "Central Almoxarifado"
admin.site.index_title = "Cadastros"
admin.site.login_form = FormularioEntradaAdmin

urlpatterns = [
    path("admin/", admin.site.urls),
    path("painel/catalogo/", include("catalogo.urls")),
    path("painel/automacoes/", include("automacoes.urls")),
    path("painel/compras/", include("compras.urls")),
    path("painel/", include("contas.urls")),
    path("", include("pedidos.urls")),
]
