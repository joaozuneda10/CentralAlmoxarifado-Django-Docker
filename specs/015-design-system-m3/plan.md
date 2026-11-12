# Implementation Plan: Troca do design system (Clean → linguagem visual do Material 3)

**Branch**: `claude/gifted-pascal-gsjrf3` | **Date**: 2026-11-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/015-design-system-m3/spec.md`

## Summary

A troca é uma **reestilização no lugar**: o CSS do projeto continua escrito à mão, os nomes de
classe e de token continuam os mesmos sempre que o componente existe, e os valores e as regras de
cada componente passam para a linguagem do M3 (superfícies tonais, contêineres, raios maiores,
elevação, pílulas, chips). Nenhuma dependência entra.

Como os componentes comuns ficam todos em `componentes.css` e os templates já usam quase só tokens
(cerca de 600 `var(--…)`, poucas cores fixas), a entrega 1 muda o visual do sistema inteiro **sem
tocar nos templates**. As entregas 2 a 4 mudam a composição das telas:

- o menu estreito e o painel novo, com os quatro comportamentos da decisão Q1;
- os formulários públicos, com o rótulo flutuante da decisão Q2;
- as demais telas internas.

Os comportamentos novos do painel só leem números que o sistema já calcula. Ficam em funções puras
(`regras`) e em consultas novas (`consultas`), com testes contra o banco. Os menus (⋮ e chips com
lista) são `<details>` nativos, que funcionam sem JavaScript; um script pequeno só fecha com Esc e
com clique fora.

## Technical Context

**Language/Version**: Python 3.13, Django 6.x. CSS e JavaScript escritos à mão, sem build.

**Primary Dependencies**: as de hoje (Django, HTMX 4.0.0 vendorizado, fontes `.woff2` locais, ícones
Lucide inline). **Nenhuma nova.**

**Storage**: MariaDB 11.4 / MySQL 8. **Sem migration**: nenhum modelo muda.

**Testing**: pytest contra MariaDB (`config.settings_test`), sem navegador. As capturas de tela para a
revisão visual saem de um script à parte (`scripts/capturar_telas.py`), fora da suíte; a constituição
(Princípio V) proíbe teste com navegador.

**Target Platform**: Chrome e Edge atuais no Windows do almoxarifado; Chrome no Android e Safari no
iPhone dos funcionários. O `:has()` é usado só onde há reserva: sem ele, o rótulo fica sempre na borda
(research R4).

**Project Type**: aplicação web Django, monólito com apps.

**Performance Goals**: o painel responde como hoje. Os contadores do menu custam no máximo duas
contagens por página inteira renderizada, uma vez por requisição (R7), e nenhuma nos trechos do HTMX.
O CSS total não cresce mais que 30% (hoje são cerca de 860 linhas comuns mais o CSS das apps).

**Constraints**: nenhuma mudança de comportamento além de FR-018 e FR-020; vocabulário de classes
preservado (FR-007); impressão do recibo idêntica; contraste AA calculado sobre os tokens; páginas
sem rolagem lateral entre 320 e 1440px.

**Scale/Scope**: 73 templates em 6 apps; 3 CSS comuns e 3 de apps; 6 scripts comuns e 2 de
`pedidos`; 52 arquivos de teste citam classes. São 4 entregas (PRs) e 29 requisitos.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Situação | Como |
|-----------|----------|------|
| I. Regras puras | ✅ | O texto "enviado hoje / ontem / há N dias" é `regras.texto_envio_mais_antigo(data, hoje)`, pura. As condições do menu ⋮ reusam `regras.edicao_permitida` (pura). As consultas novas ficam em `pedidos/consultas.py` |
| II. Uma porta de gravação | ✅ não tocado | Nada novo grava. O ⋮ só leva às telas de sempre. "Imprimir recibo" abre o detalhe, e a marcação de impresso segue o caminho de hoje (`servicos.marcar_recibos_impressos`, com a confirmação) |
| III. Nunca lançar duas vezes | ✅ não tocado | O cartão do robô mantém o botão, o formulário e o bloqueio do `LANCAMENTO_REAL` de hoje; nada no robô muda |
| IV. Importados não se perdem | ✅ não tocado | Sem importação |
| V. Testes no banco real, sem navegador | ✅ | Testes novos dos contadores, do "mais antigo", das autorizações, das condições do ⋮, do `?imprimir=1`, do markup do rótulo flutuante e do contraste dos tokens (lido do CSS). Capturas só pelo script manual, fora da suíte |
| VI. pt-BR, acessível, sem dependências externas | ✅ com **emenda** | Textos em português; selo com palavra e ícone; códigos em mono; nenhuma dependência. A frase "segue o design system Clean" muda para "segue o design system do projeto (`docs/DESIGN.md`)": emenda MINOR (2.2.0) no PR da entrega 1, com os documentos afetados (governança) |
| Restrições | ✅ | Sem variável nova no `.env`; `check --deploy` intocado; sem migration |
| Fluxo | ✅ | Spec e plano antes do código; uma branch `claude/*` por entrega, a partir de `develop`; o `CLAUDE.md` muda no mesmo PR que muda o que ele descreve (entregas 1 e 2) |

A emenda do Princípio VI não é exceção a justificar: é a emenda pelo rito da governança (PR que
altera a constituição, explica o motivo e ajusta os documentos no mesmo PR).

**Re-check depois do desenho (Phase 1)**: sem mudança. Os contratos não criam gravação nem
dependência. O `?imprimir=1` do detalhe é só leitura e só aciona o botão que já existe.

## Project Structure

### Documentation (this feature)

```text
specs/015-design-system-m3/
├── spec.md
├── plan.md                        # este arquivo
├── research.md                    # decisões técnicas (R1–R16)
├── data-model.md                  # sem banco: os dados de apresentação e de onde vêm
├── quickstart.md                  # como validar cada entrega
├── contracts/
│   ├── tokens.md                  # os tokens, valores, uso e contraste
│   ├── componentes.md             # vocabulário: o que fica, o que muda, o que entra
│   ├── painel.md                  # contexto da view, cartões, chips, ⋮ e ?imprimir=1
│   └── campos-publicos.md         # rótulo flutuante, texto de apoio e erro
├── prototipos/                    # referência visual (spec, FR-028)
├── checklists/requirements.md
└── tasks.md                       # /speckit-tasks
```

### Source Code (repository root)

```text
interface/
├── static/interface/css/
│   ├── fundacao.css               # antes clean.css: tokens, fontes, tipografia, ritmos (entrega 1)
│   ├── componentes.css            # componentes reestilizados + indicador, chip, menu-acoes, fab (1 e 2)
│   └── layouts.css                # casca: menu estreito (app-lateral) e público (2 e 3)
├── static/interface/js/
│   └── menus.js                   # novo: Esc e clique fora para details[data-menu] (2)
├── templates/interface/
│   ├── base.html                  # carrega fundacao.css e menus.js (1 e 2)
│   ├── base_almoxarifado.html     # casca com o menu estreito (2)
│   ├── _menu.html                 # ícone + rótulo + contador; conta no pé (2)
│   └── _icone.html                # ícones novos: kebab, metade, proibido, calendario, documento (1 e 2)
├── navegacao.py                   # contadores do menu, preguiçosos (2)
└── templatetags/                  # (sem mudança)

pedidos/
├── regras.py                      # texto_envio_mais_antigo (pura) (2)
├── consultas.py                   # envio_mais_antigo_aguardando, contar_aguardando_autorizacao,
│                                  # contadores_do_menu (memo por requisição) (2)
├── views/almoxarifado.py          # painel: novos números e permissões do ⋮; detalhe: ?imprimir=1 (2)
├── templatetags/pedidos_extras.py # icone_situacao / icone_scpi ao lado dos badge_* (1)
├── templates/pedidos/
│   ├── painel.html                # indicadores, chips, fab (2)
│   ├── _painel_lista.html         # colunas Situação e SCPI, recibo pendente, ⋮ (2)
│   ├── _formulario.html, _materiais.html, _resultados.html, _carrinho.html,
│   │   _resumo_pedido.html, _sucesso.html, inicio.html, consulta.html,
│   │   _folha.html                # formulários públicos (3)
│   └── detalhe.html, avulsa.html, … # demais telas (4)
├── static/pedidos/css/pedidos.css # (1 a 4)
└── static/pedidos/js/pedidos.js   # ?imprimir=1 aciona o [data-imprimir] e limpa a URL (2)

catalogo/, automacoes/, conciliacao/, contas/   # templates e CSS das telas (3: login de solicitante
                                                # e Meus pedidos; 4: as demais)

scripts/capturar_telas.py          # novo, fora da suíte: capturas a 320/375/768/1280/1440 (1)

tests/
├── test_fundacao.py               # antes test_clean.py, com os tokens novos (1)
├── test_contraste_tokens.py       # novo: pares de token ≥ AA, lidos do CSS (1)
├── test_painel_indicadores.py     # novo: mais antigo, autorizações, travadas, contadores (2)
├── test_painel_menu_acoes.py      # novo: condições do ⋮ e permissões (2)
├── test_imprimir_pela_lista.py    # novo: ?imprimir=1 no detalhe (2)
└── test_campos_flutuantes.py      # novo: markup do rótulo flutuante e do texto de apoio (3)

docs/DESIGN.md                     # reescrito (1)
.claude/skills/design-tonal/       # nova skill de estilo; sai a .claude/skills/clean-design/ (1)
.specify/memory/constitution.md    # Princípio VI, versão 2.2.0 (1)
CLAUDE.md                          # interface, convenções e skills (1 e 2)
```

**Structure Decision**: nenhuma app nova e nenhum diretório novo além de `scripts/`, para a
ferramenta de capturas. A troca mora em `interface` (fundação e casca), nos templates e no CSS de
cada app, e numa fatia pequena de `pedidos` para os quatro comportamentos do painel.

## Entregas

Cada entrega é um PR para `develop`, com deploy separado e revisão visual do chefe antes (SC-008).

| # | Entrega | Escopo | Muda templates? |
|---|---------|--------|-----------------|
| 1 | Fundação | Tokens (`fundacao.css`), componentes comuns, ícones e selos com ícone; constituição 2.2.0, `DESIGN.md`, skill `design-tonal` e `CLAUDE.md`; teste de contraste; script de capturas | Só `base.html`, `_icone.html` e os selos |
| 2 | Casca e painel | Menu estreito com contadores, painel (indicadores, chips, tabela, ⋮, fab), `?imprimir=1` no detalhe, `menus.js` | Casca e painel |
| 3 | Formulários públicos | Início, formulário (campos flutuantes, passos, busca, quantidade, Seu pedido, gaveta), sucesso, consulta, login de solicitante, Meus pedidos, folha | Telas públicas |
| 4 | Demais telas internas | Detalhe, atendimento, edição, saída avulsa, Automações, Curva ABC, Formulários, Autorizações, login, acesso negado; telas da spec 014 já integradas | Telas internas |

**Coordenação com a spec 014**: tela da 014 integrada antes da entrega 4 é convertida nela; tela que
vier depois da entrega 1 já nasce com os componentes novos. As entregas 1 e 2 tocam pouco nos templates
internos e devem ser feitas cedo, para encurtar a janela de conflito.

## Complexity Tracking

Sem violação a justificar. A única emenda (Princípio VI) segue o rito da governança.
