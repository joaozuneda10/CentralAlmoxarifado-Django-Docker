# Research: Troca do design system (Clean → linguagem visual do Material 3)

Decisões técnicas do plano. Cada uma diz o que foi escolhido, por quê e o que ficou de fora. A
escolha de não usar biblioteca está na seção "Pesquisa" da spec e não se repete aqui.

## R1. Reestilizar no lugar, sem vocabulário novo

**Decision**: manter os arquivos `componentes.css` e `layouts.css`, os nomes de classe e os nomes de
token, e trocar os valores e as regras de cada componente. Só entram classes novas para componentes
novos (contracts/componentes.md).

**Rationale**:

- Os scripts acham elementos por classe em cerca de 57 lugares (`carrinho-linha`, `app-lateral`,
  `quantidade-campo`, `campo-entrada`, `aba-ativa`…), e 52 arquivos de teste citam classes. Renomear
  multiplica o risco sem ganho visual.
- O CSS já usa quase só tokens (cerca de 600 `var(--…)`, menos de 20 cores fixas), então trocar os
  valores alcança o sistema inteiro.

**Alternatives considered**:

- Vocabulário novo, como na troca para o Clean: mais limpo no papel, mas reescreve os 83 templates,
  os scripts e os testes de uma vez.
- Uma camada M3 por cima do Clean: dois sistemas convivendo, o que é a dívida que a spec quer evitar.

## R2. `clean.css` passa a se chamar `fundacao.css`

**Decision**: renomear `interface/static/interface/css/clean.css` para `fundacao.css` na entrega 1. O
`base.html` muda a referência, e `tests/test_clean.py` vira `tests/test_fundacao.py` (as asserções de
fonte, ritmo e grade continuam; a de tokens passa aos valores novos). O `tests/test_prefixo.py` e o
`tests/test_interface.py` trocam o nome do arquivo.

**Rationale**: um arquivo chamado "clean" com outro estilo engana quem o mantém. O custo é uma linha
de template e o nome do arquivo em três testes.

**Alternatives considered**: manter o nome (zero mudança, nome mentiroso); chamar de `m3.css` (amarra o
nome ao estilo de novo, e a constituição passa a não nomear o estilo).

## R3. Tokens: mesmos nomes, valores novos, alguns acrescentados

**Decision**: os tokens de hoje continuam com o mesmo nome e semântica (`--fundo`, `--texto`,
`--texto-secundario`, `--texto-suave`, `--destaque`, os pares de status, os raios, as sombras, os
espaços, o ritmo). Entram tokens para o que o Clean não tinha: os níveis de superfície, o contorno
de controle, os contêineres tonais e as elevações. A tabela completa, com os valores e o contraste
calculado, está em `contracts/tokens.md`.

Ajustes de contraste que o cálculo exigiu:

| Token | Protótipo | Fica | Motivo |
|---|---|---|---|
| `--texto-suave` | `#767984` (4,34:1 no branco) | `#666975` (5,47:1 no branco, 4,79:1 na `--superficie-media`) | AA para texto pequeno em toda superfície |
| `--contorno` (controles: campo, chip sem seleção, botão de contorno) | `#C4C7D0` (1,69:1) | `#7A7D88` (4,10:1 no branco, 3,80:1 na `--superficie`) | WCAG 1.4.11: a borda é o único limite do chip e do campo, e precisa de 3:1 |
| Texto sobre `--destaque-superficie` | `#2563EB` (4,14:1) | `--destaque-superficie-texto` `#0F2A6B` (10,75:1) | O azul do botão não serve como texto no contêiner azul-claro |

O `--contorno-suave` (`#E2E4EA`) fica só em divisórias e no contorno decorativo de cartão, onde a borda
não é o único indicador. Hoje o `--texto-suave` (`#A8A49F`, 2,48:1) já não passa no AA: a troca corrige
isso.

**Rationale**: com os nomes mantidos, a maior parte do sistema muda só pelo `:root`. O cálculo pegou
três reprovações no protótipo, que a SC-003 cobriria tarde demais.

**Alternatives considered**: os nomes do M3 (`--md-sys-color-*`), que trocariam as 600 referências
por nada; a paleta gerada do M3 a partir da semente, que muda o azul de hoje (a spec mantém o
`#2563EB`).

