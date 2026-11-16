from django.urls import path

from . import views

app_name = "compras"

urlpatterns = [
    path("", views.pedidos, name="pedidos"),
    path("pedidos/<int:pk>/", views.pedido, name="pedido"),
    path("pedidos/<int:pk>/receber/", views.receber, name="receber"),
    path("recebimentos/<int:pk>/", views.recebimento, name="recebimento"),
    path("recebimentos/<int:pk>/editar/", views.editar_recebimento, name="editar_recebimento"),
    path(
        "recebimentos/<int:pk>/cancelar/", views.cancelar_recebimento, name="cancelar_recebimento"
    ),
]
