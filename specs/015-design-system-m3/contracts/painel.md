# Contrato: painel do almoxarifado (entrega 2)

## View `pedidos.views.almoxarifado.painel`

A página inteira ganha estas chaves de contexto. O trecho do HTMX (`_painel_lista.html`) não ganha
nenhuma: o ⋮ depende só do estado de cada pedido.

| Chave | Tipo | Fonte | Quando |
|---|---|---|---|
| `pedidos_aguardando` | int | `interface.navegacao.contadores(request)`, a mesma memória do menu (R7) | sempre |
| `envio_mais_antigo` | str ou `None` | `regras.texto_envio_mais_antigo(localdate(min_criado_em), localdate())` | só com `pedidos_aguardando` > 0 |
| `aguardando_autorizacao` | int | `consultas.contar_aguardando_autorizacao()` | sempre |
| `recibos_pendentes` | int | já existe | sempre |
| `lancamento_pendentes`, `lancamento_travados`, `lancamento_em_andamento`, `lancamento_real` | já existem (`lancamento_travados` sai da mesma memória) | já existem | só com `operar_automacoes` (spec 012), como hoje |
| `saude` | lista | já existe | sempre |
| `saude_erros`, `saude_avisos` | int | contagem de `saude` por `nivel` | sempre |

Não há chaves de permissão para o ⋮: as rotas `pedidos:painel`, `detalhe`, `editar` e
`marcar_impressos` têm a mesma regra (`_ATENDIMENTO`, `contas/acesso.py`). Quem abre o painel pode
abrir todos os destinos do ⋮. Se um papel futuro separar essas permissões, a separação entra no ⋮ no
mesmo PR. O servidor continua recusando cada rota pela tabela de rotas.

## Ordem dos formulários na página (FR-014)

O formulário de filtros (`<form id="filtros-painel">`) **nunca envolve os indicadores**. O cartão do
robô tem o próprio `<form method="post">` do "Lançar no SCPI", e um formulário dentro de outro é
descartado pelo navegador: o botão passaria a enviar o GET dos filtros, e nada seria lançado, sem
aviso. A página fica assim, de cima para baixo:

1. Cabeçalho, com a busca `q` em pílula **fora do formulário**, ligada a ele pelo atributo
   `form="filtros-painel"`.
2. Os indicadores, cada um com os seus formulários próprios.
3. O formulário de filtros: chips, material, chips com lista, "Filtrar" e "Limpar filtros".
4. A lista (`#lista-pedidos`) e a saúde do catálogo (`<section id="saude">`).

Como a busca fica fora do `<form>`, o evento `input` dela não sobe até ele. O gatilho passa a ser:

`hx-trigger="change, input delay:400ms, input delay:400ms from:#id_q, submit"`

O HTMX 4 vendorizado aceita o modificador `from:`. O `FormData` do envio inclui o campo com
`form=`, com JavaScript ou sem.

## Indicadores

| Cartão | Número | Nota | Ação | Clique no cartão |
|---|---|---|---|---|
| Aguardando atendimento | `pedidos_aguardando` | `envio_mais_antigo` (relógio); "+N aguardando autorização" como link para `?autorizacao=aguardando#pedidos`, só com N > 0 | "Atender" (como hoje: `?situacao=aguardando#pedidos`) | `?situacao=aguardando#pedidos` |
| Recibos para imprimir | `recibos_pendentes` | — | "Imprimir" (como hoje: `?recibo=pendente#pedidos`) | `?recibo=pendente#pedidos` |
| Requisições no robô (só com `operar_automacoes`) | `lancamento_pendentes` | "N para conferir" (alerta, com o link de hoje para `automacoes:pagina?aba=lancamento#travas`), só com travadas; "Lançamento em andamento", como hoje | o formulário "Lançar no SCPI" de hoje, com o mesmo bloqueio, a dica e o cadeado | `automacoes:pagina?aba=lancamento` (só com `operar_automacoes`) |
| Saúde do catálogo | `saude_erros + saude_avisos` | "N erros · N avisos" (alerta quando há erro) | "Ver avisos" → `#saude` | `#saude` |

