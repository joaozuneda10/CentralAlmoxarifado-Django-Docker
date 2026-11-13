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
| Requisições travadas | nota "N para conferir" do cartão do robô | `contar_lotes_travados()` (já existe) | sem mudança; nunca somado ao número acima (FR-018c) |
| Recebimentos travados (spec 014) | soma do contador do item Automações | `compras.consultas.contar_recebimentos_travados()` (nova): `Recebimento` em `VERIFICAR`, `EM_LANCAMENTO` ou `ERRO`, os mesmos estados de `verificacoes_entradas` | não aparece no painel |
| Travas a conferir | contador do item Automações | requisições travadas + recebimentos travados | só para quem abre Automações; some com 0 |
| Saúde do catálogo por nível | 4º cartão | `saude_do_catalogo()` (já existe), contada por `nivel` (`erro`, `aviso`) | a lista completa continua na página |
| Itens do menu ⋮ de uma linha | `_painel_lista.html` | o pedido com `atendimento` e `atendimento__linhas` já pré-carregados por `pedidos_do_painel` | ver a tabela abaixo |

## Condições do menu ⋮ (FR-018a)

| Item | Aparece quando | Permissão (spec 012) | Destino |
|---|---|---|---|
| Abrir pedido | sempre | a de abrir `pedidos:detalhe` | `pedidos:detalhe` |
| Imprimir recibo | o pedido tem `Atendimento` | a de `pedidos:marcar_impressos` | `pedidos:detalhe` com `?imprimir=1` |
| Editar atendimento / Editar saída | `regras.edicao_permitida(True, linhas).permitida` (rótulo "Editar saída" na origem `AVULSA`) | a de `pedidos:editar` | `pedidos:editar` |

As permissões são calculadas uma vez por requisição na view (`pode_abrir`), nunca por linha. As
linhas do lote já vêm pré-carregadas, então o ⋮ não acrescenta consulta por linha. O servidor
continua recusando quem não tem a permissão, como hoje.

## Contadores do menu (R7)

`pedidos.consultas.contadores_do_menu(request)` devolve `{"pedidos:painel": n, "automacoes:pagina": m}`,
com `m` = requisições travadas + recebimentos travados,
só com as chaves que o usuário pode abrir. O resultado fica guardado na própria requisição, e a
contagem só roda quando o template desenha o menu. O valor 0 não mostra o contador.

## Estados de interface (sem banco)

| Componente | Estados | Como se marca |
|---|---|---|
| Chip de situação | selecionado, não selecionado | `aria-pressed="true|false"`; o selecionado tem ícone `check` e cor tonal (nunca só a cor) |
| Chip com lista / menu ⋮ | aberto, fechado | atributo `open` do `<details>`; `menus.js` fecha com Esc, com clique fora e quando outro abre |
| Indicador | normal, crítico, ativo (o filtro dele está aplicado) | `indicador-critico` quando a nota é de alerta; `aria-current="true"` no indicador cujo filtro está na URL |
| Campo flutuante | vazio, com foco, preenchido, com erro | `:placeholder-shown`, `:focus`, `aria-invalid="true"` com `campo-com-erro` |
| Item do menu | atual, normal | `aria-current="page"` (já existe) |
