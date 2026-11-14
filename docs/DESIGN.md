# Design do Central Almoxarifado — Tonal

A interface segue o design system **Tonal**: a linguagem visual do Material 3 (superfícies tonais,
contêineres de cor, raios maiores, pílulas, chips e elevação) sobre o CSS do próprio projeto,
escrito à mão, sem biblioteca. O nome vem das superfícies tonais do M3. A skill de estilo é
`.claude/skills/design-tonal/`; este arquivo é a referência normativa e vence a skill onde
discordarem. A troca do Clean para o Tonal é a spec `specs/015-design-system-m3/` (contratos em
`contracts/`, protótipos em `prototipos/`). Continuam as decisões de antes: só tema claro, dois
ritmos, nada de seções de landing page nem *scroll reveal*.

Alguns componentes ainda não existem no código: a spec 015 sai em quatro entregas, e cada um
traz a entrega em que passa a existir ("entrega 2"). Não use o que ainda não entrou.

## Arquivos

| Arquivo | O que tem |
|---|---|
| `interface/static/interface/css/fundacao.css` | `@font-face`, tokens (`:root`), reset, tipografia, foco, utilitários e ritmos |
| `interface/static/interface/css/componentes.css` | botões, campos, cartões, selos (com o ícone pelo tom), avisos, tabela, paginação, filtros, passos, materiais, carrinho, vazio, dados, ações |
| `interface/static/interface/css/layouts.css` | layout público, casca do almoxarifado, menu móvel e impressão |
| `interface/templates/interface/_icone.html` | ícones SVG inline (Lucide) |
| `interface/static/interface/fonts/` | Geist, DM Sans e Geist Mono em `.woff2`, com as licenças OFL |
| `pedidos/…/pedidos.css`, `catalogo/…/catalogo.css`, `contas/…/entrar.css` | só o que é próprio de cada app |

Nenhum CSS de app redefine componente comum: se faltar algo, ele entra em `componentes.css`.
Nenhuma cor fora dos tokens: no CSS de tela só `var(--…)` (transparência com
`color-mix(in srgb, var(--token) N%, transparent)`). As cores fixas só aparecem na impressão.

## Tokens

Os valores e o contraste de cada par estão em `specs/015-design-system-m3/contracts/tokens.md`.
`tests/test_contraste_tokens.py` lê o `:root` de `fundacao.css` e confere as combinações abaixo.

### Cores

| Token | Valor | Uso |
|---|---|---|
| `--fundo` | `#FFFFFF` | fundo da página, campos, tabela, cartão |
| `--superficie` | `#F5F6FA` | superfície baixa: fundo da área interna, passos, linha em hover, linha aberta |
| `--superficie-media` | `#EEF0F5` | cartão sutil, aba não selecionada, indicadores, "Seu pedido" (entrega 3) |
| `--superficie-alta` | `#E8EAF0` | hover de controle tonal, busca em pílula |
| `--superficie-maxima` | `#E1E4EB` | pressionado, hover do botão suave e do chip |
| `--texto` | `#1A1C21` | texto principal |
| `--texto-secundario` | `#4A4D57` | rótulos, cabeçalho de tabela, segunda linha, apoio |
| `--texto-suave` | `#666975` | datas, dicas, contagens (AA em branco e na `--superficie-media`) |
| `--borda` | `#E2E4EA` | divisórias e contorno decorativo de cartão (nunca o único limite de um controle) |
| `--contorno` | `#7A7D88` | limite de controle: campo, botão de contorno, quantidade, caixa de marcar (3:1) |
| `--destaque` | `#2563EB` | botão cheio, link, foco, barra da aba ativa |
| `--destaque-hover` | `#1D4ED8` | hover do botão cheio |
| `--destaque-texto` | `#FFFFFF` | texto sobre o destaque |
| `--destaque-superficie` | `#DCE6FF` | contêiner tonal azul: selo info, ícone do cartão de opção, hover do botão de texto |
| `--destaque-superficie-texto` | `#0F2A6B` | texto e ícone sobre `--destaque-superficie`; texto da aba ativa |
| `--secundario-superficie` | `#E2E7F3` | botão suave, chip selecionado, item atual do menu, página atual da paginação, opção marcada do dropdown |
| `--secundario-superficie-texto` | `#1B2540` | texto sobre `--secundario-superficie` |
| `--ok-superficie` / `--ok-texto` | `#D8F0DE` / `#1D5E30` | status ok |
| `--aviso-superficie` / `--aviso-texto` | `#FCEBC9` / `#6A4600` | status aviso |
| `--erro-superficie` / `--erro-texto` | `#FBE3E1` / `#8C1D17` | status erro |
| `--erro-forte` | `#B3261E` | borda, rótulo e texto do campo com erro; contorno do botão de perigo |
| `--info-superficie` / `--info-texto` | `--destaque-superficie` / `--destaque-superficie-texto` | status informação |
| `--neutro-superficie` / `--neutro-texto` | `#ECEDF2` / `#4A4D57` | status neutro |