- **O cartão do robô não leva a filtro da lista.** O número dele conta requisições da fila do robô
  (`lotes_pendentes`), e o filtro "SCPI" da lista conta pedidos por `filtrar_scpi`. Os dois podem
  divergir (por exemplo, no lote parcialmente lançado), e um clique que mostra outro número engana.
  Ele leva à aba Lançamento no SCPI, onde está a fila que ele conta.
- A seção da saúde ganha `id="saude"` (hoje só tem a classe `saude-painel`).
- O texto de cada cartão com zero continua o de hoje ("Nenhum pedido aguardando.", "Nenhum recibo
  pendente.", "Nada aguardando o robô.").
- O cartão cujo filtro está aplicado ganha `aria-current="true"` e o contorno de destaque. O servidor
  o marca pela URL; com JavaScript, o `filtros.js` o mantém em dia (ver "Estado dos filtros").
- O "Atender" desabilitado com zero continua `aria-disabled`, como hoje.
- A saída avulsa sai dos cartões e vira o `fab`.

## Filtros

O formulário continua o `FiltrosPainel`: GET para `pedidos:painel`, com o mesmo `hx-get`,
`hx-target="#lista-pedidos"` e `hx-push-url`. O gatilho é o da seção anterior.

| Campo | Controle novo |
|---|---|
| `q` | busca em pílula no cabeçalho, fora do `<form>`, com `form="filtros-painel"` |
| `situacao` | chips **de rádio**: `<fieldset class="chips">` com uma `legend` escondida "Situação" e um `<label class="chip">` por opção ("Todas", "Aguardando atendimento", "Atendido parcialmente", "Atendido"), cada um com `<input type="radio" name="situacao" class="chip-entrada">` e o texto. O estado é o `:checked` nativo, visível pelo `check` e pela cor tonal (seletor de irmão `.chip-entrada:checked + .chip-texto`, sem `:has()`); as setas do teclado trocam a opção. O widget do `FiltrosPainel.situacao` vira `RadioSelect`, com os mesmos valores |
| `material` | campo na linha dos chips |
| `origem`, `scpi`, `recibo`, `autorizacao` | `chip-menu` com o `select` de hoje dentro (o `dropdown.js` o monta); o rótulo do chip mostra o valor escolhido ("Origem: Limpeza") |
| `de`, `ate` | `chip-menu` "Período", com os dois campos de data |

- **Por que rádio e não botão de envio**: o botão de envio só manda o valor no envio que ele mesmo
  dispara. Ao mudar outro filtro, a situação sumiria. E o Enter num campo de texto envia pelo
  primeiro botão de envio do formulário, que mandaria o valor desse chip. O rádio guarda o valor em
  todo envio, e o `change` dele já está no gatilho.
- **O "Filtrar" é o primeiro botão de envio do formulário e não tem `name`**. Assim, o Enter na
  busca ou no material envia sem acrescentar nada. Sem JavaScript, escolher um chip e apertar
  "Filtrar" filtra, como hoje com o `select`.
- "Limpar filtros" continua um link para `pedidos:painel`.

## Estado dos filtros depois de cada troca do HTMX

Com JavaScript, o HTMX troca só `#lista-pedidos`. O resto da tela não pode afirmar um filtro que não
está aplicado.

- Os **chips de rádio** já mostram o estado certo: é o próprio campo que o formulário envia.
- Os **rótulos dos chips com lista** ("Origem: Limpeza") e o **`aria-current` dos indicadores** são
  atualizados pelo `filtros.js` a partir dos valores do próprio formulário, a cada `change`. O
  formulário é a fonte do que foi enviado, e não é preciso trocar a barra de filtros pelo servidor
  (o que fecharia o painel aberto e tiraria o foco de quem digita).
- O `filtros.js` deixa de recolher o painel de filtros no painel de pedidos, que fica sempre à
  vista. O recolhimento, a contagem e os chips de filtro ativo continuam no histórico de Automações,
  sem mudança.
- Sem JavaScript, todo envio recarrega a página, e o servidor desenha o estado inteiro pela URL.

## Lista (`_painel_lista.html`)

- **Colunas**: Nº com a origem; Enviado em (data, e a hora em `texto-suave`); Pessoa (solicitante e
  "recebeu:"); Destino ou centro de custo (com a ocorrência e a placa em mono); **Situação** (selo e,
  embaixo, "Recibo não impresso" com o ícone da impressora quando `a.recibo_impresso_em` é nulo);
  **SCPI** (selo); ⋮.
- **Clique na linha**: o link do Nº continua cobrindo a linha. O ⋮ fica acima dele, com `z-index`
  maior que o do `a::after` que cobre a linha.
- **Itens do ⋮**: as condições de `data-model.md`.
- **Corte pela rolagem**: a `.tabela-rolagem` tem `overflow-x: auto`, e o `overflow-y` vira `auto`
  junto, então um menu que desce além da tabela seria cortado. Nas duas últimas linhas da página
  (`forloop.revcounter <= 2`), o menu abre para cima (`menu-acoes-acima`).
- **Largura estreita**: na container query de hoje, a linha vira cartão, com o ⋮ no canto superior
  direito. A regra de abrir para cima vale igual.
- **Sem JavaScript**: o `<details>` abre e fecha nativamente, e os itens são links comuns.

## Detalhe: `?imprimir=1` (R8)

- `GET pedidos:detalhe?imprimir=1`: a página é a mesma. O botão `[data-imprimir]` ganha
  `data-imprimir-ao-abrir` **só quando o pedido tem atendimento e o recibo ainda não foi impresso**
  (`recibo_impresso_em` nulo). Já impresso, o parâmetro é ignorado, e a pessoa imprime de novo pelo
  botão, como hoje.
- O campo `voltar` do diálogo "O recibo saiu na impressora?" (`detalhe.html`, hoje
  `request.get_full_path`) passa a levar a URL **sem** o parâmetro `imprimir`. A view monta esse valor
  (`voltar_sem_imprimir`). Sem isso, a confirmação voltaria a `?imprimir=1` e imprimiria de novo.
- O `pedidos.js` aciona o botão uma vez, no evento `load` (com as fontes já carregadas), e tira o
  parâmetro da barra com `history.replaceState(history.state, "", url_sem_imprimir)`, mantendo o
  estado de histórico do HTMX.
- A confirmação segue o fluxo de hoje. Nada é marcado sem ela.

## Testes (entrega 2)

- `regras.texto_envio_mais_antigo`: hoje, ontem, N dias e virada de mês (pura).
- O "mais antigo" ignora os aguardando autorização e os recusados, e some com zero pedido.
- "+N aguardando autorização": conta só os `AGUARDANDO` e some com zero.
- **Contadores**: aparecem só para quem abre o item, batem com os números do painel e não aparecem
  com zero. O de Automações soma as travas das saídas e das entradas pela regra de R7; o cartão do
  robô não soma as entradas. A página do painel não conta duas vezes (`django_assert_num_queries`).
- **⋮**: os itens de cada estado (aguardando, atendido com lote pendente, lançado, EPI aguardando
  autorização, saída avulsa com "Editar saída").
- **`?imprimir=1`**: marca o botão só com atendimento e recibo não impresso; o `voltar` sai sem o
  parâmetro; nada é gravado ao abrir.
- **Chips de rádio**: cada valor de `situacao` devolve o mesmo resultado que o filtro de hoje, também
  sem o cabeçalho `HX-Request`, e o rádio marcado na página inteira é o da URL.
- **Estado na página inteira**: com `?origem=…`, o rótulo do chip mostra o valor; com
  `?situacao=aguardando` ou `?recibo=pendente`, o indicador correspondente sai com `aria-current`.
- **Formulários**: o formulário do "Lançar no SCPI" não fica dentro do de filtros, e a busca tem
  `form="filtros-painel"`.
- **Testes do markup de hoje**: `tests/test_painel.py` (o cartão "Atalhos", `atalho-numero`,
  `filtros-recolhiveis`, `data-fechar-filtros`) e `tests/test_epis_painel.py` (`atalho-numero`)
  conferem uma estrutura que a entrega 2 remove. Eles são reescritos para a estrutura nova,
  conferindo **os mesmos números e os mesmos destinos** (SC-001).
