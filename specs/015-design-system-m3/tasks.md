---

description: "Tarefas da troca do design system (Clean → linguagem visual do Material 3)"
---

# Tasks: Troca do design system (Clean → linguagem visual do Material 3)

**Input**: `specs/015-design-system-m3/` (spec.md, plan.md, research.md, data-model.md,
contracts/, quickstart.md)

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: obrigatórios onde há comportamento novo (constituição, Princípio V: toda mudança de
comportamento vem com teste, contra MariaDB, sem navegador). A aparência é conferida pelas capturas
(`scripts/capturar_telas.py`, fora da suíte, research R14) e pela revisão visual do chefe (SC-008).

**Organization**: por história da spec. As histórias saem em quatro entregas (plan.md, "Entregas"),
**cada uma numa branch `claude/*` própria, criada de `develop` atualizada, e num PR próprio**. O PR só
é aberto quando o usuário pedir, e o merge é dele (`CLAUDE.md`, "Git e produção").

| Entrega | Branch sugerida | Fases |
|---|---|---|
| 1. Fundação | `claude/design-fundacao` | 1, 2, 3 (US1) e 4 (US5) |
| 2. Casca e painel | `claude/design-painel` | 5 (US2) |
| 3. Formulários públicos | `claude/design-publico` | 6 (US3) |
| 4. Demais telas internas | `claude/design-telas-internas` | 7 (US4) e 8 (acabamento) |

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivo diferente, sem depender de tarefa incompleta)
- **[Story]**: a história da spec (US1 a US5)
- Os caminhos são relativos à raiz do repositório

## Regras que valem para todas as tarefas

- **O comportamento não muda** (FR-006). Ficam iguais os endereços, os nomes de rota, os textos, os
  campos de formulário, os atributos do HTMX e os `data-*`. As exceções são as de FR-018 (painel) e
  FR-020 (campos públicos).
- **Os nomes de classe atuais ficam** onde o componente existe (FR-007, research R1). Renomear exige
  motivo no PR e o ajuste dos scripts e testes no mesmo PR.
- **Nenhuma dependência nova** (FR-008), **nenhuma migration** (`makemigrations --check` limpo) e
  nenhuma cor fora dos tokens de `contracts/tokens.md`.
- **Scripts no `<head>` com `defer`**; logout por POST num formulário único; estado nunca só por cor;
  códigos em `.mono`.
- **UI**: usar a skill de estilo do repositório com o `docs/DESIGN.md` (a `clean-design` até a fase 4
  terminar, a `design-tonal` depois), mais os plugins `ui-ux-pro-max` e `frontend-design`, como manda
  o `CLAUDE.md`.
- **Portões de todo PR**: `uv run pytest`, `uv run ruff check . && uv run ruff format --check .`,
  `uv run python manage.py makemigrations --check --dry-run`. Só mudam as asserções que a SC-001
  permite.

---

## Phase 1: Setup (entrega 1)

**Purpose**: branch, ferramenta de capturas e as medições de antes, que as SC-004, SC-005 e SC-007
comparam depois.

- [ ] T001 Criar a branch da entrega 1 a partir de `develop` atualizada, com o `git status` limpo: `git switch develop && git pull --ff-only origin develop`, depois `git switch -c claude/design-fundacao`
- [ ] T002 Acrescentar `capturas/` ao `.gitignore` (as imagens e os PDFs das capturas nunca entram no Git)
- [ ] T003 Criar `scripts/capturar_telas.py` (research R14, `contracts/componentes.md` "Telas-chave"): roda com `uv run python`, usa o Playwright já instalado (`chromium.launch()`), recebe `--base` (URL do servidor de desenvolvimento já no ar), `--usuario`/`--senha` de teste (entra pelo formulário de `/painel/entrar/`, porque o django-axes exige o `request`), `--saida` (padrão `capturas/<data-hora>/`) e `--larguras` (padrão 320,375,768,1280,1440). Captura cada tela-chave com `deviceScaleFactor` 1 e o painel também a 1366×650. Avisa toda tela com `document.documentElement.scrollWidth > largura` (SC-002). Com `--recibo <número>`, gera o PDF do detalhe em mídia de impressão (`page.pdf`). Com `--contar-linhas`, conta as linhas da tabela do painel visíveis a 1366×768. Não entra no `pytest` e não abre o SCPI
- [ ] T004 Medir a base, com o servidor de desenvolvimento no ar (conferir antes a porta 8000) e dados de exemplo: pedidos em cada situação, um EPI aguardando autorização, um lote travado, um recebimento de compra em verificação e um recibo pendente. Rodar `scripts/capturar_telas.py` com todas as telas, `--recibo` de um pedido com material acrescentado e de um sem, e `--contar-linhas`. Guardar a pasta em `capturas/base/` e anotar no PR da entrega 1 o número de linhas visíveis (base da SC-004)

---

## Phase 2: Foundational (entrega 1)

**Purpose**: o arquivo de tokens e o teste de contraste, de que todas as histórias dependem.

**⚠️ CRITICAL**: nenhuma história começa antes desta fase.

