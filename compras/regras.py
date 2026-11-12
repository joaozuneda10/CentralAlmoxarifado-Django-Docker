"""Regras puras das entradas por pedido de compra (spec 014). Sem ORM.

Recebem objetos com os atributos que o modelo tem (ou o que o teste montar) e devolvem valores
simples. As quantidades são `Decimal`; os códigos de material se comparam por
`pedidos.regras.norm_u`.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from conciliacao.regras import chave, no_intervalo
from pedidos.regras import interpretar_quantidade, norm_u, qtd_br, texto_erro_quantidade

RE_PEDIDO = re.compile(r"^(\d{5})/(\d{2})$")  # número visível do pedido no SCPI: 00514/26
TRES_CASAS = Decimal("0.001")
CONTROLE_QUANTIDADE = "Q"  # TPCONTROLE_SALDO do 07.13: o saldo do item é em quantidade
CONTROLE_VALOR = "T"  # ... ou em valor (não se recebe por quantidade)
CONTROLES = (CONTROLE_QUANTIDADE, CONTROLE_VALOR)


def chave_pedido(numped: str) -> tuple[int, int]:
    """`00514/26` → (2026, 514): o ano de origem e o número. Inválido: ValueError."""
    casou = RE_PEDIDO.match((numped or "").strip())
    if not casou:
        raise ValueError(f"número de pedido inválido: {numped!r}")
    return 2000 + int(casou.group(2)), int(casou.group(1))


def rotulo_pedido(ano: int, numero: int) -> str:
    """(2026, 514) → `00514/26`."""
    return f"{numero:05d}/{ano % 100:02d}"


def _cabe_em_tres_casas(valor: Decimal) -> bool:
    return valor == valor.quantize(TRES_CASAS)


def disponibilidade(item, *, material_visivel: bool | None, exercicio_atual: int) -> str | None:
    """Diz se o item pode ser recebido (R4): `None` se pode, senão o motivo em pt-BR.

    `material_visivel`: `True` (no cadastro e visível), `False` (no cadastro, mas oculto) ou
    `None` (o código não está no cadastro). `item` traz `controle`, `quantidade`, `anulado`,
    `ja_entrou`, `pedida`, `saldo_scpi`, `ausente_desde_id` e o `pedido` (com `exercicio` e
    `ausente_desde_id`).
    """
    if item.controle != CONTROLE_QUANTIDADE:
        return "o saldo deste item é controlado por valor, não por quantidade"
    if material_visivel is None:
        return "o código não está no cadastro de materiais"
    if material_visivel is False:
        return "o material está oculto no cadastro"
    if item.pedido.exercicio != exercicio_atual:
        return "o pedido é de outro exercício"
    if item.pedido.ausente_desde_id is not None:
        return "o pedido não veio na última importação"
    if item.ausente_desde_id is not None:
        return "o item não veio na última importação"
    quantidades = (item.quantidade, item.anulado, item.ja_entrou, item.pedida, item.saldo_scpi)
    if not all(_cabe_em_tres_casas(q) for q in quantidades):
        return "as quantidades do item têm mais de 3 casas decimais"
    if item.saldo_scpi <= 0:
        return "o item não tem saldo a entregar no SCPI"
    return None


# --- Nota fiscal, reservas e saldo livre (US1) -----------------------------------------------

RE_NF = re.compile(r"^[0-9]{1,12}$")  # ASCII: o \d do Python aceita dígitos de outros alfabetos
RESERVAM_SEMPRE = ("PREPARADO", "ERRO", "EM_LANCAMENTO", "VERIFICAR")
RE_REQUISICAO_ENTRADA = re.compile(r"^\d{6}/\d{2}$")  # 003492/26


def nf_normalizada(texto: str) -> str:
    """`000000000501` → `501`: só dígitos, até 12, sem os zeros à esquerda e diferente de zero
    (o `DOCUM` do SCPI tem 12). Inválido: ValueError."""
    t = (texto or "").strip()
    if not RE_NF.match(t) or int(t) == 0:
        raise ValueError(f"número de nota fiscal inválido: {texto!r}")
    return t.lstrip("0")


def chave_nf(fornecedor: str, nf: str) -> str:
    """A chave única da NF de um fornecedor: `19502:501` (`nf` já normalizada)."""
    return f"{fornecedor}:{nf}"


def reserva_de(
    status: str, *, visivel_desde: datetime | None, inicio_ultima_importacao: datetime | None
) -> bool:
    """Se o recebimento ainda reserva saldo (R5). Preparado, com erro, em lançamento e em
    verificação reservam; cancelado não. O lançado reserva até uma importação de pedidos
    começada **depois** do `visivel_desde` (aí o saldo do SCPI já o reflete); sem essa prova, ou
    sem `visivel_desde`, continua reservando: o saldo livre só erra para menos."""
    if status in RESERVAM_SEMPRE:
        return True
    if status != "LANCADO":
        return False
    if visivel_desde is None or inicio_ultima_importacao is None:
        return True
    return inicio_ultima_importacao <= visivel_desde


def saldo_livre(saldo_scpi: Decimal, reservas: Iterable[Decimal]) -> Decimal:
    """O saldo do SCPI menos o reservado, nunca abaixo de zero (reservado maior que o saldo, como
    depois de uma anulação, é "precisa de conferência": o livre aparece como zero)."""
    return max(saldo_scpi - sum(reservas, Decimal(0)), Decimal(0))


def sugestao_total(linhas: Iterable) -> dict[int, Decimal]:
    """O "total": o saldo livre de cada item disponível (`motivo` vazio) com saldo livre > 0.
    Cada linha traz `item_id`, `saldo_livre` e `motivo`."""
    return {
        linha.item_id: linha.saldo_livre
        for linha in linhas
        if linha.motivo is None and linha.saldo_livre > 0
    }


@dataclass(frozen=True)
class Erro:
    """Um erro do formulário do recebimento. `campo` é `nf`, `data_recebimento`, `observacao`,
    `itens`, `pedido` ou `item-<id>`; `item` é o id do item quando o erro é de uma linha."""

    campo: str
    mensagem: str
    item: int | None = None


def validar_recebimento(
    *,
    nf: str,
    data_recebimento: date | None,
    data_pedido: date,
    hoje: date,
    itens: Mapping[int, str],
    linhas: Mapping[int, object],
    nf_usada_por: str | None,
    recusa_do_pedido: str | None,
) -> list[Erro]:
    """Todos os erros de um recebimento, juntos (nada é gravado se há algum). `itens` é o que foi
    marcado, {id do item → quantidade digitada}; `linhas` são os itens do pedido (cada um com
    `numero`, `saldo_livre` e `motivo`, o da `disponibilidade`); `nf_usada_por` é o rótulo do
    recebimento que já usa a NF deste fornecedor; `recusa_do_pedido`, o motivo de o pedido não
    aceitar recebimento (travado, ausente, fora do exercício)."""
    erros: list[Erro] = []
    if recusa_do_pedido:
        erros.append(Erro("pedido", f"Este pedido não aceita recebimento: {recusa_do_pedido}."))
    try:
        numero_nf = nf_normalizada(nf)
    except ValueError:
        erros.append(Erro("nf", "Informe o número da nota fiscal, só com algarismos."))
    else:
        if nf_usada_por:
            erros.append(
                Erro(
                    "nf",
                    f"A NF {numero_nf} deste fornecedor já está no recebimento {nf_usada_por}.",
                )
            )
    if data_recebimento is None:
        erros.append(Erro("data_recebimento", "Informe a data do recebimento."))
    elif data_recebimento > hoje:
        erros.append(Erro("data_recebimento", "A data do recebimento não pode ser depois de hoje."))
    elif data_recebimento < data_pedido:
        erros.append(
            Erro(
                "data_recebimento",
                "A data do recebimento não pode ser antes da data do pedido "
                f"({data_pedido:%d/%m/%Y}).",
            )
        )
    if not itens:
        erros.append(Erro("itens", "Marque ao menos um item."))
    for item_id, texto in itens.items():
        linha = linhas.get(item_id)
        campo = f"item-{item_id}"
        if linha is None:
            erros.append(Erro(campo, "Este item não é deste pedido.", item_id))
            continue
        if linha.motivo is not None:
            erros.append(
                Erro(
                    campo, f"Item {linha.numero}: não pode ser recebido ({linha.motivo}).", item_id
                )
            )
            continue
        valor, causa = interpretar_quantidade(texto, True)
        if valor is None:
            texto_causa = texto_erro_quantidade(causa, fracionavel=True)
            erros.append(Erro(campo, f"Item {linha.numero}: {texto_causa}", item_id))
        elif valor > linha.saldo_livre:
            livre = qtd_br(linha.saldo_livre)
            erros.append(
                Erro(
                    campo,
                    f"Item {linha.numero}: o saldo livre é {livre}; informe até {livre}.",
                    item_id,
                )
            )
    return erros


# --- A marca do recebimento nas Observações da entrada (PR 3) --------------------------------

RE_RECEBIMENTO_OBSERVADO = re.compile(r"central\s+almoxarifado\s+(RC-[0-9]{1,9})\b", re.IGNORECASE)


def recebimento_observado(observacoes: str) -> str:
    """O recebimento escrito pelo robô nas Observações ("Central Almoxarifado RC-0042"), em
    maiúsculas; vazio quando não há. Prova presença; a falta dela não prova nada. A marca das
    saídas ("P-…", "AV-…") não casa: `conciliacao.regras.lote_observado` não lê "RC-"."""
    casou = RE_RECEBIMENTO_OBSERVADO.search(observacoes or "")
    return casou.group(1).upper() if casou else ""


LIMITE_OBSERVACAO_ITEM = 100  # R25: confirmar o tamanho do campo no SCPI


def texto_observacao_item(rotulo: str, observacao: str = "") -> str:
    """O que o robô escreve na coluna Observação de cada item da entrada: numa entrada por pedido
    o campo do cabeçalho é bloqueado (SCPI, 12/11/2026), então a marca vai em cada item, numa
    linha só.
    A marca vem inteira; a observação do recebimento ("Obs.: …", sem ";" nem quebras) só entra no
    que couber em `LIMITE_OBSERVACAO_ITEM`."""
    marca = f"Central Almoxarifado {rotulo}"
    obs = " ".join((observacao or "").replace(";", ",").split())
    texto = f"{marca} Obs.: {obs}" if obs else marca
    return texto[:LIMITE_OBSERVACAO_ITEM].rstrip()


def texto_observacoes(rotulo: str, observacao: str = "") -> str:
    """O que o robô escreve nas Observações da entrada: o recebimento na primeira linha e, num
    parágrafo novo, a observação dele, numa linha só.

    As mesmas duas proteções da leitura do relatório (um CSV sem aspas) das saídas: o "Obs.: " no
    começo do parágrafo, porque uma linha que começa por uma data é lida como um registro novo, e
    o ";" trocado por ",", porque é o separador de campos."""
    marca = f"Central Almoxarifado {rotulo}"
    obs = " ".join((observacao or "").replace(";", ",").split())
    return f"{marca}\nObs.: {obs}" if obs else marca


# --- O recebimento no robô: a tela do SCPI e a conferência antes do Salvar (PR 4) -------------


@dataclass(frozen=True)
class LinhaTela:
    """Uma linha de "Escolha os Itens" como o robô a leu: o item do pedido, o código e os números
    que o SCPI mostra."""

    item: int
    codigo: str
    quantidade: Decimal
    ja_entrou: Decimal
    ja_pedida: Decimal
    saldo: Decimal


@dataclass(frozen=True)
class TelaItens:
    linhas: tuple[LinhaTela, ...] = ()


@dataclass(frozen=True)
class ItemParaLancar:
    item: int  # o número do item no pedido (a coluna Item da tela)
    codigo: str
    quantidade: Decimal


@dataclass(frozen=True)
class EsperadoItem:
    """O que a tela deve mostrar para um item do recebimento (R11): o "Já Entrou" e o saldo da
    última importação mais o que os lançados do Central ainda não refletiram naquele item."""

    item: int
    codigo: str
    quantidade: Decimal  # a do recebimento
    ja_entrou: Decimal
    saldo: Decimal


@dataclass(frozen=True)
class RecebimentoParaLancar:
    """O recebimento como o robô o recebe: dado puro, montado pela seleção (`compras.robo`)."""

    id: int
    rotulo: str  # RC-0001
    versao: int
    pedido_id: int
    pedido_ano: int
    pedido_numero: int
    pedido_rotulo: str  # 00514/26
    fornecedor_codigo: str
    nf: str
    data: date
    observacoes: str  # o texto já montado, com a marca "Central Almoxarifado RC-…"
    itens: tuple[ItemParaLancar, ...]
    esperado: tuple[EsperadoItem, ...]

    def __str__(self) -> str:
        return self.rotulo


def esperado_do_item(
    *, ja_entrou: Decimal, saldo: Decimal, nao_refletido: Decimal = Decimal(0)
) -> tuple[Decimal, Decimal]:
    """O "Já Entrou" e o saldo esperados na tela: os da última importação com o que os recebimentos
    lançados do Central, ainda não refletidos nela, já tiraram do saldo (R5)."""
    return ja_entrou + nao_refletido, saldo - nao_refletido


def _qtd(valor: Decimal) -> str:
    """Decimal sem zeros à direita, para as mensagens ('2', '1.5')."""
    texto = format(valor.normalize(), "f")
    return texto if texto != "-0" else "0"


def conferir_tela(
    esperado: tuple[EsperadoItem, ...] | list[EsperadoItem], tela: TelaItens
) -> list[str]:
    """As divergências entre o que o recebimento espera e a tela "Escolha os Itens" do SCPI; vazia
    quando a tela confere. Pura. Cada mensagem começa por "O SCPI mudou:" e diz o item e o que
    difere (R11). Item ausente na tela, código diferente no mesmo número, "Já Entrou" ou saldo
    diferentes e quantidade que não cabe no saldo da tela impedem o Salvar."""
    por_item = {linha.item: linha for linha in tela.linhas}
    divergencias = []
    for esp in esperado:
        linha = por_item.get(esp.item)
        if linha is None:
            divergencias.append(f"O SCPI mudou: o item {esp.item} não está na tela.")
            continue
        if norm_codigo(linha.codigo) != norm_codigo(esp.codigo):
            divergencias.append(
                f"O SCPI mudou: item {esp.item}, código {linha.codigo} na tela, "
                f"esperado {esp.codigo}."
            )
            continue
        if linha.ja_entrou != esp.ja_entrou:
            divergencias.append(
                f"O SCPI mudou: item {esp.item}, Já Entrou {_qtd(linha.ja_entrou)} na tela, "
                f"esperado {_qtd(esp.ja_entrou)}."
            )
        if linha.saldo != esp.saldo:
            divergencias.append(
                f"O SCPI mudou: item {esp.item}, saldo {_qtd(linha.saldo)} na tela, "
                f"esperado {_qtd(esp.saldo)}."
            )
        if esp.quantidade > linha.saldo:
            divergencias.append(
                f"O SCPI mudou: item {esp.item}, a quantidade {_qtd(esp.quantidade)} passa do "
                f"saldo {_qtd(linha.saldo)} na tela."
            )
    return divergencias


def norm_codigo(codigo: str) -> str:
    """O código como o resto do sistema o compara (`pedidos.regras.norm_u`)."""
    return norm_u(codigo)


def foto(rec: RecebimentoParaLancar, tela: TelaItens | None = None) -> dict:
    """O que o robô vai digitar e o que a tela mostrou para cada item na conferência: serve à
    comparação com a requisição oficial e à terceira prova da liberação (R16). JSON puro."""
    lidas = {linha.item: linha for linha in tela.linhas} if tela else {}
    return {
        "pedido": rec.pedido_rotulo,
        "fornecedor": rec.fornecedor_codigo,
        "nf": rec.nf,
        "data": rec.data.isoformat(),
        "observacoes": rec.observacoes,
        "itens": [
            {"item": i.item, "codigo": i.codigo, "quantidade": _qtd(i.quantidade)}
            for i in rec.itens
        ],
        "tela": [
            {
                "item": i.item,
                "ja_entrou": _qtd(lidas[i.item].ja_entrou),
                "saldo": _qtd(lidas[i.item].saldo),
            }
            for i in rec.itens
            if i.item in lidas
        ],
    }


# --- Recebimento em verificação: candidatas e as três provas (PR 5) -----------------------------


@dataclass(frozen=True)
class RequisicaoEntradaResumo:
    """Uma requisição de entrada oficial, só com o que as candidatas usam."""

    requisicao: str  # 003492/26
    recebimento_observado: str  # RC-0042, ou vazio
    fornecedor_codigo: str = ""
    nf: str = ""
    pedido_ano: int | None = None
    pedido_numero: int | None = None
    itens: tuple[tuple[str, Decimal], ...] = ()


def _semelhanca(requisicao: RequisicaoEntradaResumo, foto: dict | None, nf: str) -> int:
    """Quanto a requisição se parece com o que o robô ia digitar: só ordena as candidatas, nunca
    decide nada. Itens iguais pesam mais; depois os mesmos códigos e a NF."""
    if not foto:
        return 0
    esperado = sorted(
        (norm_u(i.get("codigo")), Decimal(str(i.get("quantidade", "0")))) for i in foto["itens"]
    )
    oficial = sorted((norm_u(codigo), quantidade) for codigo, quantidade in requisicao.itens)
    pontos = 0
    if esperado and esperado == oficial:
        pontos += 3
    elif {c for c, _ in esperado} == {c for c, _ in oficial}:
        pontos += 1
    if nf and requisicao.nf == nf:
        pontos += 1
    return pontos


def candidatas(
    requisicoes: Iterable[RequisicaoEntradaResumo],
    *,
    rotulo: str,
    fornecedor: str,
    nf: str,
    pedido: tuple[int, int],
    de: str | None,
    ate: str | None,
    foto: dict | None = None,
) -> list[tuple[RequisicaoEntradaResumo, bool]]:
    """As requisições de entrada que podem ser a do recebimento `rotulo` (R15), com o "é esta".

    É esta a que tem a marca deste recebimento, ou a NF e o fornecedor dele, em qualquer número (um
    número lido errado). Entra também a que está no intervalo da tentativa, é do **mesmo pedido** e
    não tem a marca de outro recebimento: sem o filtro do pedido, toda entrada manual do dia no
    intervalo aberto bloquearia a liberação para sempre. A marca de outro recebimento nunca entra.
    A ordem é a das marcadas, depois a semelhança com a foto, depois o número."""
    rotulo = rotulo.upper()
    escolhidas = []
    for requisicao in requisicoes:
        marca = requisicao.recebimento_observado
        if marca and marca != rotulo:
            continue
        igual_nf = bool(nf) and requisicao.nf == nf and requisicao.fornecedor_codigo == fornecedor
        if marca == rotulo or igual_nf:
            escolhidas.append((requisicao, True))
        elif (requisicao.pedido_ano, requisicao.pedido_numero) == pedido and no_intervalo(
            requisicao.requisicao, de, ate
        ):
            escolhidas.append((requisicao, False))
    return sorted(
        escolhidas,
        key=lambda par: (
            not par[1],
            -_semelhanca(par[0], foto, nf),
            chave(par[0].requisicao),
        ),
    )


@dataclass(frozen=True)
class ItemDaProva:
    """Um item do recebimento na terceira prova: o "Já Entrou" que a tela mostrou antes do Salvar
    e o que a importação posterior traz."""

    item: int
    antes: Decimal  # o "Já Entrou" da foto da tentativa
    presente: bool  # o item veio na importação posterior
    depois: Decimal | None  # o "Já Entrou" dela


def tres_provas(
    *,
    momento: datetime,
    extracao_posterior: bool,
    candidatas: Iterable[str],
    importacao_posterior: bool,
    itens: Iterable[ItemDaProva],
) -> list[str]:
    """As faltas das três provas da liberação para relançar (R16, FR-025); vazia quando as três
    estão cumpridas. Cada falta é uma mensagem em português, a de `contracts/tela-e-acoes.md`.

    1. uma extração de entradas bem-sucedida, que não seja de arquivo, depois da tentativa;
    2. nenhuma candidata em nenhuma conferência dela (uma vista uma vez continua bloqueando);
    3. uma importação de pedidos depois da tentativa em que cada item do recebimento tem o "Já
       Entrou" igual ao da tela antes do Salvar. Pura: não consulta nada."""
    faltas = []
    quando = f"{momento:%d/%m/%Y %H:%M}"
    if not extracao_posterior:
        faltas.append(f"Ainda não houve extração de entradas depois da tentativa de {quando}.")
    numeros = sorted(set(candidatas), key=chave)
    if numeros:
        plural = len(numeros) > 1
        faltas.append(
            f"Há requisição candidata no intervalo: {', '.join(numeros)}."
            if not plural
            else f"Há requisições candidatas no intervalo: {', '.join(numeros)}."
        )
    for item in sorted(itens, key=lambda i: i.item):
        if not importacao_posterior:
            faltas.append(
                f"O 'Já Entrou' do item {item.item} não foi conferido depois da tentativa: "
                "atualize os pedidos."
            )
        elif not item.presente:
            faltas.append(
                f"O item {item.item} não veio na importação de pedidos depois da tentativa: "
                "a requisição pode existir."
            )
        elif item.depois != item.antes:
            faltas.append(
                f"O 'Já Entrou' do item {item.item} mudou de {_qtd(item.antes)} para "
                f"{_qtd(item.depois)} depois da tentativa: a requisição pode existir."
            )
    return faltas


