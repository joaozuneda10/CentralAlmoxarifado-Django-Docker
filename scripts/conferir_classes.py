"""Classes dos templates sem regra de CSS (spec 015, T076).

Fora da suíte. Lê as classes escritas nos atributos `class` dos templates (as tags `{{ }}` e `{% %}`
saem, o texto fixo de dentro dos `{% if %}` fica), as classes que aparecem nos seletores
de todo CSS das apps e as listadas como gancho na seção "Ganchos sem CSS" do `docs/DESIGN.md`, e
mostra as classes de template que não estão em nenhum dos dois.

    uv run python scripts/conferir_classes.py

Sai com 1 se sobrar alguma, para o resultado ser fácil de usar num laço de conferência.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTAS_IGNORADAS = {".venv", "staticfiles", "node_modules", "capturas", "docs", "specs", ".git"}

ATRIBUTO_CLASSE = re.compile(r'class="([^"]*)"')
TAG_DJANGO = re.compile(r"\{\{.*?\}\}|\{#.*?#\}")
BLOCO_DJANGO = re.compile(r"\{%.*?%\}")
ALTERNATIVA = re.compile(r"\{%-?\s*(?:else|elif\s.*?)\s*-?%\}")
CLASSE_CSS = re.compile(r"\.(-?[_a-zA-Z][\w-]*)")
NOME_VALIDO = re.compile(r"^-?[_a-zA-Z][\w-]*$")


def arquivos(sufixo: str) -> list[Path]:
    return [
        p
        for p in RAIZ.rglob(f"*{sufixo}")
        if not PASTAS_IGNORADAS.intersection(p.relative_to(RAIZ).parts)
    ]


def classes_dos_templates() -> dict[str, set[str]]:
    encontradas: dict[str, set[str]] = {}
    for caminho in arquivos(".html"):
        # As tags do Django saem do texto inteiro antes de achar os atributos (um
        # `{% if x == "A" %}` dentro do `class` teria aspas): o texto fixo de dentro dos `{% if %}`
        # fica, colado ao vizinho como no HTML gerado ("selo-{% if %}info{% endif %}" vira
        # "selo-info"). O `{% else %}` e o `{% elif %}` separam alternativas: viram espaço.
        texto = ALTERNATIVA.sub(" ", caminho.read_text(encoding="utf-8"))
        texto = BLOCO_DJANGO.sub("", TAG_DJANGO.sub("", texto))
        for valor in ATRIBUTO_CLASSE.findall(texto):
            for nome in valor.split():
                # O nome que termina em "-" é um prefixo completado por variável
                # (`selo-{{ nivel }}`).
                if NOME_VALIDO.match(nome) and not nome.endswith("-"):
                    encontradas.setdefault(nome, set()).add(str(caminho.relative_to(RAIZ)))
    return encontradas


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
    templates = classes_dos_templates()
    com_regra = classes_do_css() | ganchos_documentados()
    sobra = sorted(nome for nome in templates if nome not in com_regra)
    for nome in sobra:
        print(f"{nome}: {', '.join(sorted(templates[nome]))}")
    print(f"\n{len(sobra)} classe(s) sem regra de CSS nem registro de gancho.")
    return 1 if sobra else 0


if __name__ == "__main__":
    sys.exit(main())
