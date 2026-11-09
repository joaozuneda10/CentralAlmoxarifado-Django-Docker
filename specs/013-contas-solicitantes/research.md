# Pesquisa: Contas de solicitante (spec 013)

Decisões técnicas do plano, cada uma com o motivo e o que foi descartado. Fatos do código em
2026-11-09 (`develop`, `7b7b5da`, com a spec 012 integrada).

## R1. Quem é solicitante: participação no grupo, fora da equipe

- **Decisão**: `contas.acesso.eh_solicitante(usuario)` = autenticado, ativo, do grupo `Solicitante`,
  sem `is_staff`, sem `is_superuser` e sem nenhuma permissão interna da spec 012
  (`PERMISSOES_INTERNAS`) nem o grupo da Segurança do Trabalho. O resultado fica guardado no objeto,
  como o `da_seguranca_trabalho`.
- **Motivo**: o papel não tem permissão interna nenhuma (FR-001), então não há `has_perm` que o
  identifique; e o superusuário passa em todo `has_perm`, o que ligaria à conta dele os pedidos que
  fizesse pelos formulários. É o mesmo desenho da Segurança do Trabalho (spec 008): o acesso é a
  participação no grupo. Exigir também a ausência de papel interno faz uma conta mal configurada
  (antes da recusa do admin, FR-002) cair do lado seguro: vale como equipe, pede anônimo e não abre
  "Meus pedidos".
- **Descartado**: uma permissão `contas.acompanhar_pedidos` no grupo (o superusuário a teria);
  um campo `Usuario.solicitante` (duplicaria o grupo, que é como o admin já dá papéis).

## R2. Pedido ligado à conta

- **Decisão**: `Pedido.conta`, `ForeignKey(AUTH_USER_MODEL, null=True, blank=True,
  on_delete=PROTECT, related_name="pedidos_feitos")`, em migration nova (`pedidos/0006_conta`),
  sem dados (todo pedido antigo fica `NULL`, FR-025). `solicitante` continua o texto gravado (nome da
  conta no momento do pedido), que o painel, o recibo e o Telegram já usam.
- **Motivo**: `PROTECT` impede apagar uma conta com pedidos (a conta se desativa, Edge Cases); o
  índice da FK serve à lista de "Meus pedidos" (`conta`, ordenada por `criado_em`). Só
  `servicos.registrar_pedido` grava o campo (Princípio II).
- **Descartado**: guardar a matrícula no pedido (texto solto, sem ligação; trocaria o login de quem
  muda de matrícula); `SET_NULL` (apagar a conta tornaria o pedido anônimo e o abriria na consulta
  pública, o contrário da privacidade).

## R3. Formulário aberto com conta: o token leva a conta

- **Decisão**: `protecao.emitir(conta_id=None)` grava `"conta": <pk ou None>` no token assinado;
  `protecao.ler` devolve `Envio.conta` (`None` também para o token antigo, sem a chave, de página
  aberta antes do deploy). Na view: token com conta e sem a mesma conta logada (anônimo ou outra) →
  recusa `MENSAGEM_SESSAO_TERMINOU`, sem gravar, com o carrinho mantido (FR-015). Token sem conta e
  solicitante logado → pedido anônimo, e a tela de sucesso diz que ele não foi ligado à conta (US4,
  cenário 3).
- **Motivo**: o token já é assinado e já viaja com o formulário; o pk da conta não é segredo, e a
  assinatura impede trocá-lo. A decisão fica do lado da situação de quando a página abriu: uma
  sessão que termina no meio nunca transforma o pedido em anônimo (SC-004).
- **Descartado**: comparar só a sessão no envio (perderia a sessão terminada); um campo escondido
  com a conta sem assinatura (forjável).

### R3a. Entrar de novo sem perder o carrinho: CSRF e nova aba

- **Problema** (conferido com um teste descartável em 2026-11-09): o `login()` do Django troca o
  segredo do CSRF (`rotate_token`). A aba antiga continua com o `csrfmiddlewaretoken` de antes, e o
  envio depois de entrar de novo recebe **403 de CSRF**; como o `htmx-config` não troca a página em
  respostas 4xx, a pessoa tocaria em Enviar e nada aconteceria. Do jeito que estava, a US4 não se
  cumpria: o carrinho continuava na tela, mas não havia como enviá-lo.