# --- Recebimento lançado: vínculos, comparação e veredito (PR 6, R17) ---------------------------


@dataclass(frozen=True)
class EntradaOficial:
    """Uma requisição de entrada como o relatório a trouxe, só com o que a conferência usa."""

    requisicao: str
    recebimento_observado: str
    fornecedor_codigo: str
    nf: str
    pedido_ano: int | None
    pedido_numero: int | None
    data_entrada: date
    itens: tuple[tuple[str, Decimal], ...] = ()


@dataclass(frozen=True)
class EntregaEntrada:
    """O que o recebimento deveria ter feito no SCPI: a foto da tentativa ou o próprio
    recebimento."""

    fornecedor_codigo: str
    nf: str
    pedido_ano: int
    pedido_numero: int
    data: date
    itens: tuple[tuple[str, Decimal], ...]


@dataclass(frozen=True)
class ResultadoEntrada:
    veredito: str
    requisicao: EntradaOficial | None = None
    outra: EntradaOficial | None = None
    vinculos: tuple[str, ...] = ()  # quais dos três apontaram para a ligada: numero, marca, nf
    diferencas: tuple[dict, ...] = ()
    notas: tuple[dict, ...] = ()


def _soma_por_codigo(itens) -> dict[str, Decimal]:
    soma: dict[str, Decimal] = {}
    for codigo, quantidade in itens:
        chave_codigo = norm_u(codigo)
        soma[chave_codigo] = soma.get(chave_codigo, Decimal(0)) + quantidade
    return soma


