from django.urls import path

from automacoes import views

app_name = "automacoes"

urlpatterns = [
    path("", views.pagina, name="pagina"),
    path("atualizar/", views.atualizar, name="atualizar"),
    path("importar/<str:robo>/", views.importar, name="importar"),
    path("lancar/", views.lancar, name="lancar"),
    path("entradas/lancar/", views.lancar_entradas, name="lancar_entradas"),
    path("entradas/<int:pk>/resolver/", views.resolver_entrada, name="resolver_entrada"),
    path("entradas/conferir/", views.conferir_entradas, name="conferir_entradas"),
    path(
        "entradas/pedidos/<int:pk>/destravar/",
        views.destravar_pedido_entradas,
        name="destravar_pedido",
    ),
    path("lancamento/<str:lote>/resolver/", views.resolver, name="resolver"),
    path("lancamento/conferir/", views.conferir, name="conferir"),
    path("lancamento/<str:lote>/corrigir/", views.corrigir, name="corrigir"),
]
