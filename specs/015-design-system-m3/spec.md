# Feature Specification: Troca do design system (Clean → linguagem visual do Material 3)

**Feature Branch**: `claude/gifted-pascal-gsjrf3` (a partir de `develop` em `d011594`)

**Created**: 2026-11-12

**Status**: Rascunho, com as decisões Q1 e Q2 do usuário registradas (pronta para o plano)

**Input**: User description: trocar o design system Clean por uma linguagem visual inspirada no
Material 3 (M3), implementada no CSS próprio do projeto, sem biblioteca externa. A base são os
protótipos do painel e dos formulários públicos (`prototipos/`). Decisões do usuário em 2026-11-12,
numa conversa de design antes desta especificação:

- o motivo é a **aparência**: o usuário quer um visual mais moderno e gostou muito do painel de
  exemplo do Advanced Material Web (showcase "ERP — Purchase orders" da Viewflow), comparado ao
  painel atual;
- **não adotar biblioteca de componentes** (o levantamento está na seção "Pesquisa");
- adotar o M3 **como linguagem visual** no CSS do projeto, mantendo o comportamento atual;
- os protótipos de `prototipos/painel.html` e `prototipos/formularios-publicos.html` são a direção
  visual aprovada para seguir com a especificação.

## Contexto

Fatos do código em 2026-11-12 (branch `develop`, `d011594`):

| # | Fato | Onde |
|---|------|------|
| F1 | O Princípio VI da constituição (versão 2.1.0) diz que "a interface segue o design system Clean (`docs/DESIGN.md`)" e proíbe dependência do Google, de CDN ou de npm. | `.specify/memory/constitution.md` |
| F2 | A referência de estilo é o `docs/DESIGN.md` com a skill `.claude/skills/clean-design/`. O `CLAUDE.md` manda usar três skills em todo ajuste de UI, com a `clean-design` vencendo as outras. | `docs/DESIGN.md`, `CLAUDE.md` (Convenções) |
| F3 | A camada visual tem três CSS comuns (`clean.css`, `componentes.css` e `layouts.css`, 859 linhas) e o CSS próprio de `pedidos`, `catalogo` e `contas`. São 73 templates em seis apps (36 em `pedidos`, 18 em `catalogo`). | `interface/static/interface/css/`, `*/templates/` |
| F4 | As fontes são locais: Geist, DM Sans e Geist Mono, em `.woff2` com licença OFL. O `DESIGN.md` proíbe Inter, Roboto, Arial e system-ui. Os ícones são SVG inline no estilo Lucide, num conjunto fechado (`_icone.html`). | `interface/static/interface/fonts/`, `docs/DESIGN.md` |
| F5 | Os scripts do projeto acham os elementos sobretudo por atributos `data-*` (cerca de 125 seletores), mas também por nome de classe (cerca de 57). Trocar um nome de classe pode quebrar um comportamento. | `*/static/*/js/*.js` |
| F6 | 52 arquivos de teste citam classes CSS (`botao-primario`, `carrinho-linha`, `app-lateral`, `campo-rotulo`, `tabela-rolagem`, `selo-erro`…). | `tests/` |
| F7 | O menu da área interna tem 6 destinos para a equipe (Painel, Saída avulsa, Automações, Curva ABC, Formulários, Cadastros) e 1 para a Segurança do Trabalho (Autorizações). A spec 014 prevê mais telas internas. Até 1286px, a barra lateral vira cabeçalho com o botão de menu. | `interface/navegacao.py`, `docs/DESIGN.md` |
| F8 | O painel já calcula os números que o protótipo usa: pedidos aguardando atendimento, recibos para imprimir, requisições aguardando o robô e requisições travadas. Já existem os filtros por GET `q`, `material`, `origem`, `situacao`, `autorizacao`, `scpi`, `recibo`, `de` e `ate`. | `pedidos/views/almoxarifado.py`, `pedidos/consultas.py` |
| F9 | As specs 012 e 013 trouxeram as telas de acesso negado, o login de solicitante e "Meus pedidos". | `interface/templates/interface/acesso_negado*.html`, `contas/templates/contas/` |
| F10 | O recibo tem regras próprias de impressão (texto preto, bordas cinza, uma folha por recibo). | `layouts.css`, `pedidos.css` (`@media print`) |
| F11 | Os formulários públicos exigem JavaScript (o aviso do `<noscript>`). A área interna funciona sem ele: menu aberto, filtros por GET, painéis empilhados. | `CLAUDE.md`, `docs/DESIGN.md` |
| F12 | A spec 014 (entrada por pedido) está em andamento em `develop`, com telas internas novas previstas. | `specs/014-entrada-por-pedido/` |

