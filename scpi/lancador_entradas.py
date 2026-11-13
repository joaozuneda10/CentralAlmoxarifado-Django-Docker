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
# A espera da janela "Pesquisa de empenhos" depois do Confirmar dos itens (nem sempre abre).
ESPERA_EMPENHOS_MS = 5_000

# Colunas de "Escolha os Itens", pelo texto do cabeçalho (SCPI, 12/11/2026): `exato` para os nomes
# que são prefixo de outros ("Qtd." também comeca "Qtd. Já Entrou"). R25: confirmar "Qtd. Saldo".
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
            .map(h => h.innerText.trim());
        if (!cabecalhos.includes('Item') || !cabecalhos.includes('Código')) continue;
        const linhas = [...grade.querySelectorAll('.x-grid-row')].filter(vis).map(linha =>
            [...linha.querySelectorAll('.x-grid-cell')].map(c => c.innerText.trim()));
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


JS_GRADE_POR_CABECALHOS = """
(nomes) => {
    const vis = e => e.offsetParent !== null;
    for (const grade of [...document.querySelectorAll('.x-grid')].filter(vis)) {
        const cabecalhos = [...grade.querySelectorAll('.x-column-header')]
            .map(h => h.innerText.trim());
        if (nomes.every(n => cabecalhos.includes(n))) return grade.id;
    }
    return null;
}
"""


def _respirar(frame) -> None:
    """Dá um respiro ao SCPI depois de cada ação: espera o "Carregando…" sumir e a pausa de
    sempre (`pausar`). Cada edição de célula faz o servidor recarregar a grade; a ação seguinte
    sobre a grade em recarga se perde ou fica sem alvo (como no lançamento das saídas)."""
    aguardar_mascara(frame)
    pausar(frame)


def _clicar(botao, *, espera_ms: int = 4000) -> None:
    """Clica no botão; se o Playwright não consegue alcançá-lo (a janela do SCPI passa da altura
    do navegador e o botão fica abaixo da área visível, sem rolagem), dispara o clique pelo DOM,
    que o ExtJS trata como o de um mouse (SCPI, 12/11/2026)."""
    try:
        botao.click(timeout=espera_ms)
    except Exception:
        botao.dispatch_event("click")


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


