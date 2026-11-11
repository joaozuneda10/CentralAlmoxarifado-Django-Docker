from django.core.management import BaseCommand, CommandError

from catalogo.models import Importacao
from compras import importacao
from compras.models import ItemPedidoCompra, PedidoCompra
from scpi import execucao, relatorios
from scpi.management.comum import NOMES, descartar_arquivo, obter_csv


class Command(BaseCommand):
    help = (
        "Importa os pedidos de compra do SCPI (07.13, com saldo a entregar); o que some do "
        "relatório fica ausente, nunca é apagado."
    )

    def add_arguments(self, parser):
        parser.add_argument("--arquivo", help="CSV já baixado do SCPI (não abre o navegador).")
        parser.add_argument(
            "--apagar-arquivo",
            action="store_true",
            help="Apaga o CSV de --arquivo ao terminar (usado pelo upload da tela).",
        )
        parser.add_argument(
            "--forcar",
            action="store_true",
            help="Grava mesmo que mais de 20%% dos itens presentes sumam do relatório.",
        )

    def handle(self, *args, arquivo=None, apagar_arquivo=False, forcar=False, **opcoes):
        with descartar_arquivo(arquivo, apagar_arquivo):
            try:
                imp = importacao.importar(
                    obter_csv(arquivo, relatorios.baixar_pedidos_compra), forcar=forcar
                )
            except execucao.ImportacaoEmAndamento:
                raise CommandError(
                    f"Importação de {NOMES[Importacao.Tipo.PEDIDOS_COMPRA]} já em andamento."
                ) from None
        if imp.situacao == Importacao.Situacao.FALHA:
            raise CommandError(imp.erro)
        pedidos = PedidoCompra.objects.filter(atualizado_por=imp).count()
        novos = PedidoCompra.objects.filter(
            atualizado_por=imp, itens__ja_entrou_anterior__isnull=True
        )
        ausentes_itens = ItemPedidoCompra.objects.filter(ausente_desde=imp).count()
        ausentes_pedidos = PedidoCompra.objects.filter(ausente_desde=imp).count()
        self.stdout.write(
            f"Pedidos de compra: {pedidos} {'pedido' if pedidos == 1 else 'pedidos'}, "
            f"{imp.linhas} {'item' if imp.linhas == 1 else 'itens'} "
            f"({novos.distinct().count()} com itens novos); "
            f"ausentes agora: {ausentes_pedidos} pedidos e {ausentes_itens} itens."
        )
        for aviso in imp.avisos:
            self.stdout.write(f"  Aviso: {aviso}")
