# Contrato: formulário público com conta (spec 013)

## Abertura (GET `pedidos:formulario`)

| Quem abre | Token | Nome | Destino |
|-----------|-------|------|---------|
| Anônimo ou equipe | `conta: None` | campo livre, como hoje | vazio, `pedidos.js` sugere o do aparelho como hoje |
| Solicitante | `conta: <pk>` | o nome da conta, `readonly`, dica "Nome da sua conta." | o do último pedido da conta nesta origem, se ainda é opção válida; senão vazio |

O `<form>` do solicitante leva `data-com-conta`; o `pedidos.js` não lê nem grava o `localStorage`
(`almoxarifado.solicitante`) nesse formulário.

## Envio (POST)

Ordem das verificações (as atuais não mudam de lugar):

1. Token inválido → como hoje.
2. Isca e tempo mínimo → como hoje.
3. **Novo**: token com `conta` e (`request.user` não é solicitante ou `request.user.pk != conta`) →
   recusa sem gravar, com o carrinho e os campos mantidos, mensagem
   **"Sua sessão terminou. Entre de novo (abre em outra aba), volte aqui e toque em Enviar; os
   materiais continuam aqui."** e o link "Entrar" em **aba nova** (`target="_blank"`
   `rel="noopener"`, `next` para "Meus pedidos"). A mensagem da spec (US4) ganha o "abre em outra
   aba" (research R3a).
   - O `pedidos.js`, no formulário com `data-com-conta`, copia o cookie `csrftoken` para o
     `csrfmiddlewaretoken` logo antes de cada envio: o login da outra aba trocou o segredo do CSRF, e
     sem isso o reenvio daria 403.
4. Com `conta`: `EnvioPedido.solicitante` = nome da conta (o enviado é ignorado).
5. `registrar_pedido(..., conta=<usuário ou None>)`.

## `servicos.registrar_pedido`

- Parâmetro novo `conta=None` (o usuário). Grava `Pedido.conta`.
- Reenvio: confere `registro_confere` **e** `anterior.conta_id == (conta.pk if conta else None)`;
  qualquer diferença é `divergente`.
- Limites por IP e por nome, validação, autorização de EPI e Telegram: sem mudança (FR-017).

## Tela de sucesso

| Pedido | Mostra |
|--------|--------|
| Com conta | o número, "Acompanhe em Meus pedidos." e o botão "Ver em Meus pedidos" (`pedidos:meu_pedido`); sem o aviso para guardar o número, sem a consulta pública e sem `data-lembrar-*` |
| Anônimo, solicitante logado (página aberta sem conta) | como hoje, mais o aviso "Este pedido foi feito sem entrar na conta e não aparece em Meus pedidos." |
| Anônimo | como hoje |

## Garantias testadas

1. Pedido do solicitante sai com `conta` e o nome da conta, mesmo com outro nome enviado.
2. Formulário aberto com a conta A e enviado sem sessão, ou com a conta B: nada gravado, mensagem e
   carrinho mantidos.
3. Formulário aberto sem conta e enviado logado: pedido anônimo, com o aviso.
4. Equipe logada: pedido anônimo, token sem conta.
5. Reenvio igual com a mesma conta confirma; com outra conta é divergente.
6. Token antigo (sem a chave `conta`) continua aceito como anônimo.
7. Sessão terminada, login de novo no mesmo cliente (o CSRF troca) e reenvio com o token do CSRF do
   cookie: o pedido é registrado com a conta (o teste faz o que o `pedidos.js` faz, com
   `enforce_csrf_checks=True`).