Nenhum gradiente (a máscara que esmaece a lista de abas não é cor).

### Combinações permitidas

Só estas combinações de texto (ou elemento) sobre fundo. Combinação fora da lista não é usada.

| Frente / fundo | Mínimo |
|---|---|
| `--texto` sobre `--fundo` e sobre `--superficie-alta` | 4,5:1 |
| `--texto-secundario` sobre `--fundo` e sobre `--superficie-alta` | 4,5:1 |
| `--texto-suave` sobre `--fundo` e sobre `--superficie-media` | 4,5:1 |
| `--destaque` sobre `--fundo` (link) | 4,5:1 |
| `--destaque-texto` sobre `--destaque` | 4,5:1 |
| `--destaque-superficie-texto` sobre `--destaque-superficie` | 4,5:1 |
| `--secundario-superficie-texto` sobre `--secundario-superficie` | 4,5:1 |
| cada `--*-texto` de status sobre a própria `--*-superficie` | 4,5:1 |
| `--erro-forte` sobre `--fundo` | 4,5:1 |
| `--contorno` sobre `--fundo` e sobre `--superficie` (limite de controle) | 3:1 |

O que vale para `--superficie-alta` vale para as superfícies mais claras (`--superficie`,
`--superficie-media`).

### Combinações proibidas

Reprovam no cálculo (o teste confere que continuam reprovadas):

| Combinação | Contraste | Use em vez disso |
|---|---|---|
| `--destaque` sobre `--destaque-superficie` | 4,14:1 | `--destaque-superficie-texto` |
| `--destaque` sobre `--secundario-superficie` | 4,17:1 | `--secundario-superficie-texto` |
| `--texto-suave` sobre `--secundario-superficie` | 4,41:1 | `--secundario-superficie-texto` |
| `--texto-suave` sobre `--superficie-maxima` | 4,29:1 | `--texto-secundario` |

Sobre um contêiner, o texto usa o `-texto` do próprio contêiner, nunca o texto suave.

### Forma, elevação, espaço e movimento

| Token | Valor | Uso |
|---|---|---|
| `--raio-campo` | 4px | caixa do campo, caixa de marcar |
| `--raio-selo` | 6px | selo |
| `--raio-controle` | 8px | chip, item de lista |
| `--raio-cartao` | 16px | cartão, aviso, aba, painel flutuante |
| `--raio-bloco` | 28px | diálogo; passo, "Seu pedido" e gaveta (entrega 3) |
| `--raio-pilula` | 100px | botões, botão suave, quantidade, paginação, item do menu |
| `--sombra-cartao` | elevação 1 | hover do botão cheio |
| `--sombra-hover` | hover de cartão clicável | cartão de opção |
| `--sombra-elevada` | elevação 3 | painel flutuante, diálogo, gaveta, dica, botão flutuante |
| `--anel-foco` | 2px de fundo + 2px de destaque | foco (`:focus-visible`) |
| `--transicao` | `0.15s ease` | hover, foco, abrir e fechar |

