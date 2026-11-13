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
| `--contorno` (controles: campo, chip sem seleção, botão de contorno) | `#C4C7D0` (1,69:1) | `#7A7D88` (4,10:1 no branco, 3,80:1 na `--superficie-baixa`) | WCAG 1.4.11: a borda é o único limite do chip e do campo, e precisa de 3:1 |
| Texto sobre `--destaque-container` | `#2563EB` (4,14:1) | `--sobre-destaque-container` `#0F2A6B` (10,75:1) | O azul do botão não serve como texto no contêiner azul-claro |

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

## R5. Chips com lista e menu ⋮ são `<details>` nativos

**Decision**: o chip com lista (Origem, SCPI, Recibo, Autorização, Período) é um
`<details class="chip-menu" data-menu>`. O `<summary>` é o chip, e o painel mostra o mesmo campo do
`FiltrosPainel` de hoje, montado pelo `dropdown.js`. O menu ⋮ da linha é um
`<details class="menu-acoes" data-menu>` com links. Um script novo e pequeno, `interface/js/menus.js`,
só fecha o `details[data-menu]` aberto com Esc e com clique fora, e fecha os outros quando um abre.

**Rationale**:

- O `<details>` abre e fecha sem JavaScript e pelo teclado, e o `summary` é focável. Isso cumpre a
  FR-009 (área interna sem JavaScript) e a FR-018a sem duplicar links.
- O formulário de filtros continua um GET com os mesmos nomes de campo, e o HTMX continua com o mesmo
  `hx-trigger`.
- O chip de situação é um `<button type="submit" name="situacao" value="…">` com `aria-pressed`, que
  funciona sem script.

**Alternatives considered**: o `filtros.js` de hoje (painel recolhível com chips de filtro ativo).
Ele continua no histórico de Automações, mas no painel daria lugar aos chips sempre visíveis.
Popover API: o suporte é recente demais para os iPhones antigos dos funcionários.

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

## R7. Contadores do menu: preguiçosos e uma vez por requisição

**Decision**: o context processor `interface.navegacao.menu` põe no item Painel o número de pedidos
aguardando atendimento, e no item Automações o das travas a conferir, só para quem pode abrir cada
item. As travas a conferir são as requisições de saída travadas (`contar_lotes_travados`) mais os
recebimentos de compra em verificação, em lançamento ou com erro
(`compras.consultas.contar_recebimentos_travados`, nova: um `count` pelos mesmos estados que a
`verificacoes_entradas` lista, sem montar as candidatas). As duas se resolvem em Automações (abas
Lançamento no SCPI e Entradas no SCPI), e um contador só das saídas esconderia o recebimento travado.
O cartão do robô no painel continua só das saídas. Os números vêm de `pedidos.consultas.contadores_do_menu(request)`, que guarda o resultado na
própria requisição; a view do painel usa a mesma função e não conta duas vezes. Os valores são
preguiçosos: a contagem só roda se o template desenhar o menu, e os trechos do HTMX não desenham.

**Rationale**: as contagens já existem ou são um `count` simples (`filtrar_situacao(...,"aguardando")`,
`contar_lotes_travados` e a nova contagem dos recebimentos) e são baratas no volume atual. Por serem preguiçosas, a página sem menu (a
pública) e os trechos do HTMX não pagam nada.

**Alternatives considered**: contadores só no painel (o menu mostraria número numa página e não na
outra); cache com tempo de vida (número velho num menu que manda agir).

## R8. "Imprimir recibo" pela lista: `?imprimir=1` no detalhe

**Decision**: o item do ⋮ leva a `pedidos:detalhe` com `?imprimir=1`. No carregamento, o `pedidos.js`
aciona o botão `[data-imprimir]` que já existe (o mesmo clique da pessoa) e tira o parâmetro da URL
com `history.replaceState`, para o recarregar não imprimir de novo. Depois da impressão, o
`afterprint` de hoje abre a confirmação "O recibo saiu na impressora?". Sem JavaScript, o detalhe só
abre: o botão de imprimir fica escondido sem JavaScript, como hoje, e nada é impresso nem marcado.

**Rationale**: reusa o fluxo de impressão e de confirmação de hoje, sem rota nova nem gravação nova.
A marcação de impresso continua exigindo a confirmação da pessoa (FR-018a).

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

O selo que já traz o próprio ícone no markup (`.selo:has(svg)`, como o "N no pedido" e os selos das
abas) não ganha o segundo. Os templates não mudam.

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

## R15. Contraste verificado por teste

**Decision**: `tests/test_contraste_tokens.py` lê o bloco `:root` de `fundacao.css` e confere, para
cada par da tabela de `contracts/tokens.md`, o contraste mínimo (4,5:1 no texto, 3:1 em contorno de
controle, ícone de estado e foco), com a fórmula da WCAG 2.1. Roda sem banco.

**Rationale**: transforma a SC-003 em teste permanente: quem mudar um token depois não reprova o
contraste sem perceber.

## R16. Documentação, skill e constituição na entrega 1

**Decision**:

- **Constituição 2.2.0**: o Princípio VI passa a dizer "A interface segue o design system do projeto
  (`docs/DESIGN.md`)". As demais linhas do princípio não mudam. No relatório de impacto do topo do
  arquivo, o motivo é a spec 015.
- **`docs/DESIGN.md`**: reescrito com os tokens, o vocabulário (o que fica, o que muda, o que entra),
  os componentes novos, as regras que continuam e o passo a passo de "Tela nova".
- **Skill**: a `.claude/skills/design-tonal/` (o nome "Tonal" vem das superfícies tonais do M3)
  substitui a `.claude/skills/clean-design/`, que sai e fica no histórico do Git.
- **`CLAUDE.md`**: a regra das três skills passa a nomear a `design-tonal`, e a seção da interface
  troca `clean.css` por `fundacao.css` e Clean por Tonal.

**Rationale**: a governança manda a emenda e os documentos afetados no mesmo PR, e a entrega 1 é a
que muda o estilo. Uma skill desatualizada geraria telas Clean nas entregas seguintes e na spec 014.