## Pesquisa (alternativas avaliadas na conversa de 2026-11-12)

| Alternativa | Situação | Por que não |
|---|---|---|
| Material Web (`@material/web`, do Google) | Em modo de manutenção desde jun/2024, sem trabalho futuro planejado | Biblioteca parada; web components com Shadow DOM (o CSS e os scripts do projeto não alcançam o interior); npm; Roboto |
| Advanced Material Web (Viewflow), a do showcase | Pacote criado em 11/08/2026; 4 versões em 4 dias e nenhuma depois; um mantenedor; AGPL-3.0 com exceção | Nova demais e parada; mesmo conflito de Shadow DOM com o `pedidos.js` e o `dropdown.js`; npm |
| Tailwind v4 com Basecoat ou daisyUI | Ativos | Etapa de build e pacotes npm; reescrita das classes dos 73 templates; o Basecoat tem um mantenedor só |
| Web Awesome 3 (sucessor do Shoelace) | Ativo, com uma parte paga | Web components com Shadow DOM |
| **M3 como linguagem visual no CSS próprio** | — | **Escolhida**: nenhuma dependência nova, os scripts e o HTMX continuam iguais, e o projeto controla o resultado |

## Clarifications

### Session 2026-11-12

- Q1: Os comportamentos novos que o protótipo do painel mostra entram nesta spec (o menu ⋮ por
  linha, "o mais antigo há N dias", as requisições travadas no cartão do robô e "+N aguardando
  autorização")? → A: **sim, todos** (opção B). Regras em FR-018 a FR-018d. Na (c), as travadas
  ficam no mesmo cartão, mas numa nota à parte, sem somar com as que aguardam o robô (ver FR-018c).
- Q2: Nos campos dos formulários públicos, rótulo flutuante dentro da caixa ou rótulo fixo acima?
  → A: **rótulo flutuante** (opção A). O exemplo do campo passa a ser texto de apoio fixo embaixo
  dele (FR-020).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - O sistema inteiro troca de visual sem mudar de comportamento (Priority: P1)

O chefe do almoxarifado abre qualquer tela do sistema e encontra a nova linguagem visual. Isso vale
para os botões, campos, selos, avisos, cartões, tabelas, abas, diálogos, listas suspensas e
paginação. Os fluxos de trabalho, os textos, os endereços e as regras são os mesmos de antes, e
ninguém precisa reaprender onde fica cada coisa.

**Why this priority**: é a fundação de todas as outras histórias. Por ser global, impede que o
sistema conviva com dois visuais entre uma entrega e outra.

**Independent Test**: com a fundação entregue, a suíte de testes passa sem mudar nenhuma asserção de
comportamento. A comparação de capturas das telas-chave (painel, detalhe, formulário público, página
inicial, Automações) a 375, 768 e 1280px mostra a nova linguagem, sem elemento quebrado e sem rolagem
lateral.

**Acceptance Scenarios**:

1. **Given** a fundação entregue, **When** qualquer tela é aberta, **Then** ela usa as cores, superfícies, raios, elevações, tipografia e componentes novos, e nenhum controle perde a função.
2. **Given** um selo de situação (por exemplo, "Atendido parcialmente"), **When** aparece em qualquer tela, **Then** traz a palavra e um ícone, nunca só a cor.
3. **Given** um formulário que grava, **When** é enviado, **Then** o resultado (gravação, mensagem, redirecionamento) é o mesmo de antes da troca.
4. **Given** o recibo, **When** é impresso, **Then** a folha sai igual à de antes da troca.

---

### User Story 2 - Painel do almoxarifado no novo desenho (Priority: P1)

Quem atende abre o painel e vê:

- um menu estreito com ícone e rótulo, que mostra quantos pedidos aguardam atendimento e quantas
  requisições estão travadas;
- a busca de pedidos no topo;
- cartões de indicadores no lugar dos atalhos, com os mesmos números e as mesmas ações;
- os filtros como chips de um clique;
- a tabela com Situação e SCPI em colunas separadas e o recibo pendente visível na linha;
- o botão flutuante "Saída avulsa".

**Why this priority**: é a tela de uso diário da equipe, e foi a comparação com ela que motivou a
troca.

**Independent Test**: em `prototipos/painel.html`, cada número, ação e filtro tem o seu equivalente
no painel atual. Com dados de teste, os números e os resultados de cada filtro são os mesmos antes e
depois.

**Acceptance Scenarios**:

1. **Given** 2 pedidos aguardando atendimento, **When** o painel abre, **Then** o cartão "Aguardando atendimento" mostra 2 com a ação "Atender", e o menu mostra o contador 2 no item Painel.
2. **Given** o lançamento real bloqueado no ambiente, **When** o painel abre, **Then** o cartão das requisições mostra "Lançar no SCPI" desabilitado, com cadeado e o motivo, como hoje.
3. **Given** o chip de situação "Atendido parcialmente", **When** é clicado, **Then** a lista mostra só os parciais, com o mesmo parâmetro na URL de hoje (`?situacao=parcial`), também sem JavaScript.
4. **Given** um cartão de indicador, **When** é clicado, **Then** aplica o filtro que já existe para ele (por exemplo, `?recibo=pendente` para recibos).
5. **Given** avisos de saúde do catálogo, **When** o painel abre, **Then** o 4º cartão mostra quantos erros e avisos há, e a lista completa continua na página.
6. **Given** um pedido atendido com o lote ainda pendente, **When** a equipe abre o ⋮ da linha, **Then** vê "Abrir pedido", "Imprimir recibo" e "Editar atendimento"; num pedido aguardando atendimento, só "Abrir pedido"; com o lote já lançado, sem "Editar atendimento".
7. **Given** "Imprimir recibo" escolhido no ⋮, **When** o detalhe abre, **Then** a impressão começa e a confirmação "O recibo saiu na impressora?" aparece no detalhe; nada é marcado como impresso sem essa confirmação.
8. **Given** o pedido aguardando mais antigo enviado há 3 dias, **When** o painel abre, **Then** o cartão de atendimento mostra "há 3 dias".
9. **Given** 1 requisição aguardando o robô e 1 em verificar, **When** o painel abre, **Then** o cartão do robô mostra 1 como número principal e a nota "1 para conferir", com o link para as travas, e o menu mostra 1 em Automações.
10. **Given** 2 pedidos de EPI aguardando autorização, **When** o painel abre, **Then** o cartão de atendimento mostra "+2 aguardando autorização", com link para o filtro; com zero, a nota some.

---

### User Story 3 - Formulários públicos no novo desenho (Priority: P1)

O funcionário que pede material, no celular ou no computador, encontra o novo desenho em todas as
telas públicas: a página inicial com um cartão por formulário, os campos no padrão M3, os passos em
blocos, a busca em pílula, a quantidade com − e + em pílula, o "Seu pedido" e a tela de sucesso. A
consulta pública, o login de solicitante, "Meus pedidos" e a folha das viaturas seguem o mesmo
desenho. Pedir continua igual: tocar no material, escolher a quantidade, confirmar e enviar.

**Why this priority**: é a parte do sistema que mais gente usa, e a primeira impressão de quem não
é do almoxarifado.

**Independent Test**: um pedido de 3 materiais feito no celular antes e depois da troca leva o mesmo
número de toques, e o pedido gravado é idêntico. Os testes dos formulários públicos passam sem mudar
nenhuma asserção de comportamento.

**Acceptance Scenarios**:

1. **Given** a página inicial, **When** abre, **Then** cada formulário público aparece num cartão com ícone, título e exemplos (os textos de hoje), e o formulário geral fica à parte, depois da pergunta de sempre.
2. **Given** um campo obrigatório vazio no envio, **When** o pedido é recusado, **Then** o resumo de erros aparece no topo com link para o campo, e o próprio campo mostra o erro na borda e no texto embaixo dele, com ícone.
3. **Given** a busca de materiais, **When** o funcionário toca na busca, **Then** o painel de resultados abre como hoje: no fluxo da página, com a altura de 5 linhas e os sem estoque no fim.
4. **Given** um celular com menos de 960px de largura, **When** há material no pedido, **Then** a barra presa embaixo da tela abre a gaveta "Seu pedido", que sobe da base da tela, com o envio e "Adicionar mais materiais".
5. **Given** um pedido registrado, **When** a tela de sucesso aparece, **Then** mostra o número em destaque, o destino, os materiais, o aviso e as mesmas ações de hoje.

---

### User Story 4 - Demais telas internas no novo desenho (Priority: P2)

A equipe encontra o novo desenho nas outras telas internas:

- detalhe do pedido, com o atendimento e a edição;
- saída avulsa;
- Automações (as abas e o histórico);
- Curva ABC e Formulários (configuração);
- Autorizações (Segurança do Trabalho);
- login, acesso negado e recibo na tela.

Os layouts dessas telas usam os componentes da fundação e o menu novo.

**Why this priority**: a fundação (US1) já deixa essas telas coerentes. O que esta história
acrescenta é ajustar a composição de cada uma ao novo desenho, sem pressa, tela por tela.

**Independent Test**: cada tela listada, aberta a 375, 768 e 1280px, usa só componentes do
vocabulário documentado, sem rolagem lateral, e os testes dela passam.

**Acceptance Scenarios**:

1. **Given** o detalhe de um pedido aguardando atendimento, **When** a equipe confirma as quantidades, troca e acrescenta material, **Then** cada interação (confirmar, lápis de alterar, troca, acréscimo, "Entregar tudo") funciona como hoje.
2. **Given** a página Automações, **When** uma aba é aberta, **Then** a aba ativa continua se fundindo ao primeiro cartão do painel, e as regiões que se recarregam continuam se recarregando.

---

### User Story 5 - Referência de estilo para as telas futuras (Priority: P2)

Quem fizer uma tela nova, uma pessoa ou um agente, tem uma referência única e atualizada:

- o `docs/DESIGN.md` reescrito;
- uma skill de estilo no lugar da `clean-design`;
- o `CLAUDE.md` atualizado;
- a constituição apontando para o `DESIGN.md` sem nomear o estilo.

As telas da spec 014 nascem no novo desenho, ou são convertidas, conforme a ordem das entregas.

**Why this priority**: sem isso, cada tela nova reabre a discussão de estilo, e o sistema volta a
ter dois visuais.

**Independent Test**: uma tela nova feita só com o `DESIGN.md` e a skill fica coerente com o painel e
com os formulários na revisão visual do chefe.

**Acceptance Scenarios**:

1. **Given** o pull request da fundação, **When** é aberto, **Then** traz no mesmo pull request a emenda do Princípio VI, o `DESIGN.md` novo, a skill nova e o `CLAUDE.md` atualizado, como manda a governança.

---

### Edge Cases

- **Sem JavaScript na área interna**: o menu fica aberto, os chips são links ou botões de envio com os mesmos parâmetros de hoje, e as ações continuam acessíveis. Nada novo pode depender de script para funcionar.
- **Celular na área interna**: abaixo do limite atual (1286px), o menu vira o cabeçalho com o botão de menu, como hoje. Nenhum destino pode ficar escondido. O protótipo escondia Curva ABC e Cadastros na barra de baixo, e isso **não** vale.
- **Tela de 320px e zoom de 200%**: a página não rola de lado, e as tabelas rolam dentro da própria caixa.
- **Leitor de tela**: o item atual do menu tem `aria-current`, os chips têm `aria-pressed`, os contadores do menu têm texto (por exemplo, "2 para atender") e o selo continua tendo a palavra.
- **Movimento reduzido**: com `prefers-reduced-motion`, nada se anima.
- **Trechos trocados pelo HTMX**: os trechos que o servidor devolve (carrinho, resultados, faixa de edição, regiões de Automações) já saem com as classes novas. Nenhuma tela mostra um trecho no visual antigo dentro do novo.
- **Entre uma entrega e outra**: como os componentes comuns mudam todos na fundação, uma tela cujo layout ainda não foi ajustado fica com o visual novo e a composição antiga, nunca com os dois visuais.
- **Segurança do Trabalho**: o menu dela mostra só Autorizações, e a marca muda como hoje.
- **Impressão**: o `@media print` continua escondendo a casca, os botões flutuantes e os chips.
- **Spec 014 em paralelo**: os templates que a 014 mexer entram em conflito com a troca. A ordem das entregas decide quem converte o quê (FR-029).

## Requirements *(mandatory)*

### Functional Requirements

**Linguagem visual (fundação)**

- **FR-001**: O sistema DEVE ter um único conjunto de tokens no padrão do M3. Ele inclui: a cor primária (o azul `#2563EB` atual como semente) e os contêineres tonais; cinco níveis de superfície; contornos; os quatro status (ok, aviso, erro, informação), cada um com contêiner e texto; raios de 8, 12, 16 e 28px; duas elevações; e a escala tipográfica. Só tema claro.
- **FR-002**: As fontes continuam as atuais (Geist, DM Sans e Geist Mono), servidas pelo próprio sistema. Nada de Roboto, Inter ou fonte de CDN.
- **FR-003**: Os ícones continuam SVG inline no estilo Lucide, no conjunto fechado do `_icone.html`, que só cresce com os ícones que as telas novas usarem.
- **FR-004**: Estado nunca só por cor. Todo selo de situação traz a palavra e um ícone, e todo aviso traz texto.
- **FR-005**: Os dois ritmos continuam: o público, arejado, e o interno, compacto. Os mesmos tokens servem aos dois, em densidades diferentes.

**Compatibilidade**

- **FR-006**: Nenhum comportamento muda, salvo os do painel em FR-018 a FR-018d e o lugar dos exemplos dos campos públicos em FR-020. Ficam iguais os endereços, os nomes de rota, os textos (salvo os listados nesta spec), os campos de formulário, os atributos do HTMX, os `data-*`, as regras de negócio e as respostas do servidor.
- **FR-007**: Onde o componente continua existindo, o vocabulário de classes atual é preservado. Renomear uma classe só com motivo escrito e na mesma entrega que ajusta os scripts e os testes que dependem dela (F5, F6). Componente novo (indicador, chip, menu estreito, botão flutuante) ganha classe nova, documentada no `DESIGN.md`.
- **FR-008**: Nenhuma dependência nova: nada de biblioteca de componentes, npm, CDN ou etapa de build de CSS. O CSS continua escrito à mão no repositório.
- **FR-009**: Sem JavaScript, a área interna continua utilizável (navegação, filtros, ações). Os formulários públicos continuam exigindo JavaScript, como hoje.
- **FR-010**: A impressão do recibo não muda.
- **FR-011**: Acessibilidade:
  - contraste AA: 4,5:1 no texto e 3:1 nos contornos de campo, nos ícones de estado e no foco;
  - alvos de toque de 44px ou mais na área interna e de 48px nos formulários públicos;
  - foco sempre visível;
  - `aria-current` no item atual do menu e `aria-pressed` nos chips;
  - nada se anima com `prefers-reduced-motion`.
- **FR-012**: Nenhuma tela rola de lado entre 320 e 1440px de largura. Toda tabela fica dentro da rolagem própria.

**Painel do almoxarifado**

- **FR-013**: Menu estreito, com ícone, rótulo e item atual destacado. Os contadores mostram só números que o sistema já calcula: pedidos aguardando atendimento (no Painel) e requisições travadas (em Automações). Abaixo de 1286px, vale o cabeçalho com o botão de menu de hoje, com todos os destinos.
- **FR-014**: A busca de pedidos (o campo `q` de hoje) fica no topo da página.
- **FR-015**: Os atalhos viram cartões de indicadores, com os mesmos números, ações e bloqueios de hoje:
  - aguardando atendimento, com "Atender";
  - recibos para imprimir, com "Imprimir";
  - requisições aguardando o robô, com "Lançar no SCPI", que segue o bloqueio do `LANCAMENTO_REAL`.

  Clicar num cartão aplica o filtro que já existe para ele. O atalho "Registrar uma saída avulsa" vira o botão flutuante "Saída avulsa". A saúde do catálogo ganha um cartão com a contagem por nível, e a lista completa continua na página.
- **FR-016**: Os filtros viram chips. A situação fica em chips de um clique; origem, SCPI, recibo, autorização e período ficam em chips com menu; a busca por material vira um campo na mesma linha. Ficam iguais todos os parâmetros e o funcionamento sem JavaScript (F8).
- **FR-017**: A tabela tem as colunas Nº com a origem, Enviado em, Pessoa, Destino ou centro de custo, Situação e SCPI, com Situação e SCPI separadas. A linha inteira leva ao detalhe, e o "Recibo não impresso" aparece na linha (o dado já existe).
- **FR-018**: Comportamentos novos do painel (decisão Q1). Cada um mostra só dados que o sistema já guarda, não grava nada e tem teste próprio. Abaixo, de FR-018a a FR-018d.
- **FR-018a**: **Menu ⋮ por linha da tabela.** O menu tem só atalhos para ações que já existem; cada uma continua acontecendo na tela onde acontece hoje:
  - **Abrir pedido**: sempre presente; leva ao detalhe.
  - **Imprimir recibo**: só no pedido com atendimento registrado. Leva ao detalhe e abre a impressão, como o botão "Imprimir recibo" de lá; depois vem a confirmação "O recibo saiu na impressora?" no próprio detalhe, como hoje. O recibo nunca é impresso nem marcado como impresso a partir da lista.
  - **Editar atendimento** ("Editar saída" na saída avulsa): só quando a edição está permitida pelas linhas do lote (a mesma regra do detalhe). Leva à tela de edição de sempre.

  Cada item só aparece para quem tem a permissão que a ação já exige (spec 012), e o servidor continua recusando quem não a tem. Pedido de EPI não autorizado não ganha "Imprimir recibo" nem "Editar atendimento", porque não tem atendimento. Sem JavaScript, o menu vira os mesmos links visíveis na linha. O ⋮ tem rótulo acessível ("Ações do pedido P-000123"), abre e fecha pelo teclado e fecha com Esc.
- **FR-018b**: **"O mais antigo há N dias"** no cartão "Aguardando atendimento". É o pedido mais antigo pela data de envio, entre os que o filtro "Aguardando atendimento" já conta (fora os que aguardam autorização e os recusados). N são os dias de calendário entre a data do envio e hoje, no fuso do servidor: "enviado hoje", "enviado ontem" ou "há N dias". Some quando não há pedido aguardando.
- **FR-018c**: **Requisições travadas no cartão do robô.** O número principal continua o de hoje: as requisições aguardando o robô. As travadas (em verificar, em lançamento ou com erro; o mesmo número que o sistema já conta) continuam no mesmo cartão, como já acontece hoje: numa nota de alerta à parte, com o texto de hoje ("N para conferir"), ícone e o link de hoje para as travas na aba Lançamento no SCPI de Automações, onde elas se resolvem. Os dois números **não** se somam: um é fila, o outro exige ação de alguém, e a soma esconderia o travado dentro da fila. O protótipo somava, e a spec corrige. O contador do item Automações no menu é o mesmo número das travadas.
- **FR-018d**: **"+N aguardando autorização"** no cartão "Aguardando atendimento". N são os pedidos de EPI aguardando a decisão da Segurança do Trabalho (o mesmo do filtro Autorização). É um link para a lista filtrada por esse estado e some quando N é zero. Não entra no número principal, porque esses pedidos ainda não podem ser atendidos.

**Formulários públicos**

- **FR-019**: A página inicial tem um cartão por formulário, com os textos e a ordem de hoje. A consulta pública fica em destaque no topo, e o formulário geral fica à parte, depois da pergunta de sempre.
- **FR-020**: Os campos de texto dos formulários públicos, da consulta pública e do login de solicitante são caixas no padrão M3, com **rótulo flutuante** (decisão Q2):
  - vazio e sem foco, o rótulo fica dentro da caixa; com foco ou com valor, sobe para a borda e continua visível;
  - o exemplo que hoje fica dentro do campo (por exemplo, "Setor ou posto de trabalho" e "Centro de custo da equipe") passa a ser **texto de apoio fixo embaixo do campo**, com o mesmo texto, sempre visível e ligado ao campo pelo `aria-describedby`;
  - com erro, a borda e o rótulo ficam vermelhos, e o texto de apoio dá lugar à mensagem de erro, com ícone;
  - o resumo de erros do topo não muda;
  - o rótulo continua um `<label>` ligado ao campo, sem perder o nome de classe que os testes usam (FR-007);
  - a lista de sugestões do destino (o painel do `dropdown.js`) continua funcionando no campo com rótulo flutuante.

  A busca de materiais não é um desses campos: continua a pílula de busca, com o exemplo dentro dela. Os campos da área interna mantêm o rótulo fixo acima, pela densidade do ritmo compacto.
- **FR-021**: Os passos ficam numerados em blocos tonais, e a busca de materiais vira uma pílula. O painel de resultados mantém o comportamento atual: abre na busca, fica no fluxo da página, tem a altura do cabeçalho mais 5 linhas e mostra os bloqueados no fim.
- **FR-022**: A quantidade usa o controle − / + em pílula. O fluxo de dois passos (tocar na linha, confirmar), o "Atualizar", o selo "N no pedido" e o teto no estoque não mudam.
- **FR-023**: O "Seu pedido" fica num cartão lateral preso ao rolar a partir de 960px, e vira a barra com a gaveta abaixo disso, nos limites de hoje.
- **FR-024**: A tela de sucesso mostra o número em destaque em fonte mono, um cartão com o destino e os materiais, o aviso e as ações de hoje.
- **FR-025**: A consulta pública, o login de solicitante, "Meus pedidos", a folha das viaturas e a tela de acesso negado pública seguem o mesmo desenho.

**Demais telas**

- **FR-026**: As telas de US4 usam os componentes da fundação e o menu novo. As abas mantêm a pasta (a aba ativa se funde ao primeiro cartão) e o comportamento atual.

**Documentação e governança**

- **FR-027**: O pull request da fundação emenda o Princípio VI da constituição, que passa a dizer "segue o design system do projeto (`docs/DESIGN.md`)", sem nomear o estilo. Recomendação: versão MINOR (2.2.0), porque o princípio não perde garantia nenhuma (pt-BR, acessível, sem dependências); se o usuário entender que é uma redefinição incompatível, MAJOR (3.0.0). No mesmo pull request: reescrever o `docs/DESIGN.md`, criar a skill de estilo no lugar da `clean-design` (a antiga sai, e fica no histórico do Git) e atualizar o `CLAUDE.md`.
- **FR-028**: Os protótipos de `prototipos/` são a referência visual. Onde divergem desta spec, vale a spec. Divergências conhecidas:
  - a lista de resultados do protótipo dos formulários fica sempre aberta;
  - a mensagem "nome completo, com sobrenome" é ilustrativa;
  - a barra de baixo do painel no celular escondia destinos;
  - o cartão do robô somava as travadas com as que aguardam o robô (FR-018c corrige);
  - o menu ⋮ do protótipo aparece em todas as linhas, sem as condições de FR-018a.
  - o protótipo do painel tem uma barra no topo de toda a área interna, com a busca e o usuário. Na spec, a busca fica no topo da página do painel (FR-014), e o usuário com o "Sair" no pé do menu, como hoje: as outras telas não têm busca de pedidos, e uma barra só para o painel seria um layout a mais.
- **FR-029**: Telas da spec 014: se forem integradas antes da etapa que cobre a área interna (US4), são convertidas nela; se vierem depois da fundação, já nascem no desenho novo.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A suíte de testes passa em todas as entregas sem mudar nenhuma asserção de comportamento. Só podem mudar as asserções sobre nome de classe renomeada pela FR-007 e sobre o lugar do exemplo dos campos públicos (FR-020). Cada item de FR-018a a FR-018d ganha testes próprios: quando aparece, o número certo e quando some.
- **SC-002**: Nenhuma das telas listadas nas US1 a US4 rola de lado a 320, 375, 768, 1280 e 1440px.
- **SC-003**: Todos os pares de texto e fundo dos tokens atingem o contraste AA (verificável por cálculo sobre os tokens).
- **SC-004**: A 1366×768, o painel mostra sem rolar ao menos tantos pedidos quanto hoje, medidos antes da troca com os mesmos dados.
- **SC-005**: Um pedido de 3 materiais no celular leva o mesmo número de toques ou menos, e um tempo igual ou menor, medido com 3 funcionários antes e depois.
- **SC-006**: Zero dependências novas: nenhum arquivo de terceiros entra no repositório além das fontes e dos ícones que já estão lá.
- **SC-007**: O recibo impresso antes e depois da troca é idêntico (comparação do PDF).
- **SC-008**: O chefe do almoxarifado aprova as telas-chave de cada entrega numa revisão visual antes do deploy.

## Entregas sugeridas

Cada entrega é um pull request para `develop` com deploy separado, nesta ordem:

1. **Fundação (US1 + US5)**: tokens, componentes comuns, emenda da constituição, `DESIGN.md`, skill e `CLAUDE.md`. Todas as telas mudam de visual de uma vez.
2. **Casca e painel (US2)**: o menu estreito, a busca no topo, os indicadores, os chips, a tabela e o botão flutuante.
3. **Formulários públicos (US3)**.
4. **Demais telas internas (US4)**.

## Riscos

- **Regressão visual sem teste automático**: os testes conferem o HTML, não a aparência. A conferência é por captura a 375, 768 e 1280px em cada entrega (SC-002, SC-008).
- **Acoplamento a nomes de classe** (F5, F6): renomear sem necessidade quebra scripts e testes. A FR-007 limita as renomeações.
- **Densidade do painel**: cartões e linhas mais altos podem mostrar menos pedidos. A SC-004 garante que não piora.
- **Hábito dos usuários**: muda a aparência, não o lugar das coisas. Os textos e a ordem dos passos ficam (FR-006).
- **Conflito com a spec 014** nos templates internos: a FR-029 e a ordem das entregas resolvem.
- **Tamanho do trabalho**: são 73 templates e o CSS inteiro, em paralelo com outras specs. As entregas em etapas mantêm cada pull request revisável.

## Assumptions

- Só tema claro, como hoje. O tema escuro do M3 fica fora.
- A cor primária continua o azul atual. O M3 entra pela estrutura (superfícies tonais, contêineres, raios, elevação, componentes), não por uma paleta nova.
- O admin do Django e as páginas 404/500 ficam fora, como na troca para o Clean.
- Navegadores-alvo: Chrome e Edge atuais no Windows do almoxarifado; Chrome no Android e Safari no iPhone dos funcionários.
- O nome do design system no `DESIGN.md` e na skill é uma decisão de redação do plano. Sugestão: "Tonal".

## Fora do escopo

- Biblioteca de componentes de qualquer tipo, e etapa de build de CSS.
- Tema escuro.
- Mudança de regra de negócio, fluxo, texto (além dos listados) ou URL.
- Qualquer ação nova que grave a partir da lista do painel: o menu ⋮ só leva às telas onde as ações já existem (FR-018a).
- Admin do Django e páginas 404/500.
