# Feature Specification: Entrada de materiais por pedido de compra

**Feature Branch**: `claude/entrada-por-pedido` (a partir de `develop`)

**Created**: 2026-11-10

**Status**: Draft

**Input**: User description: entrada de materiais por pedido de compra. O almoxarifado registra no
Central o recebimento de uma nota fiscal de um pedido, total ou parcial, e o robô lança a Requisição de
Entrada por pedido no SCPI, com os cuidados da conciliação de saídas.

Decisões do usuário em 2026-11-10, numa conversa de design antes desta especificação (registro completo
em `docs/superpowers/specs/2026-11-10-entrada-por-pedido-brainstorming.md`):
- **o robô do Central lança a entrada desde o início** (D1);
- **só a entrada para o estoque**: a saída por pedido fica para outra spec (D2);
- **uma NF nunca traz itens de mais de um pedido** (D3);
- **entrada por pedido feita direto no SCPI vira exceção**: o que o Central não explica trava o pedido (D4);
- **nota e material divergentes: nada entra até resolver** (D5);
- **a data da entrada é a do recebimento** (D6);
- **o empenho não é escolhido nem conferido**: é assunto das finanças (D7);
- **os papéis Atendimento e Gestão preparam o recebimento; o lançamento pelo robô fica com a Gestão**
  (D8, ampliada pelo usuário em 2026-11-10).

O usuário também aprovou as propostas P1 a P13 do mesmo registro. "Total" é o saldo livre, a
conferência é feita antes do Salvar, a conciliação usa três vínculos, a fonte dos pedidos é o relatório
07.13 e o Central só recebe itens controlados por quantidade, entre outras.

## Contexto

Fatos observados em 10/11/2026: nos CSVs do SCPI extraídos pelo usuário, que ficam fora do repositório
porque têm nomes de pessoas, nas telas do SCPI (só consultas e inserções canceladas) e no código.

| # | Fato | Fonte |
|---|------|-------|
| F1 | A tela de entrada por pedido segue Inserir › "por pedido" › pedido (número + ano) › "Escolha os Itens" › janela de empenhos › grade. "Escolha os Itens" mostra só os itens com saldo, todos marcados e com o número do item no pedido. Na grade, a quantidade vem preenchida com o saldo e os itens são renumerados de 1 a n. | tela (`00388/26`, `00514/26`) |
| F2 | O SCPI recusa quantidade acima do saldo do item ("Quantidade de entrada é maior que quantidade do pedido!"): 2 com saldo 1 no `00514/26`, mesmo cabendo no pedido de 3. Quantidade a mais só num registro novo. | tela |
| F3 | Um parcial repetido que caiba no saldo passa no SCPI. Ele só barra a duplicação quando o saldo acaba. | F2, exemplo 100 → 30 → 20 |
| F4 | O "Já Entrou" de cada item (`QTDENT`) é igual à soma das entradas do relatório em 2.186 de 2.186 itens de pedidos de 2026. | CSVs |
| F5 | O relatório de entradas (07.04.01) filtra o período pela **data da entrada**. Na entrada por pedido, a "Data Requisição" (`DTLAN`) é a data do pedido. | CSV, tela, usuário |
| F6 | A numeração das requisições é **a mesma das saídas**. Uma requisição excluída simplesmente some, e uma com a data digitada errada (`003553/26`, 10/12/2006) fica fora de qualquer período. As duas parecem iguais no relatório. | CSVs, telas |
| F7 | Em 1.752 NFs (fornecedor + número) de 2026, nenhuma aparece em duas requisições nem em dois pedidos. A série e a chave existem na tela, mas não saem no relatório. | CSVs, tela |
| F8 | O campo Observações existe, sai no relatório e está vazio em 196 de 197 entradas por pedido de 2026. | CSV |
| F9 | O 07.13 "Relação de Pedidos (Condição da Entrega)", com "Apenas com saldo a entregar", tem uma linha por item com saldo: quantidade, anulado, já entrou, saldo, subpedido e o tipo de controle do saldo. Sai em cerca de 20 segundos, com os mesmos 2.878 itens da listagem de pedidos, e **não grava nada no pedido** (conferido pelo Log). | CSV, Log |
| F10 | O 01.08.03 Imprimir Pedidos **grava no pedido**: a Data Emissão e um contador, conforme o Log de 10/11/2026. | Log |
| F11 | Inserir uma entrada por pedido e cancelar não grava nada no pedido. | Log |
| F12 | 102 itens com saldo têm o saldo controlado por valor (`T`), e não por quantidade. Há também itens de serviço entre os itens com saldo. | CSV |
| F13 | Os pedidos do exercício anterior são recriados no novo exercício com o mesmo número, outro identificador interno e "Já Entrou" só do novo exercício (em 2026, em 10/03). | CSVs |
| F14 | Depois do Salvar, o número aparece no mesmo campo da saída. O aviso de data em outro mês aparece também na entrada. | usuário, `scpi/lancador.py` |
| F15 | A conciliação de saídas (spec 010) já tem estados, foto da tentativa, extração de antes e de depois, intervalo e candidatas, vereditos, correção de vínculo e retenção. As entradas reaproveitam essas garantias, com três diferenças: o terceiro vínculo (NF), a data pela data da entrada e a conferência antes do Salvar. | `conciliacao/`, `scpi/lancamento.py` |

