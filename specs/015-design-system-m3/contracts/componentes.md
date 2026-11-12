# Contrato: vocabulário de componentes

Regra geral (FR-007, research R1): a classe que existe continua com o mesmo nome e a mesma função;
muda só o desenho. Renomear exige motivo escrito no PR e o ajuste, no mesmo PR, dos scripts e dos
testes que a usam. O `docs/DESIGN.md` da entrega 1 é a versão normativa desta tabela.

## O que fica, com desenho novo (entrega 1)

| Componente | Classes (sem mudança de nome) | Desenho novo |
|---|---|---|
| Botões | `botao` + `botao-primario`, `botao-secundario` (`botao-destaque`, `botao-perigo`, `botao-ok`), `botao-texto`, `botao-icone`, `botao-bloco`, `botao-suave` | pílula (`--raio-pilula`); primário = cheio; secundário = contorno (`--contorno`); suave = tonal (`--secundario-superficie`); texto = sem fundo, hover em `--destaque-superficie`; ícone = círculo de 40px |
| Campos | `campo`, `campo-rotulo`, `campo-entrada`, `campo-dica`, `campo-erro`, `campo-com-erro`, `campo-busca`, … | caixa com `--contorno`; foco com borda de 2px em `--destaque`; erro com `--erro-forte` na borda, no rótulo e no texto com ícone. Na área interna o rótulo continua fixo acima |
| Selos | `selo` + `selo-ok`, `selo-aviso`, `selo-erro`, `selo-info`, `selo-neutro` | contêiner de status, raio de 6px, **ícone antes da palavra** (R12) |
| Avisos | `aviso` + variações | contêiner de status com raio de 16px e ícone |
| Cartões | `cartao`, `cartao-titulo`, `cartao-sutil`, `cartao-opcao` | `cartao`: fundo branco com `--borda` e raio de 16px; `cartao-sutil`: `--superficie-media` sem borda; `cartao-opcao`: ícone num quadrado de 48px em `--destaque-superficie` |
| Tabela | `tabela-rolagem`, `tabela`, … | cabeçalho em `--texto-secundario` 500; divisórias em `--borda`; hover em `--superficie` |
| Abas | `abas`, `aba`, `aba-ativa`, … | a pasta continua; a aba ativa ganha a cor tonal |
| Diálogo, painel flutuante, dropdown | `dialogo-confirmacao*`, `painel-flutuante`, `dropdown*` | raio de 16px (o diálogo, 28px), `--sombra-elevada`, opção marcada em tonal com `check` |
| Paginação, filtros recolhíveis, passos, materiais, carrinho, folha, recibo | os de hoje | tokens novos; a composição muda nas entregas 3 e 4 |
| Casca | `app`, `app-lateral`, `app-menu`, `app-menu-item`, `app-menu-botao`, `app-conta`, … | menu estreito acima de 1286px (R6); entrega 2 |

## O que entra

| Componente | Classes | Onde | Markup (resumo) |
|---|---|---|---|
| Indicadores | `indicadores` (grade), `indicador`, `indicador-critico`, `indicador-rotulo`, `indicador-numero`, `indicador-nota`, `indicador-nota-alerta`, `indicador-acao` | painel (2) | `<section class="indicadores" aria-label="Resumo">` com um `div.indicador` por cartão; o link do filtro cobre o cartão (`indicador-link`, `aria-current="true"` quando o filtro está ativo), e as ações ficam acima dele (`position: relative`) |
| Chips | `chips` (linha), `chip` | painel (2) | `<button type="submit" class="chip" name="situacao" value="parcial" aria-pressed="false">` com `check` escondido até ser selecionado |
| Chip com lista | `chip-menu`, `chip-menu-painel` | painel (2) | `<details class="chip-menu" data-menu><summary class="chip">Origem …</summary><div class="chip-menu-painel painel-flutuante">{{ filtros.origem }}</div></details>` |
| Menu de ações | `menu-acoes`, `menu-acoes-lista` | lista do painel (2) | `<details class="menu-acoes" data-menu><summary class="botao botao-icone" aria-label="Ações do pedido P-000123">kebab</summary><ul class="menu-acoes-lista">…links…</ul></details>` |
| Botão flutuante | `fab` | painel (2) | `<a class="fab nao-imprimir" href="{% url 'pedidos:avulsa' %}">mais + "Saída avulsa"</a>`; no celular sobe acima da área segura; a página ganha recheio embaixo para nada ficar coberto |
| Contador do menu | `app-menu-contador` | casca (2) | `<span class="app-menu-contador"><span aria-hidden="true">2</span><span class="visually-hidden">, 2 para atender</span></span>` depois do ícone, dentro do `app-menu-item` |
| Conta compacta | `app-conta-avatar` | casca (2) | iniciais num círculo, com o nome e a matrícula em `title` e em texto para o leitor de tela; "Sair" com `aria-label` |
| Campo flutuante | `campo-flutuante` (modificador do `campo`) | formulários públicos (3) | ver `campos-publicos.md` |

## Script novo: `interface/js/menus.js`

- Atua em todo `details[data-menu]`: abrir um fecha os outros; Esc fecha o aberto e devolve o foco ao
  `summary`; clique fora fecha.
- Carregado no `<head>` com `defer`, como os outros (regra do HTMX).
- Sem ele, o `<details>` continua abrindo e fechando nativamente.

## Ícones novos (`_icone.html`)

`kebab` (ellipsis-vertical), `metade` (círculo meio preenchido: atendido parcialmente), `proibido`
(ban: não lançar), `calendario` e `documento` (file-text), com os traços do Lucide e `stroke-width`
1.5, como os demais.

## Telas-chave (capturas, R14)

O script de capturas percorre esta lista a 320, 375, 768, 1280 e 1440px:

- públicas: início, formulário de limpeza (vazio e com 2 materiais, com a gaveta aberta no celular),
  formulário das viaturas com a folha aberta, sucesso, consulta pública, login de solicitante, Meus
  pedidos;
- internas: painel (sem filtro, com filtro e com o ⋮ aberto), detalhe aguardando atendimento,
  detalhe atendido, edição, saída avulsa, Automações (Visão geral e Lançamento no SCPI), Curva ABC,
  Formulários, Autorizações (Segurança do Trabalho), login, acesso negado;
- impressão: o recibo em PDF (SC-007).