## R4. Rótulo flutuante sem mudar a ordem do HTML

**Decision**: o rótulo flutuante dos formulários públicos (decisão Q2) usa `:has()`. Por padrão (sem
`:has()`), o rótulo fica sempre na borda, flutuado: é a reserva segura. Com `:has()`, ele desce para
dentro da caixa só quando o campo está vazio e sem foco:

`.campo-flutuante:has(.campo-entrada:placeholder-shown:not(:focus)) .campo-rotulo`

O campo recebe `placeholder=" "`, e o exemplo de hoje sai do `placeholder` para o `campo-dica` embaixo
(`aria-describedby`). O `<label class="campo-rotulo">` continua antes do campo, como hoje: os testes
e o `pedidos.js` (que acha `.campo-rotulo`) não mudam.

**Rationale**:

- O truque com o seletor de irmão (`input:placeholder-shown + label`) obrigaria a inverter a ordem do
  label e do campo em todos os formulários públicos, mexendo em markup que os testes conferem.
- O `:has()` existe no Chrome desde a versão 105, no Safari desde a 15.4 e no Firefox desde a 121,
  todos dentro dos alvos.
- Sem suporte, o rótulo flutuado na borda continua legível e correto.

**Alternatives considered**: JavaScript para marcar o campo preenchido (mais um script, e o estado
quebra quando o HTMX troca o trecho); rótulo fixo acima (a opção B da Q2, não escolhida).

**A conferir na entrega 3**:

- o destino é `input[list]`, que o `dropdown.js` monta como "campo com lista". É preciso confirmar que
  o campo visível continua dentro do `.campo` e que o `:placeholder-shown` vale nele;
- as observações (`obs`) não têm `<label>`: o rótulo é o título do passo (`aria-labelledby`). Elas
  ficam com a caixa nova, sem rótulo flutuante.

## R5. Chips de situação são rádios; chips com lista e menu ⋮ são `<details>` nativos

**Decision**:

- **Chips de situação**: rádios nativos estilizados como chip (`<input type="radio" name="situacao"
  class="chip-entrada">` dentro de `<label class="chip">`, num `<fieldset class="chips">` com a
  `legend` "Situação"). O estado é o `:checked`, desenhado pelo seletor de irmão
  (`.chip-entrada:checked + .chip-texto`), sem `:has()`. O `FiltrosPainel.situacao` passa a usar o
  `RadioSelect`.
- **Chips com lista** (Origem, SCPI, Recibo, Autorização, Período): `<details class="chip-menu"
  data-menu>`. O `<summary>` é o chip, e o painel mostra o mesmo campo do `FiltrosPainel` de hoje,
  montado pelo `dropdown.js`.
- **Menu ⋮**: `<details class="menu-acoes" data-menu>` com links.
- **`interface/js/menus.js`** (novo e pequeno): fecha o `details[data-menu]` aberto com Esc e com
  clique fora, e fecha os outros quando um abre.
- **O "Filtrar"** é o primeiro botão de envio do formulário e não tem `name`.
- **Estado depois da troca do HTMX**: o `filtros.js` atualiza os rótulos dos chips com lista
  ("Origem: Limpeza") e o `aria-current` dos indicadores a partir dos valores do formulário, a cada
  `change`. No painel, ele deixa de recolher o painel de filtros. No histórico de Automações, nada
  muda.

**Rationale**:

- **Botão de envio não guarda valor**: só manda o `name`/`value` no envio que ele dispara. Ao mudar
  outro filtro, a situação some. E o Enter num campo de texto envia pelo primeiro botão de envio do
  formulário, o que mandaria o valor do primeiro chip. O revisor confirmou que o HTMX 4 inclui o
  `submitter`, então o problema não é o HTMX: é o botão. O rádio guarda o valor em todo envio, e o
  `change` dele já está no gatilho.
- **O formulário é a fonte do que foi enviado**: a lista que volta foi filtrada pelos valores dele.
  Sincronizar a tela a partir do formulário dispensa trocar a barra de filtros pelo servidor (o
  `hx-swap-oob` existe no HTMX 4), que fecharia o painel aberto e tiraria o foco de quem digita.
- **Funciona sem JavaScript**: o `<details>` abre e fecha nativamente e pelo teclado, e o `summary` é
  focável. Isso cumpre a FR-009 e a FR-018a sem duplicar links. Cada envio sem JavaScript recarrega a
  página, e o servidor desenha o estado pela URL.