def _na_grade(rec: RecebimentoParaLancar) -> dict:
    """Os itens do recebimento pela posição que têm na grade "Itens da Entrada": o SCPI renumera
    os escolhidos de 1 a n, na ordem do pedido (F1; confirmado com os itens 13, 35, 47 e 55 do
    00514/26 em 12/11/2026). O código de cada linha é conferido por quem usa."""
    return dict(enumerate(sorted(rec.itens, key=lambda i: i.item), start=1))


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
            _clicar(pesquisa.get_by_role("button", name=re.compile(r"^\s*Selecionar\s*$", re.I)))
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
            _clicar(
                frame.get_by_role("button", name=re.compile(r"^\s*Confirmar\s*$", re.I))
                .filter(visible=True)
                .first
            )
            aguardar_mascara(frame)
            self._confirmar_empenhos()
            checar_mensagem(frame, "confirmar os itens")
            self._digitar("Data e Hora da Entrada", f"{rec.data:%d/%m/%Y}", comeca=True)
            self._digitar("Nota Fiscal", rec.nf, sem_zeros=True)  # o SCPI a completa com zeros
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
        Entrada"), achada pelo texto dos cabeçalhos: os IDs do ExtJS mudam a cada sessão."""
        id_grade = self.frame.evaluate(JS_GRADE_POR_CABECALHOS, list(cabecalhos))
        if not id_grade:
            raise ErroSCPI(f"nenhuma grade visível com as colunas {', '.join(cabecalhos)}")
        return self.frame.locator(f"#{id_grade}")

    def _marcar_itens(self, rec: RecebimentoParaLancar) -> None:
        """Em "Escolha os Itens", os itens do recebimento ficam marcados e os outros, não. O
        estado vem marcado (todos). A caixa é o `span.x-grid-checkcolumn` da primeira célula, com
        a classe `-checked` quando marcada: é nele que se clica (o clique na célula só seleciona a
        linha; SCPI, 12/11/2026), e o robô confere que a marca mudou. A conferência final de
        "Itens da Entrada" pega qualquer engano antes do Salvar."""
        no_recebimento = {i.item for i in rec.itens}
        grade = self._grade("Item", "Código", "Qtd. Saldo")
        vistos = set()
        for linha in grade.locator(".x-grid-row").filter(visible=True).all():
            celulas = linha.locator(".x-grid-cell")
            numero = int(re.sub(r"\D", "", celulas.nth(1).inner_text()))
            vistos.add(numero)
            caixa = linha.locator(".x-grid-checkcolumn").first
            marcada = linha.locator(".x-grid-checkcolumn-checked").count() > 0
            if (numero in no_recebimento) == marcada:
                continue
            caixa.click()
            _respirar(self.frame)
            if (linha.locator(".x-grid-checkcolumn-checked").count() > 0) == marcada:
                raise ErroSCPI(f"a marca do item {numero} em Escolha os Itens não mudou")
        faltam = no_recebimento - vistos
        if faltam:
            raise ErroSCPI(f"Escolha os Itens não tem os itens {sorted(faltam)} do recebimento")

    def _confirmar_empenhos(self) -> None:
        """A janela "Pesquisa de empenhos", se abrir, é confirmada sem escolher nada (D7): vale o
        empenho que vem selecionado. Ela abre quando o pedido tem mais de um empenho (00514/26,
        12/11/2026) e demora um instante depois do Confirmar dos itens, então o robô a espera;
        com um empenho só ela não abre, e o robô segue."""
        janela = (
            self.frame.locator(".x-window")
            .filter(has_text=re.compile(r"Pesquisa de empenhos", re.I))
            .filter(visible=True)
        )
        try:
            janela.first.wait_for(state="visible", timeout=ESPERA_EMPENHOS_MS)
        except Exception:
            return  # não abriu: o empenho já veio preenchido
        log("  janela de empenhos: confirmando o que veio selecionado")
        _clicar(
            janela.first.get_by_role("button", name=re.compile(r"^\s*Confirmar\s*$", re.I))
            .filter(visible=True)
            .first
        )
        janela.first.wait_for(state="hidden", timeout=ESPERA_ESCOLHA_MS)
        aguardar_mascara(self.frame)

    def _digitar(
        self, rotulo: str, valor: str, *, comeca: bool = False, sem_zeros: bool = False
    ) -> None:
        """Escreve no campo que tem este rótulo, sai dele (a máscara de data aceita os dígitos) e
        lê de volta: o que ficou na tela tem de ser o digitado (`comeca`: só o começo, para a data
        que o SCPI completa com a hora; `sem_zeros`: ignora os zeros à esquerda, que a máscara da
        NF acrescenta)."""
        entrada = campo(self.frame, rotulo)
        entrada.click()
        _respirar(self.frame)
        self.page.keyboard.press("ControlOrMeta+A")
        self.page.keyboard.type(valor, delay=60)
        self.page.keyboard.press("Tab")
        _respirar(self.frame)
        lido = entrada.input_value().strip()
        if sem_zeros:
            lido, esperado = lido.lstrip("0"), valor.lstrip("0")
        else:
            esperado = valor
        if not (lido.startswith(esperado) if comeca else lido == esperado):
            raise ErroSCPI(f"o campo {rotulo} ficou com '{lido}', e o robô digitou '{valor}'")

    def _abrir_itens_da_entrada(self):
        """A aba "Itens da Entrada" e a grade dela, com os índices das colunas pelos cabeçalhos."""
        self.frame.locator(".x-tab").filter(
            has_text=re.compile(r"^\s*Itens da Entrada\s*$")
        ).first.click()
        _respirar(self.frame)
        grade = self._grade("Item", "QTD", "Observação")
        cabecalhos = [
            t.strip() for t in grade.locator(".x-column-header").all_inner_texts() if t.strip()
        ]
        return grade, {
            nome: _indice(cabecalhos, nome, True)
            for nome in ("Item", "Código", "QTD", "Observação")
        }

    def _editar_celula(self, celula, texto: str) -> None:
        """Abre o editor da célula, digita tecla a tecla e confirma com Enter, dando respiro ao
        SCPI antes e depois (a grade recarrega do servidor a cada edição)."""
        _respirar(self.frame)
        celula.dblclick()
        _respirar(self.frame)
        self.page.keyboard.press("ControlOrMeta+A")
        self.page.keyboard.type(texto, delay=60)
        self.page.keyboard.press("Enter")
        _respirar(self.frame)

    def _preencher_itens(self, rec: RecebimentoParaLancar) -> None:
        """A QTD (o padrão é o saldo inteiro) e a Observação de cada item da grade. A grade
        renumera os itens escolhidos de 1 a n, na ordem do pedido (`_na_grade`); antes de digitar,
        o código da linha tem de ser o do item."""
        grade, onde = self._abrir_itens_da_entrada()
        por_posicao = _na_grade(rec)
        for linha in grade.locator(".x-grid-row").filter(visible=True).all():
            celulas = linha.locator(".x-grid-cell")
            posicao = int(re.sub(r"\D", "", celulas.nth(onde["Item"]).inner_text()))
            item = por_posicao.get(posicao)
            if item is None:
                raise ErroSCPI(
                    f"a grade tem a linha {posicao} e o recebimento, {len(por_posicao)} itens"
                )
            codigo = celulas.nth(onde["Código"]).inner_text().strip()
            if norm_codigo(codigo) != norm_codigo(item.codigo):
                raise ErroSCPI(
                    f"linha {posicao} da grade: código {codigo}, e o item {item.item} do pedido "
                    f"é {item.codigo}"
                )
            self._editar_celula(celulas.nth(onde["QTD"]), _qtd_br(item.quantidade))
            self._editar_celula(celulas.nth(onde["Observação"]), rec.observacoes)
            _respirar(self.frame)

    def _conferir_itens(self, rec: RecebimentoParaLancar) -> None:
        """A conferência final de "Itens da Entrada", antes do Salvar: só os itens do recebimento,
        com o código, a QTD e a Observação digitados. Qualquer diferença é `ErroSCPI`."""
        grade, onde = self._abrir_itens_da_entrada()
        lidas = {}
        for linha in grade.locator(".x-grid-row").filter(visible=True).all():
            celulas = [c.strip() for c in linha.locator(".x-grid-cell").all_inner_texts()]
            lidas[int(re.sub(r"\D", "", celulas[onde["Item"]]))] = celulas
        esperado = _na_grade(rec)
        if set(lidas) != set(esperado):
            raise ErroSCPI(
                f"a grade da entrada tem as linhas {sorted(lidas)} e o recebimento, "
                f"{len(esperado)} itens ({sorted(i.item for i in rec.itens)} do pedido)"
            )
        for posicao, item in esperado.items():
            celulas = lidas[posicao]
            numero = item.item
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
        """Depois de um recebimento não salvo, o próximo comeca num módulo reaberto, como depois
        de um lançamento (o mesmo cuidado do lançamento das saídas)."""
        self.limpar()
        try:
            self.reabrir_modulo()
        except Exception as exc:
            log(f"  reabertura do módulo falhou ({resumo_erro(exc)}); tentando o próximo passo")
            self.reiniciar()

    def _guardar_print(self, nome: str) -> None:
        momento = timezone.localtime()
        caminho = Path(settings.LOG_DIR) / f"scpi-entradas-{nome}-{momento:%Y%m%d_%H%M%S}.png"
        try:
            self.page.screenshot(path=str(caminho))
            log(f"  print da tela: {caminho}")
        except Exception:
            log(f"  não foi possível salvar o print da tela em {caminho}")

    def encerrar_simulacao(self) -> None:
        log("  [DRY-RUN] entrada preenchida e conferida — NÃO clicado em Salvar")
        self._guardar_print("simulacao")
        self._recomecar()

    def descartar(self, rec: RecebimentoParaLancar) -> None:
        self._guardar_print(rec.rotulo)
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
