---
name: design-tonal
description: Estilo visual do Central Almoxarifado, o "Tonal" (a linguagem do Material 3 sobre o CSS do projeto, escrito à mão). Use sempre que for criar, ajustar ou revisar qualquer tela, template, componente, CSS ou protótipo deste projeto (formulários públicos, painel, Automações, Compras, recibo, login), ou quando o pedido falar em visual, layout, cor, selo, botão, cartão, espaçamento, "deixar bonito", acessibilidade ou contraste. Não desenhe de memória: o docs/DESIGN.md é a referência e vence esta skill.
---

# Design Tonal — Central Almoxarifado

O Tonal é a linguagem visual do **Material 3** aplicada ao CSS do próprio projeto: superfícies
tonais, contêineres de cor, raios maiores, botões em pílula, chips e elevação só no que flutua. Não
há biblioteca (nada de Material Web, Tailwind, npm ou CDN): os componentes são as classes de
`interface/static/interface/css/componentes.css`, sobre os tokens de `fundacao.css`.

## Antes de mexer em qualquer tela

1. Leia o `docs/DESIGN.md` inteiro: tokens, combinações de cor permitidas e proibidas,
   vocabulário de classes, selos, ícones, ritmos, impressão e o passo a passo de "Tela nova". Ele
   é a referência normativa e vence esta skill e os plugins.
2. Veja como a tela parecida já foi feita no código e siga o mesmo padrão.
3. Os componentes marcados "(entrega N)" no `DESIGN.md` ainda não existem: não os use antes.
4. Junto desta skill, use os plugins `ui-ux-pro-max` (usabilidade e acessibilidade) e
   `frontend-design` (hierarquia, textos de interface, conferência por captura). Onde discordarem,
   valem o `DESIGN.md` e o que já está no código.

## O que define o Tonal

- **Superfícies em camadas.** `--fundo` (branco) no fundo da área interna, no conteúdo e nos campos;
  `--superficie` em passos e linhas com o cursor; `--superficie-media`, `--superficie-alta` e `--superficie-maxima` para contêineres,
  hover e pressionado. O cartão é o de contorno do M3: branco, borda `--borda`, raio de 16px e
  **sem sombra**.
- **Contêineres de cor com o texto do próprio contêiner.** Azul tonal (`--destaque-superficie` +
  `--destaque-superficie-texto`), secundário tonal (`--secundario-superficie` +
  `--secundario-superficie-texto`) e os quatro de status. Nunca `--destaque` nem `--texto-suave`
  sobre um contêiner (combinações proibidas, conferidas por `tests/test_contraste_tokens.py`).
- **Forma.** Botões, quantidade, paginação e item do menu em pílula (`--raio-pilula`); campo com raio
  de 4px (`--raio-campo`); selo com 6px; cartão, aviso e painel com 16px; diálogo com 28px
  (`--raio-bloco`).
- **Controles com contorno de 3:1.** Campo, botão secundário, quantidade e caixa de marcar usam
  `--contorno`; `--borda` é só divisória e contorno decorativo de cartão. No foco, o campo ganha a
  borda de 2px em `--destaque` (o segundo pixel é sombra interna).
- **Erro.** `--erro-forte` na borda, no rótulo e no texto do campo, com o ícone de alerta.
- **Selos.** Raio de 6px e o ícone pelo tom no `::before` (check, alerta em triângulo, alerta em
  círculo, info; o neutro sem ícone). O estado vai sempre na palavra.
- **Elevação só no que flutua.** `--sombra-elevada` em painel flutuante, diálogo, gaveta e dica.
- **Tipografia de sempre.** Geist nos títulos, DM Sans no texto, Geist Mono nos códigos (`.mono`).
  Nunca Roboto (a fonte do M3), Inter, Arial ou system-ui.
- **Movimento curto.** `--transicao` de 0.15s; `scale(.98)` no clique; nada de *scroll reveal*.

## Regras que não mudam

- Textos em pt-BR. Estado nunca só por cor. Códigos (CADPRO, matrícula, placa, requisição) em `.mono`.
- Só tema claro. Nenhuma cor fora dos tokens: nada de hexadecimal nem `rgba` no CSS de tela
  (transparência por `color-mix(in srgb, var(--token) N%, transparent)`); a impressão é a exceção.
- Alvos de toque: 44px na área interna e 48px no público (`--altura-controle` de cada ritmo).
- Tabela sempre dentro de `.tabela-rolagem`; nenhuma página rola de lado entre 320 e 1440px.
- Scripts no `<head>` com `defer`; logout por POST num formulário único; requisição HTMX que grava
  dentro de um `<form>` com `{% csrf_token %}`.
- O recibo impresso não muda: a `.folha-recibo` redefine no `@media print` os tokens que usa.
- Classe que existe continua com o mesmo nome; componente novo entra em `componentes.css` e no
  vocabulário do `DESIGN.md` no mesmo PR.

## Conferir

- `uv run pytest tests/test_fundacao.py tests/test_contraste_tokens.py` depois de mexer em token ou
  componente comum.
- `scripts/capturar_telas.py` (fora da suíte, com o servidor de desenvolvimento no ar) gera as
  capturas a 320, 375, 768, 1280 e 1440px, avisa a rolagem lateral e, com `--recibo` e
  `--comparar-com`, compara a impressão do recibo pixel a pixel.

`DESIGN.md`, nesta pasta, resume o estilo para consulta rápida; os valores exatos ficam no
`docs/DESIGN.md`.
