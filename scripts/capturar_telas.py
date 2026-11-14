"""Capturas das telas-chave para a revisão visual (spec 015, research R14).

Fora da suíte: a constituição proíbe teste com navegador. Abre o servidor de desenvolvimento que já
está no ar (nunca o SCPI), entra pelo formulário de /painel/entrar/ (o django-axes exige o
`request`) e salva uma imagem por tela e largura. Avisa toda tela com rolagem lateral (SC-002).

    uv run python scripts/capturar_telas.py --usuario <matrícula> --senha <senha> \
        --pedido P-000001 --recibo P-000001 --contar-linhas

A senha também pode vir da variável de ambiente CAPTURAS_SENHA. As imagens e os PDFs vão para
`capturas/` (ignorada pelo Git).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

LARGURAS_PADRAO = "320,375,768,1280,1440"
ALTURA = 900
PAINEL_JANELA = (1366, 650)
PAINEL_LINHAS = (1366, 768)


@dataclass(frozen=True)
class Tela:
    nome: str
    caminho: str
    logado: bool


PUBLICAS = [
    Tela("inicio", "/", False),
    Tela("limpeza", "/pedido/limpeza/", False),
    Tela("ab", "/pedido/ab/", False),
    Tela("viaturas", "/pedido/viaturas/", False),
    Tela("oficina", "/pedido/oficina/", False),
    Tela("epis", "/pedido/epis/", False),
    Tela("consulta", "/pedido/consulta/", False),
    Tela("entrar", "/painel/entrar/", False),
]

INTERNAS = [
    Tela("painel", "/painel/", True),
    Tela("painel-filtrado", "/painel/?situacao=aguardando", True),
    Tela("avulsa", "/painel/saida-avulsa/", True),
    Tela("compras", "/painel/compras/", True),
    Tela("curva", "/painel/catalogo/curva/", True),
    Tela("formularios", "/painel/catalogo/formularios/", True),
    Tela("formularios-materiais", "/painel/catalogo/formularios/?aba=materiais", True),
    Tela("autorizacoes", "/painel/autorizacoes/", True),
    Tela("trocar-senha", "/painel/senha/", True),
]


def argumentos() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--base", default="http://127.0.0.1:8000", help="URL do servidor já no ar")
    p.add_argument("--usuario", help="matrícula de teste (sem ela, só as telas públicas)")
    p.add_argument("--senha", default=os.environ.get("CAPTURAS_SENHA"))
    p.add_argument("--saida", type=Path, help="pasta (padrão capturas/<data-hora>/)")
    p.add_argument("--larguras", default=LARGURAS_PADRAO)
    p.add_argument("--telas", help="só as telas cujo nome contém um destes textos (vírgulas)")
    repete = {"action": "append", "default": []}
    p.add_argument("--pedido", **repete, help="número do detalhe a capturar (repete)")
    p.add_argument("--editar", **repete, help="número da edição a capturar (repete)")
    p.add_argument("--recibo", **repete, help="número do detalhe em PDF de impressão (repete)")
    p.add_argument("--contar-linhas", action="store_true", help="linhas do painel a 1366×768")
    p.add_argument("--comparar-com", type=Path, help="pasta com a impressão do recibo de antes")
    return p.parse_args()


def entrar(contexto: BrowserContext, base: str, usuario: str, senha: str) -> None:
    pagina = contexto.new_page()
    pagina.goto(f"{base}/painel/entrar/")
    pagina.fill("#id_username", usuario)
    pagina.fill("#id_password", senha)
    pagina.click("form button[type=submit]")
    pagina.wait_for_load_state("networkidle")
    if "/painel/entrar/" in pagina.url:
        pagina.close()
        sys.exit("Não entrou: confira a matrícula e a senha de teste.")
    pagina.close()


class PaginaComErro(Exception):
    """A página respondeu com erro (ex.: 404 de um pedido que não existe): nada é salvo."""


def abrir(pagina: Page, url: str) -> None:
    # O goto do Playwright não levanta exceção com 404 ou 500: sem esta conferência, a página de
    # erro seria salva como se fosse a tela.
    resposta = pagina.goto(url)
    if resposta is None or not resposta.ok:
        situacao = resposta.status if resposta else "sem resposta"
        raise PaginaComErro(f"{url} ({situacao})")


def capturar(pagina: Page, url: str, arquivo: Path, largura: int, altura: int = ALTURA) -> bool:
    """Salva a tela inteira e devolve se há rolagem lateral."""
    pagina.set_viewport_size({"width": largura, "height": altura})
    abrir(pagina, url)
    pagina.wait_for_load_state("networkidle")
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    pagina.screenshot(path=str(arquivo), full_page=True)
    return pagina.evaluate("document.documentElement.scrollWidth") > largura


def abas_de_automacoes(pagina: Page, base: str) -> list[Tela]:
    pagina.goto(f"{base}/painel/automacoes/")
    chaves = pagina.eval_on_selector_all("[data-aba]", "els => els.map(e => e.dataset.aba)")
    vistas = dict.fromkeys(c for c in chaves if c and "{" not in c)
    return [Tela(f"automacoes-{c}", f"/painel/automacoes/?aba={c}", True) for c in vistas]


def contar_linhas(pagina: Page, base: str) -> int:
    largura, altura = PAINEL_LINHAS
    pagina.set_viewport_size({"width": largura, "height": altura})
    pagina.goto(f"{base}/painel/")
    pagina.wait_for_load_state("networkidle")
    return pagina.evaluate(
        """() => [...document.querySelectorAll('#lista-pedidos tbody tr')].filter(tr => {
            const r = tr.getBoundingClientRect();
            return r.height > 0 && r.top >= 0 && r.bottom <= window.innerHeight;
        }).length"""
    )


def recibo_pdf(pagina: Page, base: str, numero: str, pasta: Path) -> Path:
    pagina.set_viewport_size({"width": 1280, "height": ALTURA})
    pagina.emulate_media(media="screen")
    abrir(pagina, f"{base}/painel/pedidos/{numero}/")
    pagina.wait_for_load_state("networkidle")
    pagina.emulate_media(media="print")
    destino = pasta / f"recibo-{numero}.pdf"
    destino.parent.mkdir(parents=True, exist_ok=True)
    pagina.pdf(path=str(destino), format="A4", print_background=True)
    # A mesma mídia de impressão em imagem, para comparar pixel a pixel com outra pasta (SC-007).
    pagina.set_viewport_size({"width": 794, "height": 1123})
    pagina.screenshot(path=str(pasta / f"recibo-{numero}-impressao.png"), full_page=True)
    pagina.emulate_media(media="screen")
    return destino


COMPARAR_JS = """async ([a, b]) => {
    const carregar = src => new Promise((ok, falha) => {
        const img = new Image(); img.onload = () => ok(img); img.onerror = falha; img.src = src;
    });
    const [x, y] = await Promise.all([carregar(a), carregar(b)]);
    if (x.width !== y.width || x.height !== y.height)
        return {iguais: false, motivo: `tamanhos ${x.width}x${x.height} e ${y.width}x${y.height}`};
    const pixels = img => {
        const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
        const ctx = c.getContext('2d'); ctx.drawImage(img, 0, 0);
        return ctx.getImageData(0, 0, img.width, img.height).data;
    };
    const [p, q] = [pixels(x), pixels(y)];
    let diferentes = 0;
    for (let i = 0; i < p.length; i += 4)
        if (p[i] !== q[i] || p[i + 1] !== q[i + 1] || p[i + 2] !== q[i + 2]) diferentes++;
    return {iguais: diferentes === 0, motivo: `${diferentes} pixels diferentes`};
}"""


def comparar_imagens(pagina: Page, a: Path, b: Path) -> tuple[bool, str]:
    """Compara duas PNG no próprio navegador (canvas), sem dependência nova."""
    import base64

    def dados(caminho: Path) -> str:
        return "data:image/png;base64," + base64.b64encode(caminho.read_bytes()).decode()

    pagina.goto("about:blank")
    r = pagina.evaluate(COMPARAR_JS, [dados(a), dados(b)])
    return r["iguais"], r["motivo"]


def selecionar(telas: list[Tela], filtro: str | None) -> list[Tela]:
    if not filtro:
        return telas
    partes = [p.strip() for p in filtro.split(",") if p.strip()]
    return [t for t in telas if any(p in t.nome for p in partes)]


def nome_arquivo(texto: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", texto).strip("-")


def rodar(navegador: Browser, args: argparse.Namespace) -> int:
    base = args.base.rstrip("/")
    pasta = args.saida or Path("capturas") / datetime.now().strftime("%Y%m%d-%H%M%S")
    larguras = [int(x) for x in args.larguras.split(",")]
    anonimo = navegador.new_context(device_scale_factor=1)
    logado = None
    telas = list(PUBLICAS)
    if args.usuario:
        if not args.senha:
            sys.exit("Falta a senha: --senha ou CAPTURAS_SENHA.")
        logado = navegador.new_context(device_scale_factor=1)
        entrar(logado, base, args.usuario, args.senha)
        telas += INTERNAS
        telas += [Tela(f"detalhe-{n}", f"/painel/pedidos/{n}/", True) for n in args.pedido]
        telas += [Tela(f"editar-{n}", f"/painel/pedidos/{n}/editar/", True) for n in args.editar]
        telas += abas_de_automacoes(logado.new_page(), base)
    telas = selecionar(telas, args.telas)

    rolagem: list[str] = []
    falhas: list[str] = []
    for tela in telas:
        contexto = logado if tela.logado else anonimo
        pagina = contexto.new_page()
        tamanhos = [(largura, ALTURA) for largura in larguras]
        if tela.nome == "painel":
            tamanhos.append(PAINEL_JANELA)
        situacao = "ok "
        for largura, altura in tamanhos:
            sufixo = f"{largura}" if altura == ALTURA else f"{largura}x{altura}"
            arquivo = pasta / f"{nome_arquivo(tela.nome)}-{sufixo}.png"
            try:
                if capturar(pagina, base + tela.caminho, arquivo, largura, altura):
                    rolagem.append(f"{tela.nome} a {largura}px")
            except PaginaComErro as erro:
                falhas.append(f"{tela.nome}: {erro}")
                situacao = "ERRO"
                break
        pagina.close()
        print(f"{situacao} {tela.nome}")

    recibo_diferente = False
    if logado:
        pagina = logado.new_page()
        for numero in args.recibo:
            try:
                print(f"pdf {recibo_pdf(pagina, base, numero, pasta)}")
            except PaginaComErro as erro:
                falhas.append(f"recibo {numero}: {erro}")
                continue
            if args.comparar_com:
                nome = f"recibo-{numero}-impressao.png"
                antes = args.comparar_com / nome
                if not antes.exists():
                    falhas.append(f"recibo {numero}: sem {antes} para comparar")
                    continue
                iguais, motivo = comparar_imagens(pagina, antes, pasta / nome)
                veredito = "IGUAL" if iguais else "DIFERENTE"
                print(f"     impressão {veredito} à de {antes} ({motivo})")
                recibo_diferente |= not iguais
        if args.contar_linhas:
            print(f"linhas visíveis do painel a 1366×768: {contar_linhas(pagina, base)}")
        pagina.close()

    print(f"capturas em {pasta}")
    if rolagem:
        print("ROLAGEM LATERAL (SC-002):")
        for item in rolagem:
            print(f"  - {item}")
    if falhas:
        print("FALHAS (nada salvo nessas telas ou comparação não feita):")
        for item in falhas:
            print(f"  - {item}")
    return 1 if rolagem or recibo_diferente or falhas else 0


def main() -> int:
    args = argumentos()
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            return rodar(navegador, args)
        finally:
            navegador.close()


if __name__ == "__main__":
    sys.exit(main())
