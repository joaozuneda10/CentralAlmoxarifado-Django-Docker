# Quickstart: validar as contas de solicitante (spec 013)

Validação de ponta a ponta numa cópia local (Mac ou o ambiente de desenvolvimento), nunca na produção.
Detalhes do comportamento estão nos contratos (`contracts/`); este roteiro só diz como conferir.

## Pré-requisitos

- `develop` com a spec 012 e esta branch; `uv sync` (instala o `django-axes`).
- `uv run python manage.py migrate` (cria o grupo `Solicitante`, as colunas novas e as tabelas do axes).
- Servidor na porta 8000 (reaproveite o que estiver no ar).

## Automático

```bash
uv run pytest tests/test_solicitante_*.py
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run python manage.py makemigrations --check --dry-run
DEBUG=0 uv run python manage.py check --deploy --fail-level WARNING
```

## À mão, no navegador

1. **Conta nova** (US5): no admin, crie a matrícula `90001` com nome completo, uma senha e o grupo
   `Solicitante`. Tente também marcar `Atendimento` junto: o admin recusa.
2. **Primeiro acesso**: em `/painel/entrar/`, entre com `90001`. Você é levado à troca de senha; abrir
   `/meus-pedidos/` volta para ela. Troque e confira que cai em "Meus pedidos", vazio.
3. **Pedido com conta** (US3): abra `/pedido/limpeza/`. O nome vem preenchido e travado. Envie um
   pedido; a tela de sucesso leva a "Meus pedidos". Abra o formulário de novo: o destino vem sugerido.
4. **Privacidade** (US2): em outra janela anônima, procure o número na consulta pública com o primeiro
   nome certo: "Não encontramos...". Com outra conta de solicitante, abra `/meus-pedidos/<número>/`: a
   mesma página de não encontrado.
5. **Atendimento** (US1): pela equipe, atenda o pedido entregando menos de um material e trocando
   outro. Como solicitante, abra o pedido: selo "Atendido parcialmente", pedida e entregue, "trocado
   por ...", e nada do recebedor, centro, placa, tipo ou requisição.
6. **Sessão que termina** (US4): abra o formulário logado, ponha materiais, saia em outra aba e envie:
   a mensagem da sessão aparece e os materiais continuam. Toque em "Entrar" (abre outra aba), entre,
   volte à aba do formulário e envie: o pedido sai com a conta.
7. **Bloqueio** (US6): erre a senha de `90001` 5 vezes: a página de bloqueio aparece. Outra matrícula
   entra normalmente. Apague a tentativa no admin (Axes) e entre de novo.
8. **Sem conta** (FR-025): numa janela anônima, faça um pedido e consulte-o pela consulta pública: tudo
   como antes.

## Antes do deploy (não é código)

- Conferir no servidor real que endereço chega como `REMOTE_ADDR` (F8): se for o mesmo para todos,
  o bloqueio vale por matrícula, o que ainda atende ao SC-005; registre o resultado no PR.
- O deploy precisa do `migrate` (spec 012 já implantada antes).
