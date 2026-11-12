# Contrato: painel do almoxarifado (entrega 2)

## View `pedidos.views.almoxarifado.painel`

A página inteira ganha estas chaves de contexto. O trecho do HTMX (`_painel_lista.html`) só
ganha as duas permissões do ⋮.

| Chave | Tipo | Fonte | Quando |
|---|---|---|---|
| `pedidos_aguardando` | int | já existe (agora via `contadores_do_menu`, sem contar duas vezes) | sempre |
| `envio_mais_antigo` | str ou `None` | `regras.texto_envio_mais_antigo(localdate(min_criado_em), localdate())` | só com `pedidos_aguardando` > 0 |
| `aguardando_autorizacao` | int | `consultas.contar_aguardando_autorizacao()` | sempre |
| `recibos_pendentes` | int | já existe | sempre |
| `lancamento_pendentes`, `lancamento_travados`, `lancamento_em_andamento`, `lancamento_real` | já existem | já existem | só com `operar_automacoes` (spec 012), como hoje |
| `saude` | lista | já existe | sempre |
| `saude_erros`, `saude_avisos` | int | contagem de `saude` por `nivel` | sempre |
| `pode_imprimir`, `pode_editar` | bool | `pode_abrir(user, "pedidos:marcar_impressos")`, `pode_abrir(user, "pedidos:editar")` | sempre, também no trecho do HTMX |

## Indicadores

| Cartão | Número | Nota | Ação | Clique no cartão |
|---|---|---|---|---|
| Aguardando atendimento | `pedidos_aguardando` | `envio_mais_antigo` (relógio); "+N aguardando autorização" como link para `?autorizacao=aguardando#pedidos`, só com N > 0 | "Atender" (como hoje: `?situacao=aguardando#pedidos`) | `?situacao=aguardando#pedidos` |
| Recibos para imprimir | `recibos_pendentes` | — | "Imprimir" (como hoje: `?recibo=pendente#pedidos`) | `?recibo=pendente#pedidos` |
| Requisições no robô (só com `operar_automacoes`) | `lancamento_pendentes` | "N para conferir" (alerta; link de hoje para `automacoes:pagina?aba=lancamento#travas`), só com travadas; "Lançamento em andamento", como hoje | o formulário "Lançar no SCPI" de hoje, com o mesmo bloqueio, a dica e o cadeado | `?scpi=aguardando#pedidos` |
| Saúde do catálogo | `saude_erros + saude_avisos` | "N erros · N avisos" (alerta quando há erro) | "Ver avisos" → `#saude` | `#saude` |

- O texto de cada cartão com zero continua o de hoje ("Nenhum pedido aguardando.", "Nenhum recibo
  pendente.", "Nada aguardando o robô.").
- O cartão cujo filtro está na URL ganha `aria-current="true"` e o contorno de destaque.
- O "Atender" desabilitado com zero continua `aria-disabled`, como hoje.
- A saída avulsa sai dos cartões e vira o `fab`.

## Filtros

O formulário continua o `FiltrosPainel`: GET para `pedidos:painel`, com o mesmo `hx-get`,
`hx-target="#lista-pedidos"`, `hx-push-url` e `hx-trigger`.

| Campo | Controle novo |
|---|---|
| `q` | busca em pílula no topo da página (FR-014) |
| `situacao` | chips "Todas", "Aguardando atendimento", "Atendido parcialmente" e "Atendido": `button[type=submit][name=situacao]`, com `aria-pressed` pelo valor atual |
| `material` | campo na linha dos chips |
| `origem`, `scpi`, `recibo`, `autorizacao` | `chip-menu` com o `select` de hoje dentro (o `dropdown.js` o monta); o rótulo do chip mostra o valor escolhido ("Origem: Limpeza") |
| `de`, `ate` | `chip-menu` "Período", com os dois campos de data |

- "Limpar filtros" continua um link para `pedidos:painel`.
- Sem JavaScript, os chips enviam o formulário, e os `details` abrem nativamente.
- O `filtros.js` deixa de ser usado no painel e continua no histórico de Automações.

## Lista (`_painel_lista.html`)

- **Colunas**: Nº com a origem; Enviado em (data, e a hora em `texto-suave`); Pessoa (solicitante e
  "recebeu:"); Destino ou centro de custo (com a ocorrência e a placa em mono); **Situação** (selo
  com ícone e, embaixo, "Recibo não impresso" com o ícone da impressora quando
  `a.recibo_impresso_em` é nulo); **SCPI** (selo com ícone); ⋮.
- **Clique na linha**: o link do Nº continua cobrindo a linha. O ⋮ fica acima dele.
- **Itens do ⋮**: as condições de `data-model.md`, com `pode_imprimir` e `pode_editar`.
- **Largura estreita**: na container query de hoje, a linha vira cartão, com o ⋮ no canto superior
  direito.

## Detalhe: `?imprimir=1` (R8)

- `GET pedidos:detalhe?imprimir=1`: a página é a mesma. O botão `[data-imprimir]` ganha
  `data-imprimir-ao-abrir` quando o parâmetro está presente e o pedido tem atendimento.
- O `pedidos.js`, no carregamento, aciona esse botão uma vez e remove o parâmetro com
  `history.replaceState`.
- A confirmação "O recibo saiu na impressora?" segue o fluxo de hoje. Nada é marcado sem ela.
- Sem atendimento, o parâmetro é ignorado.

## Testes (entrega 2)

- `regras.texto_envio_mais_antigo`: hoje, ontem, N dias e virada de mês (pura).
- O "mais antigo" ignora os aguardando autorização e os recusados, e some com zero pedido.
- "+N aguardando autorização": conta só os `AGUARDANDO` e some com zero.
- Os contadores do menu aparecem só para quem abre o item, mostram os mesmos números do painel e não
  aparecem com zero. A página do painel não conta duas vezes (`django_assert_num_queries` no trecho
  dos contadores).
- O ⋮: os itens de cada estado (aguardando, atendido com lote pendente, lançado, EPI aguardando
  autorização, saída avulsa) e de cada papel (com e sem as permissões).
- O `?imprimir=1` marca o botão só com atendimento, e nada é gravado ao abrir.
- Os chips: cada valor de `situacao` devolve o mesmo resultado que o filtro de hoje, também sem o
  cabeçalho `HX-Request`.
