# Contrato: relatórios do SCPI lidos pelas entradas

Dois relatórios do menu 07 (Relatórios) do módulo Compras, os dois baixados em Salvar Arquivo › CSV
(Dados) pelo `scpi.browser.interceptar_csv`. Nenhum deles grava nada no SCPI: o 07.13 foi conferido pelo
Log do pedido em 10/11/2026 (F9). O 07.04.01 é o mesmo relatório que o usuário já extrai à mão.

**Proibido**: o 01.08.03 Imprimir Pedidos, que grava a Data Emissão e um contador no pedido (F10).

## 07.13 "Relação de Pedidos (Condição da Entrega)"

**Download**: `scpi.relatorios.baixar_pedidos_compra() -> bytes`.

No menu Relatórios o item se chama "07.13. Relação de Pedidos Entregues e Não Entregues" (conferido
na tela em 12/11/2026); "Relação de Pedidos (Condição da Entrega)" é o título do relatório.

| Filtro | Valor |
|---|---|
| Tipo | Analítico |
| "Apenas com saldo a entregar" | marcado |
| Pedido, fornecedor e período | vazios (todos os pedidos do exercício da sessão) |

Os campos são achados pelo rótulo na tela, nunca pelo ID. O relatório termina como começou ("Fechar
relatório" e "Sair").

**Leitura**: `scpi.leitura.ler_pedidos_compra(bytes) -> Leitura[LinhaPedidoCompra]`, pura.

| Coluna | Uso | Formato |
|---|---|---|
| `NUMPED` | pedido: ano e número | `00514/26`; fora do formato é erro |
| `DATPED` | data do pedido | `dd/mm/aaaa` |
| `CODIF` / `NOME` | fornecedor | texto; um fornecedor por pedido (diferente é erro) |
| `ITEM` | número do item no pedido | inteiro; (`NUMPED`, `ITEM`) único |
| `CADPRO` | código do material | texto, comparado por `norm_u` |
| `UNID1` | unidade | texto |
| `TPCONTROLE_SALDO` | `Q` ou `T` | outro valor é erro |
| `QTD`, `QTDANU`, `QTDENT`, `QTDPEDIDA`, `QTDFALTA` | quantidades | decimal pt-BR (`1361,32`) |
| `PRCUNT` | preço unitário | decimal pt-BR |

Regras:
- Os registros quebrados em várias linhas são recolados (`scpi.normalizadores`). Se a contagem de
  campos não fechar, o relatório está cortado: `ErroImportacao`.
- Nos itens `Q`, `QTDFALTA = QTD − QTDANU − QTDENT − QTDPEDIDA`; diferença é `ErroImportacao`.
- Relatório sem nenhum item é `ErroImportacao`. "Nada a exibir" levanta `scpi.leitura.NadaAExibir`,
  que a importação trata como relatório vazio confirmado (todos os itens presentes somem, sob o corte
  de [comandos.md](comandos.md)).
- `CODIF` e `CADPRO` vazios, e `DATPED` ou `NOME` diferentes entre os itens do mesmo pedido, são
  `ErroImportacao`.
- A leitura é **tudo ou nada**.

## 07.04.01 "Relação de Requisições", Requisições de Entrada

**Download**: `scpi.relatorios.baixar_entradas(de, ate) -> bytes`.

| Filtro | Valor |
|---|---|
| Rádio | "Requisições de Entrada" |
| Período | `de` a `ate`, que filtra a data da entrada (`DATAE`, F5) |
| Tipo, Nº Pedido, NF, Observação | vazios |

"Nada a exibir" levanta `scpi.leitura.NadaAExibir`: num período sem nenhuma requisição de entrada, é
uma extração sem requisições. A função das saídas (`_relacao_de_requisicoes`) não muda.

**Leitura**: `scpi.leitura.ler_entradas(bytes) -> Leitura[EntradaLida]`, pura.

| Coluna | Campo | Regra |
|---|---|---|
| `REQUI` | `requisicao`, `ano`, `numero` | `003492/26`, pela `conciliacao.regras.chave` |
| `ID_REQUI` | `id_requi` | inteiro |
| `DATAE` | `data_entrada` | obrigatória |
| `DTLAN` | `data_requisicao` | guardada, nunca comparada |
| `CODIF` | `fornecedor_codigo` | |
| `DOCUM` | `nf` | só dígitos, sem os zeros à esquerda; vazio é permitido (entrada sem NF) |
| `NUMPED` | `pedido_ano`, `pedido_numero` | vazio é permitido (entrada sem pedido) |
| `SAID` | `com_saida` | `S` → verdadeiro |
| `TPREQUI` | `tipo` | |
| `OBS_CABECALHO` | `observacoes` | a marca `RC-…` é lida daqui |
| `CADPRO`, `QUAN1`, `UNID1` | itens | `QUAN1` decimal pt-BR, maior que 0 |
| `RESPONSA` | `responsavel` | opcional |

Regras:
- Uma requisição por `REQUI`. Os campos do cabeçalho (`ID_REQUI`, `DATAE`, `DTLAN`, `CODIF`,
  `DOCUM`, `NUMPED`, `SAID`, `OBS_CABECALHO`) iguais em todas as linhas dela; diferente é erro.
- Registro quebrado é recolado, e o relatório cortado é erro.
- O `GRUPO` do CSV é a `DATAE`. A leitura não depende dele.
- A leitura é **tudo ou nada**.

## Arquivos de teste

`tests/relacao_pedidos_compra.py` e `tests/relacao_entradas.py` geram CSVs sintéticos no formato real:
o cabeçalho completo (79 e 65 colunas), `;`, sem aspas, linhas `\r\n`, o BOM e um registro quebrado de
propósito. Os CSVs reais têm nomes de pessoas e nunca entram no repositório.
