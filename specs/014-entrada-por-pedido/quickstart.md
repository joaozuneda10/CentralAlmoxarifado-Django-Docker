# Quickstart: validar a entrada por pedido

Este roteiro valida cada PR da [pilha](plan.md#entrega-em-prs-empilhados). Os passos 1, 3, 5, 6 e 7 são
automáticos. Os passos 2, 4 e 8 são manuais e só o usuário os roda, porque abrem o SCPI real.

**No SCPI de produção, só consulta e simulação**: nunca Salvar, Novo, Gravar, Excluir, Alterar ou
Anular à mão durante a validação, e nunca o 01.08.03. O lançamento real só no passo 8, a pedido do
usuário, com um recebimento de verdade.

## Pré-requisitos

- MySQL 8 ou MariaDB local, `.env` de desenvolvimento e `uv sync`.
- `LANCAMENTO_REAL` desligado no `.env` local, que é o padrão.
- Para os passos manuais:
  - o Playwright instalado (`uv run playwright install chromium`);
  - acesso ao SCPI entre 7h e 17h;
  - os CSVs reais fora do repositório (têm nomes de pessoas).

## 1. Portões de cada PR

```bash
uv run pytest
```

```bash
uv run ruff check . && uv run ruff format --check .
```

```bash
uv run python manage.py makemigrations --check --dry-run
```

Esperado: tudo limpo.

Os testes das saídas passam sem mudar de expectativa (FR-031, SC-007):
- `tests/test_lancamento*.py`;
- `tests/test_lancar_saidas.py`;
- `tests/test_conciliacao_*.py`;
- `tests/test_papeis_acesso.py`, que ganha as rotas novas.

## 2. Pedidos de compra do SCPI real (PR 1, manual)

```bash
uv run python manage.py importar_pedidos_compra
```

Esperado:
- uma `Importacao` "Pedidos de compra" concluída em menos de 1 minuto;
- um número de itens perto dos 2.878 de 10/11/2026, menos os que zeraram desde então;
- os itens `T`, de serviço e de combustível fora dos disponíveis (US5, cenários 1 e 2).

Depois, no SCPI, abra o Log de um pedido trazido pela importação (botão Log na tela do Pedido de
Compra). Esperado: **nenhuma alteração** no horário da importação (FR-002).

Repetindo a importação, nada muda além do `atualizado_por`: nenhum pedido novo, nenhum ausente e
nenhuma trava.

## 3. Recebimento (PR 2, automático)

Os testes de `tests/test_compras_recebimento.py` cobrem os cenários 1 a 8 da US1, com o exemplo 100 →
30 → 20:
- o "total" sugere 50;
- 51 é recusado com o saldo livre na mensagem;
- o parcial reserva só os itens marcados;
- a NF com e sem os zeros à esquerda é recusada, mesmo com o primeiro recebimento cancelado depois de
  uma tentativa;
- as datas;
- `1.5` e 4 casas;
- as duas pessoas ao mesmo tempo, em duas conexões: uma grava e a outra recebe o saldo atualizado;
- a edição e o cancelamento antes da tentativa, com a NF liberada.

Depois os de `tests/test_compras_acesso.py`:
- sem `receber_compras`, 403;
- o Atendimento e a Gestão abrem;
- o solicitante e a Segurança do Trabalho não abrem.

Na interface local (servidor na porta 8000), prepare um recebimento total e um parcial. Confira:
- a 375 px de largura;
- a navegação só pelo teclado;
- o estado sem depender de cor.

## 4. Registro oficial e navegação do robô no SCPI real (PRs 3 e 4, manual)

```bash
uv run python manage.py conciliar_entradas --desde 01/11/2026 --ate 12/11/2026 --sem-limpeza
```

Esperado: uma `Importacao` "Entradas do SCPI" concluída, com as requisições de entrada do período. Os
números de pedido, as NFs e os fornecedores devem bater com o CSV que o usuário extrai à mão.

Depois, prepare no Central local um recebimento parcial de um item de um pedido real com saldo, com uma
NF fictícia que não existe no SCPI (por exemplo `999999`). Rode:

```bash
uv run python manage.py lancar_entradas --dry-run --recebimento RC-0001
```

Esperado no navegador (o usuário acompanha):
- o pedido é aberto pela pesquisa (número + ano);
- "Escolha os Itens" fica só com o item do recebimento;
- a janela de empenhos é confirmada;
- a grade fica com a quantidade do recebimento, e a data, a NF e as Observações com `Central
  Almoxarifado RC-0001` ficam preenchidas;
- **Cancelar**: nada é salvo;
- o recebimento continua preparado, sem tentativa.

Repita com:
- um pedido de exercício anterior (`/25`), para confirmar o ano da pesquisa (R25);
- um pedido com código repetido, se houver um com saldo, para confirmar a ordem da grade.

Anote como o SCPI mostrou a NF digitada sem os zeros e a hora da entrada.

## 5. Robô e verificação com o SCPI simulado (PRs 4 e 5, automático)

`tests/test_lancamento_entradas.py` cobre todas as linhas da tabela "Garantias" de
[contracts/robo-entradas.md](contracts/robo-entradas.md).

`tests/test_compras_verificar.py` cobre a US3:
- "salvou e perdeu a resposta": a extração posterior traz a marca, ela vira candidata "é esta", e a
  liberação é recusada; o "É esta" liga o recebimento como lançado;
- "falhou sem salvar": com a extração posterior sem candidata e a importação posterior com o "Já
  Entrou" igual ao da tela, a liberação é permitida e o **mesmo** recebimento volta à fila;
- sem extração posterior, recusa;
- a candidata que some na extração seguinte continua bloqueando;
- a lacuna na numeração não libera;
- o "Já Entrou" diferente da tela (a entrada existe com outra data) não libera.

## 6. Vereditos, entrada fora do Central e "Já Entrou" (PR 6, automático)

`tests/test_compras_vereditos.py` cobre a US4:
- Comprovado;
- Divergente, que mostra só a diferença;
- Conflito;
- Duplicado pela NF sem a marca;
- Aguardando e Não encontrado;
- a revisão depois de uma edição à mão no SCPI, sem mudar o recebimento.

`tests/test_compras_fora_do_central.py` cobre a US5, cenários 3 a 6:
- o recebimento aberto ligado à mão pela NF sai da fila;
- a NF desconhecida vira "Lançada fora do Central", reserva o saldo e trava o pedido;
- a requisição abaixo do marco é ignorada;
- o "Já Entrou" não explicado trava;
- o destravamento é recusado sem uma importação posterior e permitido depois dela, com o saldo
  recalculado.

## 7. Diária e retenção (PR 7, automático)

`tests/test_compras_diaria.py`:
- o `atualizar_catalogo` roda Entradas e depois Pedidos de compra;
- um passo que falha não desfaz os outros;
- a limpeza esvazia o bruto e as requisições sem ligação com mais de 60 dias.

## 7b. Confirmações do `--dry-run` real para a reconferência (manual, a pedido do usuário)

No `--dry-run` do PR 4, anotar: (1) depois do preenchimento, a grade ainda mostra os itens
desmarcados e o "Já Entrou" deles? (2) o 07.04.01 aceita o filtro só por NF? (3) quanto leva o
relatório. As respostas decidem o desenho da reconferência descrito no contrato do robô.

## 8. Primeiro lançamento real (só depois do PR 5 em produção, manual, a pedido do usuário)

**Pré-requisito**: os PRs 3, 4 e 5 em produção. Antes do PR 5 não há resolução segura de um
recebimento em verificação, então o lançamento real não é liberado. As validações dos PRs 6 e 7 (o
veredito Comprovado e a rotina das 07:15) só valem depois deles; até lá, o veredito fica sem ser
conferido.

Com um recebimento real conferido (NF e material na mão), na aba Automações › Entradas no SCPI:
1. "Simular" o recebimento e acompanhar o cartão até `simulada`.
2. "Lançar no SCPI" o mesmo recebimento.

Esperado:
- o recebimento fica lançado com o número;
- no SCPI, a requisição tem a marca nas Observações, a data do recebimento e a NF;
- a extração de depois a registra (PR 4); o veredito Comprovado ou Aguardando só aparece a partir do
  PR 6.

Anote também:
- qualquer janela depois do Salvar (L3);
- o tempo até a requisição aparecer no relatório (L8).

**Só depois do PR 7**: no dia seguinte, depois da rotina das 07:15, o pedido não está travado e o saldo
livre do item é o saldo do SCPI menos os outros recebimentos abertos (SC-003).
