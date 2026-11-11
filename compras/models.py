"""Entrada de materiais por pedido de compra (spec 014).

Os pedidos e os itens vêm do relatório 07.13 do SCPI pelo `importar_pedidos_compra`; nada é
apagado (o que some do relatório fica com `ausente_desde`).
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class PedidoCompra(models.Model):
    """Um pedido de compra do SCPI num exercício."""

    exercicio = models.PositiveSmallIntegerField(
        help_text="O ano da sessão do SCPI em que foi lido."
    )
    ano = models.PositiveSmallIntegerField(help_text="O ano de origem do NUMPED (/26 → 2026).")
    numero = models.PositiveIntegerField("número")
    data = models.DateField()
    fornecedor_codigo = models.CharField("código do fornecedor", max_length=20)
    fornecedor_nome = models.CharField("fornecedor", max_length=200, blank=True)
    ausente_desde = models.ForeignKey(
        "catalogo.Importacao",
        verbose_name="ausente desde",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    atualizado_por = models.ForeignKey(
        "catalogo.Importacao",
        verbose_name="atualizado por",
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        verbose_name = "pedido de compra"
        verbose_name_plural = "pedidos de compra"
        ordering = ["-ano", "-numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["exercicio", "ano", "numero"], name="pedido_compra_unico"
            ),
        ]

    def __str__(self):
        return self.rotulo

    @property
    def rotulo(self) -> str:
        """`00514/26`: o número em 5 dígitos e o ano em 2."""
        return f"{self.numero:05d}/{self.ano % 100:02d}"


class ItemPedidoCompra(models.Model):
    """Um item de um pedido de compra, com o saldo que o SCPI tinha na última importação."""

    class Controle(models.TextChoices):
        QUANTIDADE = "Q", "Quantidade"
        VALOR = "T", "Valor"

    pedido = models.ForeignKey(PedidoCompra, on_delete=models.PROTECT, related_name="itens")
    item = models.PositiveSmallIntegerField(help_text="O número do item no pedido.")
    codigo = models.CharField("código", max_length=30)
    unidade = models.CharField(max_length=20, blank=True)
    controle = models.CharField(max_length=1, choices=Controle.choices)
    quantidade = models.DecimalField(max_digits=14, decimal_places=4)
    anulado = models.DecimalField(max_digits=14, decimal_places=4)
    ja_entrou = models.DecimalField("já entrou", max_digits=14, decimal_places=4)
    ja_entrou_anterior = models.DecimalField(
        "já entrou (importação anterior)",
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Nulo na primeira importação, que é a base.",
    )
    pedida = models.DecimalField(max_digits=14, decimal_places=4)
    saldo_scpi = models.DecimalField("saldo no SCPI", max_digits=14, decimal_places=4)
    preco = models.DecimalField("preço", max_digits=14, decimal_places=4)
    ausente_desde = models.ForeignKey(
        "catalogo.Importacao",
        verbose_name="ausente desde",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        verbose_name = "item do pedido de compra"
        verbose_name_plural = "itens dos pedidos de compra"
        ordering = ["pedido", "item"]
        constraints = [
            models.UniqueConstraint(fields=["pedido", "item"], name="item_pedido_compra_unico"),
        ]
        indexes = [models.Index(fields=["pedido", "codigo"], name="item_pedido_codigo_idx")]

    def __str__(self):
        return f"{self.pedido} · item {self.item}"


class Recebimento(models.Model):
    """Uma NF de um pedido: a unidade que o robô lança como uma requisição de entrada (um
    recebimento = uma NF = um pedido = uma requisição)."""

    class Status(models.TextChoices):
        PREPARADO = "PREPARADO", "Preparado"
        ERRO = "ERRO", "Com erro"
        EM_LANCAMENTO = "EM_LANCAMENTO", "Em lançamento"
        VERIFICAR = "VERIFICAR", "Em verificação"
        LANCADO = "LANCADO", "Lançado"
        CANCELADO = "CANCELADO", "Cancelado"

    class Via(models.TextChoices):
        ROBO = "ROBO", "Robô"
        MANUAL = "MANUAL", "Ligado à mão"

    envio = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    pedido = models.ForeignKey(PedidoCompra, on_delete=models.PROTECT, related_name="recebimentos")
    nf = models.CharField("nota fiscal", max_length=12)
    fornecedor_codigo = models.CharField("código do fornecedor", max_length=20)
    chave_nf = models.CharField(
        max_length=40,
        unique=True,
        null=True,
        blank=True,
        help_text='"<fornecedor>:<nf>"; nula só no cancelamento sem tentativa.',
    )
    data_recebimento = models.DateField("data do recebimento")
    observacao = models.CharField("observação", max_length=500, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PREPARADO)
    requisicao_scpi = models.CharField("requisição no SCPI", max_length=9, blank=True)
    lancado_em = models.DateTimeField("lançado em", null=True, blank=True)
    via = models.CharField(max_length=6, choices=Via.choices, blank=True)
    visivel_desde = models.DateTimeField(
        "visível desde",
        null=True,
        blank=True,
        help_text="Desde quando o SCPI certamente tem a entrada.",
    )
    mensagem = models.CharField(max_length=500, blank=True)
    versao = models.PositiveIntegerField("versão", default=1)
    preparado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    preparado_em = models.DateTimeField("preparado em", default=timezone.now)
    alterado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    alterado_em = models.DateTimeField("alterado em", null=True, blank=True)
    motivo_cancelamento = models.CharField("motivo do cancelamento", max_length=300, blank=True)

    class Meta:
        ordering = ["-id"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(status="LANCADO") | ~models.Q(requisicao_scpi=""),
                name="recebimento_lancado_tem_requisicao",
            ),
            models.CheckConstraint(
                condition=~models.Q(status__in=["VERIFICAR", "EM_LANCAMENTO"])
                | models.Q(chave_nf__isnull=False),
                name="recebimento_em_aberto_tem_chave_nf",
            ),
        ]

    def __str__(self):
        return self.rotulo

    @property
    def rotulo(self) -> str:
        """`RC-0001`: o id com 4 dígitos ou mais."""
        return f"RC-{self.pk:04d}"


class ItemRecebimento(models.Model):
    recebimento = models.ForeignKey(Recebimento, on_delete=models.CASCADE, related_name="itens")
    item = models.ForeignKey(
        ItemPedidoCompra, on_delete=models.PROTECT, related_name="recebimentos"
    )
    quantidade = models.DecimalField(max_digits=14, decimal_places=3)

    class Meta:
        ordering = ["item__item"]
        constraints = [
            models.UniqueConstraint(fields=["recebimento", "item"], name="item_recebimento_unico"),
            models.CheckConstraint(
                condition=models.Q(quantidade__gt=0), name="item_recebimento_qtd_positiva"
            ),
        ]

    def __str__(self):
        return f"{self.recebimento} · item {self.item.item}"


class TravaPedido(models.Model):
    """Um pedido travado: não aceita recebimento nem lançamento até alguém o destravar, com motivo
    e depois de uma importação de pedidos posterior (R20)."""

    class Motivo(models.TextChoices):
        TELA = "TELA", "A tela do SCPI mudou"
        JA_ENTROU = "JA_ENTROU", "Já Entrou não explicado"
        FORA_DO_CENTRAL = "FORA_DO_CENTRAL", "Entrada feita fora do Central"
        MARCA_SEM_LANCAMENTO = "MARCA_SEM_LANCAMENTO", "Marca de recebimento não lançado"

    pedido = models.ForeignKey(PedidoCompra, on_delete=models.PROTECT, related_name="travas")
    motivo = models.CharField(max_length=30, choices=Motivo.choices)
    detalhe = models.TextField(blank=True)
    criada_em = models.DateTimeField("criada em", default=timezone.now)
    execucao = models.ForeignKey(
        "pedidos.ExecucaoRobo", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    importacao = models.ForeignKey(
        "catalogo.Importacao", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    recebimento = models.ForeignKey(
        Recebimento, null=True, blank=True, on_delete=models.PROTECT, related_name="travas"
    )
    destravada_em = models.DateTimeField("destravada em", null=True, blank=True)
    destravada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    motivo_destrave = models.CharField("motivo do destrave", max_length=300, blank=True)

    class Meta:
        ordering = ["-criada_em", "-id"]
        verbose_name = "trava de pedido"
        verbose_name_plural = "travas de pedido"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(destravada_em__isnull=True, destravada_por__isnull=True)
                | models.Q(destravada_em__isnull=False, destravada_por__isnull=False),
                name="trava_destrave_completo",
            ),
        ]

    def __str__(self):
        return f"{self.pedido} · {self.get_motivo_display()}"

    @property
    def aberta(self) -> bool:
        return self.destravada_em is None