- **Espaço:** múltiplos de 8 (`--esp-1` = 8px até `--esp-16` = 128px); `--esp-meio` = 4px para
  ajuste fino.
- **Cartão sem sombra:** o cartão é o de contorno do M3 (borda `--borda`); a elevação fica para o
  que flutua.

## Tipografia

- **Geist** 600/700 nos títulos, tracking -0.02em.
- **DM Sans** 400/500/600 no texto, entrelinha 1.6.
- **Geist Mono** 400/500 em CADPRO, Nº, placa, matrícula e requisição (classe `.mono`).
- Rótulo de seção (`.rotulo-secao`): DM Sans 500, 12px, maiúsculas, tracking 0.08em, cor suave.
- Cabeçalho de tabela: DM Sans 500, 13px, em `--texto-secundario`, sem maiúsculas.
- As fontes são servidas do próprio sistema, com `font-display: swap`. Nada de Google Fonts ou
  CDN. Nunca Inter, Roboto, Arial ou system-ui.

## Ritmos

Os mesmos tokens em duas densidades, escolhidas pela classe do `<body>`:

| | `.ritmo-publico` | `.ritmo-almox` |
|---|---|---|
| Corpo | 17px | 15px |
| H1 | `clamp(32px, 5vw, 48px)` | 24px |
| Recheio do cartão | 32px | 24px |
| Entre blocos | 48px | 24px |
| Célula de tabela | 12px/16px | 10px/12px |
| Altura do controle (e área de toque mínima) | 48px | 44px |
| Altura do campo (`--altura-campo`) | 56px (campo flutuante, entrega 3) | a do controle |

## Vocabulário de classes

Use estes nomes, e nenhum outro para essas funções. A classe que existe continua com o mesmo nome e
a mesma função; renomear exige motivo no PR e o ajuste dos scripts e testes no mesmo PR.

