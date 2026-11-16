"""Cria o grupo Solicitante (spec 013), sem permissão nenhuma, para o administrador só marcá-lo nas
contas dos funcionários que pedem material. Não muda nenhum usuário."""

from django.db import migrations

# O mesmo texto de `contas.acesso.GRUPO_SOLICITANTE`, copiado de propósito: uma migration não pode
# mudar de comportamento se a constante mudar um dia.
NOME = "Solicitante"


def criar_grupo(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=NOME)


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contas", "0004_papeis"),
        ("contas", "0005_trocar_senha"),
    ]

    operations = [
        # Reverter não apaga o grupo: ele pode já ter usuários.
        migrations.RunPython(criar_grupo, migrations.RunPython.noop),
    ]
