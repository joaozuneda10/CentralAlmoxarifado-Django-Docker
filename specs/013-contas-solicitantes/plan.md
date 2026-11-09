# Implementation Plan: Contas de solicitante

**Branch**: `claude/contas-solicitantes` | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/013-contas-solicitantes/spec.md`

## Summary

Funcionários que pedem material ganham uma conta opcional, criada pelo almoxarifado no admin (sem
cadastro aberto): entram pela matrícula, pedem com o nome da conta e o destino do último pedido já
preenchidos e acompanham em "Meus pedidos" só o que pediram com ela. O pedido feito com conta fica
ligado a ela (`Pedido.conta`) e sai da consulta pública. A conta é um `Usuario` no grupo novo
`Solicitante`, sem permissão interna, e entra na tabela de rotas da spec 012 por duas categorias novas
(`SOLICITANTE` e `LOGADO`). O formulário leva no token assinado a conta com que abriu, para uma sessão
que termina no meio nunca virar pedido anônimo. Senha inicial e senha redefinida no admin exigem troca
no acesso seguinte; o login das duas portas ganha limite de tentativas por matrícula e origem com o
django-axes.

## Technical Context

**Language/Version**: Python 3.13, Django 6.x

**Primary Dependencies**: Django (auth, admin, `PasswordChangeView`), HTMX 4 (vendorizado), e o
**django-axes 9.x** (novo, sem o extra `ipware`)

**Storage**: MariaDB 11.4 / MySQL 8. Migrations novas: `contas/0005_trocar_senha`,
`contas/0006_solicitante` (dados: o grupo), `pedidos/0006_conta`, e as do axes

**Testing**: pytest + pytest-django contra MariaDB (`config.settings_test`), sem navegador; o axes
fica ligado nos testes

**Target Platform**: servidor Windows 10 com Docker Desktop (waitress), HTTP direto, sem proxy

**Project Type**: aplicação web Django (monólito com apps)

**Performance Goals**: "Meus pedidos" responde como as páginas atuais (uma consulta paginada pela FK
`conta`, 20 por página); o formulário público não ganha consulta pesada (o destino sugerido é uma
consulta por índice)

**Constraints**: nenhuma mudança para quem não tem conta (FR-025); nenhuma conta existente obrigada a
trocar a senha (FR-007); produção sem proxy (a origem do axes é o `REMOTE_ADDR`); sem e-mail

**Scale/Scope**: dezenas de contas de solicitante; 6 histórias, 25 requisitos; 3 rotas novas

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Situação | Como |
|-----------|----------|------|
| I. Regras puras | ✅ | `regras.nome_da_conta` é pura; a situação e a mensagem reusam `regras.texto_consulta_publica` (spec 011); `eh_solicitante` e `ponto_de_partida` ficam em `contas.acesso`, junto da tabela de rotas |
| II. Uma porta de gravação | ✅ | `Pedido.conta` só é gravado em `servicos.registrar_pedido`, na mesma transação; o reenvio continua decidido pelo `Pedido.id`, agora conferindo também a conta. O admin grava só `Usuario` e o axes só as tabelas dele |
| III. Nunca lançar duas vezes | ✅ não tocado | nada no robô, nas `LinhaSaida` nem no lançamento muda; `Pedido.conta` não entra no lote |
| IV. Importados não se perdem | ✅ não tocado | sem importação |
| V. Testes no banco real, sem navegador | ✅ | testes de acesso, formulário, privacidade, admin e bloqueio contra MariaDB; o único `Client.login` passa a entrar pelo formulário (o axes exige o `request`); nada grava em `logs/` (spec do #69) |
| VI. pt-BR, acessível, sem dependências externas | ✅ | textos em português; selos com texto; matrícula em `.mono`; logout por POST num único formulário por página; o django-axes é dependência Python pelo `uv`, sem CDN nem npm |
| Restrições | ✅ | as 2 variáveis novas (`LOGIN_TENTATIVAS`, `LOGIN_BLOQUEIO_MINUTOS`) no `.env.example`; `check --deploy` sem avisos; migrations novas, nenhuma regenerada |
| Fluxo | ✅ | spec e plano antes do código; branch `claude/contas-solicitantes` a partir de `develop` com a 012; `CLAUDE.md` atualizado no mesmo PR |

Re-check depois do desenho (Phase 1): sem mudança; nenhuma exceção a justificar.

## Project Structure

### Documentation (this feature)

```text
specs/013-contas-solicitantes/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── rotas-e-acesso.md
│   ├── formulario-com-conta.md
│   ├── meus-pedidos.md
│   └── login-senha-admin.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
contas/
├── acesso.py            # SOLICITANTE, LOGADO, eh_solicitante, ponto_de_partida, rotas novas
├── middleware.py        # ExigirPermissao (categorias novas, recusa do solicitante), ExigirTrocaDeSenha
├── models.py            # Usuario.trocar_senha
├── admin.py             # UsuarioAdmin: marca de troca, combinação proibida, nome obrigatório
├── forms.py             # FormularioTrocaSenha, validação do admin
├── views.py             # Entrar (redirecionamento), TrocarSenha
├── urls.py              # entrar (Entrar), sair, senha
├── migrations/0005_trocar_senha.py, 0006_solicitante.py
└── templates/contas/    # trocar_senha.html, bloqueado.html