- **Decisão**:
  1. O link "Entrar" da recusa abre o login **numa aba nova** (`target="_blank"`, com o `next` para
     "Meus pedidos"): a aba do formulário, com o carrinho, fica onde está. A mensagem diz isso:
     "Sua sessão terminou. Entre de novo (abre em outra aba), volte aqui e toque em Enviar; os
     materiais continuam aqui."
  2. O `pedidos.js`, no formulário com conta, copia o cookie `csrftoken` para o
     `csrfmiddlewaretoken` do formulário logo antes de cada envio (o Django aceita o segredo do cookie
     como token, e o cookie não é `HttpOnly`). Assim o envio vale com o CSRF de agora, sem relaxar a
     verificação: o cookie só é lido pela própria página, do mesmo site.
- **Motivo**: o carrinho vive em campos escondidos e o servidor não guarda estado; recarregar o
  formulário depois do login o perderia. A troca do segredo no login é proteção do Django contra
  fixação de sessão e não deve ser desligada.
- **Descartado**: guardar o carrinho no servidor ou no `localStorage` (estado novo, e no aparelho
  dividido o carrinho de um ficaria para o outro); `CSRF_USE_SESSIONS` (o logout apagaria o segredo
  e pioraria o caso); desligar o CSRF no envio público (o token assinado não substitui o CSRF).

## R4. Nome e destino do pedido com conta

- **Decisão**: com conta, a view troca `EnvioPedido.solicitante` pelo nome da conta
  (`regras.nome_da_conta(first_name, last_name)`, pura) antes de chamar `registrar_pedido`, que
  recebe `conta=`; o campo do formulário sai `readonly` com o nome da conta. O destino sugerido é o
  do último pedido da conta naquele formulário (`origem`), só se ainda é uma opção de destino válida
  (`resolver_destino` contra `centros_do_fluxo`); senão, vazio. O reenvio compara também a conta:
  `anterior.conta_id` diferente da conta do envio é "divergente".
- **Motivo**: FR-013 manda ignorar o nome enviado; fazer isso na view mantém `regras` e
  `registro_confere` iguais, e o servidor, não o navegador, decide o nome. Sugerir um destino que não
  existe mais só produziria um erro no envio.
- **Descartado**: guardar o destino preferido na conta (mais um campo, e o "último pedido" já é a
  informação).

## R5. Troca obrigatória da senha

- **Decisão**: `Usuario.trocar_senha` (`BooleanField`, padrão `False`, migration nova
  `contas/0005_trocar_senha`: as contas existentes ficam `False`, FR-007). O admin liga a marca ao
  criar o usuário e ao definir a senha pela tela "Alterar senha" (`UsuarioAdmin.save_model` e
  `user_change_password`). O middleware `contas.middleware.ExigirTrocaDeSenha` (depois do
  `ExigirPermissao`) leva o solicitante com a marca à rota `trocar_senha` e só deixa abrir ela, o
  `logout` e as estáticas. A troca usa o `PasswordChangeView` do Django com formulário e template
  próprios (layout público), roda os `AUTH_PASSWORD_VALIDATORS`, desliga a marca e mantém a sessão
  (`update_session_auth_hash`).
- **Motivo**: a marca é ligada pelo admin para qualquer usuário, mas só é exigida do solicitante
  (FR-006 fala da conta de solicitante; a equipe não muda). O próprio solicitante também troca a senha
  quando quiser, pela mesma página (Assumptions).
- **Descartado**: comparar a data do último login com a da senha (o Django não guarda a data da
  senha).

## R6. Limite de tentativas: django-axes

- **Decisão**: `django-axes` 9.x (compatível com Django 6.0 e Python 3.13), sem o extra `ipware`.
  - `INSTALLED_APPS += ["axes"]`; `AUTHENTICATION_BACKENDS = ["axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend"]`; `axes.middleware.AxesMiddleware` por último.
  - `AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]` (só a combinação, FR-008).
  - `AXES_FAILURE_LIMIT` (padrão 5) e `AXES_COOLOFF_TIME` em minutos (padrão 15, vira `timedelta`),
    lidos do `.env` (`LOGIN_TENTATIVAS`, `LOGIN_BLOQUEIO_MINUTOS`) e documentados no `.env.example`
    (FR-009).
  - `AXES_RESET_ON_SUCCESS = True` (FR-011); o desbloqueio no admin é apagar a tentativa
    (`AccessAttempt`), que o próprio axes registra no admin.
  - `AXES_LOCKOUT_TEMPLATE = "contas/bloqueado.html"` (layout público, FR-010), com status 429.
  - `AXES_DISABLE_ACCESS_LOG = True`: o `AccessLog` do axes grava a matrícula, o endereço e o user
    agent de **todo login bem-sucedido**, sem limpeza; com dezenas de contas, cresceria para sempre e
    seria um registro de presença que a spec não pede. Fica só o `AccessAttempt` (as tentativas
    erradas, zeradas no login certo), que é o que o bloqueio usa. O `AccessFailureLog` já vem
    desligado no axes 9.
