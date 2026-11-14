"""Consultas do painel: filtros em SQL, para o painel não carregar todos os pedidos.

Os filtros de situação repetem `regras.situacao_pedido` e `regras.situacao_scpi` como
anotações `Exists`; `tests/test_painel.py` confere que os dois concordam em todas as
combinações.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django import forms
from django.db.models import Count, Exists, F, Min, OuterRef, Q, QuerySet
from django.db.models.functions import Coalesce
from django.utils import timezone

from catalogo.models import Material
from pedidos.models import AutorizacaoPedido, ItemPedido, LinhaSaida, Pedido
from pedidos.regras import (
    AVULSA,
    EM_LANCAMENTO,
    LANCADA,
    NAO_LANCAR,
    PENDENTE,
    VERIFICAR,
)
from scpi.requisicoes import ESTADOS_TRAVA

OPCOES_SITUACAO = [
    ("aguardando", "Aguardando atendimento"),
    ("atendido", "Atendido"),
    ("parcial", "Atendido parcialmente"),
]
# Filtro à parte da situação (spec 008): "Autorizado" é o estado da autorização, que um pedido
# atendido também tem; misturá-lo na situação sobreporia "Atendido".
OPCOES_AUTORIZACAO = [
    ("aguardando", "Aguardando autorização"),
    ("autorizado", "Autorizado"),
    ("recusado", "Recusado"),
]
_SITUACAO_DA_AUTORIZACAO = {
    "aguardando": AutorizacaoPedido.Situacao.AGUARDANDO,
    "autorizado": AutorizacaoPedido.Situacao.AUTORIZADO,
    "recusado": AutorizacaoPedido.Situacao.RECUSADO,
}
OPCOES_SCPI = [
    ("sem", "Aguarda o atendimento ou não será lançado"),
    ("aguardando", "Aguardando o robô"),
    ("lancado", "Lançado"),
    ("parcial", "Parcialmente lançado"),
    ("atencao", "Verificar / erro"),
]


class FiltrosPainel(forms.Form):
    q = forms.CharField(
        required=False,
        label="Buscar",
        widget=forms.TextInput(
            attrs={
                "class": "campo-entrada",
                "type": "search",
                "placeholder": "Nº, solicitante, recebedor ou ocorrência",
                # A busca fica no cabeçalho, fora do <form> (spec 015): o atributo a liga a ele.
                "form": "filtros-painel",
            }
        ),
    )
    # Campo próprio, para combinar com a busca geral (o material e quem recebeu, por exemplo).
    material = forms.CharField(
        required=False,
        label="Buscar material",
        widget=forms.TextInput(
            attrs={
                "class": "campo-entrada",
                "type": "search",
                "placeholder": "Material: código ou nome",
            }
        ),
    )
    origem = forms.ChoiceField(
        required=False,
        label="Origem",
        choices=[("", "Todas")] + Pedido.Origem.choices,
        widget=forms.Select(attrs={"class": "campo-entrada"}),
    )
    situacao = forms.ChoiceField(
        required=False,
        label="Situação do pedido",
        choices=[("", "Todas")] + OPCOES_SITUACAO,
        # Chips de rádio (spec 015): o valor vale em todo envio do formulário.
        widget=forms.RadioSelect(attrs={"class": "chip-entrada"}),
    )
    autorizacao = forms.ChoiceField(
        required=False,
        label="Autorização (EPIs)",
        choices=[("", "Todas")] + OPCOES_AUTORIZACAO,
        widget=forms.Select(attrs={"class": "campo-entrada"}),
    )
    scpi = forms.ChoiceField(
        required=False,
        label="Integração SCPI",
        choices=[("", "Todas")] + OPCOES_SCPI,
        widget=forms.Select(attrs={"class": "campo-entrada"}),
    )
    recibo = forms.ChoiceField(
        required=False,
        label="Recibo",
        choices=[("", "Todos"), ("pendente", "Não impresso"), ("impresso", "Impresso")],
        widget=forms.Select(attrs={"class": "campo-entrada"}),
    )
    de = forms.DateField(
        required=False,
        label="De",
        widget=forms.DateInput(attrs={"type": "date", "class": "campo-entrada"}),
    )
    ate = forms.DateField(
        required=False,
        label="Até",
        widget=forms.DateInput(attrs={"type": "date", "class": "campo-entrada"}),
    )

    def filtros(self) -> dict:
        """Os valores válidos; o que não validou é ignorado."""
        self.is_valid()
        return {k: v for k, v in getattr(self, "cleaned_data", {}).items() if v}

    # Os chips com lista do painel (spec 015): o nome curto e o valor escolhido ("Origem: Limpeza").
    CHIPS = (
        ("origem", "Origem"),
        ("scpi", "SCPI"),
        ("recibo", "Recibo"),
        ("autorizacao", "Autorização"),
    )

    def rotulos_dos_chips(self) -> dict[str, dict]:
        """O rótulo de cada chip com lista pela URL: o nome sozinho sem valor, ou "nome: valor".
        O `filtros.js` refaz o mesmo texto depois de cada troca do HTMX (`data-chip-nome`)."""
        valores = self.filtros()
        rotulos = {}
        for nome, curto in self.CHIPS:
            escolhido = dict(self.fields[nome].choices).get(valores.get(nome))
            rotulos[nome] = {
                "nome": curto,
                "texto": f"{curto}: {escolhido}" if escolhido else curto,
                "ativo": bool(escolhido),
            }
        de, ate = valores.get("de"), valores.get("ate")
        if de and ate:
            periodo = f"{de:%d/%m/%Y} a {ate:%d/%m/%Y}"
        elif de:
            periodo = f"a partir de {de:%d/%m/%Y}"
        elif ate:
            periodo = f"até {ate:%d/%m/%Y}"
        else:
            periodo = ""
        rotulos["periodo"] = {
            "nome": "Período",
            "texto": f"Período: {periodo}" if periodo else "Período",
            "ativo": bool(periodo),
        }
        return rotulos


def filtrar_situacao(qs: QuerySet, chave: str) -> QuerySet:
    entregue_a_menos = Exists(
        ItemPedido.objects.filter(pedido=OuterRef("pk"), origem=ItemPedido.Origem.PEDIDO)
        .filter(qtd_pedida__gt=Coalesce(F("qtd_entregue"), 0))
        .exclude(Exists(ItemPedido.objects.filter(no_lugar_de=OuterRef("pk"), qtd_entregue__gt=0)))
    )
    nao_avulsa = qs.exclude(origem=AVULSA)
    if chave == "aguardando":
        # Aguardando atendimento: o pedido de EPI que espera a autorização ou foi recusado não
        # entra (não pode ser atendido); sem autorização, o resultado é o de sempre.
        return nao_avulsa.filter(atendimento__isnull=True).exclude(
            autorizacao__situacao__in=[
                AutorizacaoPedido.Situacao.AGUARDANDO,
                AutorizacaoPedido.Situacao.RECUSADO,
            ]
        )
    if chave == "parcial":
        return nao_avulsa.filter(atendimento__isnull=False).filter(entregue_a_menos)
    if chave == "atendido":
        # A saída avulsa já nasce atendida.
        atendidos = nao_avulsa.filter(atendimento__isnull=False).exclude(entregue_a_menos)
        return qs.filter(Q(origem=AVULSA) | Q(pk__in=atendidos.values("pk")))
    return qs


def filtrar_scpi(qs: QuerySet, chave: str) -> QuerySet:
    ativas = LinhaSaida.objects.filter(atendimento__pedido=OuterRef("pk")).exclude(
        status=NAO_LANCAR
    )
    sem_req = Q(requisicao_scpi="")
    ativa = Exists(ativas)
    lancada = Exists(ativas.filter(~sem_req | Q(status=LANCADA)))
    atencao = Exists(ativas.filter(sem_req, status__in=ESTADOS_TRAVA))
    pendente = Exists(ativas.filter(sem_req, status=PENDENTE))
    if chave == "sem":
        return qs.exclude(ativa)
    if chave == "atencao":
        return qs.filter(atencao)
    if chave == "lancado":
        return qs.filter(ativa).exclude(atencao).exclude(pendente)
    if chave == "parcial":
        return qs.filter(lancada, pendente).exclude(atencao)
    if chave == "aguardando":
        return qs.filter(pendente).exclude(lancada).exclude(atencao)
    return qs


def inicio_do_dia(dia: date) -> datetime:
    """Começo do dia `dia` no fuso local (limite dos filtros de período)."""
    return timezone.make_aware(datetime.combine(dia, time.min))


def pedidos_do_painel(filtros: dict) -> QuerySet:
    qs = (
        Pedido.objects.select_related("atendimento", "autorizacao")
        .prefetch_related("itens", "atendimento__linhas")
        .order_by("-criado_em", "-numero")
    )
    if q := (filtros.get("q") or "").strip():
        qs = qs.filter(
            Q(numero__icontains=q)
            | Q(solicitante__icontains=q)
            | Q(atendimento__recebedor__icontains=q)
            | Q(ocorrencia__icontains=q)
        )
    if material := (filtros.get("material") or "").strip():
        # Material pedido ou acrescentado pelo almoxarifado; `Exists` para o pedido com vários
        # materiais que batem não sair repetido.
        qs = qs.filter(
            Exists(
                ItemPedido.objects.filter(pedido=OuterRef("pk")).filter(
                    Q(codigo__icontains=material) | Q(material__icontains=material)
                )
            )
        )
    if origem := filtros.get("origem"):
        qs = qs.filter(origem=origem)
    if de := filtros.get("de"):
        qs = qs.filter(criado_em__gte=inicio_do_dia(de))
    if (ate := filtros.get("ate")) and ate < date.max:  # 31/12/9999 não limita nada
        qs = qs.filter(criado_em__lt=inicio_do_dia(ate + timedelta(days=1)))
    if situacao := filtros.get("situacao"):
        qs = filtrar_situacao(qs, situacao)
    if autorizacao := filtros.get("autorizacao"):
        qs = qs.filter(autorizacao__situacao=_SITUACAO_DA_AUTORIZACAO[autorizacao])
    if scpi := filtros.get("scpi"):
        qs = filtrar_scpi(qs, scpi)
    if recibo := filtros.get("recibo"):
        # Só tem recibo o que tem saída registrada (atendimento).
        qs = qs.filter(
            atendimento__isnull=False, atendimento__recibo_impresso_em__isnull=recibo == "pendente"
        )
    return qs


@dataclass
class RequisicaoNaFila:
    lote: str  # número do pedido ou da saída avulsa
    data: date
    recebedor: str
    centro_custo: str
    materiais: int  # linhas `PENDENTE` do lote


@dataclass
class Fila:
    total: int
    requisicoes: list[RequisicaoNaFila]

    @property
    def fora(self) -> int:
        """Quantas ficaram fora da lista mostrada."""
        return self.total - len(self.requisicoes)


def fila_de_autorizacao() -> QuerySet:
    """Os pedidos de EPI que aguardam a decisão da Segurança do Trabalho, do mais antigo para o
    mais novo (spec 008, FR-011). Uma consulta, com o pedido e o número de itens (`n_itens`)."""
    return (
        AutorizacaoPedido.objects.filter(situacao=AutorizacaoPedido.Situacao.AGUARDANDO)
        .select_related("pedido")
        .annotate(n_itens=Count("pedido__itens"))
        .order_by("pedido__criado_em", "pedido__numero")
    )


def decididas_da_autorizacao() -> QuerySet:
    """Os já decididos (autorizados ou recusados), do mais recente para o mais antigo: leitura
    para a Segurança do Trabalho."""
    return (
        AutorizacaoPedido.objects.exclude(situacao=AutorizacaoPedido.Situacao.AGUARDANDO)
        .select_related("pedido", "decidido_por")
        .order_by("-decidido_em", "-pedido__numero")
    )


def fila_do_robo(limite: int | None = None) -> Fila:
    """As requisições que o robô lançaria agora, na ordem em que as percorre: todas, ou só as
    `limite` primeiras (`0` devolve só o total).

    Repete `requisicoes.agrupar` em SQL (lote com linha `PENDENTE` e sem nenhuma linha em
    `ESTADOS_TRAVA` nem `PENDENTE` com número de requisição), para não carregar todas as linhas
    pendentes a cada recarga da página; `tests/test_consultas_fila.py` confere que concordam."""
    trava = LinhaSaida.objects.filter(lote=OuterRef("lote")).filter(
        # "Com número" é com algum caractere que não seja espaço, como o `texto()` da regra.
        Q(status__in=ESTADOS_TRAVA) | Q(status=PENDENTE, requisicao_scpi__regex=r"[^[:space:]]")
    )
    lotes = (
        LinhaSaida.objects.filter(status=PENDENTE)
        .exclude(Exists(trava))
        .values("lote")
        .annotate(primeira=Min("id"), materiais=Count("id"))
        .order_by("primeira")
    )
    if limite is None:
        # A fila inteira: uma consulta só, sem o `count()` à parte.
        escolhidos = list(lotes)
        total = len(escolhidos)
    else:
        total = lotes.count()
        escolhidos = list(lotes[:limite]) if total and limite else []
    if not escolhidos:
        return Fila(total, [])
    primeiras = LinhaSaida.objects.in_bulk([lote["primeira"] for lote in escolhidos])
    return Fila(
        total,
        [
            RequisicaoNaFila(
                lote=lote["lote"],
                data=primeiras[lote["primeira"]].data,
                recebedor=primeiras[lote["primeira"]].recebedor,
                centro_custo=primeiras[lote["primeira"]].centro_custo,
                materiais=lote["materiais"],
            )
            for lote in escolhidos
        ],
    )


def lotes_pendentes() -> int:
    """Lotes que o robô lançaria agora, pela regra de `requisicoes.agrupar`."""
    return fila_do_robo(limite=0).total


@dataclass
class LoteTravado:
    lote: str
    linhas: list[LinhaSaida]
    conferir: bool  # alguma linha `VERIFICAR` ou `EM_LANCAMENTO`: o SCPI pode ter gravado
    # O que a conciliação sabe do lote em verificar (`conciliacao.consultas.Verificacao`); a aba
    # o preenche.
    verificacao: object | None = None


def lotes_travados() -> list[LoteTravado]:
    """Linhas em `VERIFICAR`, `EM_LANCAMENTO` ou `ERRO`, agrupadas por lote (na ordem do `id`
    da primeira linha de cada um)."""
    linhas = LinhaSaida.objects.filter(status__in=ESTADOS_TRAVA).order_by("id")
    lotes: dict[str, LoteTravado] = {}
    for linha in linhas:
        lote = lotes.setdefault(linha.lote, LoteTravado(linha.lote, [], False))
        lote.linhas.append(linha)
        lote.conferir = lote.conferir or linha.status in (VERIFICAR, EM_LANCAMENTO)
    return list(lotes.values())


def contar_lotes_travados(com_em_lancamento: bool = True) -> int:
    """Quantos lotes `lotes_travados` devolveria, contados no banco, sem carregar as linhas. Com
    `com_em_lancamento=False`, só os lotes com linha `VERIFICAR` ou `ERRO` (o contador do menu,
    spec 015: durante uma execução, o `EM_LANCAMENTO` é o robô trabalhando)."""
    estados = [s for s in ESTADOS_TRAVA if com_em_lancamento or s != EM_LANCAMENTO]
    return (
        LinhaSaida.objects.filter(status__in=estados).order_by().values("lote").distinct().count()
    )


def ha_lote_em_lancamento() -> bool:
    return LinhaSaida.objects.filter(status=EM_LANCAMENTO).exists()


# --- Indicadores do painel (spec 015, entrega 2) --------------------------------------------


def contar_aguardando() -> int:
    """Os pedidos do filtro "Aguardando atendimento" (fora os aguardando autorização e os
    recusados): o cartão do painel e o contador do item Painel no menu."""
    return filtrar_situacao(Pedido.objects.all(), "aguardando").count()


def envio_mais_antigo_aguardando() -> datetime | None:
    """O `criado_em` mais antigo entre os pedidos aguardando atendimento, ou None sem nenhum."""
    return filtrar_situacao(Pedido.objects.all(), "aguardando").aggregate(m=Min("criado_em"))["m"]


def contar_aguardando_autorizacao() -> int:
    """Os pedidos de EPI aguardando a decisão da Segurança do Trabalho (o filtro Autorização =
    aguardando)."""
    aguardando = AutorizacaoPedido.Situacao.AGUARDANDO
    return Pedido.objects.filter(autorizacao__situacao=aguardando).count()


def nomes_scpi(pedidos) -> dict[str, str]:
    """Nome do cadastro do SCPI de cada código dos pedidos, numa consulta. A área interna mostra o
    material pelo nome do SCPI; o do item (`ItemPedido.material`) é o do formulário, que nas
    listas de limpeza e das viaturas pode ser um nome exibido, e só vale quando o código saiu do
    cadastro."""
    codigos = {i.codigo for p in pedidos for i in p.itens.all()}
    return dict(Material.objects.filter(codigo__in=codigos).values_list("codigo", "nome"))


def unidades_scpi(pedidos) -> dict[str, str]:
    """Unidade do cadastro do SCPI de cada código dos pedidos, numa consulta. A área interna mostra
    a unidade como está no SCPI; a do item (`ItemPedido.unidade`) é a do formulário, que na limpeza
    pode ser a unidade exibida ("EMBALAGEM 500 g"), e só vale quando o código saiu do cadastro."""
    codigos = {i.codigo for p in pedidos for i in p.itens.all()}
    return dict(
        Material.objects.filter(codigo__in=codigos)
        .exclude(unidade="")
        .values_list("codigo", "unidade")
    )