## Dependências

- **Spec 010 (conciliação com o SCPI)**: o mesmo desenho de extração, tentativas, vereditos e liberação.
- **Spec 012 (papéis de acesso)**: a permissão nova entra na tabela de rotas e nos papéis Atendimento e
  Gestão.
- **Cadastro de materiais** (importador do cadastro): ele decide quais itens de pedido o Central recebe.
- **Constituição**: os Princípios II e III falam só do domínio de pedidos e saídas. Uma emenda MINOR, no
  mesmo pull request, os estende às entradas.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Preparar o recebimento de uma nota fiscal (Priority: P1)

Chega o material de um pedido de compra com a nota fiscal. Quem é do Atendimento ou da Gestão confere o material,
abre o pedido no Central, escolhe "total" ou "parcial", informa o número da NF e a data do recebimento
e grava. O Central reserva as quantidades, e a entrada vai para a fila do robô.

**Why this priority**: é o trabalho que hoje é digitado à mão no SCPI. Sem ele, nada mais existe.

**Independent Test**: com um pedido importado de dois itens, preparar um recebimento parcial de um item,
outro "total" com outra NF, e conferir as quantidades sugeridas, o saldo livre e as recusas.

**Acceptance Scenarios**:

1. **Given** um item de 100 unidades, com 30 já entradas no SCPI e 20 reservadas num recebimento
   preparado, **When** alguém escolhe "total" com outra NF, **Then** a quantidade sugerida é 50.
2. **Given** saldo livre de 50, **When** alguém informa 51, **Then** o recebimento é recusado com o saldo
   livre na mensagem, e nada é gravado.
3. **Given** um recebimento "parcial", **When** a pessoa marca só alguns itens e baixa as quantidades,
   **Then** só esses itens são reservados, cada um com a quantidade informada.
4. **Given** uma NF de um fornecedor já usada num recebimento que teve uma tentativa de lançamento,
   **When** alguém informa a mesma NF desse fornecedor, com ou sem os zeros à esquerda, **Then** é
   recusada, mesmo que o primeiro recebimento esteja cancelado.
5. **Given** uma data de recebimento futura ou anterior à data do pedido, **When** se grava, **Then** é
   recusada.
6. **Given** uma quantidade com 4 casas decimais ou escrita "1.5", **When** se grava, **Then** é
   recusada; "1,5" e até 3 casas são aceitos em qualquer unidade.
7. **Given** duas pessoas preparando "total" do mesmo item ao mesmo tempo, **When** as duas gravam,
   **Then** uma grava e a outra é recusada com o saldo livre atualizado, e a soma reservada nunca passa
   do saldo.
8. **Given** um recebimento preparado que nunca teve tentativa, **When** ele é editado ou cancelado,
   **Then** o saldo livre se ajusta. No cancelamento, a NF volta a ficar livre.

---