| Função | Classes |
|---|---|
| Ritmo (no `<body>`) | `ritmo-publico`, `ritmo-almox` |
| Texto | `rotulo-secao`, `texto-secundario`, `texto-suave`, `texto-pequeno`, `mono`, `visually-hidden` |
| Pilhas e grades | `pilha`, `pilha-larga`, `grade-2`, `grade-saida` (+ `grade-saida-largo`, duas colunas nas quatro; `grade-saida-linha`, linha toda nas duas; `grade-saida-cheio`, linha toda nas quatro; dentro de `saida-campos`: colunas pela largura do bloco), `linha` |
| Botões | `botao` (pílula) + `botao-primario` (cheio em `--destaque`), `botao-secundario` (contorno em `--contorno`; com as cores `botao-destaque` azul, `botao-perigo` vermelho e `botao-ok` verde), `botao-texto` (sem fundo, hover tonal azul), `botao-icone` (círculo com a área de toque da altura do controle), `botao-bloco` |
| Campos | `campo`, `campo-rotulo` (fixo acima na área interna), `campo-entrada` (contorno `--contorno`, raio de 4px, foco com borda de 2px em azul), `campo-dica`, `campo-erro` (com o ícone de alerta), `campo-com-erro` (borda, rótulo e texto em `--erro-forte`), `campo-check`, `campo-check-caixa`, `campo-rotulo-linha`, `campo-nota`, `campo-linha`, `campo-busca`; `campo-flutuante` (rótulo flutuante dos formulários públicos: entrega 3) |
| Diálogo de confirmação | `dialogo-confirmacao` (`<dialog>` modal, raio de 28px, com `open` no HTML: sem JavaScript fica à vista como aviso), `dialogo-confirmacao-corpo`, `-texto`, `-titulo`, `-acoes`; `data-abrir-dialogo="id"` no botão que o abre (vem `hidden`), `data-fechar-dialogo` no que fecha, como `type="submit" formmethod="dialog"` (fecha também sem JavaScript, sem enviar o formulário; `interface/js/dialogo.js`; o fundo e o Esc também fecham). Foco inicial em `autofocus`: no botão seguro (Cancelar) quando a ação é destrutiva. Usos: "O recibo saiu na impressora?" (`data-apos-imprimir`, aberto pelo `pedidos.js` depois de imprimir) e "Restaurar a regra padrão?" |
| Botão suave | `botao-suave` (tonal, em `--secundario-superficie`, pílula, com ícone; ação secundária) e, dentro de um campo, `com-acao` em volta dele + `acao-campo` (à esquerda da seta do dropdown) |
| Cartões | `cartao` (branco, borda `--borda`, raio de 16px, sem sombra), `cartao-titulo`, `cartao-sutil` (`--superficie-media`, sem borda), `cartao-opcao` (o ícone num quadrado tonal de 48px) |
| Abas | `abas` (`[data-abas]`, com `data-url`), `abas-lista` (`role="tablist"`), `aba` + `aba-ativa` (`role="tab"`, `data-aba`), `aba-painel` + `aba-painel-ativo` (`role="tabpanel"`, `id="painel-<chave>"`); `interface/js/abas.js`, na base. Pasta: a aba ativa é branca, com a barra azul em cima e o texto tonal, e se funde ao primeiro `cartao` do painel (filho direto, ou primeiro filho do primeiro filho); as outras ficam em `--superficie-media`; os demais cartões ficam soltos embaixo. Estado de cada aba em `selo aba-selo` dentro dela, com o ícone (`alerta`, ou `atualizar` em andamento) em toda largura e o texto em `aba-selo-texto`: na tela larga o texto aparece ao lado do ícone; abaixo de 1024px, só o ícone, e o texto fica para o leitor de tela. Abas que não cabem rolam de lado com encaixe no começo de cada aba, e a borda do lado em que a lista continua esmaece (`data-mais-inicio`/`data-mais-fim`, marcados pelo `abas.js`). Link para outra aba da página: `data-abrir-aba="<chave>"` com `href="?aba=<chave>"`. Sem JavaScript, os painéis ficam empilhados |
| Selos | `selo` + `selo-ok`, `selo-aviso`, `selo-erro`, `selo-info`, `selo-neutro` (ícone pelo tom: ver "Selos") |
| Avisos | `aviso` + `aviso-ok`, `aviso-atencao`, `aviso-erro`, `aviso-info` (contêiner de status com raio de 16px; o ícone vai no markup) |
| Tabela | `tabela-rolagem` (sempre em volta da `tabela`), `tabela`, `tabela-data`, `tabela-vazia` |
| Paginação | `paginacao`, `paginacao-resumo`, `paginacao-lista`, `paginacao-link` (pílula), `paginacao-atual` (tonal, em negrito), `paginacao-desativado`, `paginacao-reticencia`, `paginacao-larga`, `paginacao-compacta` |
| Dica flutuante | `dica-flutuante` (contêiner do controle) + `dica-flutuante-texto` (`role="tooltip"`, ligado ao controle por `aria-describedby`; aparece com o cursor, o toque ou o foco, também em botão desabilitado); `dica-flutuante-fim` no contêiner alinha a dica ao fim (borda direita) do controle |
| Filtros | `filtros`, `filtros-campo`, `filtros-acoes`; recolhíveis (`filtros.js`, `form[data-filtros]`, histórico de Automações): `filtros-recolhiveis`, `filtros-barra`, `filtros-busca`, `filtros-alternar` (+ `filtros-contagem`, `filtros-seta`), `filtros-limpar`, `filtros-chips`, `filtros-chip` (chip tonal do filtro ativo), `filtros-painel`, `filtros-grade`, `filtros-periodo`; em chips, sempre à vista (`filtros.js`, `form[data-filtros-estado]`, painel de pedidos): `filtros-chips-barra`, `filtros-linha`, `filtros-material`, `filtros-linha-acoes`, `filtros-enviar` (o "Filtrar", primeiro botão de envio, escondido com JavaScript); a busca em pílula do cabeçalho: `busca-cabecalho` + `campo-busca campo-busca-pilula`, fora do formulário e ligada a ele pelo atributo `form` |
| Indicadores | `indicadores` (`section`, `aria-label`), `indicador` (`--superficie-media`, raio de 16px, `data-indicador`), `indicador-critico` (barra `--erro-forte` à esquerda), `indicador-link` (cobre o cartão, primeiro filho; `aria-current="true"` com o filtro aplicado: contorno `--destaque` e "· filtro aplicado" no rótulo), `indicador-rotulo`, `indicador-numero` (34px), `indicador-notas` + `indicador-nota`, `indicador-nota-link` (texto escuro sublinhado, nunca o azul sobre o tonal), `indicador-nota-alerta` (`--aviso-*`), `indicador-acao` (acima do link; botões de 36px com área de toque de 44px). Cartão com formulário próprio (o "Lançar no SCPI") nunca fica dentro de outro formulário |
| Chips de rádio | `chips` (o `fieldset`, com `legend` escondida), `chip` (o `label`), `chip-entrada` (o rádio, fora do desenho e focável), `chip-texto` (32px de desenho, 44px de toque; o marcado em `--secundario-superficie`, com o `check`, pelo seletor `.chip-entrada:checked + .chip-texto`); chip com lista: `chip-menu` (`details[data-menu]`), o `summary` com `chip` (+ `chip-ativo` com valor) e `chip-menu-rotulo` (`data-chip-nome`, "Origem: Limpeza"), `chip-menu-painel` (+ `painel-flutuante`) |
| Menu de ações | `menu-acoes` (`details[data-menu]`, com `interface/js/menus.js`; acima do link que cobre a linha), `menu-acoes-botao` (o `summary`, `botao botao-icone` com `aria-label` e o ícone `kebab`), `menu-acoes-lista`, `menu-acoes-item` (44px), `menu-acoes-acima` (abre para cima: as duas últimas linhas de uma página com 5 ou mais); `tabela-rolagem-curta` na tabela com menos de 5 linhas (altura do menu aberto) |
| Botão flutuante | `fab` (`--destaque-superficie`, raio de 16px, `--sombra-elevada`, com `nao-imprimir`); a página ganha `pagina-com-fab` para nada ficar coberto no fim |
| Passos | `passo`, `passo-numero`, `passo-cabecalho`, `passo-corpo` (no tablet da área interna, o número fica ao lado do título e o corpo usa a largura toda) |
| Materiais | `lista-materiais`, `material`, `material-bloqueado`, `material-dados`, `material-acao`, `quantidade` (pílula com contorno), `quantidade-campo`, `botao-adicionado` ("Adicionado" por 2 s); adicionar em dois passos (formulários públicos e saída avulsa; o painel do atendimento adiciona direto): `material-abrir` (botão transparente sobre a linha), `material-mais` ("+"), `material-no-pedido` (selo `selo selo-info` com o próprio ícone, com `selo-pulso` por 2 s ao confirmar), `material-qtd`, `material-cancelar`, estado `aberto` no `[data-adicionar]`; com um aberto, as outras linhas recuam; na saída avulsa, o de/para: `material-substitui` e `material-alerta` (aviso compacto dentro da linha; dois ou mais antigos em `material-alerta-lista`) |
| Pedido (formulários de carrinho) | `pedido-layout` (container query), `pedido-grade` (passos + coluna do pedido lado a lado a partir de 960px de largura), `pedido-passos`, `pedido-lado`, `pedido-resumo` (cartão fixo ao rolar, com o botão de envio em `pedido-enviar`), `acoes-final` (o envio do fim do formulário, só quando o pedido está na gaveta); `pagina-larga` no `<body>` alarga o formulário público para 1080px a partir de 1024px |
| Busca de materiais | `busca-area`, `busca-principal` (campo em destaque), `busca-painel` (`#resultados`, painel no fluxo da página, logo abaixo da busca, em qualquer tela: o cartão do passo cresce com ele, a página rola para a busca subir e a altura é a do cabeçalho e de 5 linhas) |
| Painel flutuante (base) | `painel-flutuante` (casca, raio de 16px e `--sombra-elevada`; estados `aberto` e `fechando`) |
| Dropdown | `dropdown` (envolve o campo), `dropdown-gatilho`, `dropdown-valor`, `dropdown-seta`, `dropdown-combo`, `dropdown-painel`, `dropdown-lista`, `dropdown-grupo`, `dropdown-opcao`, `dropdown-texto`, `dropdown-check`, `dropdown-sem-opcoes`; montados pelo `dropdown.js` |
| Resultados | `resultados-vazio` ("Nenhum material encontrado."; o painel não tem legenda); `material-info` (linha de baixo do material) |
| Carrinho | `carrinho`, `carrinho-barra` (fixa), `carrinho-gaveta` (`<dialog>` sempre que o pedido cairia embaixo da busca: `data-gaveta` no `<html>`; bloco azul ao lado da busca nos demais casos), `carrinho-lista`, `carrinho-linha`, `carrinho-linha-erro`; nos formulários públicos e na saída avulsa, `carrinho-barra-contagem`, `carrinho-barra-vazia`, `carrinho-acoes-gaveta` e a quantidade em dois passos (`carrinho-qtd-texto`, `carrinho-qtd-area`, `carrinho-confirmar`, `carrinho-cancelar`, `carrinho-remover`; a linha toda é o `material-abrir`; estado `aberto` no `[data-alterar]`) |
| Folha (formulário com lista fixa, spec 006) | `folha-chamada`, `folha` (`<dialog>`: tela cheia abaixo de 640px, painel centrado com rolagem acima), `folha-corpo`, `folha-cabecalho`, `folha-titulo`, `folha-lista` (`<ol>`), `folha-linha` (+ `folha-linha-bloqueada`, `folha-linha-erro`), `folha-material`, `folha-qtd`, `folha-motivo`, `folha-erro`, `folha-acoes`; o resumo de erros é o `resumo-erros` |
| Envio recusado (formulário público) | `resumo-erros` (+ `resumo-erros-titulo`, focável, com link para o campo), `campo-com-erro` + `campo-erro` com ícone embaixo do campo; `botao-esquecer` ("Não é você? Limpar"); `sucesso-itens` (lista da tela de sucesso) |
| Recibo e atendimento | `recibo-grupo` (linha de grupo da tabela de materiais: "Pedido pelo solicitante" e o selo `selo-info` "Adicionado pelo almoxarifado", só com material acrescentado), `recibo-nota` ("Trocado por …", "No lugar de …"), `atendimento-painel` (+ `atendimento-painel-titulo`; painel de busca da troca e do acréscimo) |
| Vazio | `vazio`, `vazio-titulo` |
| Dados | `dados` (`<dl>` em grade de rótulo e valor) |
| Ações | `acoes` |
| Layout público | `publico-topo`, `publico-topo-interno`, `publico-conteudo`, `publico-cabecalho`, `publico-sub`, `publico-rodape`, `marca`, `link-discreto` |
| Casca do almoxarifado | `app`, `app-lateral`, `app-lateral-topo`, `app-lateral-painel`, `app-menu`, `app-menu-item` (pílula; o atual em `--secundario-superficie`, em negrito, com `aria-current="page"`), `app-menu-botao`, `app-conta`, `app-principal`, `pagina-cabecalho`, `pagina-sub`, `pagina-acoes`, `link-voltar`. Acima de 1286px, o menu estreito de 88px: ícone sobre rótulo, o atual com o ícone na pílula tonal de 56×32, a lista rolando com a marca (só o ícone) e a conta presas; `app-menu-contador` depois do ícone (número `aria-hidden`, texto escondido ", 2 para atender"); `app-conta-avatar` (iniciais, ou o ícone `usuario` sem nome; nome e matrícula no `title` e em `app-conta-dados`, escondido no menu estreito), `app-conta-sair` (só o ícone no menu estreito, com `aria-label`). Até 1286px, o cabeçalho com o botão de menu |
| Impressão | `nao-imprimir`, `so-tela`, `folha-recibo` |