- **Origem**: sem o `ipware`, o axes usa o `REMOTE_ADDR`. A produção não tem proxy, então não há
  cabeçalho a confiar, e nada aqui permite forjar a origem. Se o Docker Desktop entregar o mesmo
  endereço a todos (F8), a combinação vira, na prática, bloqueio por matrícula, sem bloquear todo
  mundo (SC-005). Conferir no servidor real é uma tarefa antes do deploy, não do código.
- **Testes**: o axes exige o `request` no `authenticate`. O `Client.login` não o passa, então o único
  teste que o usa (`tests/test_config.py`) passa a entrar pelo formulário; `force_login` não
  autentica e não é afetado. O axes fica ligado nos testes (os do bloqueio precisam dele), com a
  tabela `AccessAttempt` limpa entre testes pela transação.
- **Descartado**: limite próprio contado no banco, como o dos pedidos (decisão do usuário pelo axes);
  bloqueio só por IP (travaria todo um setor atrás do mesmo endereço).

## R7. "Meus pedidos" na tabela de rotas

- **Decisão**: categoria nova `SOLICITANTE` em `contas.acesso.REGRAS_POR_ROTA` para
  `pedidos:meus_pedidos` (`/meus-pedidos/`) e `pedidos:meu_pedido` (`/meus-pedidos/<numero>/`). A
  troca de senha (`trocar_senha`, `/painel/senha/`) é de qualquer usuário logado e entra numa
  segunda categoria nova, `LOGADO` (todo autenticado abre; anônimo vai ao login); ela também entra em
  `ROTAS_SEGURANCA_TRABALHO`. No `ExigirPermissao`:
  - `SOLICITANTE`: anônimo vai ao login (e volta); solicitante passa; equipe é redirecionada ao seu
    ponto de partida (`contas.acesso.ponto_de_partida`: fila de autorizações para a Segurança do
    Trabalho, painel para os demais) (FR-024).
  - Solicitante numa rota interna (`Regra`): recusa 403, como na 012, mas com a página no layout
    público e o link para "Meus pedidos" (`sem_papel` passa a excluir o solicitante).
- **Motivo**: a tabela da 012 é a fonte única, e o teste que percorre as rotas obriga a rota nova a
  entrar nela. As rotas de "Meus pedidos" ficam fora de `ROTAS_SEGURANCA_TRABALHO`, então o middleware
  da 008 já leva quem é da Segurança à fila.
- **Descartado**: um `login_required` nas views (a 012 decidiu que o acesso é da tabela).

## R8. Depois de entrar

- **Decisão**: `contas.views.Entrar` (`LoginView` com o formulário de hoje) sobrescreve
  `get_default_redirect_url`: solicitante → `pedidos:meus_pedidos`, os demais → `LOGIN_REDIRECT_URL`
  (o painel; a Segurança do Trabalho já é levada à fila pelo middleware dela). O `next` seguro
  continua valendo. O `redirect_authenticated_user` usa a mesma regra.
- **Motivo**: FR-004 sem mexer no `LOGIN_REDIRECT_URL` global.

## R9. Detalhe do pedido sem dados da equipe

- **Decisão**: `pedidos/minhas.py` (sem ORM nas regras puras; leitura com consultas) monta a
  apresentação: a situação e a mensagem de `regras.texto_consulta_publica` (a mesma da consulta
  pública, spec 011), e uma linha por item `PEDIDO` com `qtd_pedida`, `qtd_entregue` (vazia antes do
  atendimento) e, se houver item `ALMOXARIFADO` com `no_lugar_de` apontando para ele, "trocado por
  <material>". Os itens `ALMOXARIFADO` sem `no_lugar_de` (acréscimos) nunca aparecem, e o template
  recebe só esse dicionário, nunca o `Pedido` (FR-020: nada de atendimento, recebedor, centro, placa,
  tipo, SCPI ou requisição chega ao template).
- **Motivo**: passar um dicionário fechado ao template é o que garante o FR-020 por construção, como
  a consulta pública já faz (`_resultado_da_consulta`).

## R10. Consulta pública e reenvio

- **Decisão**: a consulta pública filtra `conta__isnull=True` na mesma consulta de hoje, então o
  pedido com conta cai na resposta de "não encontrado" (FR-022), sem ramo novo.
- **`pedidos.js`**: o formulário com conta leva `data-com-conta`; o script não lê nem grava o
  `localStorage` do nome e do destino nesse formulário, e a tela de sucesso com conta não tem os
  `data-lembrar-*` (FR-014, US3 cenário 5). A chave existente não é apagada (pode ser de outra pessoa
  que usa o mesmo aparelho sem conta).
