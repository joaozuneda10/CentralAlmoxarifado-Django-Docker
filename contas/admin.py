from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from contas.forms import FormularioCriacaoAdmin, FormularioSenhaAdmin, FormularioUsuarioAdmin
from contas.models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    """O admin do usuário com a troca obrigatória da senha e as regras do solicitante (spec 013):
    criar a conta e definir a senha ligam `trocar_senha`; o formulário recusa o solicitante com
    papel da equipe ou sem nome completo."""

    form = FormularioUsuarioAdmin
    add_form = FormularioCriacaoAdmin
    change_password_form = FormularioSenhaAdmin
    list_display = (*UserAdmin.list_display, "trocar_senha")
    list_filter = (*UserAdmin.list_filter, "trocar_senha")
    fieldsets = (
        *UserAdmin.fieldsets[:2],
        (
            UserAdmin.fieldsets[2][0],
            {
                **UserAdmin.fieldsets[2][1],
                "fields": (*UserAdmin.fieldsets[2][1]["fields"], "trocar_senha"),
            },
        ),
        *UserAdmin.fieldsets[3:],
    )