**Alternatives considered**:

- Botões de envio com um `input hidden name="situacao"` sincronizado por script: mais peças para o
  mesmo resultado, e sem script o valor se perde.
- Devolver a barra de filtros por `hx-swap-oob`: tiraria o foco e fecharia o chip aberto.
- Popover API: o suporte é recente demais para os iPhones antigos dos funcionários.

**A busca `q` fica fora do formulário** (FR-014): o formulário de filtros não pode envolver os
indicadores, porque o cartão do robô tem o próprio `<form method="post">` do "Lançar no SCPI", e o
navegador descarta o formulário aninhado (o botão passaria a enviar o GET dos filtros, sem lançar
nada). A busca liga-se ao formulário pelo atributo `form="filtros-painel"`. Como o `input` de um
campo fora do formulário não sobe até ele, o gatilho ganha `input delay:400ms from:#id_q`. O
revisor confirmou o `from:` no HTMX 4 vendorizado.

## R6. O menu continua a `app-lateral`, agora estreito

**Decision**: acima de 1286px, a `app-lateral` vira o menu estreito: 88px de largura, ícone sobre
rótulo e, no item atual, o ícone dentro da pílula tonal. A marca vira só o ícone. A conta (nome,
matrícula e "Sair") fica no pé, compacta: um círculo com as iniciais, com o nome e a matrícula no
`title` e no texto para o leitor de tela, e o botão "Sair" só com ícone e `aria-label`. Até 1286px,
vale o cabeçalho com o botão de menu de hoje (`shell.js` sem mudança), com o menu aberto em lista
larga e todos os destinos.

**Altura**: com a spec 014, o menu tem 7 destinos para a equipe. Cada item ocupa cerca de 51px (a
pílula de 32px, 4px e o rótulo de uma linha). Com 4px entre itens, a marca e a conta, o menu pede
cerca de 560px. A 1366×768, a janela do navegador tem por volta de 650px úteis: cabe, mas com pouca
folga. Por isso a lista de destinos tem `overflow-y: auto`, e a marca e a conta ficam presas em cima e
embaixo. Um destino a mais nunca some; no pior caso, a lista rola. A captura a 1366×650 confere.

**Ícone de Compras**: o item usa hoje o `caixa`, o mesmo da marca, que no menu estreito é só o
ícone. Passa a `caminhao` (o `truck` do Lucide), do recebimento das compras.

**Rationale**: as classes e o `shell.js` continuam iguais, então o teste
`test_menu_com_icone_e_botao_acessivel` segue valendo com o contador posto depois do ícone. O protótipo
punha uma barra no celular que escondia destinos (corrigido na spec).

**Alternatives considered**: barra de navegação embaixo no celular (6 ou 7 destinos não cabem sem um
"Mais"); manter a barra larga (perde a largura útil que motivou a troca).

## R7. Contadores do menu: preguiçosos, uma vez por requisição, em `interface`

**Decision**: o context processor `interface.navegacao.menu` põe no item Painel o número de pedidos
aguardando atendimento, e no item Automações o das travas a conferir, só para quem pode abrir cada
item. Os números vêm de `interface.navegacao.contadores(request)`, que guarda **as parcelas** na
própria requisição:

| Parcela | Fonte | Quem usa |
|---|---|---|
| pedidos aguardando | `filtrar_situacao(Pedido.objects.all(), "aguardando").count()` | contador do Painel e cartão de atendimento |
| requisições travadas (como hoje) | `contar_lotes_travados()` | nota do cartão do robô |
| requisições a conferir | lotes distintos com linha em `VERIFICAR` ou `ERRO`, mais os com `EM_LANCAMENTO` quando não há execução de saídas em andamento (`contar_lotes_travados(com_em_lancamento=…)`, parâmetro novo; o lote com linhas nos dois estados conta uma vez) | contador de Automações |
| recebimentos travados | `compras.consultas.contar_recebimentos_travados()` (nova): `Recebimento` em `VERIFICAR` ou `ERRO`, mais `EM_LANCAMENTO` quando não há execução de entradas em andamento | contador de Automações |