## Selos

O estado vai sempre na palavra do selo. O ícone é reforço e vem do **tom**, desenhado pelo CSS no
`::before` do `.selo` (máscara de um SVG do Lucide em `data:` URI, na cor do texto, com
`mask-image` e `-webkit-mask-image`): os templates não mudam.

| Tom | Ícone |
|---|---|
| `selo-ok` | check |
| `selo-aviso` | alerta em triângulo |
| `selo-erro` | alerta em círculo |
| `selo-info` | info |
| `selo-neutro` | nenhum |

O selo que já traz um `svg` no markup (o "N no pedido", o `aba-selo`) não ganha o segundo
(`.selo:has(svg)::before`). Na impressão, o ícone some (`layouts.css`). Ícone por estado
(relógio em "Aguardando", por exemplo) fica possível depois, selo a selo, pondo o `svg` no markup.

## Dropdowns

Todo `select.campo-entrada` e todo `input.campo-entrada[list]` ganha, pelo `interface/js/dropdown.js`,
um painel no mesmo estilo do painel de resultados da busca de materiais: cartão com borda e sombra
elevada, sem legenda (o rótulo do campo vai no `aria-label` da lista), linhas de 14px com divisória,
opção marcada em tonal (`--secundario-superficie`) com o ícone `check` (nunca só a cor). O painel
nunca tem caixa de busca: no `select`, digitar pula para a opção que começa com o que se digitou
(as letras se acumulam por 0,8 s).

