"""Leitura tipada de variáveis de ambiente (vindas do .env ou do sistema)."""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv.main import DotEnv

VERDADEIROS = frozenset({"1", "true", "sim", "yes", "on"})
FALSOS = frozenset({"0", "false", "nao", "não", "no", "off"})
# Os valores com que o python-dotenv entende PYTHON_DOTENV_DISABLED.
DOTENV_DESLIGADO = frozenset({"1", "true", "t", "yes", "y"})


def ler_bool(nome: str, padrao: bool) -> bool:
    """Valor booleano de `nome`; ausente ou vazio devolve `padrao`."""
    valor = (os.environ.get(nome) or "").strip()
    if not valor:
        return padrao
    normalizado = valor.casefold()
    if normalizado in VERDADEIROS:
        return True
    if normalizado in FALSOS:
        return False
    raise ImproperlyConfigured(f"{nome}: valor inválido {valor!r}; use 1 ou 0.")


def ler_int(nome: str, padrao: int) -> int:
    """Inteiro positivo de `nome`; ausente ou vazio devolve `padrao`."""
    valor = (os.environ.get(nome) or "").strip()
    if not valor:
        return padrao
    try:
        numero = int(valor)
    except ValueError:
        numero = 0
    if numero < 1:
        raise ImproperlyConfigured(f"{nome}: valor inválido {valor!r}; use um número inteiro ≥ 1.")
    return numero


def ler_lista(nome: str) -> list[str]:
    """Lista separada por vírgulas de `nome`, sem itens vazios."""
    return [item.strip() for item in (os.environ.get(nome) or "").split(",") if item.strip()]


def carregar_dotenv(caminho: Path) -> None:
    """Põe no ambiente o que o .env define. Variável já preenchida no ambiente vence o .env;
    ausente ou vazia, não: um valor vazio herdado (de um servidor iniciado antes de o .env ser
    preenchido, por exemplo) não pode esconder o valor que o .env já tem.

    Segue o `load_dotenv(override=False)`: `PYTHON_DOTENV_DISABLED` desliga a leitura e, ao
    expandir `${OUTRA}`, o valor do ambiente vence o do arquivo."""
    if (os.environ.get("PYTHON_DOTENV_DISABLED") or "").strip().casefold() in DOTENV_DESLIGADO:
        return
    for nome, valor in DotEnv(caminho, override=False).dict().items():
        if valor and not os.environ.get(nome):
            os.environ[nome] = valor
