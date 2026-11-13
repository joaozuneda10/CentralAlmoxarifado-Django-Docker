from datetime import timedelta

from django.core.management import BaseCommand, CommandError
from django.utils import timezone

from catalogo.models import Importacao
from compras.extracao import extrair
from compras.models import ExtracaoEntradas, Recebimento
from conciliacao.regras import periodo as periodo_do_relatorio
from pedidos.models import ExecucaoRobo
from scpi import relatorios
from scpi.execucao import ImportacaoEmAndamento
from scpi.leitura import ErroImportacao, ler_entradas
from scpi.management.comum import data_opcao, obter_csv

# A extração diária e a conferência voltam 9 dias (spec 014, R22).
DIAS_DE_REVISAO = 9
EM_ABERTO = (Recebimento.Status.VERIFICAR, Recebimento.Status.EM_LANCAMENTO)


def periodo_padrao(agora):
    """Do dia anterior à menor destas datas até amanhã: hoje − 9 dias, a data de recebimento dos
    lançados nos últimos 9 dias e a dos recebimentos em verificação abertos."""
    hoje = timezone.localtime(agora).date()
    datas = [hoje - timedelta(days=DIAS_DE_REVISAO)]
    datas += Recebimento.objects.filter(
        status=Recebimento.Status.LANCADO,
        lancado_em__gte=agora - timedelta(days=DIAS_DE_REVISAO),
    ).values_list("data_recebimento", flat=True)
    datas += Recebimento.objects.filter(status__in=EM_ABERTO).values_list(
        "data_recebimento", flat=True
    )
    return periodo_do_relatorio(datas, hoje)


def periodo_do_arquivo(arquivo: str):
    """O período que um CSV já baixado cobre: as datas de entrada (DATAE) que ele traz."""
    with open(arquivo, "rb") as aberto:
        lidas = ler_entradas(aberto.read()).linhas
    datas = [lida.data_entrada for lida in lidas]
    return min(datas), max(datas)


class Command(BaseCommand):
    help = (
        "Extrai do SCPI a Relação de Requisições de Entrada (ou lê o --arquivo) e a guarda, o "
        "arquivo bruto e as requisições. Só lê o SCPI."
    )

    def add_arguments(self, parser):
        parser.add_argument("--arquivo", help="CSV já baixado do SCPI (não abre o navegador).")
        parser.add_argument("--desde", help="Início do período (dd/mm/aaaa).")
        parser.add_argument("--ate", help="Fim do período (dd/mm/aaaa).")
        parser.add_argument(
            "--diaria",
            action="store_true",
            help="Extração diária (o passo Entradas do atualizar_catalogo).",
        )
        parser.add_argument(
            "--sem-limpeza",
            action="store_true",
            help="Não roda a limpeza de 60 dias (a limpeza das entradas vem no PR 7).",
        )

    def handle(
        self, *args, arquivo=None, desde=None, ate=None, diaria=False, sem_limpeza=False, **opcoes
    ):
        if ExecucaoRobo.em_andamento().exists() or Importacao.em_andamento().exists():
            raise CommandError("Há lançamento ou importação em andamento; tente depois.")
        if bool(desde) != bool(ate):
            raise CommandError("Informe --desde e --ate juntos.")
        if desde:
            periodo = (data_opcao(desde), data_opcao(ate))
            if periodo[0] > periodo[1]:
                raise CommandError("O início do período é depois do fim.")
        elif arquivo:
            try:
                periodo = periodo_do_arquivo(arquivo)
            except ErroImportacao:
                # O arquivo não se lê, e o período dele não existe. A extração roda assim mesmo,
                # com o dia de hoje no lugar, para a falha ficar registrada com o bruto (a leitura
                # falha de novo em `extrair`, antes de o período ser conferido).
                hoje = timezone.localdate()
                periodo = (hoje, hoje)
            except OSError as exc:
                raise CommandError(f"Não foi possível ler {arquivo}: {exc.strerror}.") from None
        else:
            periodo = periodo_padrao(timezone.now())
        de, ate = periodo
        if arquivo:
            motivo = ExtracaoEntradas.Motivo.ARQUIVO
        elif diaria:
            motivo = ExtracaoEntradas.Motivo.DIARIA
        else:
            motivo = ExtracaoEntradas.Motivo.MANUAL
        try:
            extracao = extrair(
                motivo, periodo, obter_csv(arquivo, lambda: relatorios.baixar_entradas(de, ate))
            )
        except ImportacaoEmAndamento:
            raise CommandError("Extração de entradas do SCPI já em andamento.") from None
        if not extracao.bem_sucedida:
            raise CommandError(extracao.importacao.erro)
        maior = extracao.maior_requisicao or "nenhuma"
        self.stdout.write(
            f"Entradas do SCPI ({de:%d/%m/%Y} a {ate:%d/%m/%Y}): {extracao.requisicoes} "
            f"requisições, a maior {maior}."
        )
