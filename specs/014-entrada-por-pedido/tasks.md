---

description: "Tarefas da funcionalidade 014: entrada de materiais por pedido de compra"
---

# Tasks: Entrada de materiais por pedido de compra

**Input**: documentos de design em `specs/014-entrada-por-pedido/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: **incluídos**. A constituição (Princípio V) exige teste automatizado para toda mudança de
comportamento. Os testes:
- rodam contra MariaDB ou MySQL;
- nunca abrem o navegador nem o SCPI real;
- nunca usam os CSVs reais;
- nunca gravam no `logs/` do repositório.

**Organization**: as tarefas seguem as histórias da spec e a [pilha de PRs do plano](plan.md#entrega-em-prs-empilhados).

| Fase | PR | Branch |
|---|---|---|
| 1. Setup | PR 0 | `claude/entrada-por-pedido` |
| 2. Foundational | PR 1 | `claude/entradas-1-pedidos` |
| 3. US1 | PR 2 | `claude/entradas-2-recebimento` |
| 4. US2 | PR 3 e PR 4 | `claude/entradas-3-extracao` e `claude/entradas-4-robo` |
| 5. US3 | PR 5 | `claude/entradas-5-verificar` |
| 6 e 7. US4 e US5 | PR 6 | `claude/entradas-6-vereditos` |
| 8. Polish | PR 7 | `claude/entradas-7-diaria` |

Os cenários 1 e 2 da US5 (a carga dos pedidos) são o próprio Foundational.

## Format: `[ID] [P?] [Story] Descrição com caminho de arquivo`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta).
- **[Story]**: a história da spec. Setup, Foundational e Polish não têm.
- **Comandos**:
  - `uv run pytest <arquivo>`;
  - `uv run ruff check . && uv run ruff format --check .`;
  - `uv run python manage.py makemigrations --check --dry-run`.

  **Só o banco de desenvolvimento**: nada de `docker compose` na produção, nenhum `migrate` no banco
  real, nenhum `lancar_entradas` sem `--dry-run` e nenhum importador do SCPI em produção sem pedido do
  usuário.

## Regras gerais para todas as tarefas

- **Código Python**: investigar com o Serena antes (`find_symbol`, `find_referencing_symbols`),
  conforme o `CLAUDE.md`.
- **Migrations**: sempre novas, nunca regeneradas. São `catalogo/0009`, `contas/0007`,
  `pedidos/0007` e as de `compras` a partir da `0001`. Nomes de grupo vão como literais dentro da
  migration de dados.
- **Porta de gravação** (Princípio II, com a emenda 2.1.0 da T002): `compras/servicos.py` é a única
  que grava recebimentos e travas. O robô de entradas grava só `status`, `requisicao_scpi`,
  `lancado_em`, `mensagem`, `via` e `visivel_desde` do `Recebimento`, e trava o pedido por
  `compras.servicos.travar_pedido`.
- **Princípio III**: a ordem das gravações do robô de entradas é a de
  [contracts/robo-entradas.md](contracts/robo-entradas.md), sem exceção.
- **Saídas intocadas**: nada muda em `scpi/lancamento.py`, `conciliacao/` nem `LinhaSaida`
  (FR-031). Os testes das saídas passam sem mudar de expectativa.
- **Rotas**: toda rota nova entra em `contas.acesso.REGRAS_POR_ROTA` na mesma tarefa que a cria.
  `tests/test_papeis_acesso.py` e `tests/test_epis_acesso.py` continuam verdes.
- **Interface**:
  - textos em pt-BR, no design Clean (`docs/DESIGN.md`, skill `clean-design`), junto das skills
    `ui-ux-pro-max` e `frontend-design`;
  - estado nunca só por cor;
  - `RC-…`, números de requisição, de pedido e de NF, e códigos em `.mono`;
  - gravação só por POST com CSRF.
- **Quantidades**: `Decimal`, pt-BR estrito, com `pedidos.regras.interpretar_quantidade` (regra
  `livre`, até 3 casas) e `qtd_br` na tela. Códigos por `norm_u`.
- **Fim de cada fase**: commit na branch da fase. Push e PR só a pedido do usuário.

---

## Phase 1: Setup (PR 0)

**Purpose**: a documentação e a emenda da constituição, antes de qualquer código.

- [X] T001 Confirmar a branch `claude/entrada-por-pedido` (de `develop`, com o commit `47423cc` da spec) e o `git status` limpo; rodar `uv run pytest` para registrar a suíte verde de partida
- [X] T002 Emendar `.specify/memory/constitution.md` para a 2.1.0 com o texto de [research R23](research.md#r23-emenda-da-constituição-minor-200--210):
  - **Princípio I**: `compras/regras.py` entra na lista de regras puras;
  - **Princípio II**: `compras/servicos.py` é a porta única dos recebimentos e das travas, com transação e `select_for_update` no pedido de compra; o robô de entradas grava só os seis campos de lançamento; o reenvio igual não duplica;
  - **Princípio III**: "lote ou recebimento", journal próprio por robô, "uma execução de lançamento por vez, de saídas ou de entradas, com a mesma trava", e a conferência da tela antes do Salvar;
  - o Sync Impact Report no topo (2.0.0 → 2.1.0, MINOR) e `Last Amended: 2026-11-11`.
- [X] T003 [P] Atualizar as notas de `specs/014-entrada-por-pedido/checklists/requirements.md`: a emenda está na T002, e o filtro sem período do 07.04.01 foi dispensado pela terceira prova ([R16](research.md#r16-liberação-para-relançar-as-três-provas))
- [X] T004 Commit do PR 0 (spec, plano, pesquisa, modelo, contratos, quickstart, tarefas e constituição) na `claude/entrada-por-pedido`. O PR 0, com a constituição 2.1.0, entra em `develop` antes de qualquer PR com código: os PRs 1 a 7 dependem dele para estar em conformidade

**Checkpoint**: a constituição 2.1.0 cobre as entradas, e a documentação está pronta para revisão.

---

## Phase 2: Foundational (PR 1): pedidos de compra importados

**Purpose**: o Central conhece os pedidos com saldo e os itens disponíveis. Todas as histórias dependem disto. Cobre a US5, cenários 1 e 2, e FR-001, FR-002, FR-003 e FR-005.

**⚠️ CRITICAL**: nenhuma história começa antes desta fase.

- [ ] T005 Criar a branch `claude/entradas-1-pedidos` a partir de `claude/entrada-por-pedido`
- [ ] T006 Criar o app `compras` com `compras/__init__.py`, `compras/apps.py` (`name = "compras"`, `verbose_name = "Compras"`), `compras/models.py`, `compras/admin.py` e `compras/migrations/__init__.py`; acrescentar `"compras"` em `INSTALLED_APPS` de `config/settings.py`
- [ ] T007 Acrescentar a `catalogo.Importacao.Tipo` (`catalogo/models.py`) os valores `PEDIDOS_COMPRA = "PEDIDOS_COMPRA", "Pedidos de compra"` e `ENTRADAS = "ENTRADAS", "Entradas do SCPI"`; gerar `catalogo/migrations/0009_importacao_compras.py`, só com os `choices`
- [ ] T008 Criar `PedidoCompra` e `ItemPedidoCompra` em `compras/models.py`, conforme [data-model.md](data-model.md#pedidocompra-pr-1), e gerar `compras/migrations/0001_initial.py`.
  - **`PedidoCompra`**:
    - `exercicio` (smallint), `ano` (smallint, "o ano de origem do `NUMPED`"), `numero` (int);
    - `data` (date), `fornecedor_codigo` (char 20), `fornecedor_nome` (char 200);
    - `ausente_desde` (FK nula → `Importacao`, `PROTECT`), `atualizado_por` (FK → `Importacao`, `PROTECT`);
    - único (`exercicio`, `ano`, `numero`);
    - a propriedade `rotulo` → `00514/26`.
  - **`ItemPedidoCompra`**:
    - `pedido` (FK, `PROTECT`), `item` (smallint), `codigo` (char 30), `unidade` (char 20);
    - `controle` (char 1, `Q`/`T`);
    - `quantidade`, `anulado`, `ja_entrou`, `pedida`, `saldo_scpi` e `preco`, todos decimal(14,4);
    - `ja_entrou_anterior` (decimal(14,4), nulo: "nulo na primeira, que é a base");
    - `ausente_desde` (FK nula → `Importacao`);
    - único (`pedido`, `item`) e índice em (`pedido`, `codigo`).
- [ ] T009 [P] Criar `tests/relacao_pedidos_compra.py`: um gerador de CSV sintético do 07.13 no formato real de [contracts/relatorios-scpi.md](contracts/relatorios-scpi.md#0713-relação-de-pedidos-condição-da-entrega).
  - Formato: as 79 colunas na ordem real, `;`, sem aspas, `\r\n`, com BOM e com `GRUPO`/`GRUPO_1` iguais a `DATPED`.
  - Função: `csv_pedidos(itens: list[dict]) -> bytes`, com padrões para as colunas não usadas e a opção `quebrar_registro=True`, que põe uma quebra de linha dentro de `OBSITEM`.
  - Sem nome de pessoa real.
- [ ] T010 [P] Escrever `tests/test_scpi_leitura_pedidos_compra.py`. Casos:
  - a leitura correta de `Q` e `T`;
  - `QTDFALTA` diferente de `QTD − QTDANU − QTDENT − QTDPEDIDA` num item `Q` → `ErroImportacao`;
  - relatório cortado (contagem de campos);
  - registro quebrado recolado;
  - (`NUMPED`, `ITEM`) repetido;
  - `NUMPED` fora do formato `00000/00`;
  - dois `CODIF` no mesmo pedido;
  - `TPCONTROLE_SALDO` desconhecido;
  - coluna obrigatória faltando;
  - CSV sem itens;
  - quantidade com 4 casas lida sem perda.
- [ ] T011 Implementar em `scpi/leitura.py` a dataclass `LinhaPedidoCompra` (ano, numero, data, fornecedor_codigo, fornecedor_nome, item, codigo, unidade, controle, quantidade, anulado, ja_entrou, pedida, saldo, preco) e `ler_pedidos_compra(conteudo: bytes) -> Leitura`, pura, tudo ou nada, sobre `_tabela`, `decimal_br` e `data_br`, com as colunas e regras do contrato; a T010 passa
- [ ] T012 [P] Escrever a parte de disponibilidade em `tests/test_compras_regras.py`. Casos:
  - `chave_pedido("00514/26") == (2026, 514)`, e o inválido levanta `ValueError`;
  - `rotulo_pedido(2026, 514) == "00514/26"`;
  - `disponibilidade` com cada motivo: `T`, código fora do cadastro, material oculto, pedido de outro exercício, pedido ausente, item ausente, quantidade com 4 casas, saldo zero; e o disponível.
- [ ] T013 Implementar em `compras/regras.py` (puro, sem ORM) `chave_pedido`, `rotulo_pedido` e `disponibilidade(item, *, material_visivel: bool, exercicio_atual: int) -> str | None`. Devolve `None` se o item é disponível ou o motivo em pt-BR ([R4](research.md#r4-item-disponível-para-recebimento)). A T012 passa
- [ ] T014 [P] Escrever `tests/test_compras_importacao.py`, com o CSV da T009 e um `obter_csv` falso. Casos:
  - a primeira importação cria pedidos e itens com `ja_entrou_anterior` nulo;
  - a segunda atualiza e guarda o `ja_entrou_anterior`;
  - o item e o pedido que somem ficam `ausente_desde` e nada é apagado;
  - o que reaparece limpa o `ausente_desde`;
  - marcar ausentes mais de 20% dos itens presentes aborta sem `forcar` e passa com ele;
  - o exercício vem do ano corrente, e o pedido igual noutro exercício é outro `PedidoCompra`;
  - a falha de leitura deixa a `Importacao` `FALHA` sem mudar nada;
  - a trava do tipo ocupada levanta `ImportacaoEmAndamento`.
- [ ] T015 Implementar `compras/importacao.py`, com `gravar(linhas, importacao, *, exercicio, forcar=False) -> Resultado` (`scpi.execucao.Resultado`) e `importar(obter_csv, *, forcar=False) -> Importacao`, sobre `scpi.execucao.executar(Importacao.Tipo.PEDIDOS_COMPRA, ...)`.
  - Na gravação: `bulk_create` e `bulk_update` em blocos, `ausente_desde` e o corte de 20% ([R3](research.md#r3-fonte-dos-pedidos-o-0713-com-saldo-a-entregar)).
  - Os avisos em `Resultado.avisos`.
  - A T014 passa.
- [ ] T016 Implementar `baixar_pedidos_compra() -> bytes` em `scpi/relatorios.py`, conforme [contracts/relatorios-scpi.md](contracts/relatorios-scpi.md).
  - Navegação: Relatórios › 07.13 "Relação de Pedidos (Condição da Entrega)", Analítico, "Apenas com saldo a entregar" e Salvar Arquivo › CSV (Dados), pelo `interceptar_csv`.
  - Os campos são achados pelo rótulo (`JS_CAMPO_ABAIXO_DO_ROTULO` e a legenda do quadro), nunca pelo ID.
  - O relatório termina com "Fechar relatório" e "Sair", e o perfil é `pedidos_compra`.
  - Sem teste de navegação (Princípio V). Num comentário no topo da função: nunca o 01.08.03.
- [ ] T017 Criar o comando `importar_pedidos_compra` (`--arquivo`, `--apagar-arquivo`, `--forcar`) em `compras/management/commands/importar_pedidos_compra.py`, conforme [contracts/comandos.md](contracts/comandos.md#importar_pedidos_compra-pr-1).
  - Lê o arquivo enviado ou chama `baixar_pedidos_compra`, dentro de `relatorios.sessao_compartilhada` quando for chamado pelo `atualizar_catalogo`.
  - A saída lista as contagens.
  - A `FALHA` sai com `CommandError`.
  - A recusa com execução de entradas em andamento depende de `ExecucaoRobo.robo` e entra no PR 4 (T064). Até lá, a trava do tipo é a barreira.
  - Testes em `tests/test_compras_importacao.py`: o comando com `--arquivo` e o `--apagar-arquivo`, mesmo quando falha.
- [ ] T018 Ligar a importação a Automações:
  - `Robo("pedidos_compra", "Pedidos de compra", ...)` com um `RoboPedidosCompraForm(RoboForm)`, que tem o campo `forcar` "Gravar mesmo que muitos itens sumam", em `catalogo/forms.py` (a aba vem do `ABAS`);
  - `"pedidos_compra": "importar_pedidos_compra"` em `COMANDOS_IMPORTACAO` (`scpi/disparo.py`);
  - os rótulos do tipo em `automacoes/historico.py`.

  Testes em `tests/test_automacoes.py`: a aba aparece, o POST com CSV inicia o comando e o histórico mostra "Pedidos de compra".
- [ ] T019 [P] Registrar `PedidoCompra` (com os itens em linha) só para leitura em `compras/admin.py`, com `has_add_permission`, `has_change_permission` e `has_delete_permission` falsos; teste em `tests/test_compras_admin.py`: a lista abre, e adicionar, alterar e apagar são recusados
- [ ] T020 [P] Criar `compras/saude.py`, com `avisos() -> list[str]` (importação de pedidos com falha na última execução ou sem sucesso há mais de um dia útil, como `conciliacao.saude.um_dia_util_depois`), e chamá-la em `catalogo.saude._demais`; testes em `tests/test_compras_saude.py`
- [ ] T021 Atualizar o `CLAUDE.md`: o app `compras` (pedidos de compra, 07.13, nunca o 01.08.03, ausentes e o corte de 20%), o comando `importar_pedidos_compra` e a aba "Pedidos de compra"
- [ ] T022 Portões do PR 1: `uv run pytest`, `ruff check`, `ruff format --check` e `makemigrations --check --dry-run`; pedir ao usuário o [quickstart, passo 2](quickstart.md#2-pedidos-de-compra-do-scpi-real-pr-1-manual) (o Log do pedido sem alteração) e anotar o resultado no PR; commit

**Checkpoint**: os pedidos e os itens disponíveis estão no banco, e a importação é segura.

---

## Phase 3: User Story 1 - Preparar o recebimento de uma nota fiscal (Priority: P1) 🎯 MVP (PR 2)

**Goal**: o Atendimento ou a Gestão abre o pedido, escolhe "total" ou "parcial", informa a NF e a data e grava. O saldo fica reservado, sem nunca reservar em dobro.

**Independent Test**: com um pedido importado de dois itens, preparar um recebimento parcial de um item, outro "total" com outra NF, e conferir as quantidades sugeridas, o saldo livre e as recusas (quickstart, passo 3).

### Tests for User Story 1

- [ ] T023 [US1] Criar a branch `claude/entradas-2-recebimento` a partir de `claude/entradas-1-pedidos`
- [ ] T024 [P] [US1] Criar `tests/compras_cenario.py`, com:
  - `importar_pedido(itens, *, data, fornecedor="19502", exercicio=None) -> PedidoCompra`, que importa pelo CSV da T009 e cria o `Material` de cada código;
  - `preparar(pedido, usuario, itens: dict[int, str], nf="501", data=None, **kw) -> Recebimento`;
  - `usuario_recebedor()`, com `tests/papeis.py`.
- [ ] T025 [P] [US1] Acrescentar a `tests/test_compras_regras.py` os casos de NF, saldo livre e validação:
  - NF: `nf_normalizada("000000000501") == "501"`; vazio, zero, letra e mais de 12 dígitos recusados; `chave_nf("19502", "501") == "19502:501"`;
  - saldo livre no exemplo 100 → 30 → 20, com as reservas por estado da [tabela do data-model](data-model.md#recebimento-pr-2); o lançado reserva até uma importação começada depois do `visivel_desde`;
  - `sugestao_total` = o saldo livre de cada item disponível;
  - `validar_recebimento`: data futura, data antes do pedido, nenhum item, `1.5`, 4 casas, ≤ 0, acima do saldo livre (com o valor na mensagem), item de outro pedido; os erros juntados.
- [ ] T026 [P] [US1] Escrever `tests/test_compras_recebimento.py`, os cenários 1 a 8 da US1, pelo serviço:
  - "total" sugere 50;
  - 51 é recusado e nada é gravado;
  - parcial;
  - a NF repetida com e sem zeros, inclusive com o primeiro recebimento `CANCELADO` depois de uma tentativa `VERIFICAR` (criada direto no banco);
  - as datas;
  - as quantidades;
  - a edição e o cancelamento antes da tentativa (o saldo ajusta, e a NF fica livre no cancelamento);
  - a edição com a versão antiga recusada;
  - o reenvio com o mesmo `envio`, igual (devolve o mesmo) e diferente (recusa "divergente");
  - o pedido travado, ausente ou de outro exercício recusa;
  - a anulação depois do preparado (o reservado fica maior que o saldo do SCPI) deixa o pedido "precisa de conferência", com o saldo livre zero;
  - a edição e o cancelamento depois de uma tentativa `VERIFICAR` recusados.
- [ ] T027 [P] [US1] Acrescentar a `tests/test_compras_recebimento.py` o teste de concorrência do cenário 7 (`pytest.mark.django_db(transaction=True)`, duas threads com conexões próprias, como os testes de travas de `tests/test_lancamento.py`): as duas preparam "total" do mesmo item; uma grava e a outra recebe a recusa com o saldo livre atualizado; a soma reservada ≤ saldo
- [ ] T028 [P] [US1] Escrever `tests/test_compras_acesso.py`:
  - as seis rotas `compras:*` com o usuário sem papel (403), o Atendimento e a Gestão (abrem), o solicitante (recusa pública) e a Segurança do Trabalho (bloqueada pelo middleware);
  - o item "Compras" do menu só para quem tem `receber_compras`;
  - a migration deu `receber_compras` aos grupos Atendimento e Gestão.
- [ ] T029 [P] [US1] Escrever `tests/test_compras_telas.py`:
  - a lista com a busca por número, fornecedor e código;
  - o detalhe com o saldo livre e o motivo de indisponibilidade;
  - o formulário "total" preenchido e o "parcial" vazio;
  - o POST com erro, que mostra o erro no campo e o resumo, e nada é gravado;
  - o POST válido, que redireciona ao detalhe com a mensagem;
  - a edição e o cancelamento em dois passos (sem `confirmado` não cancela);
  - `RC-0001` e os códigos em `.mono`.

### Implementation for User Story 1

- [ ] T030 [US1] Acrescentar `("receber_compras", "Receber compras (preparar, editar e cancelar recebimentos)")` a `Usuario.Meta.permissions` (`contas/models.py`) e `RECEBER = "contas.receber_compras"` a `PERMISSOES_INTERNAS` (`contas/acesso.py`); criar `contas/migrations/0007_receber_compras.py`.
  - A migration é RunPython: cria a permissão, a dá aos grupos `"Atendimento"` e `"Gestão"` (literais) e levanta erro se algum dos dois ficar sem ela.
  - Na volta, `noop`.
  - Depende de `contas/0006_solicitante`.
- [ ] T031 [US1] Criar `Recebimento`, `ItemRecebimento` e `TravaPedido` em `compras/models.py`, conforme [data-model.md](data-model.md#recebimento-pr-2), e gerar `compras/migrations/0002_recebimento.py`.
  - **`Recebimento`**:
    - `envio` (UUID, único), `pedido` (FK, `PROTECT`);
    - `nf` (char 12, "só dígitos, sem os zeros à esquerda, diferente de zero"), `fornecedor_codigo` (char 20);
    - `chave_nf` (char 40, único, nulo);
    - `data_recebimento` (date), `observacao` (char 500, opcional);
    - `status` (choices `PREPARADO`, `ERRO`, `EM_LANCAMENTO`, `VERIFICAR`, `LANCADO`, `CANCELADO`, com os rótulos do data-model);
    - `requisicao_scpi` (char 9), `lancado_em` (datetime nulo), `via` (`ROBO`, `MANUAL` ou vazio), `visivel_desde` (datetime nulo);
    - `mensagem` (char 500), `versao` (int, padrão 1);
    - `preparado_por`/`preparado_em`, `alterado_por`/`alterado_em` e `motivo_cancelamento` (char 300);
    - a propriedade `rotulo` → `RC-0001`;
    - `CheckConstraint`: com `LANCADO`, `requisicao_scpi` preenchido; com `VERIFICAR` ou `EM_LANCAMENTO`, `chave_nf` não nula.
  - **`ItemRecebimento`**: `quantidade` decimal(14,3), `CheckConstraint` `quantidade > 0`, único (`recebimento`, `item`).
  - **`TravaPedido`**: `motivo` com os choices `TELA`, `JA_ENTROU`, `FORA_DO_CENTRAL` e `MARCA_SEM_LANCAMENTO`; FKs nulas para `execucao`, `importacao`, `extracao` (esta acrescentada na T047) e `recebimento`; e `destravada_em`, `destravada_por` e `motivo_destrave`.
- [ ] T032 [US1] Implementar em `compras/regras.py` `nf_normalizada`, `chave_nf`, `reserva_de(status, *, visivel_desde, inicio_ultima_importacao)`, `saldo_livre(saldo_scpi, reservas)`, `sugestao_total` e `validar_recebimento(...) -> list[Erro]`. `Erro` traz `campo` e `item` para a tela. As mensagens são as de [contracts/tela-e-acoes.md](contracts/tela-e-acoes.md#formulário-do-recebimento), e a quantidade é lida por `pedidos.regras.interpretar_quantidade(texto, True)`. A T025 passa
- [ ] T033 [US1] Implementar em `compras/consultas.py`:
  - `ultima_importacao_pedidos()`, a última `PEDIDOS_COMPRA` com `SUCESSO`;
  - `reservado_por_item(pedido)`, uma consulta por tabela;
  - `saldos_do_pedido(pedido) -> list[LinhaSaldo]`, com o item, o material, a disponibilidade, o saldo do SCPI, o reservado e o saldo livre;
  - `travas_abertas(pedido)`;
  - `estado_do_pedido(pedido)`: disponível, travado, precisa de conferência (algum item com o reservado maior que o saldo do SCPI), ausente ou fora do exercício.
- [ ] T034 [US1] Implementar `compras/servicos.py`.
  - **Operações**, cada uma em `transaction.atomic()` com `select_for_update` no `PedidoCompra`, refazendo o saldo livre dentro da trava:
    - `preparar_recebimento(pedido_id, usuario, *, envio, nf, data_recebimento, observacao, itens) -> Resposta`;
    - `editar_recebimento(recebimento_id, usuario, *, versao, ...)`;
    - `cancelar_recebimento(recebimento_id, usuario, *, motivo)`;
    - `travar_pedido(pedido_id, motivo, detalhe, **origem)`;
    - `destravar_pedido(pedido_id, usuario, *, motivo)`, que exige uma importação de pedidos começada depois da trava aberta mais recente ([R20](research.md#r20-travas-do-pedido)).
  - **Recusas**:
    - NF já usada: a recusa amigável vem antes, e o `IntegrityError` da `chave_nf` vira a mesma recusa;
    - reenvio igual ou divergente pelo `envio`;
    - versão antiga;
    - recebimento com tentativa `LANCADA` ou `VERIFICAR`.
  - **Gravação**: a edição recria os itens e soma 1 na `versao`; o cancelamento sem tentativa põe `chave_nf=None`.
  - **Resposta**: o padrão de `pedidos.servicos` (sucesso, objeto e erros).
  - As T026 e T027 passam.
- [ ] T035 [US1] Criar `compras/forms.py`, com `FormularioRecebimento` (NF, data, observação, `envio`, `versao` e um par caixa/quantidade por item disponível, montado a partir de `saldos_do_pedido` e do modo `total`/`parcial`) e `FormularioCancelamento` (motivo, `confirmado`)
- [ ] T036 [US1] Criar `compras/views.py` e `compras/urls.py` (`app_name = "compras"`) com `pedidos`, `pedido`, `receber`, `recebimento`, `editar_recebimento` e `cancelar_recebimento`, nas URLs de [contracts/tela-e-acoes.md](contracts/tela-e-acoes.md#compras-permissão-contasreceber_compras-atendimento-e-gestão).
  - A view só lê e chama `compras.servicos`; a lista tem 50 por página com `_paginacao.html`.
  - Incluir `path("painel/compras/", include("compras.urls"))` em `config/urls.py`.
  - Acrescentar as seis rotas a `REGRAS_POR_ROTA` (`contas/acesso.py`), com `Regra` exigindo `contas.receber_compras` e o motivo "Receber compras é do Atendimento e da Gestão.".
- [ ] T037 [US1] Criar os templates em `compras/templates/compras/`, sobre `base_almoxarifado.html`, com as skills `clean-design`, `ui-ux-pro-max` e `frontend-design`:
  - `pedidos.html`;
  - `pedido.html`, com os itens, o saldo livre, os recebimentos e as travas abertas em texto, e o estado "precisa de conferência" em texto (também na lista);
  - `receber.html`, o formulário com o resumo de erros no topo, o erro no campo e no item, e `inputmode="numeric"` na NF;
  - `recebimento.html`, com o histórico e o cancelamento num `<details>` com `confirmado=1`.
- [ ] T038 [US1] Acrescentar o item "Compras" a `ITENS_MENU` em `interface/navegacao.py`, com um ícone já existente em `interface/templates/interface/_icone.html` (ou o SVG Lucide `package` acrescentado lá) e a rota `compras:pedidos`; a T028 e a T029 passam
- [ ] T039 [US1] Conferir à mão no navegador local (servidor da porta 8000; dizer de qual checkout e branch ele serve), com screenshots:
  - a lista, o pedido, o "total" de 30 itens (SC-002) e o "parcial" com erro;
  - a 375 px, pelo teclado e sem depender de cor.
- [ ] T040 [US1] Atualizar o `CLAUDE.md`: a permissão `receber_compras` na seção de papéis, a área Compras (rotas, saldo livre, reservas, NF única com `chave_nf` nula, `envio` e `versao`) e `compras/servicos.py` como porta única
- [ ] T041 [US1] Portões do PR 2 (`pytest`, `ruff`, `makemigrations --check`, `DEBUG=0 check --deploy --fail-level WARNING`); commit

**Checkpoint**: o recebimento é preparado, editado e cancelado com o saldo certo. Ele ainda não vai ao SCPI.

---

## Phase 4: User Story 2 - Lançar no SCPI sem nunca duplicar (Priority: P1) (PR 3 e PR 4)

**Goal**: a Gestão escolhe os recebimentos da fila e manda simular ou lançar. O robô confere a tela, preenche e salva, e qualquer dúvida depois do clique trava o recebimento em verificação.

**Independent Test**: com o SCPI simulado, lançar recebimentos e provocar cada falha: antes do Salvar, depois do clique, resposta perdida e tela mudada. Conferir os estados e que nada é relançado (quickstart, passo 5; tabela "Garantias" de [robo-entradas.md](contracts/robo-entradas.md#garantias-testadas-com-o-simulado)).

### PR 3: registro oficial das entradas

- [ ] T042 [US2] Criar a branch `claude/entradas-3-extracao` a partir de `claude/entradas-2-recebimento`
- [ ] T043 [P] [US2] Criar `tests/relacao_entradas.py`: um gerador de CSV sintético do relatório de entradas no formato real ([contracts/relatorios-scpi.md](contracts/relatorios-scpi.md#070401-relação-de-requisições-requisições-de-entrada)).
  - Formato: as 65 colunas na ordem real, `;`, sem aspas, `\r\n`, com BOM e com `GRUPO` = `DATAE`.
  - Função: `csv_entradas(requisicoes: list[dict]) -> bytes`, com a opção de registro quebrado em `OBS_CABECALHO`.
- [ ] T044 [P] [US2] Escrever `tests/test_scpi_leitura_entradas.py`. Casos:
  - a leitura com e sem `NUMPED`, `DOCUM` vazio e `SAID=S`;
  - a NF sem zeros;
  - a marca `RC-…` lida;
  - um cabeçalho que varia dentro da requisição;
  - relatório cortado;
  - registro recolado;
  - `REQUI` inválido;
  - `QUAN1` ilegível;
  - coluna obrigatória faltando.
- [ ] T045 [US2] Implementar em `scpi/leitura.py` as dataclasses `EntradaLida` e `ItemEntradaLido` e `ler_entradas(conteudo: bytes) -> Leitura`, pura, tudo ou nada; implementar `recebimento_observado(texto) -> str` e `texto_observacoes(rotulo, observacao)` (`;` → `,`, `Obs.: ` numa linha só) em `compras/regras.py`, com o padrão `central\s+almoxarifado\s+(RC-[0-9]{1,9})\b` (IGNORECASE). A T044 passa, e o teste confere que `conciliacao.regras.lote_observado` não lê `RC-`
- [ ] T046 [P] [US2] Escrever `tests/test_compras_extracao.py`. Casos:
  - a extração com sucesso grava as requisições e o `maior_requisicao`;
  - a falha não grava requisições e deixa o `maior_requisicao` nulo;
  - "Nada a exibir" é sucesso sem requisições;
  - bytes vazios são falha;
  - a impressão igual aponta para a extração que tem os bytes;
  - a impressão igual a uma origem sem bytes guarda os seus;
  - a trava do tipo ocupada;
  - `ANTES`/`DEPOIS` sem execução é recusado pela `CheckConstraint`.
- [ ] T047 [US2] Criar `ExtracaoEntradas`, `RequisicaoEntradaOficial` e `ItemEntradaOficial` em `compras/models.py`, conforme [data-model.md](data-model.md#extracaoentradas-requisicaoentradaoficial-itementradaoficial-pr-3), mais a FK nula `TravaPedido.extracao`; gerar `compras/migrations/0003_extracao_entradas.py`.
  - **`ExtracaoEntradas`**:
    - `importacao` (OneToOne, `PROTECT`), `motivo` (choices `ANTES`, `DEPOIS`, `DIARIA`, `MANUAL`, `ARQUIVO`), `execucao` (FK nula, `PROTECT`);
    - `impressao` (char 64), `arquivo` (`BinaryField` nulo), `mesmo_arquivo_que` (FK self nula), `arquivo_apagado_em` e `maior_requisicao` (char 9 nulo);
    - `requisicoes` (int);
    - `CheckConstraint`: `ANTES`/`DEPOIS` exigem `execucao`.
  - **`RequisicaoEntradaOficial`**:
    - os campos da tabela do data-model;
    - único (`extracao`, `ano`, `numero`);
    - índices em (`fornecedor_codigo`, `nf`), (`pedido_ano`, `pedido_numero`) e `recebimento_observado`.
  - **`ItemEntradaOficial`**: `quantidade` decimal(14,4).
- [ ] T048 [US2] Implementar `compras/extracao.py`, com `extrair(motivo, periodo, obter_csv, *, execucao=None) -> ExtracaoEntradas` sobre `scpi.execucao.executar(Importacao.Tipo.ENTRADAS, ..., ao_criar=...)`.
  - O bruto vai em gzip com `conciliacao.extracao.impressao`, com o `mesmo_arquivo_que`.
  - O período é conferido contra as `DATAE`.
  - `NadaAExibir` vira uma extração sem requisições.
  - A T046 passa.
- [ ] T049 [US2] Implementar `baixar_entradas(de, ate) -> bytes` em `scpi/relatorios.py`, numa função nova (`_relacao_de_requisicoes` não muda).
  - Navegação: Relatórios › Requisições › Relação de Requisições, rádio "Requisições de Entrada", só o período.
  - "Nada a exibir" levanta `NadaAExibir`.
  - O perfil é `entradas_relatorio`.
  - Sem teste de navegação.
- [ ] T050 [US2] Criar o comando `conciliar_entradas` em `compras/management/commands/conciliar_entradas.py` (`--arquivo`, `--desde`/`--ate`, `--diaria`, `--sem-limpeza`), que nesta fase só extrai.
  - Período e motivo conforme [contracts/comandos.md](contracts/comandos.md#conciliar_entradas-pr-3-extrai-pr-5-e-pr-6-conciliam-pr-7-limpa).
  - Recusa com lançamento, extração ou importação de pedidos em andamento.
  - Testes em `tests/test_compras_extracao.py`.
- [ ] T051 [P] [US2] Registrar `ExtracaoEntradas` (sem o bruto na lista) e `RequisicaoEntradaOficial` com os itens, só para leitura, em `compras/admin.py`; o mesmo teste da T019 para as extrações e as requisições, em `tests/test_compras_admin.py`
- [ ] T052 [US2] Atualizar o `CLAUDE.md` (o registro oficial das entradas, `baixar_entradas`, `ler_entradas`, o comando e a marca `RC-`) e passar os portões do PR 3; pedir ao usuário a primeira parte do [quickstart, passo 4](quickstart.md#4-registro-oficial-e-navegação-do-robô-no-scpi-real-prs-3-e-4-manual); commit

### PR 4: o robô de entradas

- [ ] T053 [US2] Criar a branch `claude/entradas-4-robo` a partir de `claude/entradas-3-extracao`
- [ ] T054 [US2] Acrescentar `ExecucaoRobo.robo` (choices `SAIDAS` "Saídas", `ENTRADAS` "Entradas"; `default="SAIDAS"`) em `pedidos/models.py` e gerar `pedidos/migrations/0007_execucao_robo.py`.
  - `em_andamento(agora=None, robo=None)` ganha o filtro opcional `robo`, com o comportamento atual sem ele.
  - Nas saídas, por chamada:
    - em `automacoes/views.py`, a última execução e o andamento da aba Lançamento no SCPI (linhas que hoje fazem `ExecucaoRobo.objects...first()` e o `acompanhar_lancamento`) passam a filtrar `robo=SAIDAS`;
    - as recusas (`automacoes/views.py` em `lancar`/`resolver`, `pedidos/servicos.py` em `resolver_lote`/`corrigir_requisicao`, `pedidos/views/almoxarifado.py` e `scpi/disparo.py`) continuam sem filtro: qualquer robô rodando recusa;
    - os botões da aba das saídas ficam desabilitados com qualquer robô rodando, com a dica "O robô de entradas está lançando." quando é ele;
    - `automacoes/historico.py` mostra o robô.
- [ ] T055 [P] [US2] Escrever `tests/test_entradas_isolamento.py`, com uma execução `ENTRADAS` em andamento e outra concluída:
  - a aba Lançamento no SCPI mostra só a última `SAIDAS` e não acompanha a de entradas;
  - os botões ficam desabilitados com a dica;
  - `iniciar_lancamento` das saídas recusa;
  - o histórico mostra "Entradas";
  - `robos_em_andamento` sai com erro;
  - os testes existentes `tests/test_pagina_lancamentos.py`, `tests/test_lancamento*.py` e `tests/test_historico_automacoes.py` passam sem mudança.
- [ ] T056 [US2] Criar `TentativaEntrada` em `compras/models.py`, conforme [data-model.md](data-model.md#tentativaentrada-pr-4): `execucao` (FK, `PROTECT`), `ordem` (smallint), `recebimento` (FK, `PROTECT`), `versao`, `momento`, `resultado` (choices `LANCADA`, `VERIFICAR`, `ERRO`, `IGNORADA`), `requisicao` (char 9) e `foto` (JSON nulo). Únicos (`execucao`, `ordem`) e (`execucao`, `recebimento`). Gerar `compras/migrations/0004_tentativa_entrada.py`
- [ ] T057 [P] [US2] Criar `tests/scpi_entradas_simulado.py` com `SCPIEntradasSimulado`, que implementa o protocolo `SCPIEntradas`.
  - **Estado**: `pedidos[(ano, numero)] = {item: {codigo, quantidade, anulado, ja_entrou, pedida}}`, `salvas` (as requisições salvas, com a observação, a NF, a data e os itens), `proximo_numero` e `chamadas`.
  - **Falhas**: `falha_antes={"abrir"|"preencher"}`, `salva_e_falha`, `tela_mudou={item: ja_entrou}`, `perde_observacoes`, `nf_errada`, `entrada_manual(...)` (uma requisição à mão, sem marca) e `falhas_relatorio`.
  - **Relatórios**: `relatorio_entradas(de, ate) -> bytes` pela T043, e `relatorio_pedidos() -> bytes` pela T009.
  - **Efeito do Salvar**: `salvar` soma o `ja_entrou` como o SCPI faria.
- [ ] T058 [P] [US2] Acrescentar a `tests/test_compras_regras.py` os casos de `conferir_tela`: a tela igual; o "Já Entrou" maior; o saldo menor; o item ausente na tela; o código diferente no mesmo número; a quantidade acima do saldo da tela; o esperado com um lançado ainda não refletido
- [ ] T059 [US2] Implementar em `compras/regras.py`:
  - as dataclasses `LinhaTela`, `TelaItens`, `EsperadoItem` e `RecebimentoParaLancar` ([contracts/robo-entradas.md](contracts/robo-entradas.md#o-recebimento-que-o-robô-recebe-recebimentoparalancar));
  - `conferir_tela(esperado, tela) -> list[str]`, com as mensagens "O SCPI mudou: item 13, Já Entrou 2 na tela, esperado 1";
  - `foto(rec, tela) -> dict`.

  A T058 passa.
- [ ] T060 [US2] Implementar `compras/robo.py`:
  - `selecionar(rotulos) -> Selecao`, com os aptos e os bloqueados com o motivo: pedido travado, ausente, fora do exercício, com recebimento `EM_LANCAMENTO` ou `VERIFICAR`, ou o recebimento não `PREPARADO`;
  - `para_lancar(recebimento) -> RecebimentoParaLancar`, com o esperado da [R11](research.md#r11-conferência-antes-do-salvar);
  - `periodo_da_execucao(...)`, sobre `conciliacao.regras.periodo`;
  - `extrair_antes(execucao, periodo, baixar)`, com 3 tentativas e `ExtracaoAntesFalhou(ErroImportacao)`;
  - `extrair_depois(...)`, em que a falha só vai ao log;
  - `registrar_tentativa(...)`;
  - `tentativa_lancada(...)`.

  Usar a pausa zerada nos testes, por um fixture autouse como o `extracao_sem_pausa` de `tests/conftest.py`.
- [ ] T061 [US2] Escrever `tests/test_lancamento_entradas.py` com o `SCPIEntradasSimulado`, uma linha por garantia de [contracts/robo-entradas.md](contracts/robo-entradas.md#garantias-testadas-com-o-simulado):
  - sucesso, com o número, `via=ROBO`, `visivel_desde` e a tentativa `LANCADA`;
  - a falha ao abrir e ao preencher (`ERRO`, nada salvo);
  - a tela mudada (`ERRO`, pedido travado `TELA`, nada salvo);
  - `salva_e_falha` (`VERIFICAR`, o simulado tem a requisição, não volta à fila);
  - o processo que morre depois do `_travar`, com uma exceção simulada entre o `_travar` e o `salvar` (`EM_LANCAMENTO` e a tentativa `VERIFICAR`);
  - o recebimento editado depois da seleção (`ignorada`);
  - o banco que recusa o número (`FalhaCritica`, o journal tem o número);
  - a simulação (nenhuma tentativa, estado nem extração);
  - `LANCAMENTO_REAL` desligado;
  - a trava ocupada pelas saídas e pela importação de pedidos;
  - o segundo recebimento do mesmo pedido com o primeiro em `VERIFICAR` (`ignorada`);
  - o aviso de data de outro mês, a cargo do simulado;
  - a extração de antes que falha (nada muda) e a de depois que falha (a execução não piora).
- [ ] T062 [US2] Implementar `scpi/lancamento_entradas.py`: o protocolo `SCPIEntradas`, `JOURNAL = "lancar_entradas_journal.jsonl"`, `_journal`, `_gravar` (com `critico`), `_travar` e `_lancar_um`, mais `lancar(execucao, abrir_scpi, *, recebimentos, extrair) -> Resumo` e `executar_lancamento_entradas(...)`.
  - **Ordem**: a de [contracts/robo-entradas.md](contracts/robo-entradas.md#ordem).
  - **Travas**: `TRAVA_LANCAMENTO` e `trava(trava_importacao(Importacao.Tipo.PEDIDOS_COMPRA))`.
  - **Reaproveitados por importação, sem mudar `scpi/lancamento.py`**: `Resumo`, `RegistroNaExecucao` e `_progresso`/`_salvar_progresso`/`_salvar_resumo`, renomeados para públicos só se for preciso, com alias.
  - **O `_travar`**: confere `status == PREPARADO`, `versao` e o pedido sem trava aberta, com `select_for_update` no recebimento e no pedido, e grava `EM_LANCAMENTO` e a tentativa `VERIFICAR` com a foto na mesma transação.

  A T061 passa.
- [ ] T063 [US2] Implementar `scpi/lancador_entradas.py`: `NavegadorEntradas(Sessao)` com `abrir_pedido`, `preencher`, `salvar`, `depois_de_salvar`, `encerrar_simulacao`, `descartar` e `reiniciar`, mais `navegador()` (perfil `entradas`, `browser.orm_liberado`).
  - **Reaproveita de `scpi/lancador.py`**: `campo`, `mensagem_scpi`, `checar_mensagem`, `salvar_requisicao`, `fechar_janelas_pos_salvar`, `cancelar_formulario` e `pausar`.
  - **Navegação**:
    - o item é achado pelo número no pedido;
    - os itens fora do recebimento são desmarcados;
    - os empenhos são confirmados sem escolher nada;
    - a grade é conferida pelo código e pela ordem, e o código repetido que não dá para distinguir vira `ErroSCPI`;
    - a data do recebimento vai digitada, com a hora sugerida mantida;
    - a NF vai sem zeros;
    - as Observações levam `texto_observacoes`.
  - **Teste de estrutura** em `tests/test_lancador_entradas.py`: implementa o protocolo e não importa o Playwright no topo.
- [ ] T064 [US2] Criar o comando `lancar_entradas` (`--recebimento` obrigatório e repetível, `--dry-run`) em `scpi/management/commands/lancar_entradas.py`.
  - Sem `--dry-run`, exige `LANCAMENTO_REAL` e recusa com `LANCAMENTO_BLOQUEADO` antes de criar a execução.
  - Cria a `ExecucaoRobo(robo=ENTRADAS)`.
  - O real passa `extrair=relatorios.baixar_entradas`.
  - Implementar `iniciar_lancamento_entradas(usuario, *, simulacao, recebimentos)` em `scpi/disparo.py`, que confere de novo `operar_automacoes` e recusa com qualquer robô rodando, com o log em `lancar_entradas.log`.
  - No `importar_pedidos_compra` (T017), antes de começar, recusar com "Um lançamento de entradas está em andamento: a importação de pedidos espera ele terminar." se `ExecucaoRobo.em_andamento(robo="ENTRADAS")` existir. A trava do tipo continua como última barreira.
  - Testes em `tests/test_lancamento_entradas.py`, inclusive a recusa da importação com uma execução de entradas em andamento.
- [ ] T065 [US2] Parametrizar em `pedidos/andamento.py` o substantivo do cartão ("requisição"/"recebimento") com o padrão de hoje, para o `acompanhamento` servir às entradas sem mudar o texto das saídas; teste em `tests/test_andamento.py`, que confere que o texto das saídas é o mesmo
- [ ] T066 [US2] Criar a aba "Entradas no SCPI" (`("entradas", "Entradas no SCPI")` em `ABAS`, depois de `lancamento`) em `automacoes/views.py`, com `contexto_entradas`, as regiões em `REGIOES` (`div#fila-entradas` e o andamento) e o template `automacoes/templates/automacoes/_entradas.html`.
  - **A fila** (`compras.consultas.fila_entradas`): caixa de marcar, "marcar todas", a contagem, os bloqueados sem caixa e com o motivo, e "Simular" e "Lançar no SCPI", este com a confirmação e o cadeado com o lançamento real bloqueado.
  - **O andamento**: `pedidos.andamento` com "recebimento".
  - **Reaproveitar `pedidos/static/pedidos/js/fila-robo.js`** pelos mesmos atributos. Se ele depender de seletores das saídas, generalizá-lo sem mudar o comportamento da aba das saídas.
  - **Rota `automacoes:lancar_entradas`** (POST): valida os `recebimentos` contra a fila de agora e chama `iniciar_lancamento_entradas`; entra em `REGRAS_POR_ROTA` com `operar_automacoes`.
  - **Testes** em `tests/test_automacoes_entradas.py`: a aba, a fila, os bloqueados, as recusas do contrato e a atualização a cada 3 s só com execução em andamento.