def _itens_texto(soma: dict[str, Decimal]) -> str:
    return "; ".join(f"{codigo} × {_qtd(q)}" for codigo, q in sorted(soma.items())) or "nenhum"


def comparar_entrada(
    entrega: EntregaEntrada, oficial: EntradaOficial, vinculos: Iterable[str] = ()
) -> tuple[list[dict], list[dict]]:
    """As diferenças (campo, esperado, oficial) e as notas entre a entrega e a requisição.

    Compara o fornecedor, a NF, o número do pedido, a data da entrada (`DATAE`) contra a data do
    recebimento e a **soma das quantidades por código** (`norm_u`, `Decimal` exato: com o código
    repetido no pedido, é o que o relatório permite comparar). Nunca a `DTLAN` (F5) nem o empenho
    (D7). Um vínculo que falta, como a marca ausente com o número e a NF certos, vira nota."""
    diferencas: list[dict] = []
    notas: list[dict] = []

    def diferenca(campo, esperado, encontrado):
        diferencas.append({"campo": campo, "esperado": str(esperado), "oficial": str(encontrado)})

    if entrega.fornecedor_codigo != oficial.fornecedor_codigo:
        diferenca("fornecedor", entrega.fornecedor_codigo, oficial.fornecedor_codigo or "(vazio)")
    if entrega.nf != oficial.nf:
        diferenca("NF", entrega.nf, oficial.nf or "(vazia)")
    esperado_pedido = (entrega.pedido_ano, entrega.pedido_numero)
    if esperado_pedido != (oficial.pedido_ano, oficial.pedido_numero):
        achado = (
            rotulo_pedido(oficial.pedido_ano, oficial.pedido_numero)
            if oficial.pedido_numero
            else "(sem pedido)"
        )
        diferenca("pedido", rotulo_pedido(*esperado_pedido), achado)
    if entrega.data != oficial.data_entrada:
        diferenca("data", f"{entrega.data:%d/%m/%Y}", f"{oficial.data_entrada:%d/%m/%Y}")
    esperados = _soma_por_codigo(entrega.itens)
    achados = _soma_por_codigo(oficial.itens)
    if esperados != achados:
        diferenca("itens", _itens_texto(esperados), _itens_texto(achados))
    achou = set(vinculos)
    if achou and "marca" not in achou:
        notas.append(
            {
                "campo": "observações",
                "texto": "o recebimento não está nas observações da requisição",
            }
        )
    return diferencas, notas


