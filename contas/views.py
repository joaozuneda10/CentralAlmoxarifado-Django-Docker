"""Entrar e trocar a senha (spec 013).

`Entrar` é o `LoginView` de sempre (mesmo formulário e mesmo template), mas leva cada um ao seu
ponto de partida: o solicitante a "Meus pedidos", a equipe ao `LOGIN_REDIRECT_URL`.
`TrocarSenha` é a troca pelo próprio usuário, obrigatória para o solicitante com a marca
`trocar_senha`.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.urls import reverse

from contas.acesso import eh_solicitante, ponto_de_partida
from contas.forms import FormularioEntrada, FormularioTrocaSenha


class Entrar(LoginView):
    template_name = "contas/entrar.html"
    authentication_form = FormularioEntrada
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        """Sem `next`: o solicitante vai a "Meus pedidos"; a equipe, ao painel (a Segurança do
        Trabalho é levada à fila pelo middleware dela)."""
        usuario = self.request.user
        destino = ponto_de_partida(usuario)
        if eh_solicitante(usuario) or destino == "compras:pedidos":
            return reverse(destino)
        return reverse(settings.LOGIN_REDIRECT_URL)


class TrocarSenha(PasswordChangeView):
    form_class = FormularioTrocaSenha
    template_name = "contas/trocar_senha.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["obrigatoria"] = self.request.user.trocar_senha
        return contexto

    def form_valid(self, form):
        # A marca desligada antes do `form.save()` (no `super`), que grava o usuário inteiro: a
        # senha nova e a marca saem na mesma gravação, e uma nunca fica sem a outra. O
        # `PasswordChangeView` também mantém a sessão (`update_session_auth_hash`).
        form.user.trocar_senha = False
        resposta = super().form_valid(form)
        messages.success(self.request, "Senha trocada.")
        return resposta

    def get_success_url(self):
        return reverse(ponto_de_partida(self.request.user))