pedidos/
├── models.py            # Pedido.conta
├── migrations/0006_conta.py
├── protecao.py          # Envio.conta no token
├── regras.py            # nome_da_conta
├── servicos.py          # registrar_pedido(conta=)
├── minhas.py            # apresentação de "Meus pedidos" (dicionário fechado)
├── views/publico.py     # formulário com conta, sessão terminada, consulta sem pedidos com conta
├── views/solicitante.py # meus_pedidos, meu_pedido
├── urls.py              # meus-pedidos/
├── templates/pedidos/   # _formulario.html, _sucesso.html, meus_pedidos.html, meu_pedido.html
└── static/pedidos/js/pedidos.js  # sem localStorage no formulário com conta

interface/templates/interface/
├── base_publico.html    # Entrar / Meus pedidos / Sair
└── acesso_negado.html   # variante no layout público para o solicitante

config/settings.py       # axes, AUTHENTICATION_BACKENDS, middlewares, LOGIN_TENTATIVAS
.env.example             # LOGIN_TENTATIVAS, LOGIN_BLOQUEIO_MINUTOS
pyproject.toml, uv.lock  # django-axes

tests/
├── solicitantes.py                     # criar_solicitante, abrir_formulario_com_conta
├── test_solicitante_acesso.py          # tabela, categorias, redirecionamentos, recusa
├── test_solicitante_formulario.py      # nome, destino, token, sessão terminada, reenvio
├── test_solicitante_meus_pedidos.py    # lista, detalhe, FR-020, 404, cache
├── test_solicitante_consulta.py        # consulta pública sem pedidos com conta
├── test_solicitante_senha_admin.py     # troca obrigatória, admin
└── test_solicitante_bloqueio.py        # axes nas duas portas
```

**Structure Decision**: tudo dentro dos apps que já existem. A conta e o login ficam em `contas` (onde
estão o login e a tabela de rotas); o pedido com conta e "Meus pedidos" ficam em `pedidos`, porque
leem `Pedido` e reusam a situação e o texto da consulta pública. Nenhum app novo.

## Ordem de implementação (para o `/speckit-tasks`)

1. Fundação: dependência e configuração do axes, `Usuario.trocar_senha`, grupo `Solicitante`,
   `Pedido.conta`, `eh_solicitante`, as categorias novas na tabela de rotas e as duas rotas de "Meus
   pedidos" em versão mínima, para o login e a troca de senha da US5 já as resolverem (com o teste da
   012 continuando verde).
2. US5 (P1): admin, troca obrigatória, redirecionamento depois de entrar.
3. US3 (P2, mas pré-requisito de US1 e US2): formulário com conta, nome, destino, token, reenvio, tela
   de sucesso, `pedidos.js`.
4. US1 e US2 (P1): "Meus pedidos", detalhe sem dados da equipe, 404, consulta pública.
5. US4 (P2): sessão que termina no meio.
6. US6 (P2): bloqueio nas duas portas, página de bloqueio, desbloqueio.
7. Fechamento: `base_publico.html`, `CLAUDE.md`, `.env.example`, `check --deploy`, quickstart.

## Riscos

- **Origem igual para todos no Docker Desktop (F8)**: sem efeito no código; o bloqueio vira por
  matrícula. Conferir no servidor antes do deploy e anotar no PR.
- **Axes nos testes**: o `Client.login` deixa de funcionar com o backend do axes; só um teste o usa.
  Um teste novo que chame `client.login` falha com erro claro (`AxesBackendRequestParameterRequired`).
- **CSRF depois de entrar de novo**: coberto pelo R3a; um teste com `enforce_csrf_checks=True`
  reproduz a troca do segredo e o reenvio.
- **Página aberta durante o deploy**: o token antigo, sem `conta`, é aceito como anônimo, e quem não
  tinha conta não percebe nada.

## Decisões além do texto da spec (revisão do plano, 2026-11-09)

- **US4, entrar de novo**: o login troca o segredo do CSRF, e a aba antiga daria 403 ao reenviar
  (conferido com um teste). O "Entrar" da recusa abre em outra aba e o `pedidos.js` usa o CSRF do
  cookie no envio do formulário com conta (research R3a). A mensagem da US4 ganhou "abre em outra
  aba", e o cenário 1a foi acrescentado à spec.
- **Axes sem registro de acessos**: `AXES_DISABLE_ACCESS_LOG = True`, para não guardar para sempre a
  matrícula, o endereço e o navegador de todo login (research R6).
- **Admin**: além dos papéis da equipe (FR-002), o solicitante também não pode ter `is_staff` nem
  `is_superuser`, e precisa de nome completo (vai nos pedidos).

## Análise de consistência (`/speckit-analyze`, 2026-11-09)

Corrigido nos documentos antes da implementação: um só formulário de Sair por página (o do layout
público); rotas de "Meus pedidos" na fundação; cobertura do FR-017 (isca, tempo mínimo, limites com
o nome da conta), do FR-019 (destino, observação e ocorrência) e do FR-023 (detalhe sem cache); a
conferência do JavaScript na T053 (o projeto não tem teste de JS); a conferência do `REMOTE_ADDR`
antes do deploy, igual na spec e no plano; o FR-011 por matrícula e origem; o `ponto_de_partida` com
o solicitante no contrato; caminhos e método exatos nas tarefas T025 e T050.

## Complexity Tracking

Sem violações da constituição.
