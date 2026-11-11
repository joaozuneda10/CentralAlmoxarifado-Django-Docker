"""Entrada de materiais por pedido de compra (spec 014).

Os pedidos e os itens vêm do relatório 07.13 do SCPI pelo `importar_pedidos_compra`; nada é
apagado (o que some do relatório fica com `ausente_desde`).
"""

from django.db import models

from compras.regras import CONTROLE_QUANTIDADE, CONTROLE_VALOR, rotulo_pedido


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
        return rotulo_pedido(self.ano, self.numero)


class ItemPedidoCompra(models.Model):
    """Um item de um pedido de compra, com o saldo que o SCPI tinha na última importação."""

    class Controle(models.TextChoices):
        QUANTIDADE = CONTROLE_QUANTIDADE, "Quantidade"
        VALOR = CONTROLE_VALOR, "Valor"

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
