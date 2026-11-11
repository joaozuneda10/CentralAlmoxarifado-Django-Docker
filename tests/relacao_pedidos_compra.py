"""Gerador do CSV do 07.13 "Relação de Pedidos (Condição da Entrega)" (spec 014).

Dados sintéticos, sem nomes de pessoas reais. O formato segue
`specs/014-entrada-por-pedido/contracts/relatorios-scpi.md`: UTF-8 com BOM, `;`, CRLF, 79 colunas
(mais o `;` final), `GRUPO` e `GRUPO_1` iguais a `DATPED`, uma linha por item. As colunas que a
leitura não usa têm nomes de preenchimento (`CAMPO_NN`): só os nomes lidos importam.
"""

from dataclasses import dataclass
from datetime import date

_USADAS = (
    "GRUPO;GRUPO_1;NUMPED;DATPED;CODIF;NOME;ITEM;CADPRO;UNID1;TPCONTROLE_SALDO;QTD;PRCUNT;QTDANU;"
    "QTDENT;QTDFALTA;QTDPEDIDA;OBSITEM"
).split(";")
COLUNAS = _USADAS + [f"CAMPO_{n:02d}" for n in range(1, 79 - len(_USADAS) + 1)]
assert len(COLUNAS) == 79


@dataclass
class ItemPedidoCSV:
    numped: str  # 00514/26
    item: int
    codigo: str
    quantidade: str = "100"  # como o SCPI escreve: "100", "1361,32"
    anulado: str = "0"
    ja_entrou: str = "0"
    pedida: str = "0"
    saldo: str | None = None  # QTDFALTA; padrão: QTD − QTDANU − QTDENT − QTDPEDIDA
    unidade: str = "UN"
    controle: str = "Q"
    preco: str = "1,5"
    data: date = date(2026, 3, 2)
    fornecedor: str = "19502"
    nome: str = "FORNECEDOR SINTÉTICO LTDA"
    obs: str = "Entrega no almoxarifado"


def _br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _num(texto: str):
    from scpi.leitura import decimal_br

    return decimal_br(texto)


def _fmt(valor) -> str:
    texto = format(valor.normalize(), "f")
    return texto.replace(".", ",")


def _saldo(it: ItemPedidoCSV) -> str:
    if it.saldo is not None:
        return it.saldo
    bruto = _num(it.quantidade) - _num(it.anulado) - _num(it.ja_entrou) - _num(it.pedida)
    return _fmt(bruto)


def _linha(it: ItemPedidoCSV, *, quebrar_registro: bool) -> str:
    valores = dict.fromkeys(COLUNAS, "")
    valores.update(
        GRUPO=_br(it.data),
        GRUPO_1=_br(it.data),
        NUMPED=it.numped,
        DATPED=_br(it.data),
        CODIF=it.fornecedor,
        NOME=it.nome,
        ITEM=str(it.item),
        CADPRO=it.codigo,
        UNID1=it.unidade,
        TPCONTROLE_SALDO=it.controle,
        QTD=it.quantidade,
        PRCUNT=it.preco,
        QTDANU=it.anulado,
        QTDENT=it.ja_entrou,
        QTDFALTA=_saldo(it),
        QTDPEDIDA=it.pedida,
        OBSITEM=(it.obs + "\nsegunda linha da observação") if quebrar_registro else it.obs,
    )
    return ";".join(valores[c] for c in COLUNAS) + ";"


def csv_pedidos(itens: list[ItemPedidoCSV], *, quebrar_registro: bool = False) -> bytes:
    """Bytes do CSV como o SCPI o entrega. `quebrar_registro` põe uma quebra de linha dentro do
    `OBSITEM` do primeiro item, como o SCPI faz com os campos de texto longo."""
    linhas = [";".join(COLUNAS) + ";"]
    for posicao, it in enumerate(itens):
        linhas.append(_linha(it, quebrar_registro=quebrar_registro and posicao == 0))
    return ("\r\n".join(linhas) + "\r\n").encode("utf-8-sig")
