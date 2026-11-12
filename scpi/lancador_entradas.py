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
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from compras.regras import LinhaTela, RecebimentoParaLancar, TelaItens, norm_codigo
from scpi.browser import abrir_sessao, frame_compras, orm_liberado
from scpi.lancador import (
    TIMEOUT,
    Sessao,
    aguardar_mascara,
    botao_habilitado,
    campo,
    checar_mensagem,
    fechar_janelas_pos_salvar,
    localizar_salvar,
    mensagem_scpi,
    parse_decimal_br,
    pausar,
    resumo_erro,
    salvar_requisicao,
)
from scpi.requisicoes import ErroSCPI, ResultadoIncerto

log = logging.getLogger("scpi.lancamento_entradas").info

ESPERA_ESCOLHA_MS = 30000  # a janela "Escolha os Itens" e as linhas dela

# Colunas de "Escolha os Itens", pelo texto do cabeçalho (SCPI, 12/11/2026): `exato` para os nomes
# que são prefixo de outros ("Qtd." também começa "Qtd. Já Entrou"). R25: confirmar "Qtd. Saldo".
COLUNAS_TELA = (
    ("item", "Item", True),
    ("codigo", "Código", True),
    ("quantidade", "Qtd.", True),
    ("ja_entrou", "Qtd. Já Entrou", False),
    ("ja_pedida", "Qtd. Já Ped", False),
    ("saldo", "Qtd. Saldo", False),
)

JS_LER_ESCOLHA_DOS_ITENS = """
() => {
    // A grade do painel "Escolha os Itens": os cabeçalhos e, por linha, o texto de cada célula.
    const vis = e => e.offsetParent !== null;
    for (const grade of [...document.querySelectorAll('.x-grid')].filter(vis)) {
        const cabecalhos = [...grade.querySelectorAll('.x-column-header')]
            .filter(vis).map(h => h.textContent.trim());
        if (!cabecalhos.includes('Item') || !cabecalhos.includes('Código')) continue;
        const linhas = [...grade.querySelectorAll('.x-grid-row')].filter(vis).map(linha =>
            [...linha.querySelectorAll('.x-grid-cell')].map(c => c.textContent.trim()));
        return {cabecalhos, linhas};
    }
    return null;
}
"""


JS_LINHA_MARCADA = """
(linha) => !!linha.querySelector(
    '.x-grid-checkcolumn-checked, .x-grid-row-checker-checked, input[type=checkbox]:checked, '
    + '.x-form-cb-checked'
) || linha.classList.contains('x-grid-item-selected')
    || linha.classList.contains('x-grid-row-selected')
"""


def _qtd_br(quantidade) -> str:
    """12 → "12"; 1.5 → "1,5": a quantidade como o SCPI a mostra e aceita."""
    return format(quantidade.normalize(), "f").replace(".", ",")


def _numero_pedido(rec: RecebimentoParaLancar) -> tuple[str, str]:
    """Número e ano para a pesquisa do pedido (R25: "00514" e "2026" ou "26")."""
    return f"{rec.pedido_numero:05d}", str(rec.pedido_ano)


def _indice(cabecalhos: list[str], texto: str, exato: bool) -> int:
    for i, cabecalho in enumerate(cabecalhos):
        if cabecalho == texto or (not exato and cabecalho.startswith(texto)):
            return i
    raise ErroSCPI(
        f"a grade de Escolha os Itens não tem a coluna '{texto}' (cabeçalhos: "
        f"{', '.join(cabecalhos)})"
    )