- **Contador de Automações** = requisições travadas (`VERIFICAR` e `ERRO`, mais `EM_LANCAMENTO` quando
  o robô de saídas não está rodando) + recebimentos travados (mesma regra, com o robô de entradas).
  Durante uma execução, o "em lançamento" é o robô trabalhando, não uma trava, e o contador
  acenderia em toda página enquanto ele roda.
- **O cartão do robô no painel não muda**: conta as travadas como hoje (`contar_lotes_travados`, que
  inclui o `EM_LANCAMENTO` sempre). Durante uma execução, o cartão pode mostrar "1 para conferir"
  enquanto o menu mostra 0 em Automações. É a diferença de propósito entre os dois: o cartão é o
  painel do robô, o contador é o aviso de pendência.
- **Custo**: até quatro contagens por página inteira (a de pedidos aguardando, as duas das saídas e a dos recebimentos), e a conferência da execução em andamento (a
  `ExecucaoRobo.em_andamento`, que usa `IS_USED_LOCK`) só roda quando há algo em `EM_LANCAMENTO`. A
  view do painel lê as mesmas parcelas da memória e não conta duas vezes. Os valores são
  preguiçosos: nada roda se o template não desenhar o menu, e os trechos do HTMX não desenham.
- **Lugar**: em `interface/navegacao.py`, que já é a camada de apresentação e já importa
  `contas.acesso`. Lá, as importações de `pedidos.consultas` e `compras.consultas` ficam dentro da
  função. Hoje `compras` depende de `pedidos`, e uma função em `pedidos.consultas` que importasse
  `compras` inverteria a direção.

**Rationale**: as contagens já existem ou são um `count` simples, baratas no volume atual. O usuário
decidiu (2026-11-13) que o contador conta só o que exige ação.

**Alternatives considered**:

- Contadores só no painel: o menu mostraria número numa página e não na outra.
- Cache com tempo de vida: número velho num menu que manda agir.
- Contar o `EM_LANCAMENTO` sempre, como o cartão: contador aceso em toda página durante cada
  execução.

## R8. "Imprimir recibo" pela lista: `?imprimir=1` no detalhe

**Decision**:

- O item do ⋮ leva a `pedidos:detalhe` com `?imprimir=1`.
- **Quando imprime**: o servidor marca o botão `[data-imprimir]` com `data-imprimir-ao-abrir` só
  quando o pedido tem atendimento e o recibo ainda não foi impresso (`recibo_impresso_em` nulo).
- **No navegador**: o `pedidos.js` aciona esse botão uma vez, no evento `load` (com as fontes
  carregadas), e tira o parâmetro da barra com `history.replaceState(history.state, "",
  url_sem_imprimir)`, sem apagar o estado de histórico do HTMX.
- **A volta da confirmação**: o campo `voltar` do diálogo "O recibo saiu na impressora?" passa a
  levar a URL sem o `imprimir`. Hoje ele é o `request.get_full_path`, e o `marcar_impressos`
  redireciona para ele.
- **Depois da impressão**: o `afterprint` de hoje abre a confirmação.
- **Sem JavaScript**: o detalhe só abre. O botão de imprimir fica escondido sem JavaScript, como hoje,
  e nada é impresso nem marcado.

**Rationale**: reusa o fluxo de impressão e de confirmação de hoje, sem rota nova nem gravação nova.
A marcação de impresso continua exigindo a confirmação da pessoa (FR-018a). Sem o `voltar` limpo, a
confirmação voltaria a `?imprimir=1` e imprimiria de novo, agora sem o diálogo: o revisor achou esse
laço.

**Risco**: o navegador pode recusar o `window.print()` sem um gesto da pessoa. No Chrome e no Edge do
almoxarifado, ele é aceito no carregamento; se algum recusar, o detalhe abre com o botão em foco e
nada se perde. Conferir no quickstart (Q-2.6).

**Alternatives considered**: imprimir num `iframe` escondido a partir da lista (outra página de
impressão para manter, e a confirmação teria de morar na lista); marcar como impresso direto da lista
(proibido pela FR-018a).

## R9. "O mais antigo há N dias": função pura e uma agregação

**Decision**:

- `consultas.envio_mais_antigo_aguardando()` devolve o menor `criado_em` entre os pedidos de
  `filtrar_situacao(..., "aguardando")`, numa agregação `Min`, ou `None`.
