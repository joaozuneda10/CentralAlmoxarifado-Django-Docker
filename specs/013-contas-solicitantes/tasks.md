---

description: "Tarefas da funcionalidade 013: contas de solicitante"
---

# Tasks: Contas de solicitante

**Input**: documentos de design em `specs/013-contas-solicitantes/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: **incluídos**. A constituição (Princípio V) exige teste automatizado para toda mudança de comportamento. Os testes rodam contra MariaDB/MySQL, sem navegador, nunca abrem o SCPI e nunca gravam no `logs/` do repositório.

**Organization**: tarefas agrupadas pelas histórias da spec. A ordem das fases não é a das prioridades: a US3 (pedido com conta) vem antes da US1 e da US2, porque elas mostram e protegem os pedidos que ela liga à conta; a US5 (criar a conta) vem primeiro, porque sem conta nenhuma história se testa de ponta a ponta.

**Entrega**: nada vai a produção sem as seis histórias. O corte mínimo que já se demonstra é Foundational + US5 + US3 + US1 + US2; a US4 e a US6 completam a spec antes do PR.

## Format: `[ID] [P?] [Story] Descrição com caminho de arquivo`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: história da spec; Setup, Foundational e Polish não têm
- Comandos: `uv run pytest <arquivo>`, `uv run ruff check . && uv run ruff format --check .`, `uv run python manage.py makemigrations --check --dry-run`. **Banco de desenvolvimento apenas; nada de `docker compose` na produção; nenhum `migrate` no banco real.**

## Regras gerais para todas as tarefas

- Código Python: investigar com o Serena antes (`find_symbol`, `find_referencing_symbols`), conforme o `CLAUDE.md`.
- Migrations sempre novas (`contas/0005_trocar_senha`, `contas/0006_solicitante`, `pedidos/0006_conta`), nunca regeneradas; nomes de grupo copiados como literais dentro da migration de dados.
- `pedidos/servicos.py` continua o único lugar que grava pedidos (Princípio II): `Pedido.conta` só é gravado em `registrar_pedido`.
- Textos de interface em pt-BR, no design Clean (`docs/DESIGN.md`, skill `clean-design`); estado nunca só por cor; matrícula e número do pedido em `.mono`; Sair por POST com CSRF, um só formulário por página.
- Testes de privacidade conferem o HTML inteiro: o que não pode aparecer é procurado no texto da resposta, não só no contexto.
- O teste da tabela de rotas da spec 012 (`tests/test_papeis_acesso.py`) tem de continuar verde: rota nova entra em `REGRAS_POR_ROTA` na mesma tarefa que a cria.

---

## Phase 1: Setup

**Purpose**: branch, dependência e ponto de partida

- [X] T001 Confirmar a branch `claude/contas-solicitantes` (de `develop` com a 012 e o #69) e rodar `uv run pytest` para registrar a suíte verde de partida
- [X] T002 Acrescentar `django-axes` (`>=9,<10`, sem o extra `ipware`) com `uv add "django-axes>=9,<10"` em `pyproject.toml` e `uv.lock`

---

## Phase 2: Foundational

**Purpose**: o que todas as histórias usam. Sem esta fase, nenhuma conta de solicitante existe nem é reconhecida.

**⚠️ CRITICAL**: nenhuma história começa antes desta fase.

- [X] T003 Acrescentar `Usuario.trocar_senha = models.BooleanField("trocar a senha no próximo acesso", default=False)` em `contas/models.py` e gerar `contas/migrations/0005_trocar_senha.py` (`AddField`, `default=False`: nenhuma conta existente fica obrigada a trocar, FR-007)
- [X] T004 Criar `contas/migrations/0006_solicitante.py` (RunPython com `noop` na volta) que faz `get_or_create` do grupo `"Solicitante"` sem permissão nenhuma e não muda nenhum usuário (FR-001); depende de `contas/0005_trocar_senha` e `contas/0004_papeis`
- [X] T005 Acrescentar `Pedido.conta = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="pedidos_feitos", verbose_name="conta do solicitante")` em `pedidos/models.py` e gerar `pedidos/migrations/0006_conta.py` (`AddField`, pedidos antigos `NULL`, FR-025)
- [X] T006 Em `contas/acesso.py`: `GRUPO_SOLICITANTE = "Solicitante"`; `eh_solicitante(usuario)` (autenticado, ativo, no grupo, sem `is_staff`, sem `is_superuser`, sem permissão de `PERMISSOES_INTERNAS`, fora da Segurança do Trabalho; guardado no objeto como `_eh_solicitante`, igual ao `da_seguranca_trabalho`); `ponto_de_partida(usuario)` (nome da rota: `pedidos:autorizacoes` para a Segurança do Trabalho, `pedidos:meus_pedidos` para o solicitante, `pedidos:painel` para os demais); categorias `SOLICITANTE = "solicitante"` e `LOGADO = "logado"`; `sem_papel` passa a devolver falso para o solicitante (research R1, R7; `contracts/rotas-e-acesso.md`). Na mesma tarefa, criar as duas rotas de "Meus pedidos" para que `ponto_de_partida` e o login já as resolvam desde a US5: `pedidos/views/solicitante.py` com `meus_pedidos` e `meu_pedido` mínimas (lista vazia e `Http404`, ambas `never_cache`), `meus-pedidos/` (`pedidos:meus_pedidos`) e `meus-pedidos/<str:numero>/` (`pedidos:meu_pedido`) em `pedidos/urls.py`, e as duas como `SOLICITANTE` em `REGRAS_POR_ROTA` (fora de `ROTAS_SEGURANCA_TRABALHO`); `tests/test_papeis_acesso.py` continua verde
- [X] T007 [P] Testes puros de `eh_solicitante`, `ponto_de_partida` e `sem_papel` em `tests/test_solicitante_acesso.py`: solicitante comum; no grupo com `is_staff`, com `is_superuser`, com `Atendimento`, com `Gestão`, com `Segurança do Trabalho` (todos falsos); inativo (falso); anônimo (falso)
- [X] T008 [P] Criar `tests/solicitantes.py` com `criar_solicitante(username="90001", nome="Maria", sobrenome="da Silva", senha=..., trocar_senha=False)` (usuário no grupo `Solicitante`, `_garantir_grupos` como em `tests/papeis.py` para os testes `transaction=True`) e `cliente_solicitante(usuario)` (`Client` com `force_login`)
- [X] T009 Configurar o axes em `config/settings.py`: `"axes"` em `INSTALLED_APPS`; `AUTHENTICATION_BACKENDS = ["axes.backends.AxesStandaloneBackend", "django.contrib.auth.backends.ModelBackend"]`; `"axes.middleware.AxesMiddleware"` por último no `MIDDLEWARE`; `AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]`; `AXES_FAILURE_LIMIT = ler_int("LOGIN_TENTATIVAS", 5)`; `AXES_COOLOFF_TIME = timedelta(minutes=ler_int("LOGIN_BLOQUEIO_MINUTOS", 15))`; `AXES_RESET_ON_SUCCESS = True`; `AXES_LOCKOUT_TEMPLATE = "contas/bloqueado.html"`; `AXES_DISABLE_ACCESS_LOG = True` (research R6; criar `ler_int` em `config/env.py` se não existir, com teste em `tests/test_config.py`)
- [X] T010 Documentar `LOGIN_TENTATIVAS` e `LOGIN_BLOQUEIO_MINUTOS` (com os padrões e o que fazem) em `.env.example`
- [X] T011 Trocar o `client.login(...)` de `tests/test_config.py` (o axes exige o `request` no `authenticate`) por um POST no formulário de entrar, mantendo o que o teste confere; criar o template mínimo `contas/templates/contas/bloqueado.html` (layout público, a frase de `contracts/login-senha-admin.md`) para o axes não falhar ao carregar o settings
- [X] T012 Rodar a suíte inteira, `makemigrations --check --dry-run` e `DEBUG=0 uv run python manage.py check --deploy --fail-level WARNING`: tudo verde antes de seguir

**Checkpoint**: grupo, colunas e axes no lugar; a suíte da 012 continua verde.

---

## Phase 3: User Story 5 - O almoxarifado cria e mantém as contas (Priority: P1) 🎯

**Goal**: o chefe cria a conta no admin, a pessoa troca a senha no primeiro acesso e cai em "Meus pedidos"; combinações proibidas são recusadas.

**Independent Test**: criar uma conta pelo admin, entrar com a senha inicial, ser levado à troca, trocar e cair em "Meus pedidos"; redefinir no admin e ver a troca de novo.

### Tests for User Story 5

- [X] T013 [P] [US5] Em `tests/test_solicitante_senha_admin.py`, testes do admin (`contracts/login-senha-admin.md`): criar usuário pelo `add_view` liga `trocar_senha`; "Alterar senha" (`user_change_password`) liga de novo; salvar com `Solicitante` + `Atendimento`/`Gestão`/`Segurança do Trabalho`/`is_staff`/`is_superuser` é recusado com a mensagem do contrato e nada muda; `Solicitante` sem nome completo é recusado; a equipe salva como antes
- [X] T014 [P] [US5] No mesmo arquivo, testes da troca obrigatória: solicitante com `trocar_senha` que abre `/meus-pedidos/` ou um formulário é levado (GET) a `trocar_senha`, e um POST em outra rota recebe 403; `logout` funciona; troca com senha fraca é recusada pelos validadores; troca válida desliga a marca, mantém a sessão e leva a "Meus pedidos"; membro da equipe com `trocar_senha` ligado não é obrigado; a migration não ligou a marca de ninguém (usuário criado antes dela continua `False`)
- [X] T015 [P] [US5] No mesmo arquivo, testes do redirecionamento depois de entrar (POST no formulário de entrar): solicitante → `pedidos:meus_pedidos`; Atendimento → painel; Segurança do Trabalho → fila; `next` do mesmo site é respeitado; solicitante já logado que abre `/painel/entrar/` vai a "Meus pedidos"

### Implementation for User Story 5

- [X] T016 [US5] Em `contas/forms.py`: `FormularioUsuarioAdmin` (o `UserChangeForm` com `clean()` que recusa `Solicitante` junto com os grupos internos, `is_staff` ou `is_superuser`, e `Solicitante` sem `first_name`/`last_name`, com as mensagens do contrato) e `FormularioTrocaSenha` (`PasswordChangeForm` com rótulos e erros em pt-BR)
- [X] T017 [US5] Em `contas/admin.py`: `UsuarioAdmin(UserAdmin)` com `form = FormularioUsuarioAdmin`, `trocar_senha` nos `fieldsets` (seção "Acesso") e `list_display`/`list_filter` com ele; `save_model` liga `trocar_senha` na criação; `user_change_password` liga `trocar_senha` depois de salvar a senha nova; registrar no lugar do `UserAdmin`
- [X] T018 [US5] Criar `contas/views.py` com `Entrar(LoginView)` (template, formulário e `redirect_authenticated_user` de hoje; `get_default_redirect_url` devolve `reverse(ponto_de_partida(usuario))` para o solicitante e `LOGIN_REDIRECT_URL` para os demais) e `TrocarSenha(PasswordChangeView)` (`FormularioTrocaSenha`, `contas/trocar_senha.html`, no sucesso desliga `trocar_senha`, `messages.success("Senha trocada.")` e vai ao `ponto_de_partida`)
- [X] T019 [US5] Em `contas/urls.py`: `entrar/` passa a `Entrar.as_view()`, e `senha/` → `TrocarSenha`, nome `trocar_senha`; em `contas/acesso.py`, `"trocar_senha": LOGADO` em `REGRAS_POR_ROTA` e `"trocar_senha"` em `ROTAS_SEGURANCA_TRABALHO`
- [X] T020 [US5] Em `contas/middleware.py`: o `ExigirPermissao` trata `LOGADO` (anônimo → login com `next`; logado passa) e `SOLICITANTE` (anônimo → login; solicitante passa; equipe → `redirect(ponto_de_partida(usuario))`); para o solicitante numa `Regra`, a recusa usa `interface/acesso_negado.html` no layout público (contexto `solicitante=True`, link "Meus pedidos") e continua registrando no log; nova classe `ExigirTrocaDeSenha.process_view` (solicitante com `trocar_senha`, rota fora de `trocar_senha` e `logout`: GET → redirect, demais → 403); em `config/settings.py`, `ExigirTrocaDeSenha` logo depois do `ExigirPermissao`
- [X] T021 [P] [US5] Template `contas/templates/contas/trocar_senha.html` (extends `base_publico.html`; título "Trocar a senha", aviso "Antes de continuar, troque a senha que o almoxarifado entregou." quando a troca é obrigatória, campos com erro embaixo de cada um, botão "Trocar a senha"; **sem** formulário de Sair próprio: o do `base_publico.html` (T052) é o único da página)
- [X] T022 [US5] Em `interface/templates/interface/acesso_negado.html`, a variante do solicitante: com `solicitante`, estende `base_publico.html`, título "Esta página é da equipe do almoxarifado" e o link "Ver meus pedidos" (sem o "Voltar ao painel" e sem Sair próprio: vale o do layout)

**Checkpoint**: uma conta de solicitante existe, entra, troca a senha, cai em "Meus pedidos" (ainda a página mínima da T006) e é recusada na área interna; os testes da fase inteira passam.

---

## Phase 4: User Story 3 - Pedir mais rápido e em nome próprio (Priority: P2, pré-requisito de US1 e US2)

**Goal**: logado, o solicitante pede com o nome da conta e o destino do último pedido; o pedido sai ligado à conta.

**Independent Test**: logado, fazer um pedido; abrir o mesmo formulário e ver o nome travado e o destino sugerido; mandar outro nome pelo POST e ver que grava o da conta.

### Tests for User Story 3

- [X] T023 [P] [US3] Em `tests/test_solicitante_formulario.py` (`contracts/formulario-com-conta.md`): GET do solicitante mostra o nome da conta `readonly`, `data-com-conta` no `<form>` e o token com a conta; GET de anônimo e de equipe sem conta e sem `data-com-conta`; destino sugerido é o do último pedido da conta naquela origem, vazio em outra origem e vazio se o centro deixou de ser destino; POST com outro nome grava o nome da conta e `Pedido.conta`; equipe logada pede anônimo; anônimo como hoje
- [X] T024 [P] [US3] No mesmo arquivo: tela de sucesso do pedido com conta tem o link para `pedidos:meu_pedido` e não tem o aviso de guardar o número, a consulta pública nem `data-lembrar-`; reenvio igual com a mesma conta confirma sem duplicar; reenvio com outra conta (token re-emitido com o mesmo id) é divergente; token antigo sem a chave `conta` é aceito como anônimo; pedido de EPI com conta nasce `AGUARDANDO` e avisa a Segurança como antes; pedido com conta continua recusado pela isca e pelo tempo mínimo, e o limite por nome conta pelo nome da conta (mesmo com outro nome no POST) e o limite por IP como antes (FR-017)
- [X] T025 [P] [US3] Testes puros em `tests/test_solicitante_regras.py`: `regras.nome_da_conta("  Maria ", "da  Silva")` → `"Maria da Silva"`; nome vazio → `""`; e, no mesmo arquivo, `emitir(conta_id=7)` → `ler(...).conta == 7`; token sem a chave → `conta is None`

### Implementation for User Story 3

- [X] T026 [US3] Em `pedidos/protecao.py`: `Envio.conta: int | None = None`; `emitir(envio_id=None, aberto_em=None, conta_id=None)` grava `"conta"`; `ler` lê `dados.get("conta")` (int ou None)
- [X] T027 [US3] Em `pedidos/regras.py`: `nome_da_conta(nome, sobrenome) -> str` (pura, com `texto`)
- [X] T028 [US3] Em `pedidos/servicos.py`: `registrar_pedido(..., conta=None)` grava `Pedido.conta`; o reenvio exige `registro_confere(...)` **e** `anterior.conta_id == (conta.pk if conta else None)`, senão divergente; nova função de leitura `destino_sugerido(conta, origem, centros) -> str` (último `Pedido` da conta naquela origem, `resolver_destino` contra os centros do fluxo, `""` se não resolve)
- [X] T029 [US3] Em `pedidos/views/publico.py` (`formulario`): com `eh_solicitante(request.user)`, o GET emite o token com `conta_id`, preenche `campos["solicitante"]` com `nome_da_conta(...)` e `campos["destino"]` com `destino_sugerido`, e põe `com_conta=True` no contexto; no POST com `envio.conta` igual ao usuário logado, substitui `EnvioPedido.solicitante` pelo nome da conta e passa `conta=request.user`; o contexto de sucesso leva `com_conta` e `sem_conta_logado` (solicitante logado com token sem conta, US4 cenário 3)
- [X] T030 [US3] Templates: em `pedidos/templates/pedidos/_formulario.html`, `data-com-conta` no `<form>` e o campo do nome `readonly`, sem o botão Limpar, com a dica "Nome da sua conta." no lugar de "Ficam guardados no seu aparelho..."; em `pedidos/templates/pedidos/_sucesso.html`, a variante com conta ("Acompanhe em Meus pedidos." e o botão "Ver em Meus pedidos", sem `data-lembrar-*`, sem o aviso de guardar o número e sem a consulta pública) e o aviso "Este pedido foi feito sem entrar na conta e não aparece em Meus pedidos." para `sem_conta_logado`
- [X] T031 [US3] Em `pedidos/static/pedidos/js/pedidos.js`: no formulário com `data-com-conta`, não ler nem gravar o `localStorage` (`almoxarifado.solicitante`), sem apagar a chave existente. O projeto não tem teste de JavaScript (Princípio V): o gatilho do script é coberto pelos testes de template da T023 e T024 (`data-com-conta` presente, `data-lembrar-*` ausente), e o comportamento no navegador pela conferência da T053

**Checkpoint**: pedidos com conta são gravados ligados a ela, com o nome da conta.

---

## Phase 5: User Story 1 - Acompanhar os próprios pedidos (Priority: P1) 🎯 MVP

**Goal**: "Meus pedidos" lista os pedidos da conta e mostra cada um com a situação, as quantidades e as trocas.

**Independent Test**: dois pedidos com a conta, um atendido parcialmente com uma troca; conferir a lista e as páginas.

### Tests for User Story 1

- [X] T032 [P] [US1] Em `tests/test_solicitante_meus_pedidos.py` (`contracts/meus-pedidos.md`): lista só com os pedidos da conta, do mais novo, com número, formulário, data e selo (texto); 21 pedidos → 2 páginas de 20; pedido anônimo da mesma pessoa não aparece; lista vazia com a frase e os links dos formulários; `Cache-Control` com `no-store`
- [X] T033 [P] [US1] No mesmo arquivo: pedido atendido parcialmente com uma troca (via `confirmar_atendimento` com troca e acréscimo) mostra "Atendido parcialmente", a mensagem da spec 011, pedida e entregue por linha e "trocado por <material>"; o HTML **não** contém o recebedor, o centro de custo, a placa, o tipo de saída, a matrícula de quem atendeu nem o material só acrescentado; EPI recusado mostra "Recusado" e o motivo, sem quem decidiu; pedido antes do atendimento mostra a entregue vazia; pedido das viaturas mostra o destino, a observação e o nº da ocorrência informados (FR-019)
- [X] T034 [P] [US1] Testes de `pedidos.minhas.apresentar` em `tests/test_solicitante_meus_pedidos.py`: as chaves do dicionário são exatamente as do contrato (nada além), e `trocado_por` só aparece no item trocado

### Implementation for User Story 1

- [X] T035 [US1] Criar `pedidos/minhas.py` com `apresentar(pedido) -> dict` (as chaves de `contracts/meus-pedidos.md`, reusando `regras.texto_consulta_publica` como `views.publico._resultado_da_consulta`; itens `PEDIDO` com `qtd_pedida`, `qtd_entregue` e `trocado_por` do item `ALMOXARIFADO` com `no_lugar_de`; nunca os acrescentados) e `linha_da_lista(pedido) -> dict` (número, formulário, data, selo)
- [X] T036 [US1] Completar em `pedidos/views/solicitante.py` (criado mínimo na T006) as views `meus_pedidos` (`never_cache`, `Paginator` de 20 sobre `Pedido.objects.filter(conta=request.user)` com `select_related("atendimento", "autorizacao")` e ordem `-criado_em`, `?pagina=`) e `meu_pedido` (`never_cache`, `get_object_or_404(Pedido, numero=numero, conta=request.user)` com o prefetch dos itens, contexto só com `apresentar(pedido)`)
- [X] T037 [US1] Conferir que as rotas criadas na T006 (`pedidos:meus_pedidos`, `pedidos:meu_pedido`) servem as views completas sem mudar caminho, nome nem categoria, e que nenhuma outra rota nova entrou fora de `REGRAS_POR_ROTA`
- [X] T038 [P] [US1] Templates `pedidos/templates/pedidos/meus_pedidos.html` (extends `base_publico.html`; lista em cartões no celular, número em `.mono`, selo com texto, paginação "Anteriores"/"Mais antigos") e `pedidos/templates/pedidos/meu_pedido.html` (link "Voltar a Meus pedidos" no bloco `voltar`; cabeçalho com número, formulário e data; o selo e a mensagem; destino, observação e ocorrência; a tabela de materiais com pedida, entregue e a troca); um `404.html` não muda: a resposta de "não encontrado" é a do projeto
- [X] T039 [US1] Rodar de novo os testes da US5 (T013 a T015), agora com a lista completa, e o `tests/test_papeis_acesso.py`

**Checkpoint**: o MVP do solicitante (entrar e acompanhar) funciona.

---

## Phase 6: User Story 2 - Só o dono vê o pedido (Priority: P1)

**Goal**: o pedido com conta só abre para o dono; a consulta pública não o mostra.

**Independent Test**: duas contas; a segunda e a consulta pública tentam abrir o pedido da primeira.

### Tests for User Story 2

- [X] T040 [P] [US2] Em `tests/test_solicitante_meus_pedidos.py`: a conta B recebe 404 no pedido da conta A, num pedido anônimo e num número inexistente, com o mesmo corpo de resposta nos três (comparar o HTML sem o token do CSRF); a resposta do pedido do próprio dono também tem `Cache-Control` com `no-store` (FR-023)
- [X] T041 [P] [US2] Em `tests/test_solicitante_consulta.py`: a consulta pública com o número e o primeiro nome certos de um pedido com conta responde `MENSAGEM_CONSULTA_NAO_ACHADA`, igual a um número inexistente; o pedido anônimo continua abrindo; a tentativa conta no limite por origem como antes
- [X] T042 [P] [US2] Em `tests/test_solicitante_acesso.py`: anônimo em `/meus-pedidos/` vai ao login e, depois de entrar como solicitante, volta à lista; Atendimento e Gestão são redirecionados ao painel; a Segurança do Trabalho, à fila; o solicitante recebe 403 (layout público, link "Ver meus pedidos", linha no log `contas.acesso`) em toda rota `Regra`, por GET e POST, sem criar `ExecucaoRobo`; nenhuma rota nomeada do projeto cria usuário fora do admin (nenhuma rota `PUBLICA` com "cadastr", "registr" ou "signup" no nome ou no caminho, FR-003)

### Implementation for User Story 2

- [X] T043 [US2] Em `pedidos/views/publico.py` (`consulta`): acrescentar `conta__isnull=True` ao filtro da busca (FR-022)

**Checkpoint**: privacidade garantida nas duas portas (Meus pedidos e consulta pública).

---

## Phase 7: User Story 4 - Sessão que termina no meio do pedido (Priority: P2)

**Goal**: o formulário aberto com conta nunca vira pedido anônimo; a pessoa entra de novo em outra aba e envia o que estava na tela.

**Independent Test**: abrir logado, sair, enviar (recusa com carrinho), entrar de novo no mesmo cliente e reenviar com o CSRF do cookie.

### Tests for User Story 4

- [X] T044 [P] [US4] Em `tests/test_solicitante_formulario.py`: formulário aberto com a conta A enviado sem sessão → recusa com a mensagem do contrato, link "Entrar" com `target="_blank"`, os materiais nos campos escondidos e nada gravado (`Pedido` e `Sequencia` intactos); enviado com a conta B → a mesma recusa; aberto sem conta e enviado logado → anônimo com o aviso de sucesso
- [X] T045 [P] [US4] No mesmo arquivo, com `Client(enforce_csrf_checks=True)`: abrir logado, sair, entrar de novo (o CSRF troca), reenviar o POST com o `csrfmiddlewaretoken` igual ao cookie `csrftoken` (o que o `pedidos.js` faz) → pedido registrado com a conta; reenviar com o token antigo → 403 (documenta o motivo do R3a)

### Implementation for User Story 4

- [X] T046 [US4] Em `pedidos/views/publico.py` (`formulario`), depois da isca e do tempo mínimo: `envio.conta` presente e (`not eh_solicitante(request.user)` ou `request.user.pk != envio.conta`) → `de_volta(envio, mensagem=MENSAGEM_SESSAO_TERMINOU, sessao_terminou=True)`; constante `MENSAGEM_SESSAO_TERMINOU` em `pedidos/protecao.py` com o texto do contrato
- [X] T047 [US4] Em `pedidos/templates/pedidos/_formulario.html`, com `sessao_terminou`: o link "Entrar" para o login com `next` = `pedidos:meus_pedidos`, `target="_blank"` e `rel="noopener"`, junto da mensagem
- [X] T048 [US4] Em `pedidos/static/pedidos/js/pedidos.js`: no formulário com `data-com-conta`, no `htmx:configRequest` (ou no `submit`, antes do HTMX), copiar o valor do cookie `csrftoken` para o `csrfmiddlewaretoken` do formulário e do pedido; sem cookie, não mexe

**Checkpoint**: sessão terminada não perde nem anonimiza o pedido.

---

## Phase 8: User Story 6 - Limite de tentativas no login (Priority: P2)

**Goal**: bloqueio por matrícula e origem nas duas portas, com página em português e desbloqueio no admin.

**Independent Test**: errar até o limite, ver o bloqueio, outra matrícula entra, desbloquear no admin.

### Tests for User Story 6

- [X] T049 [P] [US6] Em `tests/test_solicitante_bloqueio.py` (`contracts/login-senha-admin.md`, com `settings.AXES_FAILURE_LIMIT = 3` pelo fixture): 3 erros na mesma matrícula e origem → a 4ª tentativa (mesmo com a senha certa) recebe 429 com a frase do bloqueio; antes do limite, a recusa é "Matrícula ou senha incorretas."; outra matrícula da mesma origem entra; a mesma matrícula de outra origem (`REMOTE_ADDR` diferente) entra
- [X] T050 [P] [US6] No mesmo arquivo: o login do admin bloqueia do mesmo jeito; depois do `AXES_COOLOFF_TIME` (o projeto não tem `freezegun`: recuar a tentativa com `AccessAttempt.objects.filter(username=...).update(attempt_time=timezone.now() - timedelta(minutes=16))`) a senha certa entra e zera as tentativas; apagar a `AccessAttempt` desbloqueia na hora; nenhuma linha em `AccessLog` depois de um login certo

### Implementation for User Story 6

- [X] T051 [US6] Completar `contas/templates/contas/bloqueado.html` (extends `base_publico.html`; título "Muitas tentativas", a frase do contrato, link "Voltar aos formulários"), conferir que o axes responde 429 com ele nas duas portas e registrar no admin o nome em português das tentativas, se o axes não o trouxer

**Checkpoint**: as seis histórias completas.

---

## Phase 9: Polish

- [X] T052 Em `interface/templates/interface/base_publico.html`: "Entrar" (com `next` da página atual) para quem não está logado; "Meus pedidos" e "Sair" (formulário POST com CSRF, o único da página) para o solicitante; nada novo para a equipe. Teste em `tests/test_solicitante_acesso.py`: anônimo, solicitante e equipe veem o que o contrato diz, e **exatamente um** `action` de logout em cada página do solicitante (troca de senha, recusa do solicitante, lista, pedido, formulário logado, sucesso e bloqueio)
- [X] T053 [P] Conferir à mão, pelo roteiro de `quickstart.md`, no celular (375 px) e no computador, com screenshots: lista, pedido, formulário com conta, recusa da sessão, troca de senha e bloqueio. Conferir também, no navegador, o que só o JavaScript faz (Princípio V, T031 e T048): com conta, o `localStorage` `almoxarifado.solicitante` não muda depois de digitar e de enviar; e o reenvio pela aba antiga depois de entrar de novo em outra aba registra o pedido (sem 403 no console nem na rede); usar as skills `clean-design`, `ui-ux-pro-max` e `frontend-design` como manda o `CLAUDE.md`
- [X] T054 Atualizar o `CLAUDE.md`: a seção de papéis (spec 012) ganha o solicitante (grupo, `eh_solicitante`, categorias `SOLICITANTE` e `LOGADO`, `ExigirTrocaDeSenha`); os formulários públicos ganham o pedido com conta (token com a conta, nome, destino sugerido, sessão terminada e o CSRF do cookie); a consulta pública não abre pedido com conta; o axes (configuração, `AXES_DISABLE_ACCESS_LOG`, `Client.login` não funciona nos testes); as variáveis novas
- [X] T055 Marcar a spec e as tarefas: `specs/013-contas-solicitantes/spec.md` (status) e este `tasks.md`
- [X] T056 Portões finais: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run python manage.py makemigrations --check --dry-run`, `DEBUG=0 uv run python manage.py check --deploy --fail-level WARNING`; anotar no PR a conferência pendente do `REMOTE_ADDR` no servidor real (F8)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (1)** → **Foundational (2)** → **US5 (3)** → **US3 (4)** → **US1 (5)** → **US2 (6)** → **US4 (7)** e **US6 (8)** → **Polish (9)**
- US4 depende da US3 (o token com a conta e o `data-com-conta`).
- US6 depende só do Foundational (T009, T011) e pode correr em paralelo com US3 a US4.
- US2 depende da US1 (as rotas de "Meus pedidos").

