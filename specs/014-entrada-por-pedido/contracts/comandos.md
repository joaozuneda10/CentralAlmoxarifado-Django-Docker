# Contrato: comandos

Todos abrem o SCPI pelo Playwright, salvo com `--arquivo`. Os testes nunca abrem o navegador. No
servidor, os comandos rodam no container, com o projeto e os arquivos do ambiente explícitos. Em
produção, só a pedido do usuário.

## `importar_pedidos_compra` (PR 1)

```text
importar_pedidos_compra [--arquivo <csv>] [--apagar-arquivo] [--forcar]
```

- Baixa o 07.13 ([relatorios-scpi.md](relatorios-scpi.md)) ou lê o CSV enviado e grava numa
  transação, como uma `Importacao` do tipo `PEDIDOS_COMPRA`, com a trava do tipo.
- O exercício é o ano corrente.
- Cria os pedidos e itens novos e atualiza os presentes, guardando o `ja_entrou_anterior`. Marca
  `ausente_desde` nos que sumiram e limpa o dos que voltaram.
- Aborta sem `--forcar` se marcaria ausentes mais de 20% dos itens presentes na importação
  anterior.
- Depois da gravação, a partir do PR 6, roda a explicação do "Já Entrou" ([R19](../research.md#r19-já-entrou-que-o-central-não-explica-fr-029)):
  um aviso por pedido não explicado e uma trava `JA_ENTROU`.
- Antes de começar, recusa com "Um lançamento de entradas está em andamento: a importação de pedidos
  espera ele terminar." se houver uma execução de entradas em andamento. A trava do tipo continua como
  última barreira (`ImportacaoEmAndamento`).
- Saída: o número de pedidos e itens, os novos, os ausentes e os pedidos travados. Uma falha sai com
  `CommandError`.

## `conciliar_entradas` (PR 3 extrai; PR 5 e PR 6 conciliam; PR 7 limpa)

```text
conciliar_entradas [--arquivo <csv>] [--desde dd/mm/aaaa --ate dd/mm/aaaa] [--diaria] [--sem-limpeza]
```

- **Período**: sem datas, do dia anterior ao menor destes valores até amanhã
  ([R22](../research.md#r22-rotina-diária-e-retenção)):
  - hoje − 9 dias;
  - a data de recebimento dos recebimentos lançados com `lancado_em` nos últimos 9 dias;
  - a data de recebimento dos recebimentos em verificação abertos.
- **Motivo da extração**: `DIARIA` com `--diaria`; `ARQUIVO` com `--arquivo`; nos demais casos,
  `MANUAL`.
- **Extração**: guarda o bruto e as requisições como `ExtracaoEntradas`.
- **Conciliação**:
  - a dos recebimentos em verificação (PR 5), salvo com `ARQUIVO`;
  - a dos lançados (PR 6), com o primeiro veredito e as revisões; com `ARQUIVO`, só o primeiro;
  - as entradas fora do Central (PR 6).
- **Limpeza de 60 dias** (PR 7), salvo `--sem-limpeza`.
- **Recusas**: com lançamento de entradas em andamento, com outra extração de entradas em andamento e
  com a importação de pedidos em andamento.
- **Saída**: as contagens, por veredito, de ligados à mão, de fora do Central e de pedidos
  travados. A conciliação incompleta sai com `CommandError` e a contagem parcial, como o
  `conciliar_lancamentos`.

## `lancar_entradas` (PR 4)

```text
lancar_entradas --recebimento RC-0001 [--recebimento RC-0002 ...] [--dry-run]
```

- `--recebimento` é obrigatório e se repete: o comando nunca lança a fila inteira sem escolha.
- Sem `--dry-run`, lança de verdade, e só com `LANCAMENTO_REAL=1`; sem ele, recusa com `CommandError`
  antes de criar a execução.
- Cria a `ExecucaoRobo` com `robo=ENTRADAS` e roda o contrato do [robô](robo-entradas.md). O real
  passa `extrair=baixar_entradas`.
- Saída: o resumo por recebimento. `FALHA` sai com `CommandError`.

## `atualizar_catalogo` (PR 7)

Depois do passo Requisições, na mesma sessão do navegador:

1. **Entradas**: `conciliar_entradas --diaria`.
2. **Pedidos de compra**: `importar_pedidos_compra`.

Um passo que falha não desfaz os anteriores e não impede o seguinte. O resumo do comando lista os seis
passos. O `deploy/crontab` não muda (07:15, dias úteis e fins de semana como hoje).

Com `--carga-inicial`, os dois passos são os mesmos: a importação de pedidos já é sempre completa. A
primeira extração de entradas bem-sucedida define o marco, e o que veio até ele é anterior ao Central
([R18](../research.md#r18-entrada-por-pedido-feita-fora-do-central-fr-028)).

## Disparo pela página (`scpi/disparo.py`)

| Função | Comando | Log |
|---|---|---|
| `iniciar_lancamento_entradas(usuario, *, simulacao, recebimentos)` | `lancar_entradas` | `lancar_entradas.log` |
| `iniciar_conciliacao_entradas()` | `conciliar_entradas` | `conciliar_entradas.log` |
| `iniciar_importacao("pedidos_compra")` | `importar_pedidos_compra` | `importar_pedidos_compra.log` |

Cada função confere de novo `operar_automacoes` antes de criar a execução, como o
`iniciar_lancamento`.

## `robos_em_andamento`

Não muda. As execuções `ENTRADAS` são `ExecucaoRobo` sob a mesma trava, e as importações novas são
`Importacao` com trava por tipo, então o `deploy/atualizar.ps1` as vê sem mudança.
