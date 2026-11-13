# Contrato: tokens (`interface/static/interface/css/fundacao.css`, `:root`)

Os nomes que já existem continuam (research R3). "Novo" marca o que entra. Os valores de contraste
foram calculados com a fórmula da WCAG 2.1 e são conferidos por `tests/test_contraste_tokens.py`
(R15).

## Cores

| Token | Valor | Antes | Uso |
|---|---|---|---|
| `--fundo` | `#FFFFFF` | `#FFFFFF` | fundo da página, campos, tabela |
| `--superficie` | `#F5F6FA` | `#F7F6F2` | superfície baixa: passos, linha em hover, linha aberta |
| `--superficie-media` (novo) | `#EEF0F5` | — | indicadores, "Seu pedido", cartões tonais |
| `--superficie-alta` (novo) | `#E8EAF0` | — | busca em pílula, hover de botão-ícone |
| `--superficie-maxima` (novo) | `#E1E4EB` | — | pressionado |
| `--texto` | `#1A1C21` | `#0F0E0C` | texto principal |
| `--texto-secundario` | `#4A4D57` | `#6B6760` | rótulos, segunda linha, apoio |
| `--texto-suave` | `#666975` | `#A8A49F` | datas, dicas, contagens (agora AA) |
| `--borda` | `#E2E4EA` | `#E8E6E1` | divisórias e contorno decorativo de cartão |
| `--contorno` (novo) | `#7A7D88` | — | limite de controle: campo, chip sem seleção, botão de contorno |
| `--destaque` | `#2563EB` | `#2563EB` | botão cheio, link, foco, rótulo com foco |
| `--destaque-hover` | `#1D4ED8` | `#1D4ED8` | hover do botão cheio |
| `--destaque-texto` | `#FFFFFF` | `#FFFFFF` | texto sobre o destaque |
| `--destaque-superficie` | `#DCE6FF` | `#EFF4FF` | contêiner tonal azul: selo info, botão flutuante, ícone do cartão de opção |
| `--destaque-superficie-texto` (novo) | `#0F2A6B` | — | texto e ícone sobre `--destaque-superficie` |
| `--secundario-superficie` (novo) | `#E2E7F3` | — | botão suave (tonal), chip selecionado, pílula do item atual do menu |
| `--secundario-superficie-texto` (novo) | `#1B2540` | — | texto sobre `--secundario-superficie` |
| `--ok-superficie` / `--ok-texto` | `#D8F0DE` / `#1D5E30` | `#ECF7EE` / `#1E6B34` | status ok |
| `--aviso-superficie` / `--aviso-texto` | `#FCEBC9` / `#6A4600` | `#FDF4E3` / `#8A5A00` | status aviso |
| `--erro-superficie` / `--erro-texto` | `#FBE3E1` / `#8C1D17` | `#FCEDEC` / `#A3261D` | status erro |
| `--erro-forte` (novo) | `#B3261E` | — | borda e rótulo do campo com erro, contador do menu, número crítico |
| `--info-superficie` / `--info-texto` | `var(--destaque-superficie)` / `var(--destaque-superficie-texto)` | idem / `--destaque-hover` | status informação |
| `--neutro-superficie` / `--neutro-texto` | `#ECEDF2` / `#4A4D57` | `--superficie` / `--texto-secundario` | status neutro |

A impressão continua a exceção: texto preto e bordas cinza. No `@media print`, a folha do recibo
(`.folha-recibo`) **redefine os tokens que usa com os valores de hoje** (`--texto` `#000000`,
`--borda` e contornos cinza, `--raio-cartao` 12px e a tabela de hoje) e esconde o ícone dos selos,
para o recibo impresso sair idêntico (FR-010, SC-007).

## Combinações permitidas e proibidas

O `docs/DESIGN.md` declara estas listas, e `tests/test_contraste_tokens.py` confere as permitidas
(R15). Combinação fora da lista permitida não é usada.

Permitidas: as da tabela "Pares conferidos pelo teste", abaixo.

