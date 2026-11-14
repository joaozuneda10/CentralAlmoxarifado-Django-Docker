"""Template tags de apresentação compartilhadas entre apps — sem regra de domínio.

Copiadas do WMS-Almoxarifado (commit 70798439575da9d51547b0bc585b6a783b2e524c).

- `querystring_pagina`: querystring atual com um parâmetro de página trocado, preservando os
  demais (filtros, outras seções paginadas); usada por `interface/_paginacao.html`.
- `intervalo_paginas`: números e reticências da paginação (lista larga e compacta).
- `separador_milhar`: inteiro com "." de milhar.
- `iniciais`: até duas iniciais do nome (avatar da conta).
- `quantidade`: quantidade/saldo em pt-BR ("27.000", "32,5"), só para exibição — nunca em
  `value` de input nem em dado enviado.
"""

from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

from django import template
from django.core.paginator import Page

register = template.Library()


@register.simple_tag(takes_context=True)
def querystring_pagina(context, parametro, valor):
    """Querystring da requisição atual com `parametro` substituído por
    `valor`, preservando todos os demais parâmetros já presentes em
    `request.GET` (outras seções paginadas, filtros de busca etc.).

    Equivalente, para um único parâmetro dinamicamente nomeado, à tag
    nativa `{% querystring %}` do Django (5.1+) — que exige nomes de chave
    literais e por isso não serve diretamente aqui, já que `parametro` varia
    por seção (`pagina_excecoes`, `pagina_divergencias`, `pagina_alteracoes`,
    `pagina`).
    """
    params = context["request"].GET.copy()
    params[parametro] = valor
    return f"?{params.urlencode()}"


@register.simple_tag
def intervalo_paginas(pagina: Page, on_each_side: int = 2):
    """Sequência de itens da paginação numerada (FR-042b), a partir de
    `Paginator.get_elided_page_range` (`on_ends=1`): páginas próximas da
    atual e a primeira/última sempre visíveis, com reticências no lugar dos
    intervalos distantes.

    `on_each_side` (padrão 2, a lista "larga" de desktop/tablet) é
    parametrizável desde a revisão do gate visual de 2026-09-22 (achado P2:
    "6+5 não cabe numa linha a 375px"): `_paginacao.html` chama esta tag uma
    segunda vez com `on_each_side=1` para a lista "compacta" (só um vizinho
    de cada lado), alternada por media query — nunca calculada escondendo
    itens da lista larga por CSS, porque os dois intervalos têm reticências
    em posições diferentes (esconder um subconjunto de itens de um único
    range geraria um buraco sem reticência).

    Retorna uma lista de dicts `{"numero": int | None, "reticencia": bool}`
    — um item por reticência (`{"numero": None, "reticencia": True}`) ou por
    página (`{"numero": N, "reticencia": False}`) — para o template
    distinguir reticência de número sem comparar com a string mágica `"…"`
    (`Paginator.ELLIPSIS`). Uso esperado no template:

        {% intervalo_paginas pagina as paginas %}
        {% for item in paginas %}
          {% if item.reticencia %}…{% else %}{{ item.numero }}{% endif %}
        {% endfor %}
    """
    paginator = pagina.paginator
    itens = []
    for item in paginator.get_elided_page_range(
        pagina.number, on_each_side=on_each_side, on_ends=1
    ):
        if item == paginator.ELLIPSIS:
            itens.append({"numero": None, "reticencia": True})
        else:
            itens.append({"numero": item, "reticencia": False})
    return itens


@register.filter
def separador_milhar(valor):
    """Formata um inteiro com "." como separador de milhar pt-BR (revisão do
    gate visual, achado "Mundo real" — 2026-09-22: "3408 materials" não lia
    como número nem como português). Implementado sem depender de locale do
    ambiente — divide em grupos de 3 dígitos a partir da direita — porque o
    projeto não usa `django.contrib.humanize` (não está em `INSTALLED_APPS`)
    nem formatação numérica locale-aware configurada (`USE_THOUSAND_SEPARATOR`).
    Usado no resumo da paginação, tanto para o total de itens quanto para o
    número de páginas.

    Um valor não numérico é devolvido sem alteração, para nunca quebrar a
    renderização por um dado inesperado — não deveria acontecer, já que a
    origem é sempre `Paginator.count`/`num_pages` (inteiro).
    """
    try:
        valor_int = int(valor)
    except (TypeError, ValueError):
        return valor
    return f"{valor_int:,}".replace(",", ".")


