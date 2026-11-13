"""Entrada de materiais por pedido de compra (spec 014).

Os pedidos e os itens vêm do relatório 07.13 do SCPI pelo `importar_pedidos_compra`; nada é
apagado (o que some do relatório fica com `ausente_desde`).
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from catalogo.models import Importacao
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
    quantidade = models.DecimalField(max_digits=18, decimal_places=6)
    anulado = models.DecimalField(max_digits=18, decimal_places=6)
    ja_entrou = models.DecimalField("já entrou", max_digits=18, decimal_places=6)
    ja_entrou_anterior = models.DecimalField(
        "já entrou (importação anterior)",
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Nulo na primeira importação, que é a base.",
    )
    pedida = models.DecimalField(max_digits=18, decimal_places=6)
    saldo_scpi = models.DecimalField("saldo no SCPI", max_digits=18, decimal_places=6)
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
    extracao = models.ForeignKey(
        "ExtracaoEntradas", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
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


class ExtracaoEntradas(models.Model):
    """Uma extração da "Relação de Requisições" de Entrada do SCPI, bem-sucedida ou não: o
    registro oficial das entradas (spec 014, espelha a `conciliacao.ExtracaoOficial`)."""

    class Motivo(models.TextChoices):
        ANTES = "ANTES", "Antes do lançamento"
        DEPOIS = "DEPOIS", "Depois do lançamento"
        DIARIA = "DIARIA", "Diária"
        MANUAL = "MANUAL", "Manual"
        # Um CSV já baixado (`--arquivo`): não se sabe quando foi exportado. Nunca libera um
        # recebimento em verificação nem gera revisão; só dá o primeiro veredito de um lançado.
        ARQUIVO = "ARQUIVO", "Arquivo enviado"

    importacao = models.OneToOneField(
        "catalogo.Importacao", on_delete=models.PROTECT, related_name="extracao_entradas"
    )
    motivo = models.CharField(max_length=10, choices=Motivo.choices)
    execucao = models.ForeignKey(
        "pedidos.ExecucaoRobo",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="extracoes_entradas",
        verbose_name="execução do robô",
    )
    impressao = models.CharField("impressão digital (SHA-256)", max_length=64, blank=True)
    arquivo = models.BinaryField("arquivo bruto (gzip)", null=True, blank=True)
    mesmo_arquivo_que = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="repeticoes",
        verbose_name="mesmo arquivo que",
    )
    arquivo_apagado_em = models.DateTimeField("bruto apagado em", null=True, blank=True)
    maior_requisicao = models.CharField("maior requisição", max_length=9, null=True, blank=True)
    requisicoes = models.PositiveIntegerField("requisições", default=0)

    MOTIVOS_DA_EXECUCAO = (Motivo.ANTES, Motivo.DEPOIS)

    class Meta:
        ordering = ["-importacao__inicio"]
        verbose_name = "extração de entradas do SCPI"
        verbose_name_plural = "extrações de entradas do SCPI"
        indexes = [models.Index(fields=["motivo", "execucao"], name="extracao_entr_motivo_exec")]
        constraints = [
            # A extração de antes e a de depois pertencem sempre a uma execução real do robô.
            models.CheckConstraint(
                condition=~models.Q(motivo__in=["ANTES", "DEPOIS"])
                | models.Q(execucao__isnull=False),
                name="extracao_entradas_execucao_antes_depois",
            )
        ]

    def __str__(self):
        return f"{self.get_motivo_display()} · {self.importacao}"

    @property
    def bem_sucedida(self) -> bool:
        return self.importacao.situacao == Importacao.Situacao.SUCESSO


class RequisicaoEntradaOficial(models.Model):
    """Uma requisição de entrada como o relatório a trouxe numa extração (uma foto por extração)."""

    extracao = models.ForeignKey(
        ExtracaoEntradas, on_delete=models.CASCADE, related_name="requisicoes_lidas"
    )
    requisicao = models.CharField("requisição", max_length=9)
    ano = models.PositiveSmallIntegerField()
    numero = models.PositiveIntegerField("número")
    id_requi = models.PositiveIntegerField("identificador interno")
    data_entrada = models.DateField("data da entrada (DATAE)")
    data_requisicao = models.DateField("data da requisição (DTLAN)")
    fornecedor_codigo = models.CharField("código do fornecedor", max_length=20, blank=True)
    nf = models.CharField("nota fiscal", max_length=30, blank=True)
    pedido_ano = models.PositiveSmallIntegerField("ano do pedido", null=True, blank=True)
    pedido_numero = models.PositiveIntegerField("número do pedido", null=True, blank=True)
    com_saida = models.BooleanField("com saída", default=False)
    tipo = models.CharField(max_length=60, blank=True)
    observacoes = models.TextField("observações", blank=True)
    recebimento_observado = models.CharField(
        "recebimento nas observações", max_length=12, blank=True, db_index=True
    )
    responsavel = models.CharField("responsável", max_length=200, blank=True)

    class Meta:
        ordering = ["extracao", "ano", "numero"]
        verbose_name = "requisição de entrada do SCPI"
        verbose_name_plural = "requisições de entrada do SCPI"
        constraints = [
            models.UniqueConstraint(
                fields=["extracao", "ano", "numero"], name="requisicao_entrada_unica"
            )
        ]
        indexes = [
            models.Index(fields=["fornecedor_codigo", "nf"], name="req_entrada_fornecedor_nf"),
            models.Index(fields=["pedido_ano", "pedido_numero"], name="req_entrada_pedido"),
        ]

    def __str__(self):
        return self.requisicao


class ItemEntradaOficial(models.Model):
    requisicao = models.ForeignKey(
        RequisicaoEntradaOficial, on_delete=models.CASCADE, related_name="itens"
    )
    ordem = models.PositiveSmallIntegerField()
    codigo = models.CharField("código", max_length=30)
    quantidade = models.DecimalField(max_digits=18, decimal_places=6)
    unidade = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["requisicao", "ordem"]
        verbose_name = "item da requisição de entrada do SCPI"
        verbose_name_plural = "itens da requisição de entrada do SCPI"

    def __str__(self):
        return f"{self.requisicao} · {self.codigo}"


class TentativaEntrada(models.Model):
    """Uma tentativa do robô de entradas com um recebimento: nasce `VERIFICAR` na transação do
    `EM_LANCAMENTO` (o lado seguro se o processo morrer) e vai a `LANCADA` com o número, ou nasce
    `ERRO`/`IGNORADA` quando o recebimento não chegou ao Salvar (spec 014, PR 4)."""

    class Resultado(models.TextChoices):
        LANCADA = "LANCADA", "Lançada"
        VERIFICAR = "VERIFICAR", "Para verificar"
        ERRO = "ERRO", "Com erro"
        IGNORADA = "IGNORADA", "Ignorada"

    execucao = models.ForeignKey(
        "pedidos.ExecucaoRobo",
        on_delete=models.PROTECT,
        related_name="tentativas_entradas",
        verbose_name="execução do robô",
    )
    ordem = models.PositiveSmallIntegerField()
    recebimento = models.ForeignKey(
        Recebimento, on_delete=models.PROTECT, related_name="tentativas"
    )
    versao = models.PositiveIntegerField("versão")
    momento = models.DateTimeField(default=timezone.now)
    resultado = models.CharField(max_length=10, choices=Resultado.choices)
    requisicao = models.CharField("requisição", max_length=9, blank=True)
    foto = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-momento", "-id"]
        verbose_name = "tentativa de entrada"
        verbose_name_plural = "tentativas de entrada"
        constraints = [
            models.UniqueConstraint(fields=["execucao", "ordem"], name="tentativa_entrada_ordem"),
            models.UniqueConstraint(
                fields=["execucao", "recebimento"], name="tentativa_entrada_recebimento"
            ),
        ]

    def __str__(self):
        return f"{self.recebimento} · {self.get_resultado_display()}"


class ConferenciaRecebimento(models.Model):
    """O que uma extração de entradas diz de um recebimento: a conferência de um em verificação
    (intervalo e candidatas) ou o veredito de um lançado (spec 014, PR 5 e PR 6; espelha a
    `conciliacao.ConferenciaLote`)."""

    class Tipo(models.TextChoices):
        LANCAMENTO = "LANCAMENTO", "Primeira conferência do lançamento"
        REVISAO = "REVISAO", "Revisão"
        VERIFICAR = "VERIFICAR", "Em verificação"

    class Veredito(models.TextChoices):
        AGUARDANDO = "AGUARDANDO", "Aguardando"
        COMPROVADO = "COMPROVADO", "Comprovado"
        DIVERGENTE = "DIVERGENTE", "Divergente"
        NAO_ENCONTRADO = "NAO_ENCONTRADO", "Não encontrado"
        DUPLICADO = "DUPLICADO", "Duplicado"
        CONFLITO = "CONFLITO", "Vínculo em conflito"
        INTERVALO_VAZIO = "INTERVALO_VAZIO", "Nenhuma candidata no intervalo"
        COM_CANDIDATAS = "COM_CANDIDATAS", "Com candidatas"
        SEM_TENTATIVA = "SEM_TENTATIVA", "Sem tentativa registrada"

    recebimento = models.ForeignKey(
        Recebimento, on_delete=models.PROTECT, related_name="conferencias"
    )
    extracao = models.ForeignKey(
        ExtracaoEntradas, on_delete=models.PROTECT, related_name="conferencias"
    )
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    veredito = models.CharField(max_length=20, choices=Veredito.choices)
    requisicao = models.ForeignKey(
        RequisicaoEntradaOficial,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="conferencias",
    )
    outra_requisicao = models.ForeignKey(
        RequisicaoEntradaOficial,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    vinculos = models.JSONField(default=list, blank=True)  # quais apontaram: numero, marca, nf
    diferencas = models.JSONField(default=list, blank=True)
    notas = models.JSONField(default=list, blank=True)
    alterado_depois = models.BooleanField(default=False)
    intervalo_de = models.CharField("intervalo de", max_length=9, blank=True)
    intervalo_ate = models.CharField("intervalo até", max_length=9, blank=True)
    tentativa = models.ForeignKey(
        TentativaEntrada,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="conferencias",
    )
    criada_em = models.DateTimeField("criada em", default=timezone.now)

    class Meta:
        ordering = ["-criada_em", "-id"]
        verbose_name = "conferência de recebimento"
        verbose_name_plural = "conferências de recebimento"
        constraints = [
            models.UniqueConstraint(
                fields=["recebimento", "extracao", "tipo"], name="conferencia_recebimento_unica"
            )
        ]

    def __str__(self):
        return f"{self.recebimento} · {self.get_veredito_display()}"


class CandidataEntrada(models.Model):
    """Uma requisição de entrada que pode ser a de um recebimento em verificação."""

    conferencia = models.ForeignKey(
        ConferenciaRecebimento, on_delete=models.CASCADE, related_name="candidatas"
    )
    requisicao = models.ForeignKey(
        RequisicaoEntradaOficial, on_delete=models.PROTECT, related_name="candidaturas"
    )
    e_esta = models.BooleanField("é esta", default=False)
    ordem = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["conferencia", "ordem"]
        verbose_name = "candidata de entrada"
        verbose_name_plural = "candidatas de entrada"

    def __str__(self):
        return f"{self.conferencia} · {self.requisicao}"


class EntradaForaDoCentral(models.Model):
    """Uma entrada por pedido feita direto no SCPI, sem o Central: reserva o saldo até a importação
    de pedidos a refletir e trava o pedido (`FORA_DO_CENTRAL`; spec 014, R18)."""

    pedido = models.ForeignKey(
        PedidoCompra, on_delete=models.PROTECT, related_name="entradas_fora_do_central"
    )
    requisicao = models.ForeignKey(
        RequisicaoEntradaOficial,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="a primeira requisição em que apareceu",
    )
    ano = models.PositiveSmallIntegerField()
    numero = models.PositiveIntegerField("número")
    visivel_desde = models.DateTimeField("visível desde")
    itens = models.JSONField(default=list, help_text="[{codigo, quantidade}] da requisição.")

    class Meta:
        ordering = ["-visivel_desde", "-id"]
        verbose_name = "entrada fora do Central"
        verbose_name_plural = "entradas fora do Central"
        constraints = [models.UniqueConstraint(fields=["ano", "numero"], name="entrada_fora_unica")]

    def __str__(self):
        return f"{self.numero:06d}/{self.ano % 100:02d} ({self.pedido})"


class IncertoConsumido(models.Model):
    """Um recebimento ou entrada de fora que já explicou um aumento do "Já Entrou" de um código
    (spec 014, R19): o incerto entra no subconjunto que explica um aumento uma vez só, senão um
    único recebimento em verificação absolveria aumentos sucessivos de entradas feitas à mão."""

    pedido = models.ForeignKey(PedidoCompra, on_delete=models.PROTECT, related_name="+")
    codigo = models.CharField(max_length=40, help_text="Código comparado por `norm_u`.")
    recebimento = models.ForeignKey(
        Recebimento, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    entrada = models.ForeignKey(
        EntradaForaDoCentral, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    importacao = models.ForeignKey(
        "catalogo.Importacao",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="importação que o usou",
    )

    class Meta:
        verbose_name = "incerto consumido"
        verbose_name_plural = "incertos consumidos"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(recebimento__isnull=False, entrada__isnull=True)
                | models.Q(recebimento__isnull=True, entrada__isnull=False),
                name="incerto_consumido_uma_origem",
            ),
            models.UniqueConstraint(
                fields=["pedido", "codigo", "recebimento"], name="incerto_consumido_recebimento"
            ),
            models.UniqueConstraint(
                fields=["pedido", "codigo", "entrada"], name="incerto_consumido_entrada"
            ),
        ]