def veredito_entrada(
    rotulo: str,
    numero: str,
    requisicoes: Iterable[EntradaOficial],
    entrega: EntregaEntrada,
    *,
    fornecedor: str,
    nf: str,
    maior: str | None,
    numero_em_outro_recebimento: bool = False,
    ja_vista: bool = False,
) -> ResultadoEntrada:
    """O veredito de um recebimento lançado numa extração bem-sucedida que cobre a sua data (R17).

    Três vínculos: o número gravado, a marca `RC-…` nas observações e a NF com o fornecedor. Marca
    ou NF em duas requisições, ou o número numa requisição com a marca de outro recebimento, é
    Duplicado; dois vínculos achados em requisições diferentes, Conflito; nenhum vínculo, Não
    encontrado só quando o relatório já traz número maior que o do recebimento (ou uma conferência
    anterior já achou a requisição), senão Aguardando; os achados na mesma requisição, a
    comparação: Comprovado ou Divergente."""
    rotulo = rotulo.upper()
    requisicoes = list(requisicoes)
    pela_marca = [r for r in requisicoes if r.recebimento_observado == rotulo]
    pela_nf = [r for r in requisicoes if nf and r.nf == nf and r.fornecedor_codigo == fornecedor]
    pelo_numero = next((r for r in requisicoes if r.requisicao == numero), None)
    if len(pela_marca) > 1 or len(pela_nf) > 1 or numero_em_outro_recebimento:
        primeira = (pela_marca or pela_nf or [pelo_numero])[0]
        segunda_lista = pela_marca if len(pela_marca) > 1 else pela_nf
        segunda = segunda_lista[1] if len(segunda_lista) > 1 else None
        return ResultadoEntrada("DUPLICADO", primeira, segunda)
    if (
        pelo_numero
        and pelo_numero.recebimento_observado
        and pelo_numero.recebimento_observado != rotulo
    ):
        return ResultadoEntrada(
            "DUPLICADO",
            pelo_numero,
            pela_marca[0] if pela_marca else None,
            notas=(
                {
                    "campo": "observações",
                    "texto": f"a requisição {pelo_numero.requisicao} tem nas observações o "
                    f"recebimento {pelo_numero.recebimento_observado}",
                },
            ),
        )
    achados = {
        "numero": pelo_numero,
        "marca": pela_marca[0] if pela_marca else None,
        "nf": pela_nf[0] if pela_nf else None,
    }
    achados = {tipo: r for tipo, r in achados.items() if r is not None}
    distintas = {r.requisicao: r for r in achados.values()}
    if len(distintas) > 1:
        primeira, segunda, *_ = distintas.values()
        return ResultadoEntrada("CONFLITO", primeira, segunda, vinculos=tuple(achados))
    if not distintas:
        if ja_vista or (
            maior and RE_REQUISICAO_ENTRADA.match(numero or "") and chave(maior) > chave(numero)
        ):
            return ResultadoEntrada("NAO_ENCONTRADO")
        return ResultadoEntrada("AGUARDANDO")
    (ligada,) = distintas.values()
    diferencas, notas = comparar_entrada(entrega, ligada, achados)
    return ResultadoEntrada(
        "DIVERGENTE" if diferencas else "COMPROVADO",
        ligada,
        vinculos=tuple(achados),
        diferencas=tuple(diferencas),
        notas=tuple(notas),
    )


