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