- [ ] T005 Renomear `interface/static/interface/css/clean.css` para `interface/static/interface/css/fundacao.css` com `git mv` (research R2) e trocar a referência em `interface/templates/interface/base.html`
- [ ] T006 Renomear `tests/test_clean.py` para `tests/test_fundacao.py` com `git mv`, trocar `clean.css` por `fundacao.css` nele, em `tests/test_prefixo.py` (linhas 63, 72 e 92) e em `tests/test_interface.py` (linha 224), e rodar os três
- [ ] T007 Reescrever o bloco `:root` de `interface/static/interface/css/fundacao.css` com os tokens de `contracts/tokens.md`. Os nomes que já existem continuam com valor novo; entram `--superficie-media`, `--superficie-alta`, `--superficie-maxima`, `--contorno`, `--destaque-superficie-texto`, `--secundario-superficie`, `--secundario-superficie-texto`, `--erro-forte`, `--raio-campo` (4px), `--raio-selo` (6px), `--raio-bloco` (28px) e `--altura-campo` (56px no `.ritmo-publico`, a `--altura-controle` de 44px no `.ritmo-almox`). Fica: `--raio-cartao` 16px, `--transicao` 0.15s ease, as três sombras do contrato. O `--anel-foco`, os espaços e as fontes não mudam
- [ ] T008 Atualizar `test_tokens_do_clean` em `tests/test_fundacao.py` (renomear para `test_tokens_da_fundacao`) com os valores novos, mantendo a lista de fontes proibidas (Inter, Roboto, Arial, system-ui)
- [ ] T009 [P] Criar `tests/test_contraste_tokens.py` (research R15): lê o `:root` de `interface/static/interface/css/fundacao.css` pelo `finders` do Django, resolve `var(--…)` e confere, com a fórmula da WCAG 2.1, cada par da tabela "Pares conferidos pelo teste" de `contracts/tokens.md` (4,5:1 no texto; 3:1 em `--contorno` sobre `--fundo` e sobre `--superficie`). Falha também se um token da tabela sumir. Confere que as quatro combinações proibidas do contrato continuam abaixo de 4,5:1, para a lista proibida não ficar desatualizada. Roda sem banco
- [ ] T010 Rodar `uv run pytest tests/test_fundacao.py tests/test_contraste_tokens.py tests/test_prefixo.py tests/test_interface.py`

**Checkpoint**: tokens novos no ar e contraste garantido por teste.

---

## Phase 3: User Story 1 - O sistema inteiro troca de visual sem mudar de comportamento (Priority: P1) 🎯 MVP

**Goal**: todos os componentes comuns no desenho novo, sem tocar nos templates (só `base.html` e
`_icone.html`).

**Independent Test**: suíte verde sem mudar asserção de comportamento. As capturas a 375, 768 e
1280px mostram a nova linguagem, sem elemento quebrado nem rolagem lateral. O recibo impresso sai
idêntico ao de `capturas/base/`.

### Tests for User Story 1

- [ ] T011 [P] [US1] Acrescentar a `tests/test_fundacao.py`: `.selo::before` com `mask-image` e `-webkit-mask-image` em `componentes.css` para `selo-ok`, `selo-aviso`, `selo-erro` e `selo-info`, e nenhum para `selo-neutro`; a exceção `.selo:has(svg)`; o `.aba-selo` sem esconder o próprio `svg` em nenhuma largura; no `@media print`, `.selo::before { display: none }`; `.botao-icone` com largura e altura de `var(--altura-controle)`
- [ ] T012 [P] [US1] Acrescentar a `tests/test_fundacao.py` o teste dos ícones novos: `kebab`, `calendario`, `documento` e `caminhao` desenham SVG com `stroke-width="1.5"` em `interface/templates/interface/_icone.html` (como o `test_icone_conhecido_e_desconhecido`)

### Implementation for User Story 1

- [ ] T013 [P] [US1] Acrescentar a `interface/templates/interface/_icone.html` os ícones `kebab` (ellipsis-vertical), `calendario` (calendar), `documento` (file-text) e `caminhao` (truck), com os traços do Lucide e `stroke-width` 1.5, como os demais
- [ ] T014 [US1] Reestilizar os botões em `interface/static/interface/css/componentes.css` (`contracts/componentes.md`): `.botao` em pílula (`--raio-pilula`); `botao-primario` cheio em `--destaque`; `botao-secundario` com contorno `--contorno` (as cores `botao-destaque`, `botao-perigo` e `botao-ok` como hoje, sobre os tokens novos); `botao-suave` tonal (`--secundario-superficie` e `--secundario-superficie-texto`); `botao-texto` sem fundo, com hover em `--destaque-superficie`; `botao-icone` com área de toque de `var(--altura-controle)` (44px no interno, 48px no público) e o círculo do desenho de 40px. Mantém o `scale(.98)` no clique e o `nowrap` fora do `.botao` (`test_botao_quebra_texto_e_campo_nao_cresce`)
- [ ] T015 [US1] Reestilizar os campos em `interface/static/interface/css/componentes.css`: `.campo-entrada` com borda `--contorno`, `--raio-campo` e `--altura-controle`; foco com borda de 2px em `--destaque`; `.campo-com-erro` com `--erro-forte` na borda, no rótulo e no `.campo-erro` (com ícone). Rótulo fixo acima, como hoje (o rótulo flutuante é só da US3). Mantém `grid-template-columns: minmax(0, 1fr)` no `.campo`
- [ ] T016 [US1] Reestilizar os selos em `interface/static/interface/css/componentes.css` (research R12): `--raio-selo`; os pares de status dos tokens; `::before` de 14px com `mask-image` e `-webkit-mask-image` de SVG do Lucide em `data:` URI, na cor `currentColor`: `check` no `selo-ok`, triângulo de alerta no `selo-aviso`, `alerta` em círculo no `selo-erro`, `info` no `selo-info`, nenhum no `selo-neutro`; `.selo:has(svg)::before { display: none }`; no `.aba-selo`, tirar a regra que esconde o `svg` na tela larga (perto da linha 269), deixando o ícone em toda largura e o texto ao lado na tela larga
- [ ] T017 [US1] Reestilizar avisos, cartões, tabela e paginação em `interface/static/interface/css/componentes.css`: `.aviso` em contêiner de status com `--raio-cartao` e ícone; `.cartao` branco com `--borda` e `--raio-cartao`; `.cartao-sutil` em `--superficie-media`, sem borda; `.cartao-opcao` com o ícone num quadrado de 48px em `--destaque-superficie`; `.tabela` com o cabeçalho em `--texto-secundario` 500, divisórias em `--borda` e hover em `--superficie` (o recheio `--celula-v`/`--celula-h` do ritmo não muda, research R13); paginação nos tokens novos
- [ ] T018 [US1] Reestilizar abas, diálogos, painel flutuante e dropdown em `interface/static/interface/css/componentes.css`: a aba ativa em cor tonal, mantendo a pasta (funde-se ao primeiro cartão); `.dialogo-confirmacao` com `--raio-bloco`; `.painel-flutuante` com `--raio-cartao` e `--sombra-elevada`; opção marcada do `dropdown` em tonal com o `check`
- [ ] T019 [US1] Passar `interface/static/interface/css/layouts.css`, `pedidos/static/pedidos/css/pedidos.css`, `catalogo/static/catalogo/css/catalogo.css` e `contas/static/contas/css/entrar.css` para os tokens novos, sem mudar a composição: trocar as cores fixas que restaram (`#d99a1e`, `#c9891a`, `#dde8ff` e afins) pelo token equivalente e os raios fixos pelos tokens de raio. A composição de cada tela muda só nas US2 a US4
- [ ] T020 [US1] Isolar a impressão do recibo (FR-010, `contracts/tokens.md`): no `@media print` de `interface/static/interface/css/layouts.css`, `.selo::before { display: none }`; no de `pedidos/static/pedidos/css/pedidos.css`, a `.folha-recibo` redefine os tokens que usa com os valores de hoje (`--texto` `#000000`, `--borda` e contornos no cinza de hoje, `--raio-cartao` 12px e a tabela de hoje)
- [ ] T021 [US1] Gerar com `scripts/capturar_telas.py` as capturas de todas as telas-chave e os dois PDFs do recibo. Comparar com `capturas/base/`: o recibo idêntico (SC-007, Q-1.4); nenhuma rolagem lateral (SC-002); selos com o ícone do tom e o "N no pedido" sem ícone duplicado (Q-1.3). Corrigir o que quebrou
- [ ] T022 [US1] Rodar os portões e conferir que só mudaram as asserções de nome de arquivo e de valor de token (SC-001)

