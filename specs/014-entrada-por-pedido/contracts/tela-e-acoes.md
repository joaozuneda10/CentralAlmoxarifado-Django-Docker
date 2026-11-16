# Contrato: telas e ações

Toda rota nova entra em `contas.acesso.REGRAS_POR_ROTA` no mesmo PR que a cria. Nenhuma entra em
`ROTAS_SEGURANCA_TRABALHO`. Gravação só por POST com CSRF. A interface segue o `docs/DESIGN.md`:
- estado em texto, nunca só por cor;
- `RC-…`, números de requisição, de pedido e de NF, e códigos em `.mono`;
- quantidades com `regras.qtd_br`.

## Compras (permissão `contas.receber_compras`: Atendimento e Gestão)

| Rota | Método | URL | Faz |
|---|---|---|---|
| `compras:pedidos` | GET | `/painel/compras/` | lista os pedidos do exercício com item disponível ou recebimento aberto; busca por número (`514`, `00514/26`), fornecedor (código ou nome) e código de material; filtros "Travados" e "Com recebimento aberto"; 50 por página |
| `compras:pedido` | GET | `/painel/compras/pedidos/<id>/` | o cabeçalho (número, fornecedor, data e estado em texto); os itens (nº, código, descrição do cadastro, unidade, pedido, anulado, já entrou, saldo do SCPI, reservado, **saldo livre** e o motivo de indisponibilidade); os recebimentos; as travas abertas; os botões "Receber total" e "Receber parcial" |
| `compras:receber` | GET, POST | `/painel/compras/pedidos/<id>/receber/?modo=total\|parcial` | o formulário do recebimento ([abaixo](#formulário-do-recebimento)) |
| `compras:recebimento` | GET | `/painel/compras/recebimentos/<id>/` | os dados, os itens, o estado em texto, a requisição oficial, o veredito atual e o histórico (quem preparou, a última alteração, as tentativas) |
| `compras:editar_recebimento` | GET, POST | `/painel/compras/recebimentos/<id>/editar/` | o mesmo formulário, preenchido, com a `versao` |
| `compras:cancelar_recebimento` | POST | `/painel/compras/recebimentos/<id>/cancelar/` | dois passos: o `<details>` com o motivo e `confirmado=1`, também sem JavaScript |

O menu ganha o item "Compras" (`ITENS_MENU`), visível só com a permissão (`pode_abrir`).

### Formulário do recebimento

**Campos**:
- **Escondidos**: o `envio` (UUID gerado no GET) e, na edição, a `versao`.
- **NF**: só dígitos, até 12, `inputmode="numeric"`.
- **Data do recebimento**: o padrão é hoje; o mínimo é a data do pedido e o máximo é hoje.
- **Observação**: opcional, até 500 caracteres.
- **Itens disponíveis**: uma linha por item, com uma caixa "Receber este item" e a quantidade.
  - "total": todas as caixas marcadas, com a quantidade igual ao saldo livre;
  - "parcial": nenhuma marcada, com a quantidade vazia.

  O item indisponível aparece sem caixa, com o motivo.

**Validação no servidor**, dentro da trava do pedido. Juntam-se todos os erros, com o erro no campo e
o resumo no topo, e nada é gravado:

| Situação | Mensagem |
|---|---|
| NF vazia, com letra ou zero | "Informe o número da nota fiscal, só com algarismos." |
| NF do fornecedor já usada | "A NF 501 deste fornecedor já está no recebimento RC-0007." |
| Data futura | "A data do recebimento não pode ser depois de hoje." |
| Data antes do pedido | "A data do recebimento não pode ser antes da data do pedido (05/08/2026)." |
| Nenhum item marcado | "Marque ao menos um item." |
| Quantidade ilegível, `1.5`, 4 casas ou ≤ 0 | o texto de `pedidos.regras.texto_erro_quantidade`, com até 3 casas em qualquer unidade |
| Acima do saldo livre | "Item 13: o saldo livre é 50; informe até 50." |
| Pedido travado, ausente ou fora do exercício | "Este pedido não aceita recebimento: <motivo>." |
| Reenvio com o mesmo `envio` e o mesmo conteúdo | sucesso, com o recebimento já gravado |
| Reenvio com o mesmo `envio` e conteúdo diferente | "Este recebimento já foi gravado com outros dados. Abra o RC-0007 para conferir." |
| Edição de versão antiga | "Outra pessoa alterou este recebimento. Recarregue a página." |
| Edição ou cancelamento depois do Salvar | "O robô já tentou lançar este recebimento: resolva em Automações › Entradas no SCPI." |

O sucesso redireciona ao detalhe do recebimento, com a mensagem "RC-0007 preparado: vai para a fila do
robô.".

## Automações › Entradas no SCPI (permissão `contas.operar_automacoes`: Gestão)

A aba nova `?aba=entradas` fica na página `automacoes:pagina`. As regiões que se recarregam usam o
`HX-Target`, como as outras abas.

| Região | Conteúdo |
|---|---|
| Fila (`div#fila-entradas`) | os recebimentos preparados, com caixa de marcar, "marcar todas", a contagem e os botões "Simular" e "Lançar no SCPI" (este com a confirmação e o cadeado quando o lançamento real está bloqueado); os bloqueados aparecem sem caixa, com o motivo (pedido travado, ausente, fora do exercício, ou com recebimento em verificação) |
| Andamento | o cartão de `pedidos.andamento` da última execução `ENTRADAS`, no topo enquanto roda e nos 10 minutos depois |
| Em verificação e com erro | por recebimento: a mensagem, as candidatas com "É esta", "Liberar para relançar" (com "Conferi no SCPI") e "Cancelar" (dois passos) |
| Pedidos travados | por pedido: as travas abertas com o detalhe, a data da última importação e "Destravar" (com o motivo) |
| Conferência | a última extração, "Conferir agora", "Atualizar pedidos" e o veredito atual de cada recebimento lançado, com o filtro `?veredito_entradas=` (Divergências, o padrão, Aguardando, Comprovados e Todos) e 50 por página |

| Rota | Método | Faz | Recusas |
|---|---|---|---|
| `automacoes:lancar_entradas` | POST | `modo=simular\|lancar` e `recebimentos` (os `RC-…` marcados); valida contra a fila de agora e chama `iniciar_lancamento_entradas` | sem marcação; um recebimento que saiu da fila; lançamento real bloqueado; outro robô rodando; importação de pedidos em andamento |
| `automacoes:resolver_entrada` | POST | `acao=e_esta` com a candidata; `acao=liberar` com `conferi=1`; `acao=cancelar` com o motivo e `confirmado=1` | "É esta" com uma requisição que não é candidata ou que já está ligada a outro recebimento; liberar ou cancelar sem as três provas, com a mensagem de qual falta ([R16](../research.md#r16-liberação-para-relançar-as-três-provas)); com execução em andamento |
| `automacoes:destravar_pedido` | POST | o pedido e o motivo | sem motivo; "Atualize os pedidos antes: a última importação é de antes da trava."; com execução em andamento |
| `automacoes:conferir_entradas` | POST | `iniciar_conciliacao_entradas` | com lançamento, extração ou importação de pedidos em andamento |
| `automacoes:importar` (existente) | POST | o tipo novo `pedidos_compra`: baixar do SCPI ou CSV enviado | as do formulário existente |

Toda recusa volta à aba com a mensagem, sem gravar nada. Toda ação que grava passa por
`compras.servicos` ou pelo disparo, nunca pela view.

As mensagens de liberação recusada são estas:
- "Ainda não houve extração de entradas depois da tentativa de 11/11/2026 10:42.";
- "Há requisição candidata no intervalo: 003901/26.";
- "O 'Já Entrou' do item 13 não foi conferido depois da tentativa: atualize os pedidos.";
- "O 'Já Entrou' do item 13 mudou de 30 para 50 depois da tentativa: a requisição pode existir."

## Aba Lançamento no SCPI (saídas)

Não muda, salvo o filtro `robo=SAIDAS` nas consultas. Com o robô de entradas rodando, a trava ocupada
desabilita os botões, com a dica "O robô de entradas está lançando."

## Saúde (`catalogo.saude._demais`)

Avisos novos, vindos de `compras/saude.py`:
- os pedidos travados, com o motivo;
- os recebimentos em verificação ou com erro;
- a importação de pedidos sem sucesso há mais de um dia útil, ou com falha na última;
- a extração de entradas com falha;
- as entradas fora do Central nos últimos 30 dias.

A visão geral de Automações ganha as linhas "Pedidos de compra" e "Entradas" entre as fontes.
