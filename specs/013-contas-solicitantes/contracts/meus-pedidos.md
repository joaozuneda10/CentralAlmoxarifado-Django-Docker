# Contrato: Meus pedidos e consulta pública (spec 013)

Layout público (`base_publico.html`), `never_cache` nas duas páginas (FR-023).

## Lista (`pedidos:meus_pedidos`)

- Só `Pedido.objects.filter(conta=request.user)`, do mais novo para o mais antigo, 20 por página
  (`?pagina=`).
- Cada linha: número (`.mono`), formulário (`Fluxo.titulo`), data do envio e o selo da situação (os
  da spec 011, com texto, nunca só cor). A linha leva a `pedidos:meu_pedido`.
- Sem pedidos: "Você ainda não fez pedidos com a conta." e os links para os formulários.

## Pedido (`pedidos:meu_pedido`)

- Busca `Pedido` por `numero` **e** `conta=request.user`; qualquer outro caso (número inexistente,
  de outra conta, anônimo) → 404 com a mesma página (FR-021).
- O template recebe só o dicionário montado por `pedidos.minhas.apresentar(pedido)`:

| Chave | Conteúdo |
|-------|----------|
| `numero`, `formulario`, `enviado_em` | como na consulta pública |
| `consulta` | `regras.texto_consulta_publica(...)`: selo, mensagem e o motivo da recusa de EPI |
| `destino`, `obs`, `ocorrencia` | o que o solicitante informou |
| `itens` | uma linha por item `PEDIDO`: `material`, `unidade`, `qtd_pedida`, `qtd_entregue` (None antes do atendimento), `trocado_por` (material do item `ALMOXARIFADO` com `no_lugar_de` = este item, ou None) |

- Nunca chegam ao template (FR-020): `Atendimento` (recebedor, centro, placa, tipo, data efetiva além
  da que a mensagem já cita), `AutorizacaoPedido.decidido_por`, `LinhaSaida`, número da requisição,
  quem atendeu e os itens `ALMOXARIFADO` sem `no_lugar_de`.

## Consulta pública (`pedidos:consulta`, spec 011)

- A busca acrescenta `conta__isnull=True`. Pedido com conta → `MENSAGEM_CONSULTA_NAO_ACHADA`, a mesma
  de número inexistente (FR-022). O limite por origem continua contando a tentativa.

## Garantias testadas

1. A conta B recebe 404 no pedido da conta A e num pedido anônimo, igual a um número inexistente.
2. A consulta pública com número e primeiro nome certos de um pedido com conta responde "não
   encontrado".
3. O HTML do pedido não contém o recebedor, o centro, a placa, o tipo, o número da requisição, o nome
   de quem atendeu nem o material acrescentado.
4. Parcial com troca: quantidade pedida e entregue por linha e "trocado por <material>".
5. EPI recusado: selo "Recusado" e o motivo.
6. Paginação de 20 e ordem do mais novo.
7. As duas respostas têm `Cache-Control` com `no-store`.
