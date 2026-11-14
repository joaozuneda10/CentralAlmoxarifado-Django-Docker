# Tonal — resumo para consulta

Resumo do estilo. Os valores normativos, o vocabulário completo e as combinações de cor estão no
`docs/DESIGN.md` do repositório, que vence este arquivo.

## Clima

Interface de trabalho, clara e calma, na linguagem do Material 3: camadas de superfície em
cinza-azulado bem claro, contêineres de cor suaves para estado e seleção, cantos arredondados,
botões em pílula. Densa na área interna (ritmo `almox`), folgada no celular dos formulários
públicos (ritmo `publico`).

## Cor

- Base: branco `#FFFFFF`, superfícies `#F5F6FA` → `#EEF0F5` → `#E8EAF0` → `#E1E4EB`.
- Texto: `#1A1C21`, secundário `#4A4D57`, suave `#666975`.
- Destaque: azul `#2563EB` (hover `#1D4ED8`), só em botão cheio, link, foco e barra da aba ativa.
- Tonais: azul `#DCE6FF` com texto `#0F2A6B`; secundário `#E2E7F3` com texto `#1B2540`.
- Status (superfície / texto): ok `#D8F0DE`/`#1D5E30`, aviso `#FCEBC9`/`#6A4600`,
  erro `#FBE3E1`/`#8C1D17`, neutro `#ECEDF2`/`#4A4D57`; erro forte `#B3261E`.
- Linhas: divisória `#E2E4EA`; contorno de controle `#7A7D88` (3:1).

## Forma e elevação

- Raios: campo 4px, selo 6px, chip 8px, cartão 16px, diálogo 28px, pílula 100px.
- Cartão de contorno, sem sombra. Sombra elevada só no que flutua.

## Componentes

- Botões: primário cheio, secundário de contorno, suave tonal, texto sem fundo, ícone em círculo.
- Campo: caixa com contorno, foco com borda azul de 2px, erro em vermelho forte com ícone.
- Selo: contêiner de status com o ícone do tom e a palavra do estado.
- Abas: pasta; a ativa é branca, com a barra azul em cima e o texto tonal.
- Dropdown e painel flutuante: cartão elevado, opção marcada em tonal com o check.

## Tipografia

Geist 600/700 nos títulos, DM Sans 400/500/600 no texto, Geist Mono nos códigos. Nunca Roboto,
Inter, Arial ou system-ui.