### Dentro de cada história

- Testes primeiro (devem falhar), depois a implementação.
- `contas/acesso.py` e `contas/middleware.py` são tocados em T006, T019 e T020: em sequência.
- `pedidos/views/solicitante.py` e `pedidos/urls.py` nascem mínimos na T006 e são completados na T036.
- `pedidos/views/publico.py` é tocado em T029, T043 e T046: em sequência.
- `pedidos/static/pedidos/js/pedidos.js` em T031 e T048: em sequência.

### Parallel Opportunities

- T007 e T008 juntos depois de T006.
- T013, T014 e T015 (mesmo arquivo de teste, mas escritos de uma vez) em paralelo com T021.
- T023, T024 e T025 juntos.
- T032, T033 e T034 juntos; T038 em paralelo com T035 e T036.
- T040, T041 e T042 juntos.
- A fase da US6 inteira em paralelo com as fases 4 a 7.

---

## Parallel Example: User Story 1

```bash
# Testes juntos (arquivo único, escritos de uma vez):
Task: "T032 lista de Meus pedidos em tests/test_solicitante_meus_pedidos.py"
Task: "T033 pedido sem dados da equipe em tests/test_solicitante_meus_pedidos.py"
Task: "T034 chaves de apresentar em tests/test_solicitante_meus_pedidos.py"

# Templates em paralelo com a apresentação e as views:
Task: "T038 meus_pedidos.html e meu_pedido.html"
```

---

## Implementation Strategy

### MVP

1. Setup + Foundational.
2. US5 (a conta existe e entra).
3. US3 (o pedido sai ligado à conta).
4. US1 (Meus pedidos). **Parar e validar**: entrar, pedir e acompanhar.

### Incremental

5. US2 (privacidade) → validar com duas contas e a consulta pública.
6. US4 (sessão terminada) → validar o reenvio com o CSRF do cookie.
7. US6 (bloqueio) → validar as duas portas.
8. Polish → quickstart à mão, `CLAUDE.md`, portões.

Nada vai a produção sem as seis histórias, e o deploy exige a spec 012 já implantada antes.

---

## Notes

- Total: 56 tarefas (Setup 2, Foundational 10, US5 10, US3 9, US1 8, US2 4, US4 5, US6 3, Polish 5).
- [P] = arquivos diferentes, sem dependência de tarefa incompleta.
- Commit ao fim de cada fase, na `claude/contas-solicitantes`; push e PR só a pedido.
