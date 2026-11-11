# Modelo de dados: entrada de materiais por pedido de compra

Os modelos novos ficam no app `compras` ([research R1](research.md#r1-onde-ficam-os-modelos-novos)). Do
que já existe, mudam três coisas, todas aditivas:
- `catalogo.Importacao.Tipo` ganha dois `choices`;
- `pedidos.ExecucaoRobo` ganha o campo `robo`;
- `contas.Usuario.Meta.permissions` ganha `receber_compras`.

A `LinhaSaida`, a `SaidaSCPI` e os modelos de `conciliacao` não mudam (FR-031).

As migrations são novas e aditivas e entram nos PRs que mudam modelo
([plano](plan.md#entrega-em-prs-empilhados)):
- `catalogo/0009`: os `choices`;
- `pedidos/0007`: o campo `robo`;
- `contas/0007`: a permissão e os grupos;
- as de `compras`, a partir da `0001`.

```text
Importacao (catalogo, PEDIDOS_COMPRA) ── atualiza ──► PedidoCompra 1 ──< ItemPedidoCompra
                                                          │  1                 │ 1
                                                          ├──< TravaPedido     │
                                                          ├──< EntradaForaDoCentral
                                                          └──< Recebimento 1 ──< ItemRecebimento >── ItemPedidoCompra
                                                                    │
ExecucaoRobo (pedidos, robo=ENTRADAS) 1 ──< TentativaEntrada >──────┘
        │ 0..1
        └──< ExtracaoEntradas >──1 Importacao (catalogo, ENTRADAS)
                   ├──< RequisicaoEntradaOficial ──< ItemEntradaOficial
                   └──< ConferenciaRecebimento >── Recebimento
                              ├── RequisicaoEntradaOficial (ligada, 0..1; outra, 0..1)
                              └──< CandidataEntrada >── RequisicaoEntradaOficial
```

## Mudanças em modelos existentes

### `catalogo.Importacao.Tipo` (PR 1, uma migration só)

- `PEDIDOS_COMPRA = "PEDIDOS_COMPRA", "Pedidos de compra"`, usado desde o PR 1;
- `ENTRADAS = "ENTRADAS", "Entradas do SCPI"`, usado a partir do PR 3.

A trava por tipo (`trava_importacao`), o "em andamento" e o histórico de Automações passam a valer
para os dois. O `max_length=20` comporta `PEDIDOS_COMPRA`.

### `pedidos.ExecucaoRobo.robo` (PR 4)

| Campo | Tipo | Regra |
|---|---|---|
| `robo` | choices `SAIDAS` ("Saídas"), `ENTRADAS` ("Entradas"); padrão `SAIDAS` | as execuções existentes ficam `SAIDAS`; toda consulta da aba Lançamento no SCPI filtra `SAIDAS` ([R9](research.md#r9-execução-do-robô-e-travas)) |

### `contas.Usuario.Meta.permissions` (PR 2)

Ganha `("receber_compras", "Receber compras (preparar, editar e cancelar recebimentos)")`. A migration
de dados `contas/0007_receber_compras` a dá aos grupos Atendimento e Gestão e confere no fim que os dois
a têm.

## `PedidoCompra` (PR 1)

Um pedido de compra do SCPI num exercício.

| Campo | Tipo | Regra |
|---|---|---|
| `exercicio` | smallint | o ano da sessão do SCPI em que foi lido |
| `ano` | smallint | o ano de origem do `NUMPED` (`/26` → 2026) |
| `numero` | int | o número do `NUMPED` (`00514` → 514) |
| `data` | date | `DATPED` |
| `fornecedor_codigo` | char(20) | `CODIF` |
| `fornecedor_nome` | char(200) | `NOME` |
| `ausente_desde` | FK → `Importacao`, nula | a primeira importação em que o pedido não veio; volta a nula se ele reaparecer |
| `atualizado_por` | FK → `Importacao` | a última importação que o trouxe |

**Restrições**:
- único (`exercicio`, `ano`, `numero`);
- o rótulo é `00514/26`, com o número em 5 dígitos e o ano em 2.

**Estado no Central** (calculado, nunca guardado):
- **fora do exercício**: o `exercicio` é diferente do ano corrente;
- **ausente**: `ausente_desde` preenchido;
- **travado**: alguma `TravaPedido` aberta;
- **precisa de conferência**: algum item com o reservado maior que o saldo do SCPI, como uma anulação
  feita depois do preparado. O saldo livre aparece como zero, e o robô recusa o recebimento na
  conferência da tela;
- **disponível**: nenhum dos anteriores e ao menos um item disponível ([R4](research.md#r4-item-disponível-para-recebimento)).

## `ItemPedidoCompra` (PR 1)

| Campo | Tipo | Regra |
|---|---|---|
| `pedido` | FK → `PedidoCompra`, `PROTECT` | |
| `item` | smallint | `ITEM`, o número no pedido |
| `codigo` | char(30) | `CADPRO` |
| `unidade` | char(20) | `UNID1` |
| `controle` | char(1) | `TPCONTROLE_SALDO`: `Q` quantidade, `T` valor |
| `quantidade` | decimal(14,4) | `QTD` |
| `anulado` | decimal(14,4) | `QTDANU` |
| `ja_entrou` | decimal(14,4) | `QTDENT` da última importação |
| `ja_entrou_anterior` | decimal(14,4), nulo | `QTDENT` da importação anterior; nulo na primeira, que é a base ([R19](research.md#r19-já-entrou-que-o-central-não-explica-fr-029)) |
| `pedida` | decimal(14,4) | `QTDPEDIDA` (subpedido) |
| `saldo_scpi` | decimal(14,4) | `QTDFALTA`, conferido na leitura |
| `preco` | decimal(14,4) | `PRCUNT` |
| `ausente_desde` | FK → `Importacao`, nula | o item não veio: o saldo no SCPI é zero |

**Restrições**:
- único (`pedido`, `item`);
- índice em (`pedido`, `codigo`).

As quantidades guardam 4 casas para não perder o que o SCPI mandou. A disponibilidade exige até 3.

## `Recebimento` (PR 2)

Uma NF de um pedido: a unidade que o robô lança como uma requisição de entrada (um recebimento = uma
NF = um pedido = uma requisição).

| Campo | Tipo | Regra |
|---|---|---|
| `id` | auto | o número exibido é `RC-<id>`, com 4 dígitos ou mais |
| `envio` | UUID, único | gerado quando o formulário abre; o reenvio igual devolve este recebimento ([R7](research.md#r7-concorrência-idempotência-e-edição)) |
| `pedido` | FK → `PedidoCompra`, `PROTECT` | |
| `nf` | char(12) | só dígitos, sem os zeros à esquerda, diferente de zero |
| `fornecedor_codigo` | char(20) | copiado do pedido |
| `chave_nf` | char(40), único, nulo | `"<fornecedor>:<nf>"`; `NULL` só no cancelamento sem tentativa ([R6](research.md#r6-nota-fiscal)) |
| `data_recebimento` | date | entre `pedido.data` e hoje |
| `observacao` | char(500) | opcional |
| `status` | choices, ver abaixo | |
| `requisicao_scpi` | char(9) | o número oficial (`003900/26`), vazio até lançar |
| `lancado_em` | datetime, nulo | gravado pelo robô depois do Salvar |
| `via` | choices `ROBO`, `MANUAL`, vazio | `MANUAL`: ligado a uma requisição feita à mão ([R18](research.md#r18-entrada-por-pedido-feita-fora-do-central-fr-028)) |
| `visivel_desde` | datetime, nulo | desde quando o SCPI certamente tem a entrada ([R5](research.md#r5-saldo-livre-e-reservas)) |
| `mensagem` | char(500) | o erro, o motivo do bloqueio, a incerteza |
| `versao` | int, padrão 1 | concorrência otimista; o robô a confere no `_travar` |
| `preparado_por` / `preparado_em` | FK → usuário, `PROTECT` / datetime | |
| `alterado_por` / `alterado_em` | FK nula / datetime nulo | a última edição, liberação ou cancelamento |
| `motivo_cancelamento` | char(300) | obrigatório ao cancelar |

**Restrições**:
- `CheckConstraint`: com o status `LANCADO`, `requisicao_scpi` preenchido; com `VERIFICAR` ou
  `EM_LANCAMENTO`, `chave_nf` não nula.

**Estados**:

| Estado (`status`) | Rótulo | Reserva saldo | Pode ir para |
|---|---|---|---|
| `PREPARADO` | Preparado | sim | `EM_LANCAMENTO` (robô); `ERRO` (conferência ou preenchimento); `LANCADO` (ligado à mão, R18); `CANCELADO` |
| `ERRO` | Com erro | sim | `PREPARADO` (editado ou corrigido); `LANCADO` (ligado à mão); `CANCELADO` |
| `EM_LANCAMENTO` | Em lançamento | sim | `LANCADO`; `VERIFICAR` |
| `VERIFICAR` | Em verificação | sim | `LANCADO` ("É esta" ou ligado à mão); `PREPARADO` (liberado com as três provas, a mesma versão + 1); `CANCELADO` (com as três provas) |
| `LANCADO` | Lançado | até ser refletido (R5) | nenhum: o Central não edita lançado (FR-027) |
| `CANCELADO` | Cancelado | não | nenhum |

**Quem grava o quê**:
- `compras.servicos` grava todas as transições, menos as do robô.
- O robô grava só `status`, `requisicao_scpi`, `lancado_em`, `mensagem`, `via` e `visivel_desde`, nas
  transições `PREPARADO → EM_LANCAMENTO → LANCADO | VERIFICAR` e `PREPARADO → ERRO`
  ([R23](research.md#r23-emenda-da-constituição-minor-200--210)).

## `ItemRecebimento` (PR 2)

| Campo | Tipo | Regra |
|---|---|---|
| `recebimento` | FK → `Recebimento`, `CASCADE` | |
| `item` | FK → `ItemPedidoCompra`, `PROTECT` | sempre do mesmo pedido do recebimento |
| `quantidade` | decimal(14,3) | pt-BR estrito, > 0, até 3 casas, ≤ saldo livre na gravação |

**Restrições**:
- único (`recebimento`, `item`);
- `CheckConstraint` `quantidade > 0`;
- a edição apaga e recria os itens e soma 1 na versão.

## `TravaPedido` (PR 2)

| Campo | Tipo | Regra |
|---|---|---|
| `pedido` | FK → `PedidoCompra`, `PROTECT` | |
| `motivo` | choices `TELA`, `JA_ENTROU`, `FORA_DO_CENTRAL`, `MARCA_SEM_LANCAMENTO` | ([R20](research.md#r20-travas-do-pedido)) |
| `detalhe` | text | o que difere, em português |
| `criada_em` | datetime | |
| `execucao` / `importacao` / `extracao` | FKs nulas | de onde veio (`extracao` só no PR 3, junto com `ExtracaoEntradas`) |
| `recebimento` | FK nula | o recebimento que a provocou, se houver |
| `destravada_em` / `destravada_por` / `motivo_destrave` | datetime nulo / FK nula / char(300) | preenchidos juntos |

**Validação**: destravar exige o motivo e uma importação `PEDIDOS_COMPRA` bem-sucedida com `inicio >
criada_em` da trava aberta mais recente. A ação fecha todas as travas abertas do pedido.

## `EntradaForaDoCentral` (PR 6)

| Campo | Tipo | Regra |
|---|---|---|
| `pedido` | FK → `PedidoCompra`, `PROTECT` | |
| `requisicao` | FK → `RequisicaoEntradaOficial`, `PROTECT` | a primeira em que apareceu |
| `ano` / `numero` | smallint / int | únicos juntos: uma por requisição |
| `visivel_desde` | datetime | o início da extração |
| `itens` | JSON | `[{codigo, quantidade}]` da requisição, para a reserva por código |

Reserva o saldo até uma importação de pedidos começada depois do `visivel_desde` e cria uma
`TravaPedido` `FORA_DO_CENTRAL`.

## `ExtracaoEntradas`, `RequisicaoEntradaOficial`, `ItemEntradaOficial` (PR 3)

Espelham `ExtracaoOficial`, `RequisicaoOficial` e `ItemOficial` da spec 010
([R13](research.md#r13-registro-oficial-das-entradas)).

**`ExtracaoEntradas`**:
- `importacao`: OneToOne com a `Importacao` do tipo `ENTRADAS`;
- `motivo`: `ANTES`, `DEPOIS`, `DIARIA`, `MANUAL` ou `ARQUIVO`; `ANTES` e `DEPOIS` exigem
  `execucao`;
- `execucao`: FK nula para `ExecucaoRobo`;
- os campos do bruto: `impressao`, `arquivo` (gzip), `mesmo_arquivo_que` e `arquivo_apagado_em`;
- `maior_requisicao`, nulo em toda extração sem sucesso;
- `requisicoes`.

**`RequisicaoEntradaOficial`**: uma foto por extração, única por (`extracao`, `ano`, `numero`).

| Campo | Coluna |
|---|---|
| `requisicao`, `ano`, `numero` | `REQUI` (pela `conciliacao.regras.chave`) |
| `id_requi` | `ID_REQUI` |
| `data_entrada` | `DATAE`, a data comparada e a do filtro |
| `data_requisicao` | `DTLAN`, guardada, nunca comparada (F5) |
| `fornecedor_codigo` | `CODIF` |
| `nf` | `DOCUM` sem os zeros à esquerda; índice em (`fornecedor_codigo`, `nf`) |
| `pedido_ano`, `pedido_numero` | `NUMPED`, nulos sem pedido; índice nos dois |
| `com_saida` | `SAID = S` |
| `tipo` | `TPREQUI` |
| `observacoes` | `OBS_CABECALHO` |
| `recebimento_observado` | a marca `RC-…` lida das observações, com índice |
| `responsavel` | `RESPONSA` |

**`ItemEntradaOficial`**: `ordem`, `codigo` (`CADPRO`), `quantidade` (`QUAN1`, decimal(14,4)) e
`unidade`.

**Validação**:
- a leitura é tudo ou nada;
- só uma extração `SUCESSO` dá piso, veredito, candidata ou prova;
- `ARQUIVO` nunca libera nem revisa.

## `TentativaEntrada` (PR 4)

| Campo | Tipo | Regra |
|---|---|---|
| `execucao` | FK → `ExecucaoRobo` (`robo=ENTRADAS`), `PROTECT` | |
| `ordem` | smallint | única por execução |
| `recebimento` | FK → `Recebimento`, `PROTECT` | único por execução |
| `versao` | int | a versão lida pelo robô |
| `momento` | datetime | gravado no `_travar` |
| `resultado` | choices `LANCADA`, `VERIFICAR`, `ERRO`, `IGNORADA` | nasce `VERIFICAR` na transação do `EM_LANCAMENTO`; `ERRO` e `IGNORADA` sem passar pelo Salvar |
| `requisicao` | char(9) | o número, quando `LANCADA` |
| `foto` | JSON | ver abaixo |

A `foto` guarda o que o robô ia digitar:
- pedido, fornecedor, NF, data e observações;
- os itens, com o número no pedido, o código e a quantidade;
- o que a tela mostrou para cada item na conferência: o "Já Entrou" e o saldo.

Ela serve à comparação e à terceira prova da liberação
([R16](research.md#r16-liberação-para-relançar-as-três-provas)).

"Teve tentativa" (R6, FR-010, FR-012) quer dizer que existe uma tentativa `LANCADA` ou `VERIFICAR`.

## `ConferenciaRecebimento` e `CandidataEntrada` (PR 5 e PR 6)

**`ConferenciaRecebimento`** espelha a `ConferenciaLote` da spec 010.

| Campo | Regra |
|---|---|
| `recebimento` | FK, `PROTECT` |
| `extracao` | FK → `ExtracaoEntradas`, `PROTECT` |
| `tipo` | `LANCAMENTO`, `REVISAO` ou `VERIFICAR` |
| `veredito` | `AGUARDANDO`, `COMPROVADO`, `DIVERGENTE`, `NAO_ENCONTRADO`, `DUPLICADO`, `CONFLITO`, `INTERVALO_VAZIO`, `COM_CANDIDATAS` ou `SEM_TENTATIVA` |
| `requisicao`, `outra_requisicao` | FKs nulas para `RequisicaoEntradaOficial` |
| `vinculos` | JSON: quais dos três apontaram para a ligada (`numero`, `marca`, `nf`) |
| `diferencas`, `notas` | JSON |
| `alterado_depois` | booleano |
| `intervalo_de`, `intervalo_ate` | os limites do intervalo |
| `tentativa` | FK nula |
| `criada_em` | |

**Restrições**: único (`recebimento`, `extracao`, `tipo`).

**Regra**: o veredito atual de um recebimento lançado é o da última conferência conclusiva. Uma
`AGUARDANDO` é provisória ([R17](research.md#r17-vereditos-de-um-recebimento-lançado)).

**`CandidataEntrada`**: `conferencia` (FK, `CASCADE`), `requisicao` (FK, `PROTECT`), `e_esta`
(verdadeiro quando a marca ou a NF com o fornecedor batem) e `ordem`
([R15](research.md#r15-candidatas-de-um-recebimento-em-verificação)).

## Saldo livre (calculado)

Por item, em `compras.regras.saldo_livre` (pura):

```text
saldo_livre = saldo_scpi
            − Σ ItemRecebimento (status PREPARADO, ERRO, EM_LANCAMENTO, VERIFICAR)
            − Σ ItemRecebimento (status LANCADO, visivel_desde ≥ início da última importação PEDIDOS_COMPRA bem-sucedida)
            − Σ EntradaForaDoCentral.itens do código (visivel_desde ≥ esse início)
```

- O "total" sugere o saldo livre de cada item disponível.
- A gravação refaz a conta dentro da trava do pedido e recusa o item acima dela, com o saldo livre
  na mensagem (FR-007, US1 cenário 2).
- Saldo livre negativo, como o de uma anulação depois do preparado, aparece como zero. O pedido
  aparece como "precisa de conferência".