- [ ] T067 [US2] Atualizar o `CLAUDE.md`: o robô de entradas (a ordem, a conferência da tela, as duas travas, o journal, o comando e o `--dry-run`), `ExecucaoRobo.robo`, quais chamadas filtram `SAIDAS` e a aba nova
- [ ] T068 [US2] Portões do PR 4; pedir ao usuário a segunda parte do quickstart, passo 4 (o `--dry-run` com os pontos de [R25](research.md#r25-o-que-só-o-scpi-real-confirma)), e registrar os resultados no PR; commit

**Checkpoint**: o robô lança sem nunca duplicar. Um recebimento em verificação ainda só se resolve esperando ou pelo admin, e a fase seguinte resolve isso.

---

## Phase 5: User Story 3 - Resolver um recebimento em verificação (Priority: P1) (PR 5)

**Goal**: o almoxarifado vê as candidatas e liga a certa ("É esta"), ou libera para relançar só com as três provas.

**Independent Test**: com o SCPI simulado que salva e perde a resposta, a liberação é recusada. Com o que falha sem salvar, ela é permitida depois de uma extração e de uma importação posteriores (quickstart, passo 5).

- [ ] T069 [US3] Criar a branch `claude/entradas-5-verificar` a partir de `claude/entradas-4-robo`
- [ ] T070 [P] [US3] Acrescentar a `tests/test_compras_regras.py`:
  - **intervalo**: pela `conciliacao.regras.intervalo` com as tentativas de entrada;
  - **`candidatas`**: "é esta" pela marca e pela NF com o fornecedor fora do intervalo; outro pedido no intervalo não entra; a marca de outro recebimento não entra; a ordem pela semelhança;
  - **`tres_provas`**: sem extração posterior; com candidata numa conferência antiga; o "Já Entrou" diferente da foto; o item ausente na importação posterior; a importação anterior à tentativa; a extração `ARQUIVO`; tudo certo; a lacuna na numeração não conta.
- [ ] T071 [P] [US3] Escrever `tests/test_compras_verificar.py`, os cenários 1 a 5 da US3 com o simulado e as extrações e importações reais, mais:
  - o "É esta" liga como `LANCADO` (`via=ROBO`, o número da candidata, `visivel_desde` igual ao início da extração);
  - liberar devolve o **mesmo** recebimento a `PREPARADO` com `versao + 1` e a NF ainda reservada;
  - cancelar sem as provas é recusado, e com elas, permitido, sem liberar a NF;
  - a recusa com execução em andamento;
  - a requisição já ligada a outro recebimento não serve para "É esta".
- [ ] T072 [US3] Criar `ConferenciaRecebimento` e `CandidataEntrada` em `compras/models.py`, conforme [data-model.md](data-model.md#conferenciarecebimento-e-candidataentrada-pr-5-e-pr-6), com o modelo inteiro, já com os vereditos do PR 6.
  - Tipos: `LANCAMENTO`, `REVISAO` e `VERIFICAR`.
  - Vereditos: `AGUARDANDO`, `COMPROVADO`, `DIVERGENTE`, `NAO_ENCONTRADO`, `DUPLICADO`, `CONFLITO`, `INTERVALO_VAZIO`, `COM_CANDIDATAS` e `SEM_TENTATIVA`.
  - `vinculos` (JSON), `diferencas`, `notas`, `alterado_depois`, `intervalo_de`, `intervalo_ate` e `tentativa`.
  - Único (`recebimento`, `extracao`, `tipo`).

  Gerar `compras/migrations/0005_conferencia.py`.
- [ ] T073 [US3] Implementar em `compras/regras.py` `candidatas(...)` ([R15](research.md#r15-candidatas-de-um-recebimento-em-verificação)) e `tres_provas(...) -> list[str]`, que devolve as faltas com as mensagens de [contracts/tela-e-acoes.md](contracts/tela-e-acoes.md#automações--entradas-no-scpi-permissão-contasoperar_automacoes-gestão) ([R16](research.md#r16-liberação-para-relançar-as-três-provas)); a T070 passa
- [ ] T074 [US3] Implementar `compras/conciliacao.py` com `TRAVA_CONCILIACAO_ENTRADAS`, `piso(execucao)` e `conciliar_verificar(extracao)`.
  - Para cada recebimento `VERIFICAR` ou `EM_LANCAMENTO` coberto, grava a `ConferenciaRecebimento` `VERIFICAR`, mas só se a extração começou depois da tentativa mais recente; sem tentativa, `SEM_TENTATIVA`.
  - Grava também o intervalo e as `CandidataEntrada`.
  - `ARQUIVO` nunca confere.
  - Chamar em `compras.robo.extrair_depois` e no `conciliar_entradas`.
- [ ] T075 [US3] Implementar `compras.consultas.liberacao(recebimento) -> list[str]` sobre `tres_provas`, e `compras.servicos.resolver_recebimento(recebimento_id, usuario, *, acao, requisicao_id=None, conferi=False, motivo="", confirmado=False)`.
  - As ações são `e_esta`, `liberar` e `cancelar`.
  - Corre sob a `TRAVA_LANCAMENTO` (recusa com execução em andamento) e com `select_for_update` no pedido.
  - A T071 passa.
- [ ] T076 [US3] Acrescentar à aba "Entradas no SCPI" a região "Em verificação e com erro" (`compras/templates/compras/_verificacao.html` incluído em `_entradas.html`): por recebimento, a mensagem, as candidatas com "É esta", "Liberar para relançar" (com "Conferi no SCPI") e "Cancelar" em dois passos.
  - Criar a rota `automacoes:resolver_entrada` (POST) em `automacoes/urls.py` e `automacoes/views.py`, que chama `resolver_recebimento` e volta à aba com a mensagem; entra em `REGRAS_POR_ROTA` com `operar_automacoes`.
  - Testes em `tests/test_automacoes_entradas.py`.
- [ ] T077 [US3] Atualizar o `CLAUDE.md` (as candidatas por pedido, as três provas e a foto com a tela); portões do PR 5; commit

**Checkpoint**: nenhum recebimento em verificação é liberado sem prova (SC-006), e o "salvou e perdeu a resposta" se resolve pelo "É esta".

---

## Phase 6: User Story 4 - Conferir cada lançamento com o registro oficial (Priority: P2) (PR 6)

**Goal**: depois de cada execução e a cada conferência, o veredito de cada recebimento lançado: Comprovado, Divergente, Aguardando, Não encontrado, Conflito ou Duplicado.

**Independent Test**: com relatórios sintéticos, conferir cada veredito, inclusive uma requisição editada no SCPI depois do lançamento e uma excluída (quickstart, passo 6).

- [ ] T078 [US4] Criar a branch `claude/entradas-6-vereditos` a partir de `claude/entradas-5-verificar`
- [ ] T079 [P] [US4] Acrescentar a `tests/test_compras_regras.py` os casos de `veredito_entrada`, `comparar_entrada` e `alteracoes_entrada`:
  - cada linha da tabela de [R17](research.md#r17-vereditos-de-um-recebimento-lançado), inclusive o Duplicado pela NF sem a marca;
  - a soma por código com o código repetido;
  - a `DTLAN` e o empenho nunca comparados;
  - a marca ausente como nota;
  - a revisão com as alterações.
- [ ] T080 [P] [US4] Escrever `tests/test_compras_vereditos.py`, os cenários 1 a 6 da US4, com o `conciliar_entradas`, mais:
  - a primeira conclusiva `LANCAMENTO` e as seguintes `REVISAO` com `alterado_depois`;
  - a `AGUARDANDO` provisória;
  - `--arquivo` dá só o primeiro veredito;
  - o recebimento lançado nunca muda (FR-027);
  - a conciliação incompleta sai com erro e a contagem parcial.
- [ ] T081 [US4] Implementar em `compras/regras.py` `veredito_entrada`, `comparar_entrada` (fornecedor, NF, pedido, `DATAE` contra a data do recebimento, soma por código com `norm_u` e `Decimal` exato; nunca a `DTLAN` nem o empenho) e `alteracoes_entrada`; a T079 passa
- [ ] T082 [US4] Implementar em `compras/conciliacao.py`:
  - `conciliar_lancados(extracao)`: os recebimentos `LANCADO` com data no período e lançados antes do início da extração; a primeira conclusiva `LANCAMENTO`, depois `REVISAO`;
  - `conciliar(extracao) = conciliar_verificar + conciliar_lancados`, sob a trava da conciliação de entradas, com cada etapa e cada recebimento isolados, e `ConciliacaoIncompleta` no fim, como `conciliacao.servicos.conciliar`;
  - `compras.consultas.veredito_atual` e `vereditos(filtro, pagina)`;
  - trocar as chamadas da T074 (em `compras.robo.extrair_depois` e no `conciliar_entradas`) por `conciliar`.

  A T080 passa.
- [ ] T083 [US4] Acrescentar à aba a região "Conferência" (`compras/templates/compras/_conferencia.html`):
  - a última extração;
  - "Conferir agora" (`automacoes:conferir_entradas` → `scpi.disparo.iniciar_conciliacao_entradas`, desabilitado com lançamento, extração ou importação de pedidos em andamento);
  - "Atualizar pedidos" (o POST de `automacoes:importar` com `pedidos_compra`);
  - o veredito atual com o filtro `?veredito_entradas=` (Divergências, Aguardando, Comprovados e Todos) e 50 por página, com as diferenças em texto.

  A rota entra em `REGRAS_POR_ROTA`. Testes em `tests/test_automacoes_entradas.py`.
- [ ] T084 [US4] Atualizar o `CLAUDE.md` (os três vínculos, a comparação, os vereditos e o "Conferir agora" das entradas)

**Checkpoint**: todo recebimento lançado tem veredito, e uma edição à mão no SCPI aparece como revisão.

---

## Phase 7: User Story 5 - Pedidos e saldos atualizados, e o que entrou fora do Central (Priority: P2) (PR 6, continuação)

**Goal**: a entrada feita direto no SCPI é ligada ao recebimento aberto pela NF ou vira "Lançada fora do Central", que reserva e trava. O "Já Entrou" não explicado trava. O destravamento exige motivo e uma atualização posterior. Os cenários 1 e 2 já foram entregues no Foundational.

**Independent Test**: importar um relatório de pedidos sintético, depois um de entradas com uma requisição sem marca, e conferir o saldo livre, o aviso e a trava (quickstart, passo 6).

- [ ] T085 [P] [US5] Acrescentar a `tests/test_compras_regras.py` os casos de `ja_entrou_explicado(delta, certos, incertos)`:
  - só os certos;
  - certos e um subconjunto dos incertos;
  - nenhuma combinação;
  - Δ negativo;
  - os incertos vazios.

  E os do saldo livre com a `EntradaForaDoCentral` não refletida, inclusive o código repetido, que reserva em cada item.
- [ ] T086 [P] [US5] Escrever `tests/test_compras_fora_do_central.py`, os cenários 3 a 6 da US5. Casos:
  - a requisição sem marca com a NF de um recebimento `PREPARADO`, `ERRO` ou `VERIFICAR` é ligada (`via=MANUAL`) e sai da fila;
  - a NF desconhecida vira `EntradaForaDoCentral`, reserva e trava `FORA_DO_CENTRAL`;
  - a entrada com saída (`SAID=S`) também;
  - a requisição abaixo do marco é ignorada;
  - a marca de um recebimento não lançado trava `MARCA_SEM_LANCAMENTO`;
  - a importação com o "Já Entrou" não explicado trava `JA_ENTROU` e gera aviso, e a explicada pelos lançamentos do robô não trava;
  - o destravamento sem motivo, ou sem uma importação posterior, é recusado; depois dela é permitido, com o saldo recalculado;
  - a mesma requisição em duas extrações não duplica a `EntradaForaDoCentral`.
- [ ] T087 [US5] Criar `EntradaForaDoCentral` em `compras/models.py`, conforme [data-model.md](data-model.md#entradaforadocentral-pr-6): `pedido` (FK, `PROTECT`), `requisicao` (FK → `RequisicaoEntradaOficial`, `PROTECT`), `ano` e `numero` (únicos juntos), `visivel_desde` (datetime) e `itens` (JSON `[{codigo, quantidade}]`). Gerar `compras/migrations/0006_entrada_fora_do_central.py`
- [ ] T088 [US5] Implementar em `compras/regras.py` `ja_entrou_explicado`. Estender `saldo_livre` e `compras.consultas.reservado_por_item` com as `EntradaForaDoCentral` não refletidas. Implementar `compras.consultas.marco()`, o `maior_requisicao` da primeira `ExtracaoEntradas` bem-sucedida, comparado pela `conciliacao.regras.chave`. A T085 passa
- [ ] T089 [US5] Implementar `conciliar_fora(extracao)` em `compras/conciliacao.py` ([R18](research.md#r18-entrada-por-pedido-feita-fora-do-central-fr-028)) e incluí-la em `conciliar`, depois de `conciliar_verificar` e antes de `conciliar_lancados`.
  - Liga à mão o recebimento aberto com a mesma NF e o mesmo fornecedor, pelo `compras.servicos`, com `select_for_update`.
  - Cria a `EntradaForaDoCentral` com a trava `FORA_DO_CENTRAL`.
  - Trava `MARCA_SEM_LANCAMENTO`.
  - Ignora o que está abaixo do marco e o que já está ligado.
- [ ] T090 [US5] Ligar a explicação do "Já Entrou" à importação em `compras/importacao.py`: por (pedido, código), entre esta importação e a anterior, os certos e os incertos de [R19](research.md#r19-já-entrou-que-o-central-não-explica-fr-029), a trava `JA_ENTROU` por `compras.servicos.travar_pedido` e um aviso em `Resultado.avisos`. A T086 passa
- [ ] T091 [US5] Acrescentar à aba a região "Pedidos travados" (`compras/templates/compras/_travas.html`): as travas abertas com o detalhe, a data da última importação e "Destravar" com o motivo.
  - Criar a rota `automacoes:destravar_pedido` (POST), que chama `compras.servicos.destravar_pedido` e entra em `REGRAS_POR_ROTA` com `operar_automacoes`.
  - Mostrar as travas e as entradas fora do Central também em `compras/templates/compras/pedido.html`.
  - Testes em `tests/test_automacoes_entradas.py`.
- [ ] T092 [US5] Completar `compras/saude.py` com os avisos de [contracts/tela-e-acoes.md](contracts/tela-e-acoes.md#saúde-catalogosaude_demais): os pedidos travados, os recebimentos em verificação ou com erro, a extração de entradas com falha e as entradas fora do Central nos últimos 30 dias. Acrescentar as linhas "Pedidos de compra" e "Entradas" à visão geral de Automações (`automacoes/visao_geral.py` e `catalogo.saude.situacao_do_catalogo`). Testes em `tests/test_compras_saude.py`
- [ ] T093 [US5] Conferir à mão no navegador local as regiões novas da aba (verificação, conferência e travas) e as travas no detalhe do pedido, a 375 px e sem depender de cor, com screenshots
- [ ] T094 [US5] Atualizar o `CLAUDE.md` (entrada fora do Central, o marco, a explicação do "Já Entrou", as travas e o destravamento) e passar os portões do PR 6; commit

**Checkpoint**: toda entrada feita fora do Central trava o pedido (SC-005), e o saldo livre bate com o SCPI menos o reservado (SC-003).

---

## Phase 8: Polish & Cross-Cutting (PR 7): rotina diária e retenção

**Purpose**: a atualização diária sem intervenção e a limpeza de 60 dias. Fecha a FR-021 (diária) e o SC-005 ("até a próxima atualização diária").

- [ ] T095 Criar a branch `claude/entradas-7-diaria` a partir de `claude/entradas-6-vereditos`
- [ ] T096 [P] Escrever `tests/test_compras_diaria.py`. Casos:
  - o `atualizar_catalogo` roda Entradas (`conciliar_entradas --diaria`) e depois Pedidos de compra, na mesma sessão;
  - um passo que falha não desfaz os anteriores nem impede o seguinte;
  - `--carga-inicial` roda os dois;
  - o período diário cobre um recebimento lançado hoje com data de 20 dias atrás e um em verificação aberto com data antiga ([R22](research.md#r22-rotina-diária-e-retenção));
  - a limpeza esvazia o bruto de mais de 60 dias, inclusive o de quem aponta para ele, e apaga as requisições sem conferência que as ligue ou as liste como candidatas;
  - a limpeza com a trava ocupada fica para a próxima;
  - `--sem-limpeza`.
- [ ] T097 Implementar `compras/limpeza.py`, com `limpar(agora=None)`, como `conciliacao.limpeza`: retenção de 60 dias, a trava da extração `ENTRADAS` e a da conciliação de entradas. A `RequisicaoEntradaOficial` ligada a uma `EntradaForaDoCentral` nunca é apagada. Chamá-la no fim do `conciliar_entradas`, salvo com `--sem-limpeza`
- [ ] T098 Acrescentar os passos Entradas e Pedidos de compra, nessa ordem, ao comando `atualizar_catalogo` (`scpi/management/commands/atualizar_catalogo.py`), depois de Requisições e dentro de `relatorios.sessao_compartilhada`, com o resumo dos seis passos. O `deploy/crontab` não muda. A T096 passa
- [ ] T099 Atualizar o `CLAUDE.md`: os seis passos do `atualizar_catalogo` e a limpeza das entradas
- [ ] T100 Marcar a spec como implementada (`specs/014-entrada-por-pedido/spec.md`, status) e este `tasks.md`
- [ ] T101 Portões finais: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run python manage.py makemigrations --check --dry-run` e `DEBUG=0 uv run python manage.py check --deploy --fail-level WARNING`. Anotar no PR o [quickstart, passo 8](quickstart.md#8-primeiro-lançamento-real-depois-do-pr-4-em-produção-manual-a-pedido-do-usuário) como pendência do usuário (L3 e L8). Commit

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (1)** → **Foundational (2)** → **US1 (3)** → **US2 (4)** → **US3 (5)** → **US4 (6)** e **US5 (7)** → **Polish (8)**
- A pilha é linear, como no plano. Cada PR tem como base a branch do anterior.
- A US1 depende do Foundational: pedidos e itens.
- A US2 depende da US1: o recebimento e a `TravaPedido`. A parte do PR 3 (extração) depende só do Foundational, mas fica na pilha depois do PR 2.
- A US3 depende da US2: tentativas e extração de depois.
- A US4 e a US5 dependem da US3: `ConferenciaRecebimento` e `conciliar`. Elas vão juntas no PR 6, e as fases 6 e 7 podem correr em paralelo depois da T078, porque tocam funções diferentes de `compras/conciliacao.py` e `compras/regras.py`. Os arquivos são os mesmos: combinar a ordem dos commits.
- O Polish depende de tudo.

### Dentro de cada fase

- Os testes vêm primeiro e devem falhar; depois a implementação.
- Arquivos tocados por várias tarefas, sempre em sequência:
  - `compras/models.py`: T008, T031, T047, T056, T072 e T087;
  - `compras/regras.py`: T013, T032, T045, T059, T073, T081 e T088;
  - `compras/conciliacao.py`: T074, T082 e T089;
  - `automacoes/views.py`: T054, T066, T076, T083 e T091;
  - `contas/acesso.py`: T030, T036, T066, T076, T083 e T091;
  - `scpi/leitura.py`: T011 e T045;
  - `scpi/relatorios.py`: T016 e T049.
- As migrations seguem a ordem dos PRs: `compras/0001` a `0006`, `catalogo/0009`, `contas/0007` e `pedidos/0007`.

### Parallel Opportunities

- **Foundational**: T009, T010, T012 e T014 juntos; T019 e T020 juntos depois da T008.
- **US1**: de T024 a T029 juntos, porque os testes estão em arquivos diferentes, salvo T026 e T027, que estão no mesmo arquivo e são escritos de uma vez.
- **US2**: T043, T044 e T046 juntos; T055, T057 e T058 juntos depois da T054 e da T056.
- **US3**: T070 e T071 juntos.
- **US4 e US5**: T079, T080, T085 e T086 juntos.

---

## Parallel Example: User Story 1

```bash
# Testes juntos (arquivos diferentes):
Task: "T025 NF, saldo livre e validação em tests/test_compras_regras.py"
Task: "T026 e T027 serviço e concorrência em tests/test_compras_recebimento.py"
Task: "T028 acesso em tests/test_compras_acesso.py"
Task: "T029 telas em tests/test_compras_telas.py"

# Depois, a permissão e os modelos em sequência (T030, T031), e as regras (T032) em paralelo com os
# templates (T037), que só dependem das rotas definidas no contrato.
```

## Parallel Example: User Story 2

```bash
# PR 3, testes e gerador juntos:
Task: "T043 tests/relacao_entradas.py"
Task: "T044 tests/test_scpi_leitura_entradas.py"
Task: "T046 tests/test_compras_extracao.py"

# PR 4, depois do modelo da tentativa:
Task: "T055 tests/test_entradas_isolamento.py"
Task: "T057 tests/scpi_entradas_simulado.py"
Task: "T058 conferir_tela em tests/test_compras_regras.py"
```

---

## Implementation Strategy

### MVP

1. Setup (PR 0) e Foundational (PR 1): os pedidos e o saldo do SCPI no Central.
2. US1 (PR 2): o almoxarifado prepara recebimentos com o saldo livre certo. **Parar e validar**:
   quickstart, passos 2 e 3.

Esse corte já tem valor em produção: o saldo livre e a NF única, sem o robô.

### Incremental

3. US2 (PR 3 e PR 4): o robô, com o `--dry-run` no SCPI real antes do merge.
4. US3 (PR 5): a verificação sem risco. **O lançamento real em produção só a partir daqui** (PR 3 + PR
   4 + PR 5), como no plano.
5. US4 e US5 (PR 6): os vereditos, a entrada fora do Central e o "Já Entrou".
6. Polish (PR 7): a rotina diária e a retenção; depois, o quickstart, passo 8, com o usuário.

---

## Notes

- **Total**: 101 tarefas.

  | Fase | Tarefas |
  |---|---|
  | Setup | 4 |
  | Foundational | 18 |
  | US1 | 19 |
  | US2 | 27 (11 do PR 3 e 16 do PR 4) |
  | US3 | 9 |
  | US4 | 7 |
  | US5 | 10 |
  | Polish | 7 |
- **[P]**: arquivos diferentes, sem dependência de tarefa incompleta.
- **Commits**: um ao fim de cada fase, na branch do PR. Push, PR e merge só a pedido do usuário. O merge
  é de baixo para cima, um de cada vez, nunca pelo botão de stack nem pelo `merge-async`.