A base é uma só: `.painel-flutuante` (casca, entrada e saída animadas, em `componentes.css`) e o
`dropdown.js` (abrir e fechar, teclado, ARIA, posição, fechar por fora). Os tipos só montam o
controle: seleção simples (`select`), campo com lista (`input[list]`, texto livre), select digitável
(`select[data-dropdown-digitavel]`: campo de texto que filtra a lista, mas só vale uma opção dela;
placa e centro de custo) e árvore (`select[data-dropdown-arvore]`). A busca de materiais
(`#resultados`, `.busca-painel`) usa a mesma casca e o mesmo abrir e fechar por
`window.Dropdown.abrirPainel` e `fecharPainel`. O elemento original continua na página, escondido,
e guarda o valor e dispara `change`: quem troca o valor de um `select` por script precisa disparar
`change`. Fora do escopo: o Django admin e `<input type="date">`.

## Ícones

`{% include "interface/_icone.html" with nome="busca" %}` desenha um SVG inline no estilo
Lucide (traço 1.5, `currentColor`, `aria-hidden`). O conjunto é fechado: `caixa`, `busca`,
`mais`, `menos`, `lixeira`, `impressora`, `sair`, `seta-direita`, `seta-esquerda`, `alerta`,
`check`, `menu`, `fechar`, `painel`, `recibo`, `catalogo`, `cadastros`, `saida`, `enviar`,
`olho`, `robo`, `grafico`, `trocar`, `atualizar`, `caixa-check`, `filtro`, `seta-baixo`, `lapis`,
`usuario`, `cadeado`, `relogio`, `info`, `check-duplo`, `escudo`, `chave-inglesa`, `kebab`,
`calendario`, `documento` e `caminhao`. Nome desconhecido não desenha nada. Ícone novo entra no
`_icone.html`, com os traços do Lucide. Os ícones dos selos não passam por ele (são máscaras no
CSS). Nunca emoji na interface.

