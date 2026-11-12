"""Navegação do lançamento de entradas por pedido no SCPI (Playwright), atrás do protocolo
`scpi.lancamento_entradas.SCPIEntradas`.

NÃO É COBERTA PELOS TESTES AUTOMÁTICOS (Princípio V) e **ainda não foi exercitada contra o SCPI
real**: os rótulos, o caminho de menu e a leitura da grade seguem o contrato
(`specs/014-entrada-por-pedido/contracts/robo-entradas.md`) e a pesquisa do registro (F1 a F25), e
cada ponto incerto está marcado com "R25" (o que só o SCPI real confirma). O primeiro `--dry-run`
(quickstart, passo 4) é quem os confirma: tudo o que falhar aqui levanta `ErroSCPI` antes do Salvar,
e o robô descarta a tela sem salvar nada. O Salvar e a leitura do número reaproveitam, sem mudança,
as funções de `scpi/lancador.py` que o lançamento das saídas já exerce no SCPI real.

Caminho no SCPI: COMPRAS → Movimento → Entrada de Material → Inserir → "por pedido" → Pesquisa
Pedido de Compra (número + ano) → "Escolha os Itens" → formulário da entrada.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from compras.regras import LinhaTela, RecebimentoParaLancar, TelaItens
from scpi.browser import abrir_sessao, frame_compras, orm_liberado
from scpi.lancador import (
    TIMEOUT,
    Sessao,
    aguardar_mascara,
    cancelar_formulario,
    checar_mensagem,
    fechar_janelas_pos_salvar,
    localizar_salvar,
    parse_decimal_br,
    pausar,
    resumo_erro,
    salvar_requisicao,
)
from scpi.requisicoes import ErroSCPI, ResultadoIncerto

log = logging.getLogger("scpi.lancamento_entradas").info

# Colunas de "Escolha os Itens", pelo cabeçalho (R25: confirmar os rótulos no --dry-run).
COLUNAS_TELA = ("Item", "Código", "Qtd.", "Já Entrou", "Já Pedida", "Qtd. Saldo")

JS_LER_ESCOLHA_DOS_ITENS = """
(colunas) => {
    // As linhas visíveis da grade "Escolha os Itens": cada uma é a lista dos textos das células,
    // na ordem das colunas pedidas (pelo texto do cabeçalho).
    const vis = e => e.offsetParent !== null;
    const grades = [...document.querySelectorAll('.x-grid')].filter(vis);
    for (const grade of grades) {
        const cabecalhos = [...grade.querySelectorAll('.x-column-header')]
            .filter(vis).map(h => h.textContent.trim());
        const indices = colunas.map(c => cabecalhos.indexOf(c));
        if (indices.some(i => i < 0)) continue;
        return [...grade.querySelectorAll('.x-grid-row')].filter(vis).map(linha => {
            const celulas = [...linha.querySelectorAll('.x-grid-cell')]
                .map(c => c.textContent.trim());
            return indices.map(i => celulas[i] ?? '');
        });
    }
    return null;
}
"""


def _numero_pedido(rec: RecebimentoParaLancar) -> tuple[str, str]:
    """Número e ano para a pesquisa do pedido (R25: "00514" e "2026" ou "26")."""
    return f"{rec.pedido_numero:05d}", str(rec.pedido_ano)


def ler_escolha_dos_itens(linhas: list[list[str]] | None) -> TelaItens:
    """As linhas lidas da grade (textos) como `TelaItens`; vazio é erro (a tela não abriu)."""
    if not linhas:
        raise ErroSCPI('a janela "Escolha os Itens" não trouxe nenhuma linha')
    lidas = []
    for item, codigo, quantidade, ja_entrou, ja_pedida, saldo in linhas:
        try:
            lidas.append(
                LinhaTela(
                    item=int(re.sub(r"\D", "", item)),
                    codigo=codigo,
                    quantidade=parse_decimal_br(quantidade),
                    ja_entrou=parse_decimal_br(ja_entrou),
                    ja_pedida=parse_decimal_br(ja_pedida),
                    saldo=parse_decimal_br(saldo),
                )
            )
        except (ValueError, ArithmeticError) as exc:
            raise ErroSCPI(f"linha ilegível em Escolha os Itens: {linhas!r}") from exc
    return TelaItens(tuple(lidas))


class NavegadorEntradas(Sessao):
    """O `SCPIEntradas` sobre o Playwright, com o perfil `entradas`."""

    def __init__(self, playwright):
        super().__init__(playwright)
        self._salvar = None

    def abrir(self) -> None:
        self.context, self.page = abrir_sessao(
            self.playwright, settings.SCPI_PERFIL_DIR / "entradas"
        )
        self.frame = frame_compras(self.page)
        self._abrir_tela_de_entrada()

    def _abrir_tela_de_entrada(self) -> None:
        """Movimento → a tela de entrada (R25). O nome provável é "Requisição de Entrada", irmã da
        "Requisição de Saída" das saídas; os outros são alternativas. Sem nenhum, o erro lista o que
        o menu mostrava, para o nome certo poder ser conferido na tela."""
        frame = self.frame
        nomes = ("Requisição de Entrada", "Entrada de Material", "Entrada por Pedido")
        frame.locator("div").filter(has_text=re.compile(r"^Movimento$")).first.wait_for(
            state="attached", timeout=TIMEOUT
        )
        for nome in nomes:
            menu = frame.locator("div").filter(has_text=re.compile(rf"^{re.escape(nome)}$")).first
            try:
                menu.wait_for(state="attached", timeout=3000)
            except Exception:
                frame.locator("div").filter(has_text=re.compile(r"^Movimento$")).first.click()
                try:
                    menu.wait_for(state="attached", timeout=3000)
                except Exception:
                    continue
            if not menu.is_visible():
                frame.locator("div").filter(has_text=re.compile(r"^Movimento$")).first.click()
            menu.click()
            frame.get_by_role("button", name="Inserir", exact=True).wait_for(
                state="visible", timeout=TIMEOUT
            )
            aguardar_mascara(frame)
            log(f"  tela de entrada aberta pelo item de menu '{nome}'")
            return
        visiveis = frame.evaluate(
            """() => [...new Set([...document.querySelectorAll('div')]
                .filter(e => e.offsetParent !== null && !e.children.length)
                .map(e => e.textContent.trim())
                .filter(t => t && t.length < 40))].slice(0, 60)"""
        )
        raise ErroSCPI(
            "não achei a tela de entrada no menu Movimento (tentei "
            f"{', '.join(nomes)}); itens à vista: {', '.join(visiveis) or 'nenhum'}"
        )

    def reabrir_modulo(self) -> None:
        log("  reabrindo módulo Compras")
        self.page.get_by_role("button", name="Fechar", exact=True).click()
        self.page.get_by_text("COMPRAS", exact=True).wait_for(state="visible", timeout=TIMEOUT)
        self.frame = frame_compras(self.page)
        self._abrir_tela_de_entrada()

    def reiniciar(self) -> None:
        log("  reabrindo sessão SCPI do zero")
        self.fechar()
        self.abrir()

    def limpar(self) -> None:
        for passo in (lambda: cancelar_formulario(self.frame), self.reabrir_modulo, self.reiniciar):
            try:
                passo()
                return
            except Exception as exc:
                log(f"  limpeza falhou ({resumo_erro(exc)}); tentando o próximo passo")
        raise RuntimeError("não foi possível voltar a um estado limpo no SCPI")

    # --- o protocolo ---------------------------------------------------------------------------

    def abrir_pedido(self, rec: RecebimentoParaLancar) -> TelaItens:
        """Inserir › "por pedido" › Pesquisa Pedido de Compra (número + ano) › lê "Escolha os
        Itens". Qualquer falha é `ErroSCPI`: nada foi salvo."""
        frame = self.frame
        try:
            log("  etapa: abrir pedido")
            numero, ano = _numero_pedido(rec)
            frame.get_by_role("button", name="Inserir", exact=True).click()
            frame.get_by_role("menuitem", name=re.compile("por pedido", re.I)).click()  # R25
            pesquisa = frame.get_by_label(re.compile("Pesquisa Pedido de Compra", re.I))
            pesquisa.wait_for(state="visible", timeout=TIMEOUT)
            pesquisa.get_by_label(re.compile(r"N[úu]mero", re.I)).fill(numero)  # R25
            pesquisa.get_by_label(re.compile("Ano", re.I)).fill(ano)  # R25: o ano do pedido
            pesquisa.get_by_role("button", name=re.compile("Pesquisar|Buscar", re.I)).click()
            aguardar_mascara(frame)
            pesquisa.locator(".x-grid-row").filter(visible=True).first.dblclick()  # R25
            aguardar_mascara(frame)
            checar_mensagem(frame, "abrir pedido")
            linhas = frame.evaluate(JS_LER_ESCOLHA_DOS_ITENS, list(COLUNAS_TELA))
            return ler_escolha_dos_itens(linhas)
        except ErroSCPI:
            raise
        except Exception as exc:
            raise ErroSCPI(resumo_erro(exc)) from exc

    def preencher(self, rec: RecebimentoParaLancar) -> None:
        """Desmarca os itens fora do recebimento, confirma os empenhos sem escolher, preenche a
        QTD de cada linha da grade, a data da entrada, a NF e as Observações, e confere tudo."""
        frame = self.frame
        try:
            log("  etapa: preencher a entrada")
            no_recebimento = {i.item for i in rec.itens}
            escolha = frame.get_by_label(re.compile("Escolha os Itens", re.I))
            for linha in escolha.locator(".x-grid-row").filter(visible=True).all():
                numero = int(re.sub(r"\D", "", linha.locator(".x-grid-cell").first.inner_text()))
                caixa = linha.get_by_role("checkbox")
                if (numero in no_recebimento) != caixa.is_checked():
                    caixa.click()
                pausar(frame)
            escolha.get_by_role("button", name=re.compile("OK|Confirmar", re.I)).click()  # R25
            aguardar_mascara(frame)
            self._confirmar_empenhos()
            for i in rec.itens:
                self._preencher_qtd(i.codigo, i.quantidade)
            self._digitar("Data", f"{rec.data:%d/%m/%Y}")  # a hora sugerida fica (R25)
            self._digitar("Nota Fiscal", rec.nf)  # sem zeros à esquerda (R25: o rótulo)
            self._digitar("Observações", rec.observacoes)
            checar_mensagem(frame, "preencher a entrada")
            self._salvar = localizar_salvar(frame)
        except ErroSCPI:
            raise
        except Exception as exc:
            raise ErroSCPI(resumo_erro(exc)) from exc

    def _confirmar_empenhos(self) -> None:
        """A janela de empenhos é confirmada sem escolher nada (D7)."""
        janela = self.frame.get_by_label(re.compile("Empenho", re.I))
        if janela.count():
            janela.get_by_role("button", name=re.compile("OK|Confirmar", re.I)).click()
            aguardar_mascara(self.frame)

    def _digitar(self, rotulo: str, valor: str) -> None:
        from scpi.lancador import campo

        entrada = campo(self.frame, rotulo)
        entrada.fill(valor)
        entrada.press("Tab")
        pausar(self.frame)

    def _preencher_qtd(self, codigo: str, quantidade: Decimal) -> None:
        """A grade renumera de 1 a n: a linha é a do código, e um código repetido que não dá para
        distinguir é erro (R25: confirmar no --dry-run com um pedido de código repetido)."""
        grade = self.frame.locator(".x-grid-row").filter(visible=True, has_text=codigo)
        if grade.count() != 1:
            raise ErroSCPI(f"o código {codigo} aparece {grade.count()} vezes na grade da entrada")
        celula = grade.first.locator(".x-grid-cell").filter(has_text=re.compile(r"[\d,.]+$")).last
        celula.dblclick()
        self.page.keyboard.type(format(quantidade.normalize(), "f").replace(".", ","))
        self.page.keyboard.press("Tab")
        pausar(self.frame)

    def salvar(self) -> str:
        try:
            log("  etapa: salvar no SCPI")
            return salvar_requisicao(self.frame, self._salvar)
        except ResultadoIncerto:
            raise
        except Exception as exc:
            raise ResultadoIncerto(resumo_erro(exc)) from exc

    def depois_de_salvar(self) -> None:
        try:
            fechar_janelas_pos_salvar(self.frame)
        except Exception as exc:
            log(f"  ⚠ janelas pós-salvar ({type(exc).__name__}); seguindo com a reabertura")
        self.reabrir_modulo()

    def _recomecar(self) -> None:
        """Depois de um recebimento não salvo, o próximo começa num módulo reaberto, como depois
        de um lançamento (o mesmo cuidado do lançamento das saídas)."""
        self.limpar()
        try:
            self.reabrir_modulo()
        except Exception as exc:
            log(f"  reabertura do módulo falhou ({resumo_erro(exc)}); tentando o próximo passo")
            self.reiniciar()

    def encerrar_simulacao(self) -> None:
        log("  [DRY-RUN] entrada preenchida e conferida — NÃO clicado em Salvar")
        self._recomecar()

    def descartar(self, rec: RecebimentoParaLancar) -> None:
        momento = timezone.localtime()
        caminho = Path(settings.LOG_DIR) / f"scpi-entradas-{rec.rotulo}-{momento:%Y%m%d_%H%M%S}.png"
        try:
            self.page.screenshot(path=str(caminho))
            log(f"  print da tela: {caminho}")
        except Exception:
            log(f"  não foi possível salvar o print da tela em {caminho}")
        self._recomecar()


@contextmanager
def navegador() -> Iterator[NavegadorEntradas]:
    """Abre o Playwright, entra no SCPI até a tela de entrada e fecha tudo no fim. O lançamento
    grava no banco com o navegador aberto, então o ORM fica liberado (`orm_liberado`)."""
    from playwright.sync_api import sync_playwright

    with orm_liberado(), sync_playwright() as playwright:
        sessao = NavegadorEntradas(playwright)
        try:
            sessao.abrir()
            yield sessao
        finally:
            sessao.fechar()
