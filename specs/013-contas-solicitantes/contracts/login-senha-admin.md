# Contrato: login, senha e admin (spec 013)

## Limite de tentativas (django-axes)

| Configuração | Valor |
|--------------|-------|
| `AXES_LOCKOUT_PARAMETERS` | `[["username", "ip_address"]]` |
| `AXES_FAILURE_LIMIT` | `.env` `LOGIN_TENTATIVAS`, padrão `5` |
| `AXES_COOLOFF_TIME` | `.env` `LOGIN_BLOQUEIO_MINUTOS`, padrão `15` (vira `timedelta`) |
| `AXES_RESET_ON_SUCCESS` | `True` |
| `AXES_LOCKOUT_TEMPLATE` | `contas/bloqueado.html` (layout público) |
| `AXES_DISABLE_ACCESS_LOG` | `True` (não registra todo login bem-sucedido; research R6) |
| Backend | `axes.backends.AxesStandaloneBackend` antes do `ModelBackend` |
| Middleware | `axes.middleware.AxesMiddleware`, o último |

- Vale nas duas portas: `/painel/entrar/` e o login do admin (as duas chamam `authenticate` com o
  `request`).
- Bloqueado: status 429, a página "Muitas tentativas. Tente de novo em alguns minutos ou procure o
  almoxarifado." Antes do limite, a recusa é a de hoje ("Matrícula ou senha incorretas.").
- Desbloquear: apagar a tentativa da matrícula em Admin › Axes › Tentativas de acesso.
- `check --deploy` continua sem avisos; as duas variáveis novas vão para o `.env.example`.

## Troca de senha (`trocar_senha`)

- `PasswordChangeView` com `FormularioTrocaSenha` (rótulos e erros em português) e
  `contas/trocar_senha.html` (layout público).
- Valida com os `AUTH_PASSWORD_VALIDATORS`; não aceita a senha nova igual à atual.
- Sucesso: `trocar_senha = False`, sessão mantida, mensagem "Senha trocada." e redirecionamento ao
  ponto de partida (solicitante: "Meus pedidos").

## Admin do usuário (`contas.admin.UsuarioAdmin`, subclasse do `UserAdmin`)

- Criar usuário (`add_view`) e "Alterar senha" (`user_change_password`) ligam `trocar_senha`.
- O formulário de edição mostra `trocar_senha` (o chefe pode ligar ou desligar à mão).
- Ao salvar, recusa (`ValidationError` no campo `groups`) quando o grupo `Solicitante` vem com
  `Atendimento`, `Gestão`, `Segurança do Trabalho`, `is_staff` ou `is_superuser`:
  "Uma conta de solicitante não pode ter papel da equipe nem acesso ao admin."
- Recusa salvar um usuário do grupo `Solicitante` sem nome completo: "Informe o nome completo: ele vai
  nos pedidos da conta."

## Garantias testadas

1. Errar até o limite bloqueia a matrícula naquela origem, nas duas portas; outra matrícula entra.
2. Depois do tempo (com o relógio adiantado no teste), a senha certa entra e zera as tentativas.
3. Apagar a `AccessAttempt` desbloqueia na hora.
4. Conta nova de solicitante entra e só abre a troca e o Sair; trocou, cai em "Meus pedidos".
5. Senha definida no admin liga a troca de novo; contas existentes não são afetadas pela migration.
6. O admin recusa as combinações proibidas e o solicitante sem nome.