**Checkpoint**: o sistema inteiro no visual novo, com o mesmo comportamento. A US5 sai no mesmo PR.

---

## Phase 4: User Story 5 - Referência de estilo para as telas futuras (Priority: P2, entra no PR da entrega 1)

**Goal**: constituição, `DESIGN.md`, skill e `CLAUDE.md` coerentes com a fundação, no mesmo PR, como
manda a governança (FR-027).

**Independent Test**: `grep` não acha o Clean como estilo vigente nos documentos ativos (Q-1.5). Uma
sessão nova carrega a `design-tonal` e encontra os tokens e o vocabulário do `DESIGN.md` (Q-1.6).

- [ ] T023 [US5] Emendar `.specify/memory/constitution.md`. O Princípio VI passa a dizer "A interface segue o design system do projeto (`docs/DESIGN.md`)", e as outras linhas dele não mudam. **Version** vira 2.2.0 e **Last Amended** a data do PR. O relatório de impacto do topo do arquivo cita a spec 015 e o motivo: redefinição compatível, porque nenhuma garantia do princípio cai e a referência fica mais geral (FR-027, research R16)
- [ ] T024 [US5] Reescrever `docs/DESIGN.md` com:
  - os tokens de `contracts/tokens.md`;
  - as combinações de contraste permitidas e proibidas;
  - o vocabulário de `contracts/componentes.md` (o que fica, o que muda, o que entra), com cada componente novo marcado com a entrega em que passa a existir ("indicador: entrega 2", "campo flutuante: entrega 3");
  - a regra do ícone dos selos;
  - movimento, impressão e as regras que continuam;
  - o passo a passo de "Tela nova".
- [ ] T025 [US5] Criar `.claude/skills/design-tonal/SKILL.md` (frontmatter com `name: design-tonal` e uma `description` com os gatilhos de UI do projeto) e `.claude/skills/design-tonal/DESIGN.md`, no lugar da `clean-design`. Remover `.claude/skills/clean-design/` com `git rm -r`, que fica no histórico do Git
- [ ] T026 [US5] Atualizar `CLAUDE.md`:
  - o parágrafo do `interface`: Tonal no lugar de Clean, `fundacao.css` no lugar de `clean.css`, e a skill `.claude/skills/design-tonal/`;
  - a convenção das três skills: `design-tonal` no lugar de `clean-design`.
- [ ] T027 [US5] Rodar `grep -rn -i "clean" interface/ docs/DESIGN.md CLAUDE.md .specify/memory/constitution.md .claude/skills/` e corrigir toda referência ao Clean como estilo vigente. As specs e os planos antigos em `docs/superpowers/` são histórico e não mudam
- [ ] T028 [US5] Preparar o PR da entrega 1 para `develop`, sem abrir antes do pedido do usuário. O texto leva:
  - o resumo;
  - a linha de base da SC-004;
  - a comparação do recibo;
  - o caminho das capturas, para a revisão visual (SC-008);
  - a lista de asserções de teste que mudaram e o motivo de cada uma.

**Checkpoint**: entrega 1 pronta para revisão e deploy.

---

## Phase 5: User Story 2 - Painel do almoxarifado no novo desenho (Priority: P1)

