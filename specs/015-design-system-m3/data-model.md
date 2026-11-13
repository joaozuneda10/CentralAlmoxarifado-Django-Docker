# Data Model: Troca do design system

**Nenhum modelo muda e nenhuma migration é criada.** A troca é de apresentação. Os quatro
comportamentos novos do painel (FR-018) só **leem** dados que o sistema já guarda; esta página diz de
onde vem cada valor e qual regra o calcula.

## Valores de apresentação

| Valor | Onde aparece | Fonte | Regra |
|---|---|---|---|
| Pedidos aguardando atendimento | cartão do painel; contador do item Painel no menu | `filtrar_situacao(Pedido.objects.all(), "aguardando").count()` (já existe) | o mesmo conjunto do filtro "Aguardando atendimento": fora os aguardando autorização e os recusados |
| Envio mais antigo aguardando | nota do cartão de atendimento | `consultas.envio_mais_antigo_aguardando()`: `Min("criado_em")` sobre o conjunto acima; `None` sem pedido | texto por `regras.texto_envio_mais_antigo(data_envio, hoje)`: 0 dia → "enviado hoje", 1 → "enviado ontem", N → "há N dias"; dias de calendário no fuso do servidor (`timezone.localdate`) |
| Aguardando autorização | nota "+N aguardando autorização" | `consultas.contar_aguardando_autorizacao()`: `Pedido` com `autorizacao__situacao=AGUARDANDO` | a mesma condição do filtro Autorização = aguardando; some com 0 |
| Recibos para imprimir | cartão do painel | `Atendimento` com `recibo_impresso_em` nulo (já existe) | sem mudança |
| Requisições aguardando o robô | número do cartão do robô | `lotes_pendentes()` (já existe) | sem mudança |
| Requisições travadas | nota "N para conferir" do cartão do robô | `contar_lotes_travados()` (já existe; inclui o `EM_LANCAMENTO` sempre) | sem mudança; nunca somado ao número acima (FR-018c) |
| Requisições a conferir | parcela do contador de Automações | `contar_lotes_travados(com_em_lancamento=…)`: lotes com linha `VERIFICAR` ou `ERRO`, mais os `EM_LANCAMENTO` sem execução de saídas em andamento; lote distinto | R7 |
| Recebimentos a conferir (spec 014) | parcela do contador de Automações | `compras.consultas.contar_recebimentos_travados()` (nova): `Recebimento` em `VERIFICAR` ou `ERRO`, mais `EM_LANCAMENTO` sem execução de entradas em andamento | não aparece no painel |
| Travas a conferir | contador do item Automações | requisições a conferir + recebimentos a conferir | só para quem abre Automações; some com 0 |
| Saúde do catálogo por nível | 4º cartão | `saude_do_catalogo()` (já existe), contada por `nivel` (`erro`, `aviso`) | a lista completa continua na página |
| Itens do menu ⋮ de uma linha | `_painel_lista.html` | o pedido com `atendimento` e `atendimento__linhas` já pré-carregados por `pedidos_do_painel` | ver a tabela abaixo |

## Condições do menu ⋮ (FR-018a)

| Item | Aparece quando | Destino |
|---|---|---|
| Abrir pedido | sempre | `pedidos:detalhe` |
| Imprimir recibo | o pedido tem `Atendimento` | `pedidos:detalhe` com `?imprimir=1` (imprime sozinho só com `recibo_impresso_em` nulo) |
| Editar atendimento / Editar saída | `regras.edicao_permitida(True, linhas).permitida` (rótulo "Editar saída" na origem `AVULSA`) | `pedidos:editar` |

Não há condição de permissão: `pedidos:painel`, `detalhe`, `editar` e `marcar_impressos` têm a mesma
regra (`_ATENDIMENTO`), e quem abre o painel abre todos os destinos. O servidor continua recusando
cada rota pela tabela de rotas. As linhas do lote já vêm pré-carregadas, então o ⋮ não acrescenta
consulta por linha.

## Contadores do menu (R7)

`interface.navegacao.contadores(request)` guarda as parcelas na própria requisição (pedidos
aguardando, requisições travadas como hoje, requisições a conferir e recebimentos a conferir). O menu
mostra `{"pedidos:painel": aguardando, "automacoes:pagina": requisições a conferir + recebimentos a
conferir}`, só com as chaves que o usuário pode abrir, e o painel lê as mesmas parcelas. A contagem
só roda quando o template desenha o menu ou o painel. O valor 0 não mostra o contador.

## Estados de interface (sem banco)

| Componente | Estados | Como se marca |
|---|---|---|
| Chip de situação | marcado, não marcado | o `:checked` do rádio nativo; o marcado tem o ícone `check` e a cor tonal (nunca só a cor) |
| Chip com lista / menu ⋮ | aberto, fechado | atributo `open` do `<details>`; `menus.js` fecha com Esc, com clique fora e quando outro abre |
| Indicador | normal, crítico, ativo (o filtro dele está aplicado) | `indicador-critico` quando a nota é de alerta; `aria-current="true"` no indicador cujo filtro está aplicado: o servidor o marca pela URL, e o `filtros.js` o atualiza pelo formulário depois de cada troca do HTMX |
| Chip com lista (rótulo) | sem valor, com valor | "Origem" ou "Origem: Limpeza": o servidor desenha pela URL, e o `filtros.js` atualiza pelo formulário |
| Campo flutuante | vazio, com foco, preenchido (inclusive pelo preenchimento automático), com erro | `:placeholder-shown`, `:focus`, `:autofill`/`:-webkit-autofill`, `aria-invalid="true"` com `campo-com-erro` |
| Item do menu | atual, normal | `aria-current="page"` (já existe) |
