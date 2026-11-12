"""SCPI simulado das entradas para os testes do robô (sem pytest).

Cumpre o protocolo `scpi.lancamento_entradas.SCPIEntradas` sem navegador: guarda os pedidos como o
SCPI os tem (`pedidos`), registra as chamadas em `chamadas`, falha quando pedido, numera as
requisições salvas em sequência e, no Salvar, soma o "Já Entrou" como o SCPI faria. Entrega também
os dois relatórios no formato real: `relatorio_entradas` (o registro oficial) e `relatorio_pedidos`
(o 07.13).
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from compras.regras import LinhaTela, RecebimentoParaLancar, TelaItens
from scpi.leitura import NadaAExibir
from scpi.requisicoes import ResultadoIncerto
from tests.relacao_entradas import EntradaCSV, ItemEntradaCSV, csv_entradas
from tests.relacao_pedidos_compra import ItemPedidoCSV, csv_pedidos


class ErroSCPISimulado(Exception):
    """O SCPI recusou antes do Salvar (nada foi salvo)."""


@dataclass
class EntradaSalva:
    """O que um Salvar gravou no SCPI (ou o que alguém lançou à mão)."""

    requisicao: str
    pedido: tuple[int, int]
    fornecedor: str
    nf: str
    data: date
    observacoes: str
    itens: list[tuple[str, Decimal]]


def _csv_numero(n: int) -> str:
    return f"{n:06d}/26"


class SCPIEntradasSimulado:
    def __init__(self, *, proximo_numero: int = 3492):
        # {(ano, número do pedido): {item: {codigo, quantidade, anulado, ja_entrou, pedida}}}
        self.pedidos: dict[tuple[int, int], dict[int, dict]] = {}
        self.salvas: list[EntradaSalva] = []
        self.chamadas: list[tuple[str, str]] = []
        self.abertas = 0
        self.proximo_numero = proximo_numero
        # Falhas antes do Salvar: "abrir" e/ou "preencher".
        self.falha_antes: set[str] = set()
        # O Salvar grava a entrada no SCPI e depois falha (resposta perdida), por rótulo.
        self.salva_e_falha: set[str] = set()
        # O Salvar falha sem gravar (por rótulo).
        self.falha_salvar: set[str] = set()
        # {item: "Já Entrou" que a tela mostra}: alguém mexeu no pedido depois da importação.
        self.tela_mudou: dict[int, Decimal] = {}
        self.perde_observacoes: set[str] = set()
        self.nf_errada: dict[str, str] = {}  # rótulo → NF que o SCPI grava no lugar
        self.falhas_relatorio = 0  # quantas extrações seguidas falham antes de funcionar
        self.relatorios: list[tuple[date, date]] = []
        self.ao_preencher: Callable[[RecebimentoParaLancar], None] | None = None
        self.ao_salvar: Callable[[], None] | None = None
        self._rec: RecebimentoParaLancar | None = None

    # --- o estado do SCPI --------------------------------------------------------------------

    def pedido(self, ano: int, numero: int, itens: dict[int, tuple[str, str]], **campos) -> None:
        """Cria um pedido: `itens` é {número do item: (código, quantidade)}."""
        self.pedidos[(ano, numero)] = {
            item: {
                "codigo": codigo,
                "quantidade": Decimal(quantidade),
                "anulado": Decimal(0),
                "ja_entrou": Decimal(0),
                "pedida": Decimal(0),
                **campos,
            }
            for item, (codigo, quantidade) in itens.items()
        }

    def entrada_manual(
        self,
        pedido: tuple[int, int],
        itens: dict[int, str],
        *,
        data: date,
        nf: str = "999999",
        fornecedor: str = "19502",
    ) -> str:
        """Alguém lança uma entrada à mão no SCPI: pega o próximo número, sem a marca do robô."""
        numero = self._numero()
        linhas = self.pedidos[pedido]
        for item, quantidade in itens.items():
            linhas[item]["ja_entrou"] += Decimal(quantidade)
        self.salvas.append(
            EntradaSalva(
                numero,
                pedido,
                fornecedor,
                nf,
                data,
                "",
                [(linhas[i]["codigo"], Decimal(q)) for i, q in itens.items()],
            )
        )
        return numero

    def _numero(self) -> str:
        numero = _csv_numero(self.proximo_numero)
        self.proximo_numero += 1
        return numero

    # --- o protocolo -------------------------------------------------------------------------

    @contextmanager
    def abrir(self) -> Iterator["SCPIEntradasSimulado"]:
        self.abertas += 1
        yield self

    def abrir_pedido(self, rec: RecebimentoParaLancar) -> TelaItens:
        self._rec = rec
        self.chamadas.append(("abrir_pedido", rec.rotulo))
        if "abrir" in self.falha_antes:
            raise ErroSCPISimulado("o SCPI não abriu o pedido")
        linhas = []
        for item, dados in sorted(self.pedidos[(rec.pedido_ano, rec.pedido_numero)].items()):
            ja_entrou = self.tela_mudou.get(item, dados["ja_entrou"])
            saldo = dados["quantidade"] - dados["anulado"] - ja_entrou - dados["pedida"]
            linhas.append(
                LinhaTela(
                    item=item,
                    codigo=dados["codigo"],
                    quantidade=dados["quantidade"],
                    ja_entrou=ja_entrou,
                    ja_pedida=dados["pedida"],
                    saldo=saldo,
                )
            )
        return TelaItens(tuple(linhas))

    def preencher(self, rec: RecebimentoParaLancar) -> None:
        self._rec = rec
        self.chamadas.append(("preencher", rec.rotulo))
        if "preencher" in self.falha_antes:
            raise ErroSCPISimulado("o SCPI recusou o preenchimento")
        if self.ao_preencher is not None:
            self.ao_preencher(rec)

    def salvar(self) -> str:
        rec = self._rec
        self.chamadas.append(("salvar", rec.rotulo))
        if rec.rotulo in self.falha_salvar:
            raise ResultadoIncerto("o SCPI não respondeu ao Salvar")
        numero = self._numero()
        linhas = self.pedidos[(rec.pedido_ano, rec.pedido_numero)]
        for i in rec.itens:
            linhas[i.item]["ja_entrou"] += i.quantidade
        self.salvas.append(
            EntradaSalva(
                numero,
                (rec.pedido_ano, rec.pedido_numero),
                rec.fornecedor_codigo,
                self.nf_errada.get(rec.rotulo, rec.nf),
                rec.data,
                "" if rec.rotulo in self.perde_observacoes else rec.observacoes,
                [(i.codigo, i.quantidade) for i in rec.itens],
            )
        )
        if rec.rotulo in self.salva_e_falha:
            raise ResultadoIncerto("o SCPI salvou, mas a resposta se perdeu")
        if self.ao_salvar is not None:
            self.ao_salvar()
        return numero

    def depois_de_salvar(self) -> None:
        self.chamadas.append(("depois_de_salvar", self._rec.rotulo if self._rec else ""))

    def encerrar_simulacao(self) -> None:
        self.chamadas.append(("simulacao", self._rec.rotulo if self._rec else ""))

    def descartar(self, rec: RecebimentoParaLancar) -> None:
        self.chamadas.append(("descartar", rec.rotulo))

    def reiniciar(self) -> None:
        self.chamadas.append(("reiniciar", ""))

    # --- os relatórios -----------------------------------------------------------------------

    def relatorio_entradas(self, de: date, ate: date) -> bytes:
        """A "Relação de Requisições" de Entrada, filtrada pela data da entrada; sem nenhuma,
        `NadaAExibir`, como em `relatorios.baixar_entradas`."""
        self.relatorios.append((de, ate))
        if self.falhas_relatorio:
            self.falhas_relatorio -= 1
            raise RuntimeError("SCPI fora do ar")
        no_periodo = [s for s in self.salvas if de <= s.data <= ate]
        if not no_periodo:
            raise NadaAExibir("Entradas do SCPI: nada a exibir.")
        return csv_entradas(
            [
                EntradaCSV(
                    s.requisicao,
                    int(s.requisicao[:6]) + 100,
                    s.data,
                    fornecedor=s.fornecedor,
                    nf=s.nf.zfill(12),
                    pedido=f"{s.pedido[1]:05d}/{s.pedido[0] % 100:02d}",
                    observacoes=s.observacoes,
                    itens=[
                        ItemEntradaCSV(codigo, format(q.normalize(), "f")) for codigo, q in s.itens
                    ],
                )
                for s in no_periodo
            ]
        )

    def relatorio_pedidos(self) -> bytes:
        """O 07.13: uma linha por item com saldo, no estado de agora."""
        itens = []
        for (ano, numero), linhas in self.pedidos.items():
            for item, d in sorted(linhas.items()):
                saldo = d["quantidade"] - d["anulado"] - d["ja_entrou"] - d["pedida"]
                if saldo > 0:
                    itens.append(
                        ItemPedidoCSV(
                            f"{numero:05d}/{ano % 100:02d}",
                            item,
                            d["codigo"],
                            quantidade=format(d["quantidade"].normalize(), "f"),
                            ja_entrou=format(d["ja_entrou"].normalize(), "f"),
                        )
                    )
        return csv_pedidos(itens)