**Goal**: o menu estreito com contadores, o painel com indicadores, chips, tabela, ⋮ e botão
flutuante, e os quatro comportamentos novos da decisão Q1 (`contracts/painel.md`).

**Independent Test**: com dados de teste, os números, os filtros e os destinos são os mesmos de antes;
os comportamentos de FR-018a a FR-018d passam nos testes novos; Q-2.1 a Q-2.8 do quickstart passam.

- [ ] T029 [US2] Com a entrega 1 integrada em `develop`, criar `claude/design-painel` a partir de `develop` atualizada (como em T001)

### Tests for User Story 2

> Escrever primeiro e ver falhar.

- [ ] T030 [P] [US2] Criar `tests/test_painel_indicadores.py`:
  - `regras.texto_envio_mais_antigo` (puro): "enviado hoje", "enviado ontem", "há N dias" e a virada de mês;
  - o "mais antigo" ignora os aguardando autorização e os recusados, e some com zero pedido;
  - "+N aguardando autorização" conta só os `AGUARDANDO`, leva a `?autorizacao=aguardando#pedidos` e some com zero;
  - o cartão da saúde soma erros e avisos e leva a `#saude`, e a seção tem `id="saude"`;
  - o cartão do robô (com `operar_automacoes`) leva a `automacoes:pagina?aba=lancamento` e mantém o "N para conferir" de hoje, com o link para as travas;
  - os textos com zero continuam os de hoje.
- [ ] T031 [P] [US2] Criar `tests/test_contadores_menu.py` (research R7, `data-model.md`):
  - **quem vê**: o contador do Painel e o de Automações aparecem só para quem abre cada item, e nenhum aparece com zero;
  - **Painel**: o contador é igual ao cartão "Aguardando atendimento";
  - **Automações**: soma os lotes com linha `VERIFICAR` ou `ERRO` e os recebimentos de compra `VERIFICAR` ou `ERRO`;
  - **em lançamento**: o `EM_LANCAMENTO` só entra sem execução do robô daquele tipo em andamento. A execução fica em andamento com uma `ExecucaoRobo` criada há menos de 60 s, sem fim e com o `robo` certo, `SAIDAS` ou `ENTRADAS`;
  - **lote com dois estados**: o lote com linhas `VERIFICAR` e `EM_LANCAMENTO` conta uma vez;
  - **cartão do robô**: continua contando o `EM_LANCAMENTO` sempre;
  - **quem só recebe compras** (`usuario_com` só com `contas.receber_compras`): não vê contador de Painel nem de Automações;
  - **sem contagem dupla**: o painel não conta duas vezes (`django_assert_num_queries` comparando a página com e sem os contadores na memória).
- [ ] T032 [P] [US2] Criar `tests/test_painel_menu_acoes.py`:
  - pedido aguardando: só "Abrir pedido";
  - atendido com o lote `PENDENTE`: "Abrir pedido", "Imprimir recibo" (com `?imprimir=1`) e "Editar atendimento";
  - atendido e lançado: sem "Editar atendimento";
  - EPI aguardando autorização: só "Abrir pedido";
  - saída avulsa: "Editar saída";
  - nas duas últimas linhas da página, o `details` tem `menu-acoes-acima`;
  - o `summary` tem o `aria-label` "Ações do pedido <número>".
- [ ] T033 [P] [US2] Criar `tests/test_painel_filtros.py`:
  - a situação é um grupo de rádios `name="situacao"`, com a legenda "Situação", e o rádio marcado é o da URL;
  - cada valor de `situacao` devolve o mesmo resultado de hoje, com e sem `HX-Request`;
  - com `?origem=<valor>`, o rótulo do chip mostra o valor;
  - com `?situacao=aguardando` e com `?recibo=pendente`, o indicador correspondente sai com `aria-current="true"`;
  - a busca `q` está fora do `<form id="filtros-painel">` e tem `form="filtros-painel"`;
  - o `hx-trigger` contém `input delay:400ms from:#id_q`;
  - o primeiro `button[type=submit]` do formulário é o "Filtrar", sem `name`;
  - o `<form>` do "Lançar no SCPI" não fica dentro do `<form id="filtros-painel">`.
- [ ] T034 [P] [US2] Criar `tests/test_imprimir_pela_lista.py`:
  - `GET pedidos:detalhe?imprimir=1` marca o botão `[data-imprimir]` com `data-imprimir-ao-abrir` só com atendimento e `recibo_impresso_em` nulo;
  - o campo `voltar` do diálogo sai sem o parâmetro `imprimir`;
  - abrir a página não grava nada (contagem de `Atendimento.recibo_impresso_em` nula igual antes e depois);
  - sem atendimento, o parâmetro é ignorado.
- [ ] T035 [US2] Reescrever as asserções de markup de `tests/test_painel.py` (linhas 223-330: `cartao atalhos`, `atalho-numero`, "Atalhos", `filtros-recolhiveis`, `data-fechar-filtros`) e de `tests/test_epis_painel.py` (linha 89: `atalho-numero`) para a estrutura nova: `indicador-numero`, a ordem dos cartões e os mesmos links. Conferir **os mesmos números e os mesmos destinos** de antes (SC-001) e registrar no PR cada asserção reescrita

### Implementation for User Story 2

- [ ] T036 [P] [US2] Implementar `texto_envio_mais_antigo(data_envio: date, hoje: date) -> str` em `pedidos/regras.py`. É pura e conta dias de calendário: 0 → "enviado hoje", 1 → "enviado ontem", N → "há N dias"
- [ ] T037 [P] [US2] Em `pedidos/consultas.py`:
  - acrescentar `envio_mais_antigo_aguardando()`: `Min("criado_em")` sobre `filtrar_situacao(Pedido.objects.all(), "aguardando")`, ou `None`;
  - acrescentar `contar_aguardando_autorizacao()`: `Pedido` com `autorizacao__situacao=AGUARDANDO`;
  - dar a `contar_lotes_travados` o parâmetro `com_em_lancamento: bool = True`, que com `False` conta só os lotes distintos com linha `VERIFICAR` ou `ERRO`. O padrão mantém o comportamento de hoje.
