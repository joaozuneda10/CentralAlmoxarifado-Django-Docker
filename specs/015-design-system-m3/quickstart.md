# Quickstart: validar cada entrega da troca do design system

## Pré-requisitos

- MariaDB ou MySQL local e o `.env` de desenvolvimento (README).
- O servidor de desenvolvimento no ar (`uv run python manage.py runserver`). Confira antes se já há um
  na porta 8000.
- Um superusuário de teste e dados de exemplo: pedidos em cada situação, um de EPI aguardando
  autorização, um lote travado e um recibo pendente.
- Antes da entrega 2: anotar no PR quantos pedidos o painel atual mostra sem rolar a 1366×768
  (base da SC-004).
- Antes da entrega 3: medir com 3 funcionários o tempo e os toques de um pedido de 3 materiais no
  celular (base da SC-005).

## Portões de todo PR

```bash
uv run pytest
```

```bash
uv run ruff check . && uv run ruff format --check .
```

```bash
uv run python manage.py makemigrations --check --dry-run
```

Esperado: tudo limpo e nenhuma migration nova. Só podem mudar as asserções de nome de classe
renomeada (com o motivo no PR), as de valor de token (`test_fundacao.py`) e as do lugar do exemplo nos
campos públicos (entrega 3).

## Capturas (toda entrega)

```bash
uv run python scripts/capturar_telas.py --base http://127.0.0.1:8000
```

Esperado: uma imagem por tela-chave e largura (`contracts/componentes.md`), numa pasta ignorada pelo
Git, e nenhuma tela com rolagem lateral (o script avisa). As capturas vão para a revisão visual do
chefe (SC-008), lado a lado com os protótipos de `prototipos/`.

## Entrega 1: fundação

| # | Conferência | Esperado |
|---|---|---|
| Q-1.1 | `uv run pytest tests/test_contraste_tokens.py` | todos os pares de `contracts/tokens.md` acima do mínimo |
| Q-1.2 | abrir o painel, o detalhe, um formulário público e Automações | visual novo; nenhum botão, campo ou selo quebrado; o mesmo comportamento |
| Q-1.3 | selos de situação e do SCPI | ícone + palavra em todos |
| Q-1.4 | imprimir um recibo para PDF e comparar com o de antes | idêntico (SC-007) |
| Q-1.5 | `grep -rn "clean" interface/ docs/DESIGN.md CLAUDE.md .specify/memory/constitution.md` | nenhuma referência ao Clean como estilo vigente; constituição em 2.2.0 |
| Q-1.6 | a skill `design-tonal` carregada numa sessão nova | descreve os tokens e o vocabulário do `DESIGN.md` |

## Entrega 2: casca e painel

| # | Conferência | Esperado |
|---|---|---|
| Q-2.1 | menu acima de 1286px | estreito, com ícone e rótulo; contador no Painel e em Automações (só para quem os abre); até 1286px, o cabeçalho com o botão de menu de hoje, com todos os destinos |
| Q-2.2 | os quatro cartões com os dados de exemplo | os números iguais aos de antes; "há N dias" correto; "+1 aguardando autorização"; "1 para conferir" com o link para as travas, fora do número principal |
| Q-2.3 | clicar em cada cartão e em cada chip | o mesmo resultado e o mesmo parâmetro na URL dos filtros de hoje; com o JavaScript desligado, também |
| Q-2.4 | o ⋮ num pedido aguardando, num atendido com lote pendente, num lançado e numa saída avulsa | os itens de `data-model.md`; Esc fecha; o Tab percorre os itens |
| Q-2.5 | o ⋮ com um usuário sem a permissão de atendimento | sem "Imprimir recibo" e sem "Editar atendimento" |
| Q-2.6 | "Imprimir recibo" pelo ⋮, no Chrome e no Edge | o detalhe abre, a impressão começa, a confirmação aparece depois, e recarregar não imprime de novo; se o navegador recusar a impressão automática, o detalhe abre com o botão de imprimir |
| Q-2.7 | contar as linhas visíveis a 1366×768 | igual ou maior que a base (SC-004) |
| Q-2.8 | o botão flutuante no celular | não cobre o último pedido nem a paginação; some na impressão |

## Entrega 3: formulários públicos

| # | Conferência | Esperado |
|---|---|---|
| Q-3.1 | campos vazios, com foco, preenchidos e com erro | o rótulo dentro, na borda e na borda vermelha; o exemplo embaixo do campo; o erro no lugar do exemplo |
| Q-3.2 | o nome e o destino lembrados no aparelho | campos preenchidos, com o rótulo na borda |
| Q-3.3 | a lista de destinos no campo do destino | abre, filtra e escolhe sem cobrir o rótulo |
| Q-3.4 | um pedido de 3 materiais no celular | os mesmos toques ou menos e um tempo igual ou menor (SC-005); o pedido gravado igual |
| Q-3.5 | a folha das viaturas, a consulta, o login de solicitante e Meus pedidos | o mesmo desenho; o mesmo comportamento |

## Entrega 4: demais telas internas

| # | Conferência | Esperado |
|---|---|---|
| Q-4.1 | atendimento completo: confirmar, alterar, trocar, acrescentar e "Entregar tudo" | as mesmas interações e o mesmo resultado gravado |
| Q-4.2 | edição com o robô rodando | a faixa recarrega e o "Salvar" some se o lote travar, como hoje |
| Q-4.3 | Automações: abas, regiões que recarregam, histórico com filtros | o mesmo comportamento; a pasta da aba ativa |
| Q-4.4 | a Segurança do Trabalho: fila e decisão | o menu só com Autorizações; as telas no desenho novo |
