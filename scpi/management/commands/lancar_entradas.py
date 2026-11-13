from django.core.management import BaseCommand, CommandError
from django.utils import timezone

from compras import robo
from pedidos.models import ExecucaoRobo
from scpi.lancador_entradas import navegador
from scpi.lancamento import LancamentoEmAndamento
from scpi.lancamento_entradas import executar_lancamento_entradas
from scpi.leitura import ErroImportacao
from scpi.relatorios import baixar_entradas
from scpi.requisicoes import FalhaCritica


class Command(BaseCommand):
    help = (
        "Lança no SCPI os recebimentos preparados de pedidos de compra, uma requisição de entrada "
        "por recebimento (ou só os simula)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--execucao",
            type=int,
            help="Execução já criada pelo botão da página (em andamento).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Abre o pedido, confere e preenche a tela e descarta, sem salvar nada.",
        )
        parser.add_argument(
            "--recebimento",
            action="append",
            dest="recebimentos",
            default=[],
            metavar="RC-0001",
            help="Número do recebimento (RC-0001) a processar; repita para mais de um.",
        )

    def handle(self, *args, execucao=None, dry_run=False, recebimentos=(), **opcoes):
        recebimentos = [r.strip() for r in recebimentos if r.strip()]
        if not recebimentos:
            raise CommandError(
                "Informe ao menos um recebimento com --recebimento (ex.: --recebimento RC-0001)."
            )
        registro = None
        if execucao is not None:
            registro = ExecucaoRobo.objects.filter(
                pk=execucao,
                robo=ExecucaoRobo.Robo.ENTRADAS,
                situacao=ExecucaoRobo.Situacao.ANDAMENTO,
            ).first()
            if registro is None:
                raise CommandError(f"Execução {execucao} não encontrada ou já encerrada.")

        # A simulação nunca vira lançamento real: um dos dois basta, e o que valer fica gravado.
        simulacao = dry_run or (registro is not None and registro.simulacao)

        # O modo é decidido antes de qualquer trabalho: com o lançamento real bloqueado, só a
        # simulação segue. Sem execução do botão, nada é criado; com ela, ela termina em falha.
        if not simulacao and not robo.lancamento_real_liberado():
            bloqueio = robo.motivo_do_bloqueio_real()
            if registro is not None:
                registro.situacao = ExecucaoRobo.Situacao.FALHA
                registro.erro = bloqueio
                registro.fim = timezone.now()
                registro.save(update_fields=["situacao", "erro", "fim"])
            raise CommandError(bloqueio)

        if registro is None:
            registro = ExecucaoRobo.objects.create(
                iniciada_por=None, robo=ExecucaoRobo.Robo.ENTRADAS
            )
        registro.simulacao = simulacao
        registro.save(update_fields=["simulacao"])

        try:
            registro = executar_lancamento_entradas(
                registro, navegador, recebimentos=recebimentos, extrair=baixar_entradas
            )
        except LancamentoEmAndamento as exc:
            raise CommandError(str(exc)) from exc
        except FalhaCritica as exc:
            raise CommandError(str(exc), returncode=2) from exc
        except ErroImportacao as exc:  # o SCPI não abriu, ou a extração de antes falhou
            raise CommandError(str(exc)) from exc

        if registro.situacao == ExecucaoRobo.Situacao.ATENCAO:
            raise CommandError("Lançamento terminou com erros ou recebimentos a verificar.")
        r = registro.resumo
        self.stdout.write(
            f"Lançados: {r['lancadas']} · simulados: {r['simuladas']} · falhas: {r['falhas']} · "
            f"verificar: {r['verificar']} · ignorados: {r['ignoradas']}"
        )