- [ ] T038 [P] [US2] Acrescentar `contar_recebimentos_travados(com_em_lancamento: bool) -> int` em `compras/consultas.py`. Conta os `Recebimento` em `VERIFICAR` ou `ERRO`, e também os `EM_LANCAMENTO` com `com_em_lancamento=True`
- [ ] T039 [US2] Em `pedidos/consultas.py`, trocar o widget de `FiltrosPainel.situacao` por `forms.RadioSelect`, com as mesmas opções e o valor vazio "Todas" (`contracts/painel.md`)
- [ ] T040 [US2] Implementar `contadores(request)` em `interface/navegacao.py` (research R7), que guarda as parcelas na própria requisição e calcula cada uma só quando é lida:
  - pedidos aguardando;
  - requisições travadas como hoje (`contar_lotes_travados()`);
  - requisições a conferir: `contar_lotes_travados(com_em_lancamento=False)` mais os lotes `EM_LANCAMENTO` quando `ExecucaoRobo.em_andamento(agora, robo=SAIDAS)` está vazio, sem contar duas vezes o lote que já entrou;
  - recebimentos a conferir: a mesma regra com `ENTRADAS`. A conferência da execução só roda se houver algo `EM_LANCAMENTO`.

  As importações de `pedidos.consultas` e `compras.consultas` ficam dentro da função. O context processor `menu` passa a dar a cada item o `contador`: Painel = aguardando; Automações = requisições a conferir + recebimentos a conferir. Só para quem abre o item, e nada com zero. O `ItemMenu` de Compras troca o ícone `caixa` por `caminhao`.
- [ ] T041 [US2] Reescrever `interface/templates/interface/_menu.html` e a casca em `interface/static/interface/css/layouts.css` (research R6):
  - **acima de 1286px**: menu estreito de 88px, com ícone sobre rótulo e o item atual na pílula tonal (`aria-current="page"`). O `app-menu-contador` vai depois do ícone, com o número `aria-hidden` e o texto para o leitor de tela (", 2 para atender"; ", 1 trava para conferir" em Automações). A lista de destinos tem `overflow-y: auto`, e a marca (só o ícone) e a conta ficam presas;
  - **conta**: a `app-conta-avatar` com as iniciais e, em `title` e em texto escondido, o nome e a matrícula; o "Sair" só com ícone e `aria-label`, no formulário POST único de hoje;
  - **até 1286px**: o cabeçalho com o botão de menu de hoje, sem mudança no `shell.js`.

  Mantém o markup que o `test_menu_com_icone_e_botao_acessivel` confere.
- [ ] T042 [US2] Em `pedidos/views/almoxarifado.py`, fazer o `painel` montar o contexto de `contracts/painel.md`: `pedidos_aguardando` e `lancamento_travados` vindos de `interface.navegacao.contadores(request)`, mais `envio_mais_antigo`, `aguardando_autorizacao`, `saude_erros` e `saude_avisos`. O trecho do HTMX não ganha chave nova
- [ ] T043 [US2] Reescrever `pedidos/templates/pedidos/painel.html` na ordem de `contracts/painel.md`:
  - o cabeçalho com a busca `q` em pílula, fora do formulário e com `form="filtros-painel"`;
  - a `section.indicadores`, com os quatro cartões, cada um com os seus formulários próprios. O do robô mantém o formulário, o bloqueio, a dica e o cadeado de hoje;
  - o `<form id="filtros-painel">` com:
    - o `hx-trigger="change, input delay:400ms, input delay:400ms from:#id_q, submit"` e o resto dos atributos HTMX de hoje;
    - o "Filtrar" como primeiro botão de envio, sem `name`;
    - o `fieldset.chips` dos rádios de situação e o campo de material;
    - os `details.chip-menu data-menu` de Origem, SCPI, Recibo, Autorização e Período, com os campos do `FiltrosPainel` dentro e o rótulo com o valor escolhido;
    - o "Limpar filtros";
  - o `#lista-pedidos`;
  - a `section#saude`;
  - o `a.fab.nao-imprimir` para `pedidos:avulsa`.
- [ ] T044 [US2] Acrescentar a `interface/static/interface/css/componentes.css` os componentes da entrega 2 (`contracts/componentes.md`):
  - `indicadores`, `indicador`, `indicador-critico`, `indicador-rotulo`, `indicador-numero`, `indicador-nota`, `indicador-nota-alerta`, `indicador-acao` e o link que cobre o cartão, com as ações acima dele; contorno de destaque com `aria-current="true"`;
  - `chips`, `chip`, `chip-entrada`, `chip-texto` (com `.chip-entrada:checked + .chip-texto`), com 32px de desenho e 44px de área de toque;
  - `chip-menu` e `chip-menu-painel`;
  - `menu-acoes`, `menu-acoes-acima` e `menu-acoes-lista`, com `z-index` acima do `a::after` da linha;
  - `fab`, com recheio embaixo da página para não cobrir a paginação;
  - `app-menu-contador` e `app-conta-avatar`.
- [ ] T045 [US2] Reescrever `pedidos/templates/pedidos/_painel_lista.html`:
  - as colunas Situação e SCPI separadas, com os selos de sempre;
  - "Recibo não impresso", com o ícone da impressora, quando `a.recibo_impresso_em` é nulo;
  - o `details.menu-acoes data-menu` com os itens de `data-model.md` e `menu-acoes-acima` quando `forloop.revcounter <= 2`;
  - o link do Nº continua cobrindo a linha;
  - a container query de hoje faz a linha virar cartão, com o ⋮ no canto superior direito.