def ler_escolha_dos_itens(dados: dict | None) -> TelaItens:
    """A grade lida (`cabecalhos` e `linhas` de texto) como `TelaItens`; vazia é erro (a tela não
    abriu ou ainda não carregou)."""
    if not dados or not dados.get("linhas"):
        raise ErroSCPI('a grade de "Escolha os Itens" não trouxe nenhuma linha')
    cabecalhos = dados["cabecalhos"]
    onde = {nome: _indice(cabecalhos, texto, exato) for nome, texto, exato in COLUNAS_TELA}
    lidas = []
    for celulas in dados["linhas"]:
        try:
            valor = {nome: celulas[i] for nome, i in onde.items()}
            lidas.append(
                LinhaTela(
                    item=int(re.sub(r"\D", "", valor["item"])),
                    codigo=valor["codigo"],
                    quantidade=parse_decimal_br(valor["quantidade"]),
                    ja_entrou=parse_decimal_br(valor["ja_entrou"]),
                    ja_pedida=parse_decimal_br(valor["ja_pedida"]),
                    saldo=parse_decimal_br(valor["saldo"]),
                )
            )
        except (ValueError, ArithmeticError, IndexError) as exc:
            raise ErroSCPI(f"linha ilegível em Escolha os Itens: {celulas!r}") from exc
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
        for passo in (self._cancelar_entrada, self.reabrir_modulo, self.reiniciar):
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
            # O diálogo "Nova Requisição de Entrada" tem os botões Por Pedido, Por Produto, Por
            # Subpedido, Por Devolução e Copiar Existente (SCPI, 12/11/2026).
            frame.get_by_role("button", name=re.compile(r"^\s*Por Pedido\s*$", re.I)).filter(
                visible=True
            ).first.click()
            pesquisa = frame.get_by_label(re.compile("Pesquisa Pedido de Compra", re.I))
            pesquisa.wait_for(state="visible", timeout=TIMEOUT)
            # "Pesquisa por: 1- Nº Pedido" já vem marcado. Os dois campos de texto são, na ordem, o
            # pedido (máscara ____/__: número e ano de dois dígitos) e o ano da pesquisa (SCPI,
            # 12/11/2026; R25: o que o ano da pesquisa faz com um pedido do exercício anterior).
            campos = pesquisa.locator('input[type="text"]').filter(visible=True)
            pedido_digitado = f"{numero}{rec.pedido_ano % 100:02d}"
            campos.nth(0).click()
            campos.nth(0).press_sequentially(pedido_digitado, delay=50)
            campos.nth(1).fill(ano)
            pesquisa.get_by_role("button", name=re.compile(r"^\s*Pesquisar\s*$", re.I)).click()
            aguardar_mascara(frame)
            # A linha do pedido e o botão Selecionar (SCPI, 12/11/2026): carrega "Escolha os Itens".
            pesquisa.locator(".x-grid-row").filter(visible=True).first.click()
            pesquisa.get_by_role("button", name=re.compile(r"^\s*Selecionar\s*$", re.I)).click()
            # Depois do duplo clique o SCPI mostra "Aguarde…" e só então abre "Escolha os Itens":
            # espera a janela e a grade carregarem (as linhas chegam depois da janela).
            frame.get_by_text("Escolha os Itens", exact=True).filter(visible=True).first.wait_for(
                state="visible", timeout=ESPERA_ESCOLHA_MS
            )
            aguardar_mascara(frame)
            checar_mensagem(frame, "abrir pedido")
            linhas = None
            for _ in range(ESPERA_ESCOLHA_MS // 500):
                linhas = frame.evaluate(JS_LER_ESCOLHA_DOS_ITENS)
                if linhas and linhas.get("linhas"):
                    break
                frame.page.wait_for_timeout(500)
            return ler_escolha_dos_itens(linhas)
        except ErroSCPI:
            raise
        except Exception as exc:
            raise ErroSCPI(resumo_erro(exc)) from exc

    def preencher(self, rec: RecebimentoParaLancar) -> None:
        """Marca só os itens do recebimento em "Escolha os Itens" e confirma; preenche a data da
        entrada e a NF no formulário e, em "Itens da Entrada", a QTD e a Observação (a marca
        `RC-…`) de cada item; depois confere tudo na tela. Qualquer falha é `ErroSCPI`."""
        frame = self.frame
        try:
            log("  etapa: preencher a entrada")
            self._marcar_itens(rec)
            frame.get_by_role("button", name=re.compile(r"^\s*Confirmar\s*$", re.I)).filter(
                visible=True
            ).first.click()
            aguardar_mascara(frame)
            self._confirmar_empenhos()
            checar_mensagem(frame, "confirmar os itens")
            self._digitar("Data e Hora da Entrada", f"{rec.data:%d/%m/%Y}")
            self._digitar("Nota Fiscal", rec.nf)  # sem zeros à esquerda
            self._preencher_itens(rec)
            self._conferir_itens(rec)
            checar_mensagem(frame, "preencher a entrada")
            self._salvar = localizar_salvar(frame)
        except ErroSCPI:
            raise
        except Exception as exc:
            raise ErroSCPI(resumo_erro(exc)) from exc

    def _grade(self, *cabecalhos: str):
        """A grade visível que tem estes cabeçalhos (a de "Escolha os Itens" ou a de "Itens da
        Entrada")."""
        grade = self.frame.locator(".x-grid").filter(visible=True)
        for cabecalho in cabecalhos:
            grade = grade.filter(
                has=self.frame.locator(".x-column-header").filter(
                    has_text=re.compile(rf"^\s*{re.escape(cabecalho)}\s*$")
                )
            )
        return grade.first

    def _marcar_itens(self, rec: RecebimentoParaLancar) -> None:
        """Em "Escolha os Itens", os itens do recebimento ficam marcados e os outros, não. O
        estado vem marcado (todos); clicar na primeira célula da linha alterna (R25: o estado
        marcado é lido pela classe ou pelo input; a conferência final de "Itens da Entrada" pega
        qualquer engano antes do Salvar)."""
        no_recebimento = {i.item for i in rec.itens}
        grade = self._grade("Item", "Código", "Qtd. Saldo")
        for linha in grade.locator(".x-grid-row").filter(visible=True).all():
            celulas = linha.locator(".x-grid-cell")
            numero = int(re.sub(r"\D", "", celulas.nth(1).inner_text()))
            marcada = linha.evaluate(JS_LINHA_MARCADA)
            if (numero in no_recebimento) != marcada:
                celulas.first.click()
                pausar(self.frame)

    def _confirmar_empenhos(self) -> None:
        """A janela de empenhos, se abrir, é confirmada sem escolher nada (D7). Na entrada vista em
        12/11/2026 o empenho já veio preenchido e a janela não abriu."""
        janela = self.frame.get_by_label(re.compile("Empenho", re.I)).filter(visible=True)
        if janela.count():
            janela.first.get_by_role("button", name=re.compile("OK|Confirmar", re.I)).click()
            aguardar_mascara(self.frame)

    def _digitar(self, rotulo: str, valor: str) -> None:
        """Escreve no campo que tem este rótulo e sai dele (a máscara de data aceita os dígitos)."""
        entrada = campo(self.frame, rotulo)
        entrada.click()
        self.page.keyboard.press("ControlOrMeta+A")
        self.page.keyboard.type(valor, delay=30)
        self.page.keyboard.press("Tab")
        pausar(self.frame)

    def _abrir_itens_da_entrada(self):
        """A aba "Itens da Entrada" e a grade dela, com os índices das colunas pelos cabeçalhos."""
        self.frame.locator(".x-tab").filter(
            has_text=re.compile(r"^\s*Itens da Entrada\s*$")
        ).first.click()
        pausar(self.frame)
        grade = self._grade("Item", "QTD", "Observação")
        cabecalhos = [
            t.strip() for t in grade.locator(".x-column-header").all_inner_texts() if t.strip()
        ]
        return grade, {
            nome: _indice(cabecalhos, nome, True)
            for nome in ("Item", "Código", "QTD", "Observação")
        }

    def _editar_celula(self, celula, texto: str) -> None:
        celula.dblclick()
        self.page.keyboard.press("ControlOrMeta+A")
        self.page.keyboard.type(texto, delay=30)
        self.page.keyboard.press("Enter")
        pausar(self.frame)

    def _preencher_itens(self, rec: RecebimentoParaLancar) -> None:
        """A QTD (o padrão é o saldo inteiro) e a Observação de cada item da grade, achados pelo
        número do item no pedido, nunca pela posição."""
        grade, onde = self._abrir_itens_da_entrada()
        por_item = {i.item: i for i in rec.itens}
        for linha in grade.locator(".x-grid-row").filter(visible=True).all():
            celulas = linha.locator(".x-grid-cell")
            numero = int(re.sub(r"\D", "", celulas.nth(onde["Item"]).inner_text()))
            item = por_item.get(numero)
            if item is None:
                continue
            self._editar_celula(celulas.nth(onde["QTD"]), _qtd_br(item.quantidade))
            self._editar_celula(celulas.nth(onde["Observação"]), rec.observacoes)

    def _conferir_itens(self, rec: RecebimentoParaLancar) -> None:
        """A conferência final de "Itens da Entrada", antes do Salvar: só os itens do recebimento,
        com o código, a QTD e a Observação digitados. Qualquer diferença é `ErroSCPI`."""
        grade, onde = self._abrir_itens_da_entrada()
        lidas = {}
        for linha in grade.locator(".x-grid-row").filter(visible=True).all():
            celulas = [c.strip() for c in linha.locator(".x-grid-cell").all_inner_texts()]
            lidas[int(re.sub(r"\D", "", celulas[onde["Item"]]))] = celulas
        esperado = {i.item: i for i in rec.itens}
        if set(lidas) != set(esperado):
            raise ErroSCPI(
                f"os itens da entrada são {sorted(lidas)} e o recebimento tem {sorted(esperado)}"
            )
        for numero, item in esperado.items():
            celulas = lidas[numero]
            if norm_codigo(celulas[onde["Código"]]) != norm_codigo(item.codigo):
                raise ErroSCPI(f"item {numero}: código {celulas[onde['Código']]} na grade")
            if parse_decimal_br(celulas[onde["QTD"]]) != item.quantidade:
                raise ErroSCPI(
                    f"item {numero}: QTD {celulas[onde['QTD']]} na grade, esperado "
                    f"{_qtd_br(item.quantidade)}"
                )
            if celulas[onde["Observação"]] != rec.observacoes:
                raise ErroSCPI(f"item {numero}: a Observação não ficou como o robô digitou")

    def _cancelar_entrada(self) -> None:
        """Descarta o que estiver aberto: o botão Cancelar (da pesquisa ou do formulário) e, no
        formulário, o "Você Realmente Deseja Cancelar?" com Sim (SCPI, 12/11/2026). Repete até o
        Inserir voltar a ficar disponível."""
        frame = self.frame
        inserir = frame.get_by_role("button", name="Inserir", exact=True).filter(visible=True).first
        for _ in range(4):
            try:
                frame.get_by_role("button", name="Cancelar", exact=True).filter(
                    visible=True
                ).last.click(timeout=5000)
            except Exception:
                pass
            try:
                frame.get_by_role("button", name="Sim", exact=True).filter(visible=True).last.click(
                    timeout=3000
                )
            except Exception:
                pass
            pausar(frame)
            msg = mensagem_scpi(frame)
            if msg and "OK" in msg["botoes"]:
                frame.get_by_role("button", name="OK", exact=True).last.click()
            if botao_habilitado(inserir):
                return
        raise ErroSCPI("o SCPI não voltou ao estado inicial depois de cancelar a entrada")

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
