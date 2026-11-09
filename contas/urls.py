from django.contrib.auth.views import LogoutView
from django.urls import path

from contas.views import Entrar, TrocarSenha

# Sem `app_name`: `LOGIN_URL = "login"` e `LOGOUT_REDIRECT_URL = "login"` usam nomes globais.
urlpatterns = [
    path("entrar/", Entrar.as_view(), name="login"),
    path("sair/", LogoutView.as_view(), name="logout"),
    # A troca de senha de qualquer usuário logado; obrigatória para o solicitante (spec 013).
    path("senha/", TrocarSenha.as_view(), name="trocar_senha"),
]