- [ ] T046 [P] [US2] Criar `interface/static/interface/js/menus.js` para todo `details[data-menu]`: abrir um fecha os outros, o Esc fecha e devolve o foco ao `summary`, o clique fora fecha. Carregar em `interface/templates/interface/base.html`, no `<head>` com `defer`
- [ ] T047 [US2] Ajustar `interface/static/interface/js/filtros.js`:
  - no formulário do painel (sem o `data-filtros-alternar`), não recolher nada;
  - a cada `change` do formulário, atualizar os rótulos dos `chip-menu` ("Origem: Limpeza") e o `aria-current` dos indicadores pelos valores do formulário;
  - no histórico de Automações, manter o comportamento de hoje.
- [ ] T048 [US2] Ajustar a impressão pela lista:
  - **view** (`pedidos/views/almoxarifado.py`): no detalhe, `voltar_sem_imprimir` (o `get_full_path` sem o parâmetro `imprimir`) e o sinal de imprimir ao abrir, só com atendimento e `recibo_impresso_em` nulo;
  - **template** (`pedidos/templates/pedidos/detalhe.html`): o campo `voltar` usa o valor novo, e o botão ganha `data-imprimir-ao-abrir`;
  - **script** (`pedidos/static/pedidos/js/pedidos.js`): no `load`, aciona uma vez o botão com `data-imprimir-ao-abrir` e roda `history.replaceState(history.state, "", url_sem_imprimir)`.
- [ ] T049 [US2] Atualizar `CLAUDE.md` (menu estreito, contadores e a regra do `EM_LANCAMENTO`, chips de rádio, `filtros.js` no painel, `menus.js` e `?imprimir=1`) e tirar a marca "entrega 2" dos componentes que passaram a existir em `docs/DESIGN.md`
- [ ] T050 [US2] Gerar as capturas (o painel a 1366×650, com o ⋮ aberto numa linha do meio e na última) e conferir Q-2.1 a Q-2.8. Em especial: os 7 destinos visíveis ou rolando; os chips mantendo o filtro; o "Lançar no SCPI" lançando; o recibo não impresso duas vezes; o ⋮ inteiro na última linha a 375px. Contar as linhas visíveis a 1366×768 com `--contar-linhas` (≥ a base, SC-004)
- [ ] T051 [US2] Rodar os portões e preparar o PR da entrega 2 (só abrir com o pedido do usuário), com a lista das asserções reescritas (T035)

**Checkpoint**: casca e painel novos, com os quatro comportamentos testados.

---

## Phase 6: User Story 3 - Formulários públicos no novo desenho (Priority: P1)

**Goal**: as telas públicas no desenho novo, com o rótulo flutuante da decisão Q2
(`contracts/campos-publicos.md`), e o mesmo fluxo de pedir.

**Independent Test**: um pedido de 3 materiais no celular com os mesmos toques e tempo igual ou menor
(SC-005), e o pedido gravado idêntico; os testes dos formulários públicos passam; Q-3.1 a Q-3.5.

- [ ] T052 [US3] Com a entrega 2 integrada, criar `claude/design-publico` a partir de `develop` atualizada
- [ ] T053 [US3] Medir a base da SC-005 antes do deploy da entrega 3: 3 funcionários, um pedido de 3 materiais no celular, no sistema de hoje. Anotar no PR o tempo e o número de toques de cada um

### Tests for User Story 3

- [ ] T054 [P] [US3] Criar `tests/test_campos_flutuantes.py` (`contracts/campos-publicos.md`, "Testes"):
  - em `_formulario.html` (nome, destino, ocorrência), `consulta.html`, `entrar.html` e `trocar_senha.html`: o `campo-flutuante`, o `placeholder=" "` e o `campo-dica` com o texto do antigo placeholder. No destino, o `exemplo_destino` de limpeza, viaturas, oficina e EPIs, e o padrão "Setor, posto ou placa" no AB;
  - sem erro, o `aria-describedby` com o id da dica; com erro, `aria-invalid="true"`, o `campo-erro`, nenhum `campo-dica` e o `aria-describedby` só com o id do erro;
  - os widgets de `FormularioEntrada` e `FormularioTrocaSenha` com `placeholder=" "`;
  - o `FormularioEntradaAdmin` sem mudança;
  - a busca de materiais com o `placeholder` do `fluxo.exemplo_busca`.
- [ ] T055 [US3] Ajustar as asserções dos testes públicos que conferem o exemplo do destino no `placeholder` (`tests/test_formularios_publicos.py`, `tests/test_viaturas_formulario.py`, `tests/test_oficina_formulario.py`, `tests/test_epis_formulario.py`, `tests/test_solicitante_formulario.py`) para o texto de apoio, sem mudar o restante (SC-001)

### Implementation for User Story 3

- [ ] T056 [US3] Acrescentar o `campo-flutuante` a `interface/static/interface/css/componentes.css`:
  - **por padrão**, o rótulo fica na borda, a reserva sem `:has()`;
  - **com `:has()`**, o rótulo desce para dentro da caixa só com `.campo-entrada:placeholder-shown:not(:focus):not(:autofill):not(:-webkit-autofill)`;
  - **estados**: os de `contracts/campos-publicos.md`, com `--altura-campo` de 56px.

  Reestilizar o layout público (`publico-topo`, `publico-cabecalho`, `publico-rodape`) em `interface/static/interface/css/layouts.css`.