_CASAS_QUANTIDADE = Decimal("0.001")  # `decimal_places=3` dos models (saldo, quantidade)


@register.filter
def quantidade(valor):
    """Formata uma quantidade/saldo/diferença para EXIBIÇÃO em pt-BR: milhar
    "." e decimal ",", só com as casas significativas (até 3, o
    `decimal_places` dos models de saldo e quantidade) — Fase C, decisão do
    usuário. Antes, `floatformat:"-3"` imprimia "32,500" ao lado de "27000"
    (que parece 32 mil, não 32 e meio), e o detalhe da entrada mostrava "6,000"
    sem filtro algum.

    Exemplos: `27000` → "27.000"; `32.5` → "32,5"; `Decimal("6.000")` → "6";
    `0.125` → "0,125"; `-1234.5` → "-1.234,5" (hífen simples, o mesmo sinal
    que `diferenca` sempre usou; o "+" explícito das divergências fica no
    template, `{% if diferenca > 0 %}+{% endif %}`); `0` → "0"; `None` → "".

    Aritmética em `Decimal` (nunca `float`): um `float` de entrada é lido por
    `str()` (`0.1` → "0,1", não "0,1000000000000000055…"). Os valores
    exibidos já vêm com no máximo 3 casas dos models; por segurança a
    exibição é quantizada em 3 casas (`ROUND_HALF_EVEN`) — nunca menos: não
    há arredondamento para menos casas do que o model guarda.

    SÓ para células de exibição. Nunca aplicar ao `value` de um `<input>`, a
    `as_hidden` nem a dado enviado ao servidor: o formato de exibição não é o
    formato de entrada (`estoque.quantidade.interpretar_quantidade_recebida`).
    Um valor não numérico é devolvido sem alteração, para nunca quebrar a
    renderização.
    """
    if valor is None or valor == "":
        return ""
    try:
        numero = valor if isinstance(valor, Decimal) else Decimal(str(valor))
        if not numero.is_finite():
            return valor
        numero = numero.quantize(_CASAS_QUANTIDADE, rounding=ROUND_HALF_EVEN)
    except (InvalidOperation, ValueError, TypeError):
        return valor
    texto = f"{abs(numero):f}"
    inteira, _, fracao = texto.partition(".")
    fracao = fracao.rstrip("0")
    inteira = f"{int(inteira):,}".replace(",", ".")
    resultado = f"{inteira},{fracao}" if fracao else inteira
    negativo = numero < 0
    return f"-{resultado}" if negativo else resultado


_CENTAVOS = Decimal("0.01")


def _numero_br(numero: Decimal) -> str:
    """Decimal já quantizado em duas casas → "1.234,56" (sem sinal)."""
    inteira, _, fracao = f"{abs(numero):f}".partition(".")
    return f"{int(inteira):,}".replace(",", ".") + "," + (fracao or "00")


@register.filter
def percentual(valor):
    """Fração em Decimal → percentual pt-BR com duas casas: `Decimal("0.0394")` → "3,94%".
    Um valor não numérico é devolvido sem alteração."""
    try:
        numero = (Decimal(str(valor)) * 100).quantize(_CENTAVOS, rounding=ROUND_HALF_EVEN)
    except (InvalidOperation, ValueError, TypeError):
        return valor
    return f"{'-' if numero < 0 else ''}{_numero_br(numero)}%"


@register.filter
def dinheiro(valor):
    """Valor em reais com duas casas: `Decimal("1988.96038")` → "R$ 1.988,96". Um valor não
    numérico é devolvido sem alteração."""
    try:
        numero = Decimal(str(valor)).quantize(_CENTAVOS, rounding=ROUND_HALF_EVEN)
    except (InvalidOperation, ValueError, TypeError):
        return valor
    return f"{'-' if numero < 0 else ''}R$ {_numero_br(numero)}"


@register.filter
def iniciais(nome):
    """Até duas iniciais do nome, para o avatar da conta: "Ana Maria Souza" → "AS",
    "joao" → "J". Sem letra (vazio ou só a matrícula), vazio: o avatar mostra o ícone."""
    partes = [p for p in str(nome or "").split() if p[:1].isalpha()]
    if not partes:
        return ""
    if len(partes) == 1:
        return partes[0][0].upper()
    return (partes[0][0] + partes[-1][0]).upper()