## Movimento

- Transições de 0.15s em hover e foco; `scale(.98)` no clique dos botões.
- O cartão de opção sobe 2px no hover e a seta anda 4px.
- O cartão de sucesso do pedido entra com 0.4s (`subir`).
- `prefers-reduced-motion: reduce` zera transições e animações.
- Sem *scroll reveal* nem animação de entrada em listas.

## Regras que continuam

- Estado nunca só por cor: todo selo e aviso tem texto; o item atual do menu e a página atual da
  paginação também mudam de peso.
- Códigos em `.mono`.
- Foco visível: anel de 2px no destaque, afastado 2px (`:focus-visible`).
- Alvos de toque de 44px ou mais na área interna e de 48px nos formulários públicos (a altura do
  controle de cada ritmo), inclusive o botão de ícone; o desenho pode ser menor, a área de toque não.
- Tabelas sempre dentro de `.tabela-rolagem`: a página não rola de lado.
- Scripts no `<head>` com `defer`; logout por POST num formulário único; o `htmx-config`
  com `noSwap` fica no `base.html`.
- Bloco de cabeçalho vazio (`rotulo`, `sub`) não deixa buraco: o `<p>` do layout fica sem
  espaço dentro e some pelo `:empty`.
- Os resultados da busca de materiais abrem num painel preso ao campo e fecham com Esc ou ao sair
  da área; sem JavaScript ficam na página. Os formulários públicos buscam só pelo nome; a saída
  avulsa também pelo código.
