"""Cria a permissão `receber_compras` e a dá aos grupos Atendimento e Gestão (spec 014).

Quem já estava nos dois grupos passa a abrir a área Compras sem ajuste: a migration confere no fim
que os dois grupos a têm (levanta erro e desfaz tudo se faltar). Nomes e codinomes copiados de
propósito: uma migration não pode mudar de comportamento se as constantes de `contas.acesso`
mudarem um dia.
"""

from django.db import migrations

CODINOME = "receber_compras"
NOME = "Receber compras (preparar, editar e cancelar recebimentos)"
GRUPOS = ("Atendimento", "Gestão")


def criar_permissao(apps):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    tipo, _ = ContentType.objects.get_or_create(app_label="contas", model="usuario")
    return Permission.objects.get_or_create(
        content_type=tipo, codename=CODINOME, defaults={"name": NOME}
    )[0]


def dar_aos_grupos(apps, permissao):
    Group = apps.get_model("auth", "Group")
    for nome in GRUPOS:
        grupo, _ = Group.objects.get_or_create(name=nome)
        grupo.permissions.add(permissao)


def conferir(apps):
    Group = apps.get_model("auth", "Group")
    sem = [
        nome
        for nome in GRUPOS
        if not Group.objects.filter(name=nome, permissions__codename=CODINOME).exists()
    ]
    if sem:
        raise RuntimeError("Grupos sem a permissão receber_compras depois da migração: " + ", ".join(sem))


def aplicar(apps, schema_editor):
    dar_aos_grupos(apps, criar_permissao(apps))
    conferir(apps)


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("contas", "0006_solicitante"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="usuario",
            options={
                "permissions": [
                    (
                        "atender_pedidos",
                        "Atender pedidos (painel, atendimento, edição e saída avulsa)",
                    ),
                    (
                        "operar_automacoes",
                        "Operar as automações (SCPI, importações e conferência)",
                    ),
                    ("ver_curva", "Ver a Curva ABC"),
                    ("ver_formularios", "Ver a configuração dos formulários"),
                    (
                        "receber_compras",
                        "Receber compras (preparar, editar e cancelar recebimentos)",
                    ),
                ],
                "verbose_name": "usuário",
                "verbose_name_plural": "usuários",
            },
        ),
        # Reverter não apaga permissão nem grupo: podem já ter sido ajustados à mão.
        migrations.RunPython(aplicar, migrations.RunPython.noop),
    ]