- `regras.texto_envio_mais_antigo(data_envio, hoje)` (pura) devolve "enviado hoje", "enviado ontem"
  ou "há N dias", com os dias de calendário entre `data_envio` e `hoje`.
- A view passa `timezone.localdate()` e a data local do envio.

**Rationale**: é o mesmo conjunto que o cartão já conta, e a regra do texto se testa sem banco
(Princípio I).

**Alternatives considered**: horas corridas ("há 30 h") são menos legíveis para a equipe; dias úteis
exigiriam um calendário que o sistema não tem.

## R10. "+N aguardando autorização"

**Decision**: `consultas.contar_aguardando_autorizacao()` conta os pedidos com
`autorizacao__situacao=AGUARDANDO`, a mesma condição do filtro Autorização. O link leva a
`?autorizacao=aguardando`. Some com zero.

**Rationale**: reusa o filtro que já existe; nenhum número novo.

## R11. Requisições travadas: o que já existe

**Decision**: nada muda na regra nem no link. O cartão de hoje já mostra "N para conferir", com o
link para `automacoes:pagina?aba=lancamento#travas`. A entrega 2 só o reestiliza como a nota de alerta
do indicador. A spec foi alinhada a isso (FR-018c).

## R12. Selos com ícone, pelo tom e no CSS

**Decision**: o ícone do selo vem do **tom** e é desenhado pelo CSS, no `::before` do `.selo`, com
`mask-image` de um SVG do Lucide em `data:` URI. Não há arquivo externo. A cor é o `currentColor` do
selo.

| Tom | Ícone |
|---|---|
| `selo-ok` | `check` |
| `selo-aviso` | `alerta` em triângulo |
| `selo-erro` | `alerta` em círculo |
| `selo-info` | `info` |
| `selo-neutro` | nenhum |

Detalhes da regra:

