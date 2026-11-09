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
        if eh_solicitante(self.request.user):
            return reverse(ponto_de_partida(self.request.user))
        return reverse(settings.LOGIN_REDIRECT_URL)


class TrocarSenha(PasswordChangeView):
    form_class = FormularioTrocaSenha
    template_name = "contas/trocar_senha.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["obrigatoria"] = self.request.user.trocar_senha
        return contexto

    def form_valid(self, form):
        # O `PasswordChangeView` grava a senha e mantém a sessão (`update_session_auth_hash`).
        resposta = super().form_valid(form)
        usuario = form.user
        if usuario.trocar_senha:
            usuario.trocar_senha = False
            usuario.save(update_fields=["trocar_senha"])
        messages.success(self.request, "Senha trocada.")
        return resposta

    def get_success_url(self):
        return reverse(ponto_de_partida(self.request.user))