### User Story 2 - Lançar no SCPI sem nunca duplicar (Priority: P1)

Na aba de Automações, a Gestão escolhe os recebimentos da fila e manda simular ou lançar. O robô abre a
entrada por pedido e marca só os itens do recebimento. Antes de salvar, confere na tela que o SCPI
ainda tem o saldo que o Central espera. Depois preenche quantidades, data, NF e a marca do Central nas
Observações, e salva. Qualquer dúvida depois do clique trava o recebimento em verificação.

**Why this priority**: lançar duas vezes é um erro contábil que o sistema não desfaz (Princípio III).

**Independent Test**: com o SCPI simulado, lançar recebimentos e provocar cada falha: antes do Salvar,
depois do clique, resposta perdida e saldo mudado na tela. Conferir os estados e que nada é relançado.

**Acceptance Scenarios**:

1. **Given** um recebimento na fila, **When** o lançamento real termina bem, **Then** ele fica lançado
   com o número da requisição, e o SCPI tem a marca do recebimento nas Observações.
2. **Given** um recebimento em lançamento, **When** a falha acontece depois do clique em Salvar, **Then**
   ele fica em verificação, continua reservando o saldo e não volta à fila.
3. **Given** um recebimento na fila, **When** a tela do SCPI mostra para algum item um "Já Entrou" maior
   ou um saldo menor que o esperado, **Then** o robô não salva, o recebimento fica com erro ("o SCPI
   mudou") e o pedido fica travado para novos lançamentos.
4. **Given** um recebimento com data num mês anterior, **When** o SCPI avisa que a data é de outro mês,
   **Then** o robô confirma o aviso uma vez; qualquer outra mensagem no Salvar é resultado incerto.
5. **Given** o lançamento real bloqueado no ambiente, **When** se pede o lançamento real, **Then** ele é
   recusado, e só a simulação roda.
6. **Given** uma simulação, **When** ela termina, **Then** o SCPI não tem nenhuma requisição nova, o
   pedido não mudou e nenhum recebimento mudou de estado.
7. **Given** o robô de saídas em execução, **When** se pede o lançamento de entradas, **Then** ele é
   recusado até a outra execução terminar: um robô de lançamento por vez.

---

### User Story 3 - Resolver um recebimento em verificação (Priority: P1)

O SCPI pode ter salvo e perdido a resposta. O almoxarifado vê o recebimento em verificação com as
requisições candidatas e liga a certa ("É esta"). Também pode liberá-lo para relançar, mas só quando a
ausência estiver provada.

**Why this priority**: sem isso, o primeiro erro de rede trava o pedido para sempre ou leva a relançar
no escuro.

**Independent Test**: com o SCPI simulado que salva e perde a resposta, conferir que a liberação é
recusada; com o que falha sem salvar, conferir que ela é permitida depois de uma extração posterior.

**Acceptance Scenarios**:

1. **Given** um recebimento em verificação, **When** uma extração começada depois da tentativa traz uma
   requisição com a marca dele ou com a NF e o fornecedor dele, **Then** ela aparece como "é esta", e a
   escolha liga o recebimento a ela como lançado.
2. **Given** um recebimento em verificação, **When** a extração posterior não tem candidata no intervalo
   da tentativa e o "Já Entrou" de cada item é o esperado, **Then** a liberação para relançar é
   permitida, e é o **mesmo** recebimento que volta à fila.
3. **Given** um recebimento em verificação sem extração posterior à tentativa, **When** alguém pede a
   liberação, **Then** ela é recusada.
4. **Given** uma candidata que apareceu numa extração e sumiu na seguinte, **When** alguém pede a
   liberação, **Then** ela continua recusada.
5. **Given** um número faltando na sequência do relatório, **When** a conciliação avalia a liberação,
   **Then** a lacuna conta como falta de evidência, nunca como prova de que o SCPI não salvou.

---

### User Story 4 - Conferir cada lançamento com o registro oficial (Priority: P2)

Depois de cada execução e todo dia, o Central lê o relatório de entradas. Para cada recebimento lançado,
diz se a requisição oficial confere: Comprovado, Divergente (com a diferença), Aguardando, Não
encontrado, Conflito ou Duplicado.

**Why this priority**: é a prova independente de que o que foi lançado é o que foi recebido; sem ela, um
erro do SCPI ou uma correção à mão passa despercebido.

**Independent Test**: com relatórios sintéticos no formato real, conferir cada veredito, inclusive uma
requisição editada no SCPI depois do lançamento e uma excluída.

**Acceptance Scenarios**:

1. **Given** um recebimento lançado, **When** a requisição oficial tem o número, a marca e a NF com o
   fornecedor apontando para ela, e o mesmo pedido, data da entrada, códigos e quantidades, **Then** o
   veredito é Comprovado.
2. **Given** a mesma situação com uma quantidade diferente, **When** a conciliação roda, **Then** o
   veredito é Divergente e mostra só o que difere.
3. **Given** os três vínculos apontando para requisições diferentes, **When** a conciliação roda,
   **Then** o veredito é Conflito.
4. **Given** duas requisições oficiais com a mesma NF do mesmo fornecedor, **When** a conciliação roda,
   **Then** o veredito é Duplicado, mesmo sem a marca do Central.
5. **Given** um recebimento lançado cuja requisição não aparece, **When** o relatório ainda não tem
   número maior, **Then** o veredito é Aguardando; quando já tem, é Não encontrado.
6. **Given** uma correção feita à mão no SCPI depois do lançamento, **When** a conciliação roda de novo,
   **Then** o veredito mostra a alteração, e o Central não muda o recebimento.

---

### User Story 5 - Pedidos e saldos atualizados, e o que entrou fora do Central (Priority: P2)

O Central carrega os pedidos com saldo uma vez e os atualiza todo dia, sem nunca usar uma operação do
SCPI que grave nos pedidos. Quando aparece no SCPI uma entrada por pedido que o Central não fez, ela vira
um aviso e trava o pedido até alguém conferir.

**Why this priority**: o saldo livre só é confiável se o Central souber tudo o que entrou; sem isso, o
"total" sugere mais do que existe.

**Independent Test**: importar um relatório de pedidos sintético, depois um de entradas com uma
requisição sem marca, e conferir o saldo livre, o aviso e a trava.

**Acceptance Scenarios**:

1. **Given** a carga inicial, **When** ela termina, **Then** o Central tem todos os itens com saldo dos
   pedidos do exercício atual que são controlados por quantidade e cujo material está no cadastro.
2. **Given** um item controlado por valor, de serviço ou de combustível, **When** a carga roda, **Then**
   ele não fica disponível para recebimento.
3. **Given** uma requisição oficial de um pedido conhecido, sem a marca e com a NF de um recebimento
   aberto, **When** a conciliação roda, **Then** o recebimento é ligado a ela como lançado à mão e sai
   da fila; o robô nunca o lança.
4. **Given** uma requisição oficial sem a marca e com uma NF desconhecida, **When** a conciliação roda,
   **Then** ela aparece como "Lançada fora do Central", o saldo livre cai e o pedido fica travado.
5. **Given** uma importação em que o "Já Entrou" de um item é maior que a soma das entradas conhecidas,
   **When** ela termina, **Then** há aviso de saúde e o pedido fica travado.
6. **Given** um pedido travado e uma atualização posterior à trava, **When** quem opera automações
   confere e destrava informando o motivo, **Then** o pedido volta a aceitar recebimento com o saldo
   recalculado. Sem atualização posterior, o destravamento é recusado.

---

### Edge Cases

- **Pedido anulado em parte depois de um recebimento preparado:** o saldo livre fica menor que o
  reservado. O recebimento não é lançado (a conferência antes do Salvar o recusa), e o pedido aparece
  como precisando de conferência.
- **Mesmo código em dois itens do pedido** (por exemplo, cotas de 1.125 e 375): o recebimento escolhe o
  item, e não só o código. A conciliação compara a soma por código, porque o relatório não traz o item.
- **Pedido que some do relatório** (excluído, entregue ou anulado): os recebimentos já lançados ficam
  como estão. Um recebimento preparado e não lançado fica bloqueado até alguém conferir.
- **Virada do exercício:** só se prepara recebimento de pedido que existe no exercício atual. O
  recebimento preparado e não lançado na virada fica bloqueado até a nova carga.
- **Recebimento lançado à mão no SCPI com a mesma NF de um recebimento preparado:** a conciliação o liga
  ("É esta"), e o robô nunca o lança.
- **Entrada à mão com data errada:** fica fora do período do relatório, mas muda o "Já Entrou". A
  conferência antes do Salvar e a importação travam o pedido.
- **Requisição lançada pelo Central e depois excluída no SCPI:** o veredito vira Não encontrado quando o
  relatório tem número maior; o Central não relança sozinho.
- **Pedido com vários empenhos:** o robô aceita o que vem selecionado, e a conciliação não confere
  empenho.

## Requirements *(mandatory)*

### Functional Requirements

**Pedidos e saldo**

- **FR-001**: O sistema DEVE manter os itens com saldo dos pedidos de compra do SCPI, identificados pelo
  número do pedido com o ano de origem e pelo número do item, com material, unidade, quantidade, anulado,
  já entrou, já passado a subpedido, preço e fornecedor.
- **FR-002**: Os pedidos DEVEM vir de uma carga inicial completa e de uma atualização diária por um
  relatório do SCPI que não grava nada no pedido. O sistema NUNCA DEVE usar uma operação do SCPI que
  altere pedidos para ler pedidos.
- **FR-003**: Só DEVE ficar disponível para recebimento o item com saldo controlado por quantidade e cujo
  material esteja no cadastro de materiais do Central.
- **FR-004**: O saldo livre de cada item DEVE ser: quantidade − anulado − já entrou no SCPI − já passado a
  subpedido − o reservado pelo Central. Reservam os recebimentos preparados, em lançamento, em
  verificação, com erro e os lançados que o SCPI ainda não mostra como entrados.
- **FR-005**: A importação DEVE ser registrada como as outras do sistema e gravar tudo ou nada. Ela não
  DEVE apagar recebimentos nem pedidos com recebimento.

**Recebimento**

- **FR-006**: Quem tem a permissão de receber compras DEVE poder preparar um recebimento de um pedido com:
  - o número da NF;
  - a data do recebimento;
  - os itens e as quantidades;
  - uma observação opcional.

  O sistema guarda quem preparou e quando.
- **FR-007**: "Total" DEVE sugerir o saldo livre de cada item disponível; "parcial" DEVE permitir
  escolher itens e baixar quantidades. Nenhum item pode passar do saldo livre.
- **FR-008**: As quantidades DEVEM ser decimais pt-BR, maiores que 0, com até 3 casas, em qualquer
  unidade.
- **FR-009**: A data do recebimento NÃO DEVE ser futura nem anterior à data do pedido.
- **FR-010**: A mesma NF do mesmo fornecedor, comparada sem os zeros à esquerda, NÃO DEVE estar em dois
  recebimentos. O cancelamento só a libera se nenhuma tentativa do recebimento chegou ao Salvar.
- **FR-011**: Gravar, editar e cancelar um recebimento DEVEM serializar o acesso aos itens do pedido, de
  modo que duas pessoas nunca reservem o mesmo saldo; o reenvio igual NÃO DEVE criar outro recebimento.
- **FR-012**: Um recebimento DEVE poder ser editado ou cancelado até a primeira tentativa que chegar ao
  Salvar; depois dela, só pela resolução da conciliação.
- **FR-013**: Um pedido travado NÃO DEVE aceitar recebimento novo nem lançamento até ser destravado por
  quem opera automações, com o motivo registrado e depois de uma atualização posterior à trava.

**Lançamento no SCPI**

- **FR-014**: A fila de recebimentos DEVE ficar na aba de Automações, com escolha dos recebimentos,
  simulação e lançamento real, para quem opera automações.
- **FR-015**: O lançamento real só DEVE rodar com o lançamento real liberado no ambiente; a simulação
  preenche e cancela, sem gravar nada no SCPI e sem extrair.
- **FR-016**: Só DEVE rodar um robô de lançamento por vez, de entradas ou de saídas.
- **FR-017**: O robô DEVE marcar só os itens do recebimento e confirmar a janela de empenhos sem escolher.
  Depois DEVE preencher as quantidades, a data do recebimento, o número da NF e, nas Observações, a marca
  do Central ("Central Almoxarifado <recebimento>", com prefixo próprio) seguida da observação.
- **FR-018**: Antes do Salvar, o robô DEVE comparar, para cada item, o saldo e o "Já Entrou" da tela com o
  esperado. Se forem diferentes, não salva: o recebimento fica com erro e o pedido, travado.
- **FR-019**: O estado "em lançamento" e a foto do que será digitado DEVEM estar gravados antes do clique
  em Salvar. Qualquer falha depois do clique DEVE deixar o recebimento em verificação, e nunca de volta
  na fila. O número obtido DEVE ser registrado num diário fora do banco antes do banco.
- **FR-020**: O robô DEVE confirmar uma vez o aviso de data em outro mês; qualquer outra mensagem no
  Salvar é resultado incerto.

**Conciliação**

- **FR-021**: O sistema DEVE extrair o relatório de entradas antes de cada lançamento real (sem essa
  extração, nada é lançado), depois dele e todo dia. O período vai do dia anterior à data de recebimento
  mais antiga envolvida até o dia seguinte a hoje. Na extração diária, entram na conta os últimos 9 dias,
  os recebimentos em verificação e os lançados nos últimos 9 dias, pela data de recebimento de cada um.
- **FR-022**: Cada recebimento lançado DEVE ser ligado à requisição oficial por três vínculos (número,
  marca nas Observações e NF com fornecedor) que apontam para a mesma requisição.
- **FR-023**: A comparação DEVE cobrir fornecedor, NF, pedido, data da entrada, códigos e quantidades
  (soma por código). O empenho e a "Data Requisição" do SCPI NÃO DEVEM ser comparados.
- **FR-024**: Os vereditos DEVEM ser os da conciliação de saídas (Aguardando, Comprovado, Divergente, Não
  encontrado, Conflito, Duplicado), com a primeira conferência conclusiva e as revisões.
- **FR-025**: Um recebimento em verificação só DEVE ser liberado para relançar com três provas:
  - uma extração começada depois da tentativa;
  - nenhuma candidata no intervalo, nem agora nem antes;
  - o "Já Entrou" de cada item igual ao esperado.

  Uma lacuna na numeração NÃO DEVE contar como prova.
- **FR-026**: O sistema DEVE mostrar as candidatas de um recebimento em verificação e permitir ligá-lo a
  uma delas ("É esta").
- **FR-027**: O sistema NÃO DEVE alterar um recebimento lançado; a correção é à mão no SCPI e aparece na
  conciliação.

**Entrada fora do Central**

- **FR-028**: Uma requisição oficial de um pedido conhecido sem a marca do Central DEVE ser ligada ao
  recebimento aberto com a mesma NF e o mesmo fornecedor, se existir. Sem ele, DEVE aparecer como
  "Lançada fora do Central", reduzir o saldo livre e travar o pedido.
- **FR-029**: Uma importação ou extração que mostre um "Já Entrou" que o Central não explica DEVE gerar
  aviso de saúde e travar o pedido.

**Acesso e implantação**

- **FR-030**: Preparar, editar e cancelar recebimentos DEVEM exigir uma permissão nova, dada aos papéis
  Atendimento e Gestão. A fila e o lançamento continuam exigindo a permissão de operar automações
  (Gestão). As rotas novas DEVEM entrar na tabela de rotas da spec 012, e a Segurança do Trabalho
  continua sem acesso.
- **FR-031**: A implantação NÃO DEVE mudar nada nas saídas: formulários, atendimento, robô e conciliação
  de saídas seguem iguais. A única diferença é a recusa das ações das saídas enquanto o robô de entradas
  ou uma importação nova está rodando, pela regra de um robô de lançamento por vez (FR-016).

### Key Entities

- **Pedido de compra (importado):** número com o ano de origem, fornecedor, data, exercício e a situação
  no Central (disponível, travado e por quê).
- **Item do pedido:** número do item, material, unidade, tipo de controle do saldo, quantidade, anulado,
  já entrou, já passado a subpedido e preço.
- **Recebimento:**
  - uma NF de um pedido: número da NF, fornecedor, data do recebimento e observação;
  - quem preparou;
  - o estado: preparado, em lançamento, lançado, em verificação, com erro ou cancelado;
  - o número da requisição oficial, quando houver.
- **Item do recebimento:** o item do pedido e a quantidade.
- **Tentativa de lançamento:** cada vez que o robô tenta salvar um recebimento, com a ordem na execução e
  a foto do que foi digitado. Para a NF (FR-010) e para a edição (FR-012), só conta a tentativa que chegou
  ao Salvar, com o estado em lançamento gravado. A que parou antes, por erro ou porque o recebimento
  mudou, não salvou nada e não conta.
- **Extração de entradas:** cada leitura guardada do relatório de entradas, com o período e as
  requisições oficiais lidas.
- **Requisição de entrada oficial:** número, data da entrada, fornecedor, NF, pedido, observações e
  itens (código e quantidade).
- **Conferência:** o veredito de um recebimento numa extração, com as diferenças e as candidatas.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 0 requisição de entrada duplicada no SCPI por causa do Central. Isso vale em todos os
  cenários de falha exercitados: resposta perdida, falha antes e depois do Salvar, reenvio, duas pessoas
  ao mesmo tempo e entrada à mão com a mesma NF.
- **SC-002**: O almoxarifado prepara o recebimento total de uma NF de até 30 itens em menos de 2 minutos,
  sem digitar quantidade.
- **SC-003**: Em 100% dos itens disponíveis, o saldo livre mostrado é igual ao saldo do SCPI da última
  atualização menos o reservado pelo Central.
- **SC-004**: Todo recebimento lançado tem um veredito conclusivo na primeira extração que cobre a sua
  data, salvo quando o relatório ainda não mostra a requisição (Aguardando).
- **SC-005**: Toda entrada por pedido feita fora do Central num pedido com saldo é detectada até a
  próxima atualização diária, gera um aviso e trava o pedido até alguém destravar.
- **SC-006**: 0 recebimento em verificação liberado sem uma extração posterior à tentativa.
- **SC-007**: No dia da implantação, 0 mudança no comportamento das saídas, do atendimento e da
  conciliação de saídas.

## Assumptions

- O SCPI é o mesmo de hoje: a tela de entrada por pedido e o relatório de entradas seguem como foram
  observados em 10/11/2026.
- Se aparecer alguma janela depois do Salvar da entrada (impressão, etiquetas), ela é fechada como nas
  saídas; isso se confirma na primeira simulação real.
- Se o SCPI confere o saldo de novo no Salvar quando duas telas foram abertas antes é desconhecido. A
  spec não depende disso: o Central serializa, e o robô confere antes do Salvar.
- A latência entre o Salvar e o relatório é curta, como nas saídas, e não foi medida. Enquanto não
  aparece, o veredito é Aguardando.
- Pedido "não empenhado" não tem tratamento especial. Se o SCPI recusar a entrada, a falha acontece
  antes do Salvar e o recebimento fica com erro.
- Pedidos de outro exercício migram no SCPI de uma vez, como em 10/03/2026, e a carga seguinte os
  traz de volta.
- O almoxarifado confere nota e material antes de preparar o recebimento; divergências são resolvidas com
  o fornecedor fora do sistema.

## Fora do escopo

- Saída por pedido (entrada com saída direta para o centro de custo).
- Receber acima do pedido (o "registro novo" do SCPI).
- Registrar divergência entre nota e material, ou nota parada esperando correção.
- Série, chave e data de emissão da NF.
- Escolha e conferência do empenho.
- Itens de serviço, de combustível e com saldo controlado por valor.
- Editar no Central um recebimento já lançado, ou corrigir o SCPI pelo Central.
- Corrigir a Data Emissão gravada nos pedidos pelo 01.08.03 em 10/11/2026 (assunto do setor de Compras).