- **Selo com ícone próprio**: o selo que já traz o ícone no markup (`.selo:has(svg)`, como o "N no
  pedido") não ganha o segundo. Os templates não mudam.
- **Selo das abas** (`aba-selo`): hoje ele esconde o próprio `svg` na tela larga e mostra só o texto.
  Com a regra, ficaria sem ícone nenhum. Passa a mostrar o `svg` em toda largura, com o texto ao lado
  na tela larga.
- **Selo informativo usado como rótulo** ("Adicionado pelo almoxarifado", `selo-info`): ganha o
  ícone `info`. É coerente com o tom, e no papel o ícone some (abaixo).
- **Impressão**: `@media print { .selo::before { display: none } }`. O recibo sai como hoje (FR-010).
- **Compatibilidade**: `mask-image` e `-webkit-mask-image`, os dois.

**Rationale**:

- Com a spec 014 há selos em 36 templates, e vários decidem a cor por condição no próprio template
  (`compras/_estado.html`, `compras/_status.html`, os vereditos de compras e de conciliação). Um ícone
  por estado exigiria mexer em todos e criar um mapa para cada domínio; a entrega 1 deixaria de ser
  só de CSS.
- Pelo tom, um lugar só cobre o sistema inteiro, inclusive as telas futuras, e o ícone nunca
  contradiz a cor.
- A palavra continua lá (FR-004); o ícone é reforço, `aria-hidden` por ser pseudo-elemento.

**Alternatives considered**:

- Um ícone por estado (relógio em "Aguardando", meio círculo em "Parcial"), como no protótipo: mais
  expressivo, mas 36 templates e um mapa por domínio. Fica possível depois, selo a selo, porque
  `.selo:has(svg)` já respeita o ícone posto no markup.
- Filtros `icone_*` só em `pedidos`: deixaria de fora compras, conciliação e Automações (F13).

**Ícones novos no `_icone.html`**: `kebab`, `calendario`, `documento` e `caminhao`. O `metade` e o
`proibido` da primeira versão deste plano saem: serviam só aos ícones por estado.

## R13. Densidade do painel (SC-004)

**Decision**:

- No ritmo compacto, as células da tabela mantêm o recheio de hoje (`--celula-v` 10px).
- A segunda linha (origem, recebeu, centro) usa a fonte pequena.
- Os indicadores, com recheio de 16px e número de 28px, ficam numa grade de 4 colunas.
- O cartão "Atalhos" sai, e com ele o título e a moldura.

Antes da entrega 2, a contagem de linhas visíveis a 1366×768 é medida no painel atual e anotada no PR.

**Rationale**: o protótipo usava o ritmo público (linhas de 64px). No ritmo compacto, a troca do
cartão de atalhos pelos indicadores libera altura para a tabela.

## R14. Capturas de tela fora da suíte

**Decision**: `scripts/capturar_telas.py` (com `uv run python`) abre o servidor de desenvolvimento
já no ar, entra com um usuário de teste e captura as telas da lista (`contracts/componentes.md`, seção
"Telas-chave") a 320, 375, 768, 1280 e 1440px, com `deviceScaleFactor` 1. As imagens vão para uma
pasta ignorada pelo Git, e o script avisa toda tela com rolagem lateral (SC-002). Ele não entra no
`pytest`.

**Rationale**: a constituição proíbe teste com navegador, mas a revisão visual precisa de capturas
iguais em toda entrega. O Playwright já é dependência do projeto (robôs do SCPI).

**Alternatives considered**: regressão visual automática com comparação de pixels (frágil com
fontes e antialiasing, e exigiria o navegador na suíte); capturas à mão (sem padrão, ninguém repete).

## R15. Contraste verificado por teste, sobre as combinações declaradas

**Decision**: o `docs/DESIGN.md` declara as combinações de texto e fundo permitidas (a tabela
"Combinações" de `contracts/tokens.md`). O teste `tests/test_contraste_tokens.py` lê o bloco `:root` de
`fundacao.css` e confere cada combinação declarada: 4,5:1 no texto e 3:1 em contorno de controle,
ícone de estado e foco, com a fórmula da WCAG 2.1. Roda sem banco.

Combinações que o cálculo reprovou e por isso ficam **proibidas**, declaradas no `DESIGN.md`:

| Combinação | Contraste |
|---|---|
| `--destaque` sobre `--destaque-superficie` | 4,14:1 |
| `--destaque` sobre `--secundario-superficie` | 4,17:1 |
| `--texto-suave` sobre `--secundario-superficie` | 4,41:1 |
| `--texto-suave` sobre `--superficie-maxima` | 4,29:1 |

Sobre os contêineres, o texto usa o `-texto` do próprio contêiner, e o texto suave não é usado.

**Rationale**: "todos os pares" não tem como ser conferido, porque nem todo par é usado. A lista
declarada é a regra que quem desenha segue, e o teste garante que ela continua passando quando um
token mudar.

## R16. Documentação, skill e constituição na entrega 1

**Decision**:

- **Constituição 2.2.0** (decisão do usuário): o Princípio VI passa a dizer "A interface segue o
  design system do projeto (`docs/DESIGN.md`)". As demais linhas do princípio não mudam. Pela regra de
  versão (MAJOR para princípio "redefinido de forma incompatível", MINOR para "acrescentado ou
  ampliado"), é uma redefinição **compatível**: nenhuma garantia cai, e a referência fica mais geral.
  O relatório de impacto do topo do arquivo registra esse motivo e a spec 015.
- **`docs/DESIGN.md`**: reescrito com os tokens, as combinações de contraste permitidas e proibidas
  (R15), o vocabulário (o que fica, o que muda, o que entra), os componentes novos, as regras que
  continuam e o passo a passo de "Tela nova". Cada componente novo traz a entrega em que passa a
  existir (por exemplo, "indicador: entrega 2"), para o documento não descrever o que ainda não está
  no código.
- **Skill**: a `.claude/skills/design-tonal/` (o nome "Tonal" vem das superfícies tonais do M3)
  substitui a `.claude/skills/clean-design/`, que sai e fica no histórico do Git.
- **`CLAUDE.md`**: a regra das três skills passa a nomear a `design-tonal`, e a seção da interface
  troca `clean.css` por `fundacao.css` e Clean por Tonal.
- **`CLAUDE.md` nas outras entregas**: a 2 descreve o menu estreito, os contadores, os chips de rádio
  e o `?imprimir=1`; a 3 troca "o placeholder do destino" (`Fluxo.exemplo_destino`, parágrafo da spec
  007) por "o texto de apoio do destino".

**Rationale**: a governança manda a emenda e os documentos afetados no mesmo PR, e a entrega 1 é a
que muda o estilo. Uma skill desatualizada geraria telas Clean nas entregas seguintes e na spec 014.