- [ ] T057 [US3] Converter os campos de `pedidos/templates/pedidos/_formulario.html` (nome completo, destino ou número da viatura, nº da ocorrência) para o markup de `contracts/campos-publicos.md`:
  - **destino**: o `fluxo.exemplo_destino` sai do `placeholder` e vai para o `p.campo-dica#destino-dica`;
  - **erro**: a dica só aparece sem erro, e o `aria-describedby` aponta para a dica ou para o erro;
  - **observações**: só a caixa nova, sem rótulo flutuante;
  - **"Limpar"**: continua dentro do campo.

  Mantém os `data-*`, os nomes de campo e o `pedidos.js`.
- [ ] T058 [P] [US3] Reestilizar `pedidos/templates/pedidos/inicio.html` e as regras em `pedidos/static/pedidos/css/pedidos.css`: os cartões de opção (ícone em `--destaque-superficie`), a `consulta-chamada` em bloco tonal e o formulário geral à parte, com o separador. Os textos e a ordem não mudam
- [ ] T059 [US3] Reestilizar o pedido em `pedidos/static/pedidos/css/pedidos.css`, mexendo nos templates (`_materiais.html`, `_resultados.html`, `_carrinho.html`, `_resumo_pedido.html`) só se necessário e sem mudar classes nem `data-*`:
  - passos em blocos tonais com `--raio-bloco` e o número em círculo;
  - busca em pílula;
  - painel de resultados com o comportamento de hoje (5 linhas, no fluxo da página);
  - linha aberta com a barra azul;
  - quantidade − / + em pílula;
  - "Seu pedido" em cartão tonal preso ao rolar a partir de 960px;
  - barra e gaveta (`dialog`) com cantos de cima de `--raio-bloco`.
- [ ] T060 [P] [US3] Reestilizar `pedidos/templates/pedidos/_sucesso.html` com as regras em `pedidos/static/pedidos/css/pedidos.css`: o ✓ em contêiner ok, o número em `.mono` grande, o cartão com o destino e os materiais, o aviso em `aviso-info` e as mesmas ações. Os `data-lembrar-*` não mudam
- [ ] T061 [P] [US3] Converter os campos de `pedidos/templates/pedidos/consulta.html` (número e primeiro nome) para o `campo-flutuante` e reestilizar a tela
- [ ] T062 [US3] Pôr `placeholder=" "` nos widgets de `FormularioEntrada` e `FormularioTrocaSenha` em `contas/forms.py`, sem tocar no `FormularioEntradaAdmin`. Converter `contas/templates/contas/entrar.html` (layout próprio, com `contas/static/contas/css/entrar.css`) e `contas/templates/contas/trocar_senha.html` para o `campo-flutuante`, e reestilizar `contas/templates/contas/bloqueado.html`. O login é um só, e a equipe continua entrando por ele (Q-3.5)
- [ ] T063 [P] [US3] Reestilizar `pedidos/templates/pedidos/meus_pedidos.html`, `pedidos/templates/pedidos/meu_pedido.html`, `pedidos/templates/pedidos/_folha.html` e `interface/templates/interface/acesso_negado_publico.html` com os componentes da fundação
- [ ] T064 [US3] Atualizar `CLAUDE.md`: o `Fluxo.exemplo_destino` passa de "o placeholder do destino" para "o texto de apoio do destino" (parágrafo da spec 007); o campo flutuante entra no parágrafo dos formulários públicos. Tirar a marca "entrega 3" dos componentes em `docs/DESIGN.md`
- [ ] T065 [US3] Gerar as capturas das telas públicas (também o login com preenchimento automático e a gaveta aberta no celular) e conferir Q-3.1 a Q-3.5. Repetir a medição da SC-005 com os mesmos 3 funcionários. Rodar os portões e preparar o PR da entrega 3 (só abrir com o pedido do usuário)

**Checkpoint**: telas públicas novas, com o mesmo fluxo de pedir.

---

## Phase 7: User Story 4 - Demais telas internas no novo desenho (Priority: P2)

**Goal**: as telas internas restantes compostas com os componentes da fundação e o menu novo.

**Independent Test**: cada tela a 375, 768 e 1280px só com o vocabulário documentado, sem rolagem
lateral, com os testes dela verdes; Q-4.1 a Q-4.6.

- [ ] T066 [US4] Com a entrega 3 integrada, criar `claude/design-telas-internas` a partir de `develop` atualizada

### Implementation for User Story 4

