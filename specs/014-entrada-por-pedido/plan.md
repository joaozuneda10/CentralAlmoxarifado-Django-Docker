# Implementation Plan: Entrada de materiais por pedido de compra

**Branch**: `014-entrada-por-pedido` (branch de trabalho: `claude/entrada-por-pedido`, base da pilha) | **Date**: 2026-11-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/014-entrada-por-pedido/spec.md`

## Summary

O almoxarifado passa a preparar no Central o recebimento de uma nota fiscal de um pedido de compra, total
ou parcial. Um robô lança a Requisição de Entrada por pedido no SCPI, com as garantias da conciliação de
saídas (spec 010) e três a mais:
- a conferência da tela antes do Salvar;
- o terceiro vínculo, a NF com o fornecedor;
- o "Já Entrou" do pedido como prova independente da data.

A entrega é feita em oito PRs empilhados ([abaixo](#entrega-em-prs-empilhados)), na ordem de
consequência:

- **Pedidos de compra** (PR 1): carga e atualização pelo 07.13, que não grava no SCPI, com os itens
  disponíveis.
- **Recebimento** (PR 2): saldo livre, "total" e "parcial", NF única, concorrência e a permissão nova
  `receber_compras`.
- **Registro oficial das entradas** (PR 3): extração do relatório de entradas, guardada como na
  spec 010.
- **Robô de entradas** (PR 4): a fila em Automações, a simulação, o lançamento real com a ordem do
  Princípio III, a conferência antes do Salvar e as extrações de antes e de depois.
- **Verificação sem risco** (PR 5): candidatas, "É esta" e a liberação só com as três provas.
- **Vereditos e entradas fora do Central** (PR 6): os seis vereditos, a ligação da entrada feita à mão,
  "Lançada fora do Central", o "Já Entrou" não explicado e o destravamento.
- **Diária e retenção** (PR 7): dois passos novos no `atualizar_catalogo` e a limpeza de 60 dias.

O PR 0 leva esta documentação e a emenda MINOR da constituição. Decisões técnicas em
[research.md](research.md); modelo em [data-model.md](data-model.md); contratos em
[contracts/](contracts/); roteiro de validação em [quickstart.md](quickstart.md).

## Technical Context

**Language/Version**: Python 3.13 (`>=3.13,<3.14`), Django 6.x

**Primary Dependencies**: Django, Playwright (o que já existe), HTMX 4.0.0 (vendorizado, só nos
componentes existentes), waitress; nenhuma dependência nova

**Storage**: MariaDB 11.4 / MySQL 8, com migrations aditivas e novas:
- app novo `compras`, a partir da `0001`;
- `catalogo/0009`: os `choices` `PEDIDOS_COMPRA` e `ENTRADAS`;
- `pedidos/0007`: `ExecucaoRobo.robo`;
- `contas/0007`: a permissão `receber_compras` nos grupos Atendimento e Gestão.

O bruto das extrações fica em `BinaryField` com gzip, como na spec 010.

**Testing**: pytest contra MySQL/MariaDB (`config.settings_test`), sem navegador:
- um SCPI simulado de entradas (`tests/scpi_entradas_simulado.py`), com falhas controladas;
- CSVs sintéticos no formato real dos dois relatórios;
- a concorrência em duas conexões (`transaction=True`).

**Target Platform**: Docker Compose em Windows 10 com Docker Desktop; robôs no container `web`,
agendador no `agendador`

**Project Type**: aplicação web Django com HTMX (monólito; apps `pedidos`, `catalogo`, `scpi`,
`automacoes`, `interface`, `contas`, `implantacao`, `conciliacao` e o novo `compras`)

**Performance Goals**:
- importação de cerca de 3 mil itens em menos de 1 minuto (o 07.13 sai em uns 20 s);
- saldo livre de um pedido de até 30 itens numa consulta por tabela;
- o recebimento total de 30 itens preparado em menos de 2 minutos (SC-002), porque o formulário já vem
  preenchido;
- a conciliação de algumas dezenas de recebimentos por dia em menos de 1 s.

**Constraints**:
- O Princípio III não admite exceção.
- O SCPI só é estável das 7h às 17h.
- Nunca o 01.08.03.
- Nada muda nas saídas (FR-031): `scpi/lancamento.py`, `scpi/lancador.py` (só reaproveitado),
  `conciliacao/` e `LinhaSaida` sem mudança de comportamento.
- Um robô de lançamento por vez.
- Nenhum teste abre navegador nem usa o CSV real.
- Produção com dados reais: migrations novas, nunca regeneradas.
- `check --deploy` sem avisos.
- Nada de CDN ou npm.

**Scale/Scope**:
- dados: cerca de 700 pedidos e 2.900 itens com saldo, cerca de 200 entradas por pedido por ano, 10
  entradas por dia no total;
- código: 12 modelos novos e 3 comandos novos (`importar_pedidos_compra`, `conciliar_entradas`,
  `lancar_entradas`);
- telas: 6 rotas em `compras`, 4 em `automacoes` e uma aba nova;
- arquivos que mudam:
  - `scpi/relatorios.py`, `scpi/leitura.py` e `scpi/disparo.py`;
  - `pedidos/models.py`, `pedidos/views` e `automacoes/` (filtro `robo`);
  - `catalogo/saude.py`;
  - `contas/acesso.py` e `contas/models.py`;
  - `interface/navegacao.py`;
  - `atualizar_catalogo`;
  - a constituição e o `CLAUDE.md`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

A constituição 2.0.0 fala só de pedidos e saídas nos Princípios II e III. A emenda MINOR 2.1.0
([R23](research.md#r23-emenda-da-constituição-minor-200--210)) entra no PR 0, antes de qualquer
código, e estende os dois princípios às entradas sem afrouxar nada. A verificação abaixo é contra o
texto emendado.

| Princípio | Verificação | Situação |
|---|---|---|
| I. Regras puras | Ficam em `compras/regras.py`, sem ORM e com teste próprio: saldo livre, disponibilidade, NF, validação do recebimento, `conferir_tela`, marca, candidatas, as três provas, veredito com três vínculos e explicação do "Já Entrou". As leituras ficam em `scpi.leitura.ler_pedidos_compra` e `ler_entradas`. Quantidades em `Decimal` pt-BR estrito; códigos por `norm_u`. | Passa |
| II. Uma porta de gravação | `compras/servicos.py` grava recebimentos e travas, cada operação numa transação com `select_for_update` no pedido de compra. O envio por UUID impede a duplicação. O robô de entradas grava só os campos de lançamento do recebimento e trava o pedido pela função do serviço. `pedidos` só ganha o campo `robo` na `ExecucaoRobo`. | Passa (com 2.1.0) |
| III. Nunca lançar duas vezes | Garantias de antes, mantidas: `EM_LANCAMENTO` e a tentativa gravados e a transação fechada antes do clique; qualquer falha depois do clique vira `VERIFICAR`; journal antes do banco; `FalhaCritica` se o banco recusa; a mesma `TRAVA_LANCAMENTO` das saídas; `LANCAMENTO_REAL`. Garantias novas, que só bloqueiam: a conferência da tela antes do Salvar; a extração de antes obrigatória; a liberação só com as três provas; nenhum outro recebimento do pedido enquanto um está em verificação; a NF nunca liberada depois de uma tentativa. O simulado exercita "salvou e perdeu a resposta" (SC-001). | Passa |
| IV. Dados importados não se perdem | Importação e extração pela `scpi.execucao.executar`, em transação e com trava por tipo. A leitura é tudo ou nada, e o relatório cortado aborta. A importação que marcaria ausentes mais de 20% dos itens aborta sem `--forcar`. Nada é apagado: item e pedido que somem ficam `ausente_desde`. O "Já Entrou" não explicado vira aviso e trava. Cada execução fica registrada. | Passa |
| V. Testes no banco real, sem navegador | SCPI simulado e CSVs sintéticos; concorrência com duas conexões. A navegação nova (07.13, relatório de entradas, tela de entrada por pedido) só pelo `--dry-run` e pelos comandos, feitos à mão. | Passa |
| VI. pt-BR, acessível, sem dependências | Textos em pt-BR. Estado em texto. `RC-…`, números e códigos em mono. Nada externo. UI com `clean-design` + `docs/DESIGN.md`, `ui-ux-pro-max` e `frontend-design`. | Passa |
| Fluxo | Spec e plano antes do código; branch `claude/*` por PR; `CLAUDE.md` atualizado em cada PR que muda o que ele descreve; os portões em cada PR. | Passa |

Sem exceções.

**Reverificação depois da Fase 1**:
- O modelo põe tudo das entradas em `compras`. `pedidos` só ganha o `robo`, e as consultas das saídas o
  filtram.
- O contrato do robô repete a ordem das gravações das saídas e acrescenta passos que só bloqueiam
  (conferência da tela, pedido com verificação aberta).
- A liberação exige mais prova que a das saídas, nunca menos.
- A NF única é garantida pelo banco (índice único com `NULL`).

O desenho continua passando.

## Project Structure

### Documentation (this feature)

```text
specs/014-entrada-por-pedido/
├── spec.md
├── plan.md              # este arquivo
├── research.md          # R1–R26
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── relatorios-scpi.md
│   ├── robo-entradas.md
│   ├── comandos.md
│   └── tela-e-acoes.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks (não criado aqui)
```

### Source Code (repository root)

```text
compras/                             # app novo
├── models.py                        # PedidoCompra, ItemPedidoCompra, Recebimento, ItemRecebimento,
│                                    # TravaPedido, EntradaForaDoCentral, ExtracaoEntradas,
│                                    # RequisicaoEntradaOficial, ItemEntradaOficial, TentativaEntrada,
│                                    # ConferenciaRecebimento, CandidataEntrada
├── regras.py                        # puro: disponibilidade, saldo_livre, nf, validar_recebimento,
│                                    # marca, conferir_tela, candidatas, provas, veredito_entrada,
│                                    # ja_entrou_explicado
├── importacao.py                    # gravar a leitura do 07.13 (criar, atualizar, ausentes, corte)
├── extracao.py                      # extrair(motivo, periodo, obter_csv) via scpi.execucao.executar
├── servicos.py                      # a porta única: preparar, editar, cancelar, resolver, travar,
│                                    # destravar
├── conciliacao.py                   # conciliar(extracao): verificar, lançados, fora do Central
├── robo.py                          # seleção, foto, tentativas, extrair antes/depois
├── consultas.py                     # saldo livre por pedido, fila, liberacao, marco, veredito atual
├── saude.py                         # avisos para catalogo.saude
├── limpeza.py                       # retenção de 60 dias
├── forms.py, views.py, urls.py      # Compras: lista, pedido, receber, recebimento, editar, cancelar
├── templates/compras/
├── admin.py                         # só leitura (pedidos, extrações); recebimentos só leitura
├── migrations/0001…
└── management/commands/
    ├── importar_pedidos_compra.py
    └── conciliar_entradas.py

scpi/
├── leitura.py                       # + ler_pedidos_compra, ler_entradas
├── relatorios.py                    # + baixar_pedidos_compra, baixar_entradas (funções novas)
├── lancamento_entradas.py           # novo: o robô (contrato robo-entradas.md)
├── lancador_entradas.py             # novo: navegação Playwright da entrada por pedido
├── disparo.py                       # + iniciar_lancamento_entradas, iniciar_conciliacao_entradas
└── management/commands/
    ├── lancar_entradas.py           # novo
    └── atualizar_catalogo.py        # + passos Entradas e Pedidos de compra (PR 7)

pedidos/models.py                    # ExecucaoRobo.robo (+ migration 0007)
pedidos/ (consultas da aba)          # filtro robo=SAIDAS
catalogo/models.py                   # Importacao.Tipo (+ migration 0009)
catalogo/saude.py, catalogo/forms.py # avisos; tipo pedidos_compra no formulário de importação
contas/models.py, contas/acesso.py   # receber_compras, PERMISSOES_INTERNAS, REGRAS_POR_ROTA
                                     # (+ migration 0007)
automacoes/views.py, urls.py         # aba Entradas no SCPI; lancar_entradas, resolver_entrada,
                                     # destravar_pedido, conferir_entradas
automacoes/historico.py              # rótulos dos tipos e do robô
interface/navegacao.py               # item Compras
.specify/memory/constitution.md      # 2.1.0 (PR 0)
CLAUDE.md                            # seção nova de compras e entradas; comandos; Automações

tests/
├── scpi_entradas_simulado.py
├── relacao_pedidos_compra.py
├── relacao_entradas.py
├── compras_cenario.py
├── test_scpi_leitura_pedidos_compra.py
├── test_scpi_leitura_entradas.py
├── test_compras_regras.py
├── test_compras_importacao.py
├── test_compras_recebimento.py
├── test_compras_acesso.py
├── test_compras_extracao.py
├── test_lancamento_entradas.py
├── test_compras_verificar.py
├── test_compras_vereditos.py
├── test_compras_fora_do_central.py
└── test_compras_diaria.py
```

**Structure Decision**: monólito Django, como as specs anteriores. O app novo `compras` guarda todo o
estado das entradas ([R1](research.md#r1-onde-ficam-os-modelos-novos)). O código de SCPI continua em
`scpi`, em módulos novos e paralelos aos das saídas. A apresentação fica numa área nova do painel
(Compras) e numa aba nova de Automações.

## Entrega em PRs empilhados

### Regras da pilha

As mesmas da spec 010:

- **Base da pilha**: o PR 0, `claude/entrada-por-pedido` → `develop`, com a spec, este plano e a emenda
  da constituição. Cada PR seguinte tem como base a branch do anterior e mostra só o próprio diff.
- **O PR 0 entra em `develop` antes de qualquer PR com código**: os PRs 1 a 7 dependem da constituição
  2.1.0 para estar em conformidade.
- **Cada PR passa os portões sozinho**: `pytest`, `ruff check`, `ruff format --check` e
  `makemigrations --check`. Cada um deixa o sistema funcionando em produção se o deploy parar nele e
  atualiza o `CLAUDE.md` no que muda.
- **Merge de baixo para cima, um de cada vez, pelo usuário**, em `develop`. Nunca se mergeia a pilha
  inteira pelo botão de stack do GitHub nem pelo `merge-async`: isso já fez squash direto em `main` e
  deixou `develop` sem o PR de cima.
- **Depois que o PR k entra**: troca-se a base do PR k+1 para `develop` e rebaseia-se a branch dele
  sobre `origin/develop` (`git rebase --onto origin/develop <ponta antiga de k> <branch k+1>`). Em
  seguida, `git push --force-with-lease`, só na própria branch `claude/*`.
- **Produção** continua por tag e imagem aprovada (`deploy/FLUXO_GIT.md`), num pedido explícito. A
  pilha pode ir em partes:
  - PR 1 e PR 2 já são úteis sozinhos: o almoxarifado vê o saldo e prepara;
  - o lançamento real exige, no mínimo, PR 3 + PR 4 + PR 5. Sem o PR 5, um recebimento em verificação
    não tem saída segura além de esperar.

### Os PRs

| # | Branch | Base | Entrega | Requisitos | Migration |
|---|---|---|---|---|---|
| 0 | `claude/entrada-por-pedido` | `develop` | spec, checklist, plano, pesquisa, modelo, contratos, quickstart, constituição 2.1.0 | — | — |
| 1 | `claude/entradas-1-pedidos` | 0 | pedidos de compra importados | FR-001–003, 005; US5 cenários 1 e 2 | `catalogo/0009`, `compras/0001` |
| 2 | `claude/entradas-2-recebimento` | 1 | recebimento, saldo livre, travas, permissão e telas de Compras | FR-004, 006–013, 030; US1 | `contas/0007`, `compras/0002` |
| 3 | `claude/entradas-3-extracao` | 2 | registro oficial das entradas | FR-021 (a extração) | `compras/0003` |
| 4 | `claude/entradas-4-robo` | 3 | fila, simulação e lançamento real | FR-014–020; US2 | `pedidos/0007`, `compras/0004` |
| 5 | `claude/entradas-5-verificar` | 4 | candidatas, "É esta" e as três provas | FR-025, 026; US3 | `compras/0005` |
| 6 | `claude/entradas-6-vereditos` | 5 | vereditos, fora do Central, "Já Entrou", destravar e a tela de conferência | FR-022–024, 027–029; US4; US5 cenários 3 a 6 | `compras/0006` |
| 7 | `claude/entradas-7-diaria` | 6 | dois passos no `atualizar_catalogo` e retenção | FR-021 (diária), SC-005 | — |

#### PR 0. Documentação e constituição

- **O quê**:
  - esta pasta;
  - o registro do brainstorming (já commitado);
  - a constituição 2.1.0 com o texto de [R23](research.md#r23-emenda-da-constituição-minor-200--210)
    e o Sync Impact Report no topo.
- **Não muda**: código.
- **Pronto quando**: o usuário revisou a spec e o plano.

#### PR 1. Pedidos de compra importados

- **O quê**:
  - `PedidoCompra` e `ItemPedidoCompra`;
  - `Importacao.Tipo.PEDIDOS_COMPRA` e o rótulo no histórico;
  - `scpi.leitura.ler_pedidos_compra` e `scpi.relatorios.baixar_pedidos_compra`;
  - `compras.importacao`, com os ausentes e o corte de 20%;
  - `compras.regras.disponibilidade`;
  - o comando `importar_pedidos_compra` e o tipo no formulário de importação de Automações;
  - o admin só leitura;
  - o gerador `tests/relacao_pedidos_compra.py`.
- **Não muda**: nada das saídas; ainda não há tela de Compras.
- **Testes**:
  - leitura: colunas, `QTDFALTA` conferido, cortado, recolado, `T`, 4 casas, `NUMPED` inválido,
    fornecedor diferente no pedido;
  - importação: criar, atualizar, ausente, reaparecer, corte com e sem `--forcar`, exercício,
    falha sem gravar nada, trava ocupada;
  - disponibilidade.
- **Pronto quando**: os portões passam e o usuário fez o [quickstart, passo 2](quickstart.md#2-pedidos-de-compra-do-scpi-real-pr-1-manual)
  (o Log do pedido sem alteração).
- **Risco**: os campos do 07.13 não serem achados pelo rótulo. Aparece no passo 2, antes do PR 2.

#### PR 2. Recebimento

- **O quê**:
  - `Recebimento`, `ItemRecebimento` e `TravaPedido` (o modelo inteiro, com os motivos dos PRs
    seguintes);
  - `compras.regras` (saldo livre, NF, validação, marca);
  - `compras.servicos` (preparar, editar, cancelar, destravar);
  - `contas.receber_compras` com a migration de dados;
  - as rotas `compras:*` em `REGRAS_POR_ROTA`, o item de menu e as telas
    ([tela-e-acoes.md](contracts/tela-e-acoes.md#compras-permissão-contasreceber_compras-atendimento-e-gestão)).
- **Não muda**: o robô. O recebimento preparado ainda não vai a lugar nenhum: a fila é do PR 4.
- **Testes**: [quickstart, passo 3](quickstart.md#3-recebimento-pr-2-automático), mais
  `tests/test_papeis_acesso.py` e `tests/test_epis_acesso.py` cobrindo as rotas novas.
- **Pronto quando**: os portões passam e a conferência visual no navegador local foi feita (375 px,
  teclado, sem depender de cor).
- **Risco**: a tela de muitos itens ficar pesada no celular. Mitigação: a linha do item segue a do
  atendimento, e o "parcial" começa vazio.

#### PR 3. Registro oficial das entradas

- **O quê**:
  - `ExtracaoEntradas`, `RequisicaoEntradaOficial` e `ItemEntradaOficial`;
  - `Importacao.Tipo.ENTRADAS`;
  - `scpi.leitura.ler_entradas` e `scpi.relatorios.baixar_entradas`;
  - `compras.extracao.extrair`, com o bruto gzip e a impressão;
  - o comando `conciliar_entradas` (por enquanto só extrai);
  - o gerador `tests/relacao_entradas.py`.
- **Não muda**: `conciliacao` e o relatório das saídas.
- **Testes**: leitura (cabeçalho variando, cortado, `DOCUM` e `NUMPED` vazios, `SAID`, marca);
  extração (sucesso, falha sem gravar requisições, impressão igual, "Nada a exibir", trava).
- **Pronto quando**: os portões passam e a primeira parte do [quickstart, passo 4](quickstart.md#4-registro-oficial-e-navegação-do-robô-no-scpi-real-prs-3-e-4-manual)
  foi feita.

#### PR 4. Robô de entradas

- **O quê**:
  - `ExecucaoRobo.robo` e o filtro `SAIDAS` nas consultas da aba das saídas;
  - `TentativaEntrada`;
  - `scpi/lancamento_entradas.py` e `scpi/lancador_entradas.py`;
  - `compras.robo`: seleção, foto, extração de antes e de depois (só guarda; a conciliação vem nos PRs
    5 e 6);
  - `compras.regras.conferir_tela` e a trava `TELA`;
  - o comando `lancar_entradas` e `iniciar_lancamento_entradas`;
  - a aba "Entradas no SCPI" com a fila e o andamento;
  - o SCPI simulado de entradas.
- **Não muda**: `scpi/lancamento.py`, `scpi/lancador.py` (só importado), `conciliacao`. Os testes do
  lançamento das saídas passam sem mudar.
- **Testes**: a tabela "Garantias" de [robo-entradas.md](contracts/robo-entradas.md); a aba das saídas
  sem as execuções de entradas; os botões das saídas desabilitados com o robô de entradas rodando.
- **Pronto quando**: os portões passam e o usuário fez o `--dry-run` do quickstart, passo 4 (segunda
  parte), com os pontos de [R25](research.md#r25-o-que-só-o-scpi-real-confirma) anotados.
- **Risco**: a grade da entrada por pedido não deixar conferir a QTD de cada linha pela tela, como faz
  a das saídas. Se acontecer, o preenchimento recusa (`ErroSCPI`) e o recebimento fica com erro, sem
  salvar. O desenho não depende do resultado: a garantia está antes do Salvar.

#### PR 5. Verificação sem risco

- **O quê**:
  - `ConferenciaRecebimento` e `CandidataEntrada` (o modelo inteiro, com os vereditos do PR 6);
  - `compras.regras.candidatas` e as três provas;
  - `compras.conciliacao.conciliar_verificar`, chamada depois da extração de depois e pelo
    `conciliar_entradas`;
  - `compras.consultas.liberacao`;
  - `resolver_recebimento` (É esta, liberar, cancelar) e `automacoes:resolver_entrada`, com as
    mensagens do contrato;
  - o cartão de cada recebimento em verificação, com as candidatas.
- **Testes**: [quickstart, passo 5](quickstart.md#5-robô-e-verificação-com-o-scpi-simulado-prs-4-e-5-automático).
- **Pronto quando**: os portões passam.
- **Risco**: um recebimento em verificação sem prova ficar preso. É o lado seguro: ele se resolve pelo
  "É esta" ou depois da próxima extração e da próxima importação.

#### PR 6. Vereditos, entradas fora do Central e "Já Entrou"

- **O quê**:
  - `compras.regras.veredito_entrada`, a comparação e `ja_entrou_explicado`;
  - `conciliar_lancados` (lançamento e revisão);
  - a ligação à mão, `EntradaForaDoCentral`, o marco e as travas `FORA_DO_CENTRAL`,
    `MARCA_SEM_LANCAMENTO` e `JA_ENTROU`;
  - a explicação do "Já Entrou" no `importar_pedidos_compra`;
  - `automacoes:destravar_pedido` e `automacoes:conferir_entradas`;
  - a região de conferência e a de pedidos travados;
  - os avisos de saúde.
- **Não muda**: o recebimento lançado (FR-027).
- **Testes**: [quickstart, passo 6](quickstart.md#6-vereditos-entrada-fora-do-central-e-já-entrou-pr-6-automático).
- **Pronto quando**: os portões passam e a conferência visual das regiões novas foi feita.
- **Risco**: falsas travas `JA_ENTROU`. Os certos e os incertos de
  [R19](research.md#r19-já-entrou-que-o-central-não-explica-fr-029) garantem que só o robô mexendo no
  pedido nunca trava. Fora disso, a trava é o comportamento pedido (D4).

#### PR 7. Diária e retenção

- **O quê**:
  - os passos Entradas e Pedidos de compra no `atualizar_catalogo`, na mesma sessão;
  - `compras.limpeza` com as travas da extração e da conciliação;
  - o `CLAUDE.md` com a rotina.
- **Não muda**: os quatro passos atuais e o horário (07:15).
- **Testes**: [quickstart, passo 7](quickstart.md#7-diária-e-retenção-pr-7-automático).
- **Pronto quando**: os portões passam.
- **Risco**: o `atualizar_catalogo` ficar mais longo. São mais dois relatórios de segundos na mesma
  sessão.

### Dependências entre os PRs

```text
0 ─► 1 ─► 2 ─► 3 ─► 4 ─► 5 ─► 6 ─► 7
```

A pilha é linear. Cada PR usa modelos ou funções do anterior. O PR 3 poderia vir antes do 2, porque a
extração não depende do recebimento. Mas o PR 4 precisa dos dois, e manter a ordem da spec deixa cada
PR com um valor visível para o usuário.

## Pendências levadas da spec

- **Emenda MINOR (L9)**: no PR 0 ([R23](research.md#r23-emenda-da-constituição-minor-200--210)).
- **Filtro sem período do 07.04.01**: fechado sem consulta. A terceira prova da liberação já não
  depende da data ([R16](research.md#r16-liberação-para-relançar-as-três-provas)).
- **Lacunas do registro que ficaram como premissa**:
  - L3 (janelas depois do Salvar) e L8 (latência): no lançamento real (quickstart, passo 8);
  - L4 (recheck do saldo pelo SCPI): coberta pela conferência da tela;
  - L5 (subpedido): o `QTDPEDIDA` entra no saldo;
  - L6 (virada do exercício): pedido por exercício ([R2](research.md#r2-identidade-do-pedido-do-item-e-do-exercício));
  - L7 (não empenhado): falha antes do Salvar, que deixa o recebimento com erro.
- **Fora da spec**: o aviso ao setor de Compras sobre a Data Emissão gravada pelo 01.08.03 em
  10/11/2026 continua com o usuário.

## Complexity Tracking

Sem violações da constituição a justificar. Três escolhas pedem registro, porque têm uma alternativa
mais simples:

| Escolha | Por quê | Alternativa mais simples descartada porque |
|---|---|---|
| App novo com modelos paralelos aos da conciliação | FR-031: nada muda nas saídas | estender `conciliacao` poria um filtro de domínio em cada consulta das saídas |
| Robô em módulo paralelo, não generalizado | o Princípio III das saídas fica intacto e testado como está | um robô genérico mudaria `scpi/lancamento.py` e os testes dele |
| `ExecucaoRobo.robo` em vez de um modelo próprio | um "em andamento", um histórico e o `robos_em_andamento` sem mudança | um modelo próprio duplicaria o "em andamento" e arriscaria o deploy recriar o `web` com o robô rodando |
