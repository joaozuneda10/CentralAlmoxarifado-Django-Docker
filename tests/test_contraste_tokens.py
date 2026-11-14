"""Contraste dos tokens (spec 015, research R15, contracts/tokens.md).

Lê o `:root` de `fundacao.css`, resolve os `var(--…)` e confere, com a fórmula da WCAG 2.1, as
combinações permitidas que o `docs/DESIGN.md` declara. As proibidas são conferidas também, para a
lista não ficar desatualizada: se uma delas passar a ter contraste, o documento precisa mudar.
Roda sem banco.
"""

import re
from pathlib import Path

import pytest
from django.contrib.staticfiles import finders

TEXTO = 4.5
CONTROLE = 3.0

PERMITIDAS = [
    ("texto", "fundo", TEXTO),
    ("texto", "superficie-alta", TEXTO),
    ("texto-secundario", "fundo", TEXTO),
    ("texto-secundario", "superficie-alta", TEXTO),
    ("texto-suave", "fundo", TEXTO),
    ("texto-suave", "superficie-media", TEXTO),
    ("destaque", "fundo", TEXTO),
    ("destaque-texto", "destaque", TEXTO),
    ("destaque-superficie-texto", "destaque-superficie", TEXTO),
    ("secundario-superficie-texto", "secundario-superficie", TEXTO),
    ("ok-texto", "ok-superficie", TEXTO),
    ("aviso-texto", "aviso-superficie", TEXTO),
    ("erro-texto", "erro-superficie", TEXTO),
    ("erro-forte", "fundo", TEXTO),
    ("neutro-texto", "neutro-superficie", TEXTO),
    ("contorno", "fundo", CONTROLE),
    ("contorno", "superficie", CONTROLE),
]

PROIBIDAS = [
    ("destaque", "destaque-superficie"),
    ("destaque", "secundario-superficie"),
    ("texto-suave", "secundario-superficie"),
    ("texto-suave", "superficie-maxima"),
]


def tokens() -> dict[str, str]:
    texto = Path(finders.find("interface/css/fundacao.css")).read_text(encoding="utf-8")
    raiz = re.search(r":root\s*\{(.*?)\n\}", texto, re.S).group(1)
    raiz = re.sub(r"/\*.*?\*/", "", raiz, flags=re.S)
    return dict(re.findall(r"--([\w-]+)\s*:\s*([^;]+);", raiz))


def cor(nome: str, valores: dict[str, str]) -> str:
    valor = valores[nome].strip()
    referencia = re.fullmatch(r"var\(--([\w-]+)\)", valor)
    if referencia:
        return cor(referencia.group(1), valores)
    assert re.fullmatch(r"#[0-9a-fA-F]{6}", valor), f"--{nome} não é uma cor hexadecimal: {valor}"
    return valor


def luminancia(hexa: str) -> float:
    canais = []
    for i in (1, 3, 5):
        c = int(hexa[i : i + 2], 16) / 255
        canais.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = canais
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a: str, b: str) -> float:
    claro, escuro = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (claro + 0.05) / (escuro + 0.05)


@pytest.mark.parametrize(("frente", "fundo", "minimo"), PERMITIDAS)
def test_combinacao_permitida_tem_contraste(frente, fundo, minimo):
    valores = tokens()
    assert frente in valores, f"o token --{frente} sumiu do :root"
    assert fundo in valores, f"o token --{fundo} sumiu do :root"
    razao = contraste(cor(frente, valores), cor(fundo, valores))
    assert razao >= minimo, f"--{frente} sobre --{fundo}: {razao:.2f}:1 (mínimo {minimo}:1)"


@pytest.mark.parametrize(("frente", "fundo"), PROIBIDAS)
def test_combinacao_proibida_continua_reprovada(frente, fundo):
    valores = tokens()
    razao = contraste(cor(frente, valores), cor(fundo, valores))
    assert razao < TEXTO, (
        f"--{frente} sobre --{fundo} passou a ter {razao:.2f}:1: tire-a da lista de proibidas "
        "do docs/DESIGN.md e deste teste"
    )


def test_formula_da_wcag():
    assert contraste("#000000", "#ffffff") == pytest.approx(21)
    assert contraste("#2563eb", "#ffffff") == pytest.approx(5.17, abs=0.01)
