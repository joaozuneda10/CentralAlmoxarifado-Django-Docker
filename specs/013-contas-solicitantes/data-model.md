# Modelo de dados: Contas de solicitante (spec 013)

Duas colunas novas, um grupo novo e as tabelas do django-axes. Nenhum dado existente muda.

## `contas.Usuario` (existente)

| Campo | Tipo | Regra |
|-------|------|-------|
| `trocar_senha` | `BooleanField(default=False)` | Novo. Ligado pelo admin ao criar o usuário e ao definir a senha; desligado pela troca feita pelo próprio usuário. Só é exigido do solicitante (R5). Migration `contas/0005_trocar_senha`: `AddField` com `default=False`, então nenhuma conta existente é obrigada a trocar (FR-007). |

O nome completo da conta é `first_name` + `last_name` (`regras.nome_da_conta`, espaços normalizados
por `texto`). O admin recusa salvar um solicitante sem nome (`contracts/login-senha-admin.md`).

## Grupo `Solicitante` (novo)

- Criado pela migration de dados `contas/0006_solicitante` com `get_or_create`, **sem permissão
  nenhuma** (FR-001). Não muda nenhum usuário.
- Incompatível com `Atendimento`, `Gestão` e `Segurança do Trabalho`, e com `is_staff`/`is_superuser`:
  o formulário do usuário no admin recusa a combinação ao salvar (FR-002). Uma combinação que exista
  mesmo assim faz `eh_solicitante` dar falso (R1): a conta vale como equipe.

## `pedidos.Pedido` (existente)

| Campo | Tipo | Regra |
|-------|------|-------|
| `conta` | `ForeignKey(AUTH_USER_MODEL, null=True, blank=True, on_delete=PROTECT, related_name="pedidos_feitos")` | Novo. Preenchido só por `servicos.registrar_pedido` quando o formulário foi aberto e enviado com a mesma conta de solicitante (FR-012, FR-015). Nunca muda depois (nem a edição do atendimento o toca). Migration `pedidos/0006_conta`: `AddField`, todos os pedidos antigos `NULL` (FR-025). |

- `solicitante` (texto) continua obrigatório e, no pedido com conta, é o nome da conta no momento do
  envio; mudar o nome da conta depois não muda os pedidos (Edge Cases).
- O reenvio (`Pedido.id` igual) confere também `conta_id`: diferente é "divergente".
- Consulta pública: só pedidos com `conta IS NULL` (FR-022).
- "Meus pedidos": `Pedido.objects.filter(conta=usuario)` ordenado por `-criado_em` (o índice da FK
  basta para o volume esperado).

## django-axes (tabelas do pacote)

- `axes.AccessAttempt`: tentativas erradas por `username` + `ip_address`, com a contagem; apagar a
  linha no admin desbloqueia (FR-011). Zerada no login certo (`AXES_RESET_ON_SUCCESS`).
- `axes.AccessLog` e `axes.AccessFailureLog`: as tabelas existem (migrations do pacote), mas ficam
  vazias: `AXES_DISABLE_ACCESS_LOG = True` e o registro de falhas desligado, que é o padrão do axes 9
  (research R6).
- Criadas pelas migrations do próprio pacote no `migrate` do deploy.

## Token do formulário público (sem tabela)

`pedidos.protecao.Envio` ganha `conta: int | None`. O token assinado passa a levar
`{"id", "aberto_em", "conta"}`; token sem `conta` (página aberta antes do deploy) vale como `None`.