- [ ] T067 [US4] Reestilizar o detalhe, o atendimento e a edição (`pedidos/templates/pedidos/detalhe.html`, `_campos_saida.html`, `_entrega_formas.html`, `_adicionado.html`, `_alteracoes.html`, `_edicao_faixa.html`, `_edicao_aviso.html`, `_itens_pedidos.html`, `_nao_gravadas.html`, `_saldo_antigos.html`, `_recibo.html` e `_recibo_item.html` na tela) com as regras em `pedidos/static/pedidos/css/pedidos.css`. Ficam sem mudança os `data-*` da confirmação das quantidades, da troca, do acréscimo e do "Entregar tudo", e a impressão (T020)
- [ ] T068 [P] [US4] Reestilizar `pedidos/templates/pedidos/avulsa.html`
- [ ] T069 [US4] Reestilizar Automações: `automacoes/templates/automacoes/pagina.html`, `_historico.html`, `_filtros_historico.html`, `catalogo/templates/catalogo/_situacao.html`, `_robo.html`, `_saude.html`, `_selo_fonte.html`, `pedidos/templates/pedidos/_lancamentos.html`, `_andamento.html`, `_andamento_falha.html`, `_andamento_selo.html` e `conciliacao/templates/conciliacao/*.html`. Mantém as regiões recarregadas pelo `HX-Target`, a pasta das abas e o recolhimento do `filtros.js` no histórico
- [ ] T070 [US4] Reestilizar Compras e a aba Entradas (`compras/templates/compras/*.html`). Dar regra às cinco classes sem CSS (`filtros-veredito`, `conferir-cabecalho`, `lista-travas`, `acoes-trava`, `cancelar-entrada`) em `pedidos/static/pedidos/css/pedidos.css`, igual à das equivalentes das saídas (`conciliacao-filtros` e afins), ou trocá-las por essas classes, sem mudar comportamento (FR-029). `tests/test_compras_telas.py` continua verde
- [ ] T071 [P] [US4] Reestilizar a Curva ABC e a página Formulários (`catalogo/templates/catalogo/curva.html`, `_curva_*.html`, `formularios*.html`, `_formularios_*.html`, `_centros_acoes.html`, `_material_estado.html`, `_material_info.html`, `_volta.html`) com as regras em `catalogo/static/catalogo/css/catalogo.css`
- [ ] T072 [P] [US4] Reestilizar a Segurança do Trabalho (`pedidos/templates/pedidos/autorizacoes.html`, `autorizacao.html`, `_autorizacao.html`), conferindo que o menu dela mostra só Autorizações
- [ ] T073 [P] [US4] Reestilizar `interface/templates/interface/acesso_negado.html` e `interface/templates/403.html`
- [ ] T074 [US4] Gerar as capturas das telas internas e conferir Q-4.1 a Q-4.6. Rodar os portões

**Checkpoint**: todas as telas no desenho novo.

---

## Phase 8: Polish & Cross-Cutting Concerns (entrega 4)

- [ ] T075 Tirar de `docs/DESIGN.md` as últimas marcas de "entrega N", conferir que todo componente descrito existe no código e que todo componente do código está descrito
- [ ] T076 [P] Conferir que nenhuma classe usada nos templates fica sem regra em CSS, exceto as que só servem de gancho a script ou a teste, documentadas como tal em `docs/DESIGN.md`. Usar um comando de conferência à parte, fora da suíte
- [ ] T077 [P] Conferir o tamanho do CSS: as linhas de `interface/static/interface/css/*.css` e do CSS das apps não crescem mais que 30% sobre a base de T004 (plan.md, "Performance Goals")
- [ ] T078 Rodar `scripts/capturar_telas.py` com todas as telas-chave e todo o `specs/015-design-system-m3/quickstart.md`, para a revisão visual final do chefe (SC-008). Rodar os portões e preparar o PR da entrega 4 (só abrir com o pedido do usuário)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (fase 1)** → **Foundational (fase 2)** → **US1 (fase 3)** e **US5 (fase 4)**, juntas no PR da
  entrega 1. A US5 depende do que a US1 fizer (o `DESIGN.md` descreve os componentes reestilizados).
- **US2 (fase 5)** depende da entrega 1 integrada em `develop` (tokens, componentes, ícones novos).
- **US3 (fase 6)** depende da entrega 1. Na ordem do plano, sai depois da US2, mas não usa nada dela.
  Pode ir antes, se o usuário preferir.
- **US4 (fase 7)** depende da entrega 1 e, para o menu novo nas telas, da US2.
- **Acabamento (fase 8)** depende de todas.

### Within Each User Story

- Os testes primeiro, falhando, e depois a implementação (Princípio V).
- Regras puras e consultas (T036 a T038) antes da view (T042); a view antes dos templates (T043, T045).
- A conferência por captura e os portões fecham cada história.

### Parallel Opportunities

- Fase 2: T009 em paralelo com T007 e T008.
- US1: T011, T012 e T013 em paralelo. As tarefas de `componentes.css` (T014 a T018) são do mesmo
  arquivo e vão em sequência.
- US2: os testes T030 a T034 em paralelo; T036, T037 e T038 em paralelo; T046 em paralelo com T043 a
  T045.
- US3: T058, T060, T061 e T063 em paralelo, depois de T056.
- US4: T068, T071, T072 e T073 em paralelo.

---

## Parallel Example: User Story 2

```text
# Testes da US2, juntos (arquivos diferentes):
T030 tests/test_painel_indicadores.py
T031 tests/test_contadores_menu.py
T032 tests/test_painel_menu_acoes.py
T033 tests/test_painel_filtros.py
T034 tests/test_imprimir_pela_lista.py

# Regras e consultas, juntas:
T036 pedidos/regras.py (texto_envio_mais_antigo)
T037 pedidos/consultas.py (mais antigo, autorizações, contar_lotes_travados)
T038 compras/consultas.py (contar_recebimentos_travados)
```

---

## Implementation Strategy

### MVP (entrega 1: US1 + US5)

1. Fases 1 e 2: base medida, tokens novos e contraste garantido por teste.
2. Fase 3: o sistema inteiro no visual novo, sem tocar nos templates.
3. Fase 4: constituição 2.2.0, `DESIGN.md`, skill e `CLAUDE.md` no mesmo PR.
4. **Parar e validar**: capturas, recibo idêntico, revisão do chefe. Deploy só com a tag e a imagem
   aprovadas, numa ação separada (`CLAUDE.md`).

### Entregas seguintes

1. Entrega 2 (US2): painel e casca, com os comportamentos novos testados.
2. Entrega 3 (US3): formulários públicos, com a medição da SC-005 antes e depois.
3. Entrega 4 (US4 e acabamento): as telas restantes e a revisão final.

Cada entrega é revisável sozinha e não quebra a anterior. Entre uma e outra, as telas ainda não
recompostas ficam com o visual novo e a composição antiga, nunca com os dois visuais.