def alteracoes_entrada(antes: EntradaOficial, agora: EntradaOficial) -> list[dict]:
    """O que mudou na requisição entre a conferência do lançamento e uma revisão: compara os
    valores, não os textos (uma quantidade que muda na quarta casa é alteração)."""
    mudou = []
    for campo, a, b in (
        ("fornecedor", antes.fornecedor_codigo, agora.fornecedor_codigo),
        ("NF", antes.nf, agora.nf),
        (
            "pedido",
            (antes.pedido_ano, antes.pedido_numero),
            (agora.pedido_ano, agora.pedido_numero),
        ),
        ("data", antes.data_entrada, agora.data_entrada),
    ):
        if a != b:
            mudou.append(
                {"campo": campo, "antes": _texto_da_alteracao(a), "agora": _texto_da_alteracao(b)}
            )
    if _soma_por_codigo(antes.itens) != _soma_por_codigo(agora.itens):
        mudou.append(
            {
                "campo": "itens",
                "antes": _itens_texto(_soma_por_codigo(antes.itens)),
                "agora": _itens_texto(_soma_por_codigo(agora.itens)),
            }
        )
    return mudou


def _texto_da_alteracao(valor) -> str:
    if isinstance(valor, date):
        return f"{valor:%d/%m/%Y}"
    if isinstance(valor, tuple):
        return rotulo_pedido(*valor) if valor[1] else "(sem pedido)"
    return str(valor or "")


# --- "Já Entrou" que o Central não explica (PR 6, R19) -------------------------------------------


def ja_entrou_explicado(delta: Decimal, certos: Decimal, incertos: Iterable[Decimal]) -> bool:
    """Se o aumento do "Já Entrou" (`delta`, a soma do `QTDENT` novo menos a do anterior, por
    pedido e código) é explicado pelos recebimentos do Central: os `certos` (lançados pelo robô
    entre as duas importações) e, de modo opcional, **algum subconjunto** dos `incertos` (em
    verificação nesse intervalo, ligados à mão ou fora do Central, de hora desconhecida). Um delta
    negativo (entrada excluída ou corrigida no SCPI) nunca é explicado."""
    if delta < 0:
        return False
    restante = delta - certos
    if restante < 0:
        return False
    somas = {Decimal(0)}
    for quantidade in incertos:
        somas |= {parcial + quantidade for parcial in somas}
    return restante in somas
