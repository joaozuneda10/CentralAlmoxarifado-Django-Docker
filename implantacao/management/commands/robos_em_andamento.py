from django.core.management import BaseCommand, CommandError
from django.utils import timezone

from catalogo.models import Importacao
from pedidos.models import ExecucaoRobo


class Command(BaseCommand):
    help = (
        "Diz se algum robô (lançamento no SCPI ou importação do catálogo) está em andamento. "
        "Sai com erro se houver, para o script de atualização não reiniciar o serviço no meio."
    )

    def handle(self, *args, **options):
        linhas = []
        for execucao in ExecucaoRobo.em_andamento().order_by("inicio"):
            hora = timezone.localtime(execucao.inicio)
            linhas.append(f"- {execucao} desde {hora:%H:%M}")
        for importacao in Importacao.em_andamento().order_by("inicio"):
            hora = timezone.localtime(importacao.inicio)
            linhas.append(f"- Importação de {importacao.get_tipo_display()} desde {hora:%H:%M}")
        if not linhas:
            self.stdout.write("Nenhum robô em andamento.")
            return
        raise CommandError("Há robô em andamento; espere terminar:\n" + "\n".join(linhas))