- Sem espaço para a coluna ao lado dos passos, "Seu pedido" vira uma barra fixa no rodapé que abre
  uma gaveta (`<dialog>`); sem JavaScript, ou com espaço, o pedido aparece na página.
- Até 1286px de largura a barra lateral vira cabeçalho com o botão `menu`/`fechar`
  (`aria-expanded`, Esc fecha). Sem JavaScript, a navegação fica aberta.

## Impressão

`@media print` em `layouts.css` esconde a casca (barra lateral, cabeçalho da página,
mensagens, topo e rodapé públicos), `.nao-imprimir` e `.so-tela`, tira fundos e sombras e o ícone
dos selos. Em `pedidos.css`, cada `.folha-recibo` sai numa folha e **redefine os tokens que usa com
os valores de antes da troca do visual** (texto, bordas, raios e o cabeçalho da tabela em
maiúsculas): o recibo impresso sai idêntico ao do Clean, e os selos do recibo viram contorno cinza
com texto preto. Mudar o recibo no papel é decisão própria, nunca efeito de um token novo. O
`scripts/capturar_telas.py --recibo <n> --comparar-com <pasta>` compara a impressão pixel a pixel.

## Tela nova

1. Carregue a skill `design-tonal` e leia este arquivo.
2. Estenda `interface/base_publico.html` (blocos `rotulo`, `heading`, `sub`, `page`,
   `rodape`) ou `interface/base_almoxarifado.html` (`rotulo`, `heading`, `sub`, `tools`,
   `page`).
3. Monte a página só com o vocabulário acima e com as combinações de cor permitidas. CSS próprio da
   app fica no CSS da app, carregado pelo bloco `extra_css`, e só usa tokens.
4. Destino novo do menu entra em `ITENS_MENU` (`interface/navegacao.py`) com um ícone do
   conjunto (e a rota em `contas.acesso.REGRAS_POR_ROTA`).
5. Confira a 320, 375, 768, 1280 e 1440px, sem rolagem lateral: `scripts/capturar_telas.py`
   (fora da suíte, com o servidor de desenvolvimento no ar) gera as capturas e avisa a rolagem.
