from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.forms import (
    AdminPasswordChangeForm,
    AdminUserCreationForm,
    AuthenticationForm,
    PasswordChangeForm,
    UserChangeForm,
)
from django.core.exceptions import ValidationError

from contas.acesso import (
    GRUPO_ATENDIMENTO,
    GRUPO_GESTAO,
    GRUPO_SEGURANCA_TRABALHO,
    GRUPO_SOLICITANTE,
)


class FormularioEntrada(AuthenticationForm):
    """Login por matrícula.

    A tradução pt-BR do Django interpola o rótulo do campo e produz "entre com um matrícula";
    a recusa aqui é uma frase própria e genérica, igual para senha errada, matrícula
    desconhecida e conta desativada.
    """

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Matrícula ou senha incorretas.",
        "inactive": "Matrícula ou senha incorretas.",
    }


class FormularioEntradaAdmin(AdminAuthenticationForm):
    """Login do admin, com a mesma recusa em português correto do `FormularioEntrada`."""

    error_messages = {
        **AdminAuthenticationForm.error_messages,
        "invalid_login": "Matrícula ou senha incorretas, ou a conta não tem acesso aos cadastros.",
        "inactive": "Matrícula ou senha incorretas, ou a conta não tem acesso aos cadastros.",
    }


class FormularioTrocaSenha(PasswordChangeForm):
    """A troca de senha pelo próprio usuário (spec 013), com os rótulos em português do projeto. A
    senha nova passa pelos `AUTH_PASSWORD_VALIDATORS` (no `PasswordChangeForm`) e não pode ser a
    atual."""

    error_messages = {
        **PasswordChangeForm.error_messages,
        "password_incorrect": "A senha atual não confere.",
        "password_mismatch": "As duas senhas novas não são iguais.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "Senha atual"
        self.fields["new_password1"].label = "Senha nova"
        self.fields["new_password2"].label = "Repita a senha nova"

    def clean_new_password1(self):
        nova = self.cleaned_data.get("new_password1")
        if nova and self.user.check_password(nova):
            raise ValidationError("A senha nova precisa ser diferente da atual.")
        return nova


MENSAGEM_SOLICITANTE_COM_PAPEL = (
    "Uma conta de solicitante não pode ter papel da equipe nem acesso ao admin."
)
MENSAGEM_SOLICITANTE_SEM_NOME = "Informe o nome completo: ele vai nos pedidos da conta."


class FormularioUsuarioAdmin(UserChangeForm):
    """O usuário no admin. O papel Solicitante não combina com os da equipe, com o admin nem com o
    superusuário (spec 013, FR-002), e o solicitante precisa do nome completo, que vai nos
    pedidos."""

    def clean(self):
        dados = super().clean()
        nomes = {g.name for g in dados.get("groups") or []}
        if GRUPO_SOLICITANTE not in nomes:
            return dados
        if (
            nomes & {GRUPO_ATENDIMENTO, GRUPO_GESTAO, GRUPO_SEGURANCA_TRABALHO}
            or dados.get("is_staff")
            or dados.get("is_superuser")
        ):
            self.add_error("groups", MENSAGEM_SOLICITANTE_COM_PAPEL)
        if (
            not (dados.get("first_name") or "").strip()
            or not (dados.get("last_name") or "").strip()
        ):
            self.add_error("first_name", MENSAGEM_SOLICITANTE_SEM_NOME)
        return dados


class FormularioCriacaoAdmin(AdminUserCreationForm):
    """A criação no admin liga a troca obrigatória: a senha foi definida por outra pessoa."""

    def save(self, commit=True):
        self.instance.trocar_senha = True
        return super().save(commit=commit)


class FormularioSenhaAdmin(AdminPasswordChangeForm):
    """A senha definida no admin ("Alterar senha") liga a troca obrigatória de novo."""

    def save(self, commit=True):
        self.user.trocar_senha = True
        return super().save(commit=commit)
