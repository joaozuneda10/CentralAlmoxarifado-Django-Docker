# Contrato: rotas e acesso (spec 013)

Acréscimos à tabela de rotas da spec 012 (`contas.acesso.REGRAS_POR_ROTA`).

## Rotas novas

| Rota nomeada | Caminho | Métodos | Categoria |
|--------------|---------|---------|-----------|
| `pedidos:meus_pedidos` | `/meus-pedidos/` | GET | `SOLICITANTE` |
| `pedidos:meu_pedido` | `/meus-pedidos/<numero>/` | GET | `SOLICITANTE` |
| `trocar_senha` | `/painel/senha/` | GET, POST | `LOGADO` |

`trocar_senha` também entra em `ROTAS_SEGURANCA_TRABALHO`.

## Quem é solicitante

`eh_solicitante(usuario)` é verdadeiro só com tudo isto: autenticado, ativo, do grupo `Solicitante`,
sem `is_staff`, sem `is_superuser`, sem nenhuma das permissões de `PERMISSOES_INTERNAS` e fora da
Segurança do Trabalho. Guardado no objeto do usuário durante a requisição.

## Decisão do `ExigirPermissao` por categoria

| Categoria | Anônimo | Solicitante | Equipe (demais logados) |
|-----------|---------|-------------|--------------------------|
| `SOLICITANTE` | login, com `next` | passa | redireciona ao `ponto_de_partida` |
| `LOGADO` | login, com `next` | passa | passa |
| `Regra` (spec 012) | login, com `next` | 403 no layout público, link "Meus pedidos", linha no log | como na 012 |
| `PUBLICA`, `ADMIN`, `SEGURANCA` | como na 012 | como na 012 | como na 012 |

- `ponto_de_partida(usuario)` (nome da rota): `pedidos:autorizacoes` para a Segurança do Trabalho,
  `pedidos:meus_pedidos` para o solicitante e `pedidos:painel` para os demais. As duas rotas de "Meus
  pedidos" existem desde a fundação (tasks T006), para o login e a troca de senha já as resolverem.
- A recusa do solicitante é registrada como as outras (`registrar_recusa`, `falta=` a permissão da
  regra).
- `sem_papel` passa a ser falso para o solicitante (ele tem papel; só não é interno).

## Troca obrigatória (`ExigirTrocaDeSenha`, depois do `ExigirPermissao`)

Com `eh_solicitante` e `trocar_senha` ligados, qualquer rota fora de `trocar_senha` e `logout`:
GET redireciona a `trocar_senha`; os demais métodos recebem 403. Como o `ExigirPermissao`, age em
`process_view`, só sobre rotas nomeadas: os estáticos não são afetados.

## Depois de entrar

`contas.views.Entrar.get_default_redirect_url`: solicitante → `pedidos:meus_pedidos`; demais →
`LOGIN_REDIRECT_URL`. `next` seguro (mesmo host) continua tendo precedência, salvo para o solicitante
com troca pendente, que o middleware leva à troca.

## Layout público

`base_publico.html` mostra, no topo: "Entrar" (link para o login com `next` da página atual) a quem
não está logado; "Meus pedidos" e "Sair" (o único formulário de logout da página, POST com CSRF) ao
solicitante; nada novo para a equipe.

## Garantias testadas

1. Todas as rotas nomeadas continuam na tabela (teste da 012).
2. Solicitante recebe 403 em toda rota `Regra`, por GET e POST, e nenhuma execução é criada.
3. Equipe abrindo `meus_pedidos` é redirecionada ao seu ponto de partida; a Segurança do Trabalho
   vai à fila.
4. Anônimo em `meus_pedidos` vai ao login e volta à lista depois de entrar.
5. Superusuário e staff no grupo Solicitante não são solicitantes.