Proibidas (reprovam no cálculo):

| Combinação | Contraste | Use em vez disso |
|---|---|---|
| `--destaque` sobre `--destaque-superficie` | 4,14 | `--destaque-superficie-texto` |
| `--destaque` sobre `--secundario-superficie` | 4,17 | `--secundario-superficie-texto` |
| `--texto-suave` sobre `--secundario-superficie` | 4,41 | `--secundario-superficie-texto` |
| `--texto-suave` sobre `--superficie-maxima` | 4,29 | `--texto-secundario` |

## Pares conferidos pelo teste

| Par (texto ou elemento / fundo) | Mínimo | Calculado |
|---|---|---|
| `--texto` / `--fundo` | 4,5 | 17,05 |
| `--texto` / `--superficie-alta` | 4,5 | 14,17 |
| `--texto-secundario` / `--fundo` | 4,5 | 8,43 |
| `--texto-secundario` / `--superficie-alta` | 4,5 | 7,01 |
| `--texto-suave` / `--fundo` | 4,5 | 5,47 |
| `--texto-suave` / `--superficie-media` | 4,5 | 4,79 |
| `--destaque` / `--fundo` (link) | 4,5 | 5,17 |
| `--destaque-texto` / `--destaque` | 4,5 | 5,17 |
| `--destaque-superficie-texto` / `--destaque-superficie` | 4,5 | 10,75 |
| `--secundario-superficie-texto` / `--secundario-superficie` | 4,5 | 12,24 |
| `--ok-texto` / `--ok-superficie` | 4,5 | 6,47 |
| `--aviso-texto` / `--aviso-superficie` | 4,5 | 7,18 |
| `--erro-texto` / `--erro-superficie` | 4,5 | 7,46 |
| `--erro-forte` / `--fundo` | 4,5 | 6,54 |
| `--neutro-texto` / `--neutro-superficie` | 4,5 | 7,21 |
| `--contorno` / `--fundo` (controle) | 3,0 | 4,10 |
| `--contorno` / `--superficie` (controle) | 3,0 | 3,80 |

O teste falha se um par cair abaixo do mínimo, ou se um token da tabela sumir do `:root`.

## Forma, elevação e movimento

| Token | Valor | Antes | Uso |
|---|---|---|---|
| `--raio-campo` (novo) | `4px` | — | caixa do campo no padrão M3 |
| `--raio-controle` | `8px` | `8px` | chip, item de menu |
| `--raio-selo` (novo) | `6px` | — | selo |
| `--raio-cartao` | `16px` | `12px` | cartão, indicador, painel flutuante, tabela |
| `--raio-bloco` (novo) | `28px` | — | passo do formulário, "Seu pedido", gaveta (só os cantos de cima) |
| `--raio-pilula` | `100px` | `100px` | botões, busca em pílula, controle de quantidade |
| `--sombra-cartao` | `0 1px 2px rgba(16,24,40,.06), 0 1px 3px rgba(16,24,40,.08)` | — | elevação 1 |
| `--sombra-hover` | `0 2px 6px rgba(16,24,40,.08), 0 4px 12px rgba(16,24,40,.08)` | — | hover de cartão clicável |
| `--sombra-elevada` | `0 4px 8px rgba(16,24,40,.10), 0 8px 24px rgba(16,24,40,.12)` | — | elevação 3: menu ⋮, painéis flutuantes, botão flutuante |
| `--anel-foco` | `0 0 0 2px var(--fundo), 0 0 0 4px var(--destaque)` | igual | foco (sem mudança) |
| `--transicao` | `0.15s ease` | `0.18s ease` | hover, foco, abrir e fechar |

## Ritmos (sem mudança de mecânica)

Os dois ritmos continuam no `<body>` (`ritmo-publico`, `ritmo-almox`). Entra só
`--altura-campo` (novo): 56px no público (campo M3) e a `--altura-controle` de hoje (44px) no
almoxarifado.
