"""Classes dos templates sem regra de CSS (spec 015, T076).

Fora da suíte. Lê as classes escritas nos atributos `class` dos templates (cada ramo dos `{% if %}`
conta, colado ao texto vizinho; o nome completado por `{{ }}` fica de fora), as classes que
aparecem nos seletores de todo CSS das apps e as listadas como gancho na seção "Ganchos sem CSS"
do `docs/DESIGN.md`, e mostra as classes de template que não estão em nenhum dos dois.

    uv run python scripts/conferir_classes.py

Sai com 1 se sobrar alguma ou se algum atributo tiver combinações demais para conferir inteiro.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTAS_IGNORADAS = {".venv", "staticfiles", "node_modules", "capturas", "docs", "specs", ".git"}

# O valor do `class`, entre aspas duplas ou simples; as tags do Django de dentro (que podem ter
# aspas, `{% if x == "A" %}`) entram inteiras.
_TAG = r"\{%.*?%\}|\{\{.*?\}\}|\{#.*?#\}"
ATRIBUTO_CLASSE = re.compile(
    rf"""(?<![\w-])class=(?:"((?:{_TAG}|[^"])*)"|'((?:{_TAG}|[^'])*)')""", re.S
)
BLOCO_DJANGO = re.compile(r"(\{%.*?%\})", re.S)
VARIAVEL = re.compile(r"\{\{.*?\}\}|\{#.*?#\}", re.S)
CLASSE_CSS = re.compile(r"\.(-?[_a-zA-Z][\w-]*)")
NOME_VALIDO = re.compile(r"^-?[_a-zA-Z][\w-]*$")
LIMITE_VARIANTES = 256


def _palavra(bloco: str) -> str:
    return bloco[2:-2].strip(" -").split(" ", 1)[0]


def _arvore(partes: list[str], i: int = 0, fim: tuple[str, ...] = ()) -> tuple[list, int, str]:
    """Os pedaços de texto e os `{% if %}` (com os ramos) até uma das tags de `fim`."""
    nos: list = []
    while i < len(partes):
        parte = partes[i]
        i += 1
        if not BLOCO_DJANGO.fullmatch(parte):
            nos.append(parte)
            continue
        palavra = _palavra(parte)
        if palavra in fim:
            return nos, i, palavra
        if palavra == "if":
            ramos, tem_else = [], False
            while True:
                ramo, i, parou = _arvore(partes, i, ("elif", "else", "endif"))
                ramos.append(ramo)
                tem_else = tem_else or parou == "else"
                if parou in ("endif", ""):
                    break
            if not tem_else:
                ramos.append([])  # nenhum ramo vale
            nos.append(ramos)
        # As outras tags (`{% url %}`, `{% for %}`…) não escrevem classe: somem.
    return nos, i, ""


class VariantesDemais(Exception):
    """O atributo tem mais combinações de ramos do que `LIMITE_VARIANTES`."""


def _variantes(nos: list) -> list[str]:
    """Os textos possíveis do atributo, cada `{% if %}` num dos seus ramos."""
    textos = [""]
    for no in nos:
        opcoes = [no] if isinstance(no, str) else [v for ramo in no for v in _variantes(ramo)]
        if len(textos) * len(opcoes) > LIMITE_VARIANTES:
            raise VariantesDemais
        textos = [t + o for t in textos for o in opcoes]
    return textos


def arquivos(sufixo: str) -> list[Path]:
    return [
        p
        for p in RAIZ.rglob(f"*{sufixo}")
        if not PASTAS_IGNORADAS.intersection(p.relative_to(RAIZ).parts)
    ]


def classes_dos_templates() -> tuple[dict[str, set[str]], list[str]]:
    """As classes de cada template e os atributos que não deu para conferir inteiros."""
    encontradas: dict[str, set[str]] = {}
    incompletos: list[str] = []
    for caminho in arquivos(".html"):
        # Cada ramo dos `{% if %}` do atributo vira um texto, colado aos vizinhos como no HTML
        # gerado: "selo-{% if a %}info{% else %}erro{% endif %}" dá "selo-info" e "selo-erro".
        for duplas, simples in ATRIBUTO_CLASSE.findall(caminho.read_text(encoding="utf-8")):
            valor = duplas or simples
            try:
                textos = _variantes(_arvore(BLOCO_DJANGO.split(valor))[0])
            except VariantesDemais:
                incompletos.append(f'{caminho.relative_to(RAIZ)}: class="{valor[:60]}…"')
                continue
            for texto in textos:
                # A variável vira "\0": o nome que ela completa (`selo-{{ nivel }}`) não é
                # conferido.
                for nome in VARIAVEL.sub("\0", texto).split():
                    if NOME_VALIDO.match(nome):
                        encontradas.setdefault(nome, set()).add(str(caminho.relative_to(RAIZ)))
    return encontradas, incompletos


def classes_do_css() -> set[str]:
    nomes: set[str] = set()
    for caminho in arquivos(".css"):
        texto = re.sub(r"/\*.*?\*/", "", caminho.read_text(encoding="utf-8"), flags=re.S)
        # Só os seletores (o que vem antes de cada `{`), para não pegar números como `.5em`.
        for seletor in re.findall(r"([^{}]+)\{", texto):
            nomes.update(CLASSE_CSS.findall(seletor))
    return nomes


def ganchos_documentados() -> set[str]:
    texto = (RAIZ / "docs" / "DESIGN.md").read_text(encoding="utf-8")
    secao = re.search(r"## Ganchos sem CSS\n(.*?)(?:\n## |\Z)", texto, re.S)
    return set(re.findall(r"`([\w-]+)`", secao.group(1))) if secao else set()


def main() -> int:
    templates, incompletos = classes_dos_templates()
    com_regra = classes_do_css() | ganchos_documentados()
    sobra = sorted(nome for nome in templates if nome not in com_regra)
    for nome in sobra:
        print(f"{nome}: {', '.join(sorted(templates[nome]))}")
    print(f"\n{len(sobra)} classe(s) sem regra de CSS nem registro de gancho.")
    if incompletos:
        print(
            f"\nConferência incompleta: {len(incompletos)} atributo(s) com mais de "
            f"{LIMITE_VARIANTES} combinações de ramos ficaram de fora:"
        )
        for linha in incompletos:
            print(f"  {linha}")
    return 1 if sobra or incompletos else 0


if __name__ == "__main__":
    sys.exit(main())
