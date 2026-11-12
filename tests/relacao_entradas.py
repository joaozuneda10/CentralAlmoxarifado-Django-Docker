"""Gerador do CSV da "Relação de Requisições" de Entrada, no formato real do SCPI (spec 014).

Dados sintéticos, sem nomes de pessoas reais. O formato segue
`specs/014-entrada-por-pedido/contracts/relatorios-scpi.md`: UTF-8 com BOM, `;` sem aspas, CRLF, as
65 colunas do cabeçalho (mais o `;` final), `GRUPO` e `GRUPO_1` iguais a `DATAE` e uma linha por
item, com o cabeçalho da requisição repetido. As colunas que a leitura não usa têm os nomes de
preenchimento do relatório de saídas; só os nomes lidos importam. A observação do cabeçalho pode
quebrar o registro em duas linhas, como no SCPI.
"""

from dataclasses import dataclass, field
from datetime import date

from tests.relacao_requisicoes import COLUNAS as COLUNAS_SAIDAS

# As entradas trazem a quantidade em QUAN1 (as saídas, em QUAN2).
COLUNAS = [
    c.replace("QUAN2", "QUAN1").replace("VAUN2", "VAUN1").replace("VATO2", "VATO1")
    for c in COLUNAS_SAIDAS
]
assert len(COLUNAS) == 65


@dataclass
class ItemEntradaCSV:
    codigo: str
    quantidade: str = "1"  # como o SCPI escreve: "2", "1,5"
    unidade: str = "UN"


@dataclass
class EntradaCSV:
    requisicao: str  # 003492/26
    id_requi: int
    data_entrada: date
    fornecedor: str = "19502"
    nf: str = "000000000501"  # DOCUM: o SCPI guarda com zeros à esquerda
    pedido: str = "00514/26"  # NUMPED; vazio é entrada sem pedido
    observacoes: str = ""
    data_requisicao: date | None = None  # DTLAN; padrão: a mesma data
    saida: bool = False  # SAID = S
    tipo: str = "ENTRADA"
    responsavel: str = "USUARIO DO ROBO"
    itens: list[ItemEntradaCSV] = field(default_factory=lambda: [ItemEntradaCSV("006.011.020")])


def _br(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def _linha(req: EntradaCSV, item: ItemEntradaCSV) -> str:
    valores = dict.fromkeys(COLUNAS, "")
    valores.update(
        GRUPO=_br(req.data_entrada),
        GRUPO_1=_br(req.data_entrada),
        ID_REQUI=str(req.id_requi),
        REQUI=req.requisicao,
        CODIF=req.fornecedor,
        NOME="FORNECEDOR SINTÉTICO LTDA",
        DTLAN=_br(req.data_requisicao or req.data_entrada),
        DATAE=_br(req.data_entrada),
        ENTR="S",
        SAID="S" if req.saida else "",
        OBS_CABECALHO=req.observacoes,
        CADPRO=item.codigo,
        DISC1=f"MATERIAL {item.codigo}",
        UNID1=item.unidade,
        QUAN1=item.quantidade,
        VAUN1="1,5",
        VATO1="1,5",
        DOCUM=req.nf,
        TPREQUI=req.tipo,
        NUMPED=req.pedido,
        NPEDFILHO="",
        RESPONSA=req.responsavel,
    )
    return ";".join(valores[c] for c in COLUNAS) + ";"


def csv_entradas(requisicoes: list[EntradaCSV], *, quebra_final: bool = True) -> bytes:
    """Bytes do CSV como o SCPI o entrega. Uma `observacoes` com "\\n" quebra o registro."""
    linhas = [";".join(COLUNAS) + ";"]
    linhas += [_linha(req, item) for req in requisicoes for item in req.itens]
    texto = "\r\n".join(linhas) + ("\r\n" if quebra_final else "")
    return texto.encode("utf-8-sig")
