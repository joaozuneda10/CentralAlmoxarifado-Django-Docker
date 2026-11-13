from django.db import migrations


def marcar_origem_desconhecida(apps, schema_editor):
    """As importações de pedidos de compra de antes do campo `de_arquivo` não guardaram a origem
    (podem ter vindo de um CSV já baixado): ficam como de arquivo, o lado seguro, e não servem de
    prova do "Já Entrou" de depois de uma tentativa. As novas gravam a origem certa."""
    Importacao = apps.get_model("catalogo", "Importacao")
    Importacao.objects.filter(tipo="PEDIDOS_COMPRA").update(de_arquivo=True)


class Migration(migrations.Migration):
    dependencies = [
        ("catalogo", "0011_importacao_de_arquivo"),
    ]

    operations = [
        migrations.RunPython(marcar_origem_desconhecida, migrations.RunPython.noop),
    ]
