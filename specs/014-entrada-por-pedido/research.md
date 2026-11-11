# Pesquisa: entrada de materiais por pedido de compra

Decisões técnicas do [plano](plan.md). As decisões de produto estão na [spec](spec.md) (D1 a D8) e no
registro do brainstorming (`docs/superpowers/specs/2026-11-10-entrada-por-pedido-brainstorming.md`,
regras R1 a R19 e fatos F1 a F25 de lá; aqui elas aparecem como "R1 do registro"). Este arquivo guarda
só as escolhas de como fazer. Cada item traz a decisão, o motivo e as alternativas descartadas.

As colunas citadas foram conferidas nos CSVs reais de 10/11/2026, que ficam fora do repositório:
- relatório de entradas: 65 colunas, entre elas `REQUI`, `ID_REQUI`, `CODIF`, `DTLAN`, `DATAE`,
  `ENTR`, `SAID`, `OBS_CABECALHO`, `CADPRO`, `UNID1`, `QUAN1`, `DOCUM`, `TPREQUI`, `NUMPED`,
  `NPEDFILHO` e `RESPONSA`;
- 07.13: 79 colunas, entre elas `NUMPED`, `DATPED`, `CODIF`, `NOME`, `ITEM`, `CADPRO`, `UNID1`,
  `TPCONTROLE_SALDO`, `QTD`, `PRCUNT`, `QTDANU`, `QTDENT`, `QTDFALTA` e `QTDPEDIDA`.

## R1. Onde ficam os modelos novos

**Decisão**: num app novo, `compras`. Ele guarda:
- os pedidos de compra importados e os itens deles;
- os recebimentos e as travas dos pedidos;
- o registro oficial das entradas;
- as tentativas do robô de entradas e as conferências.

O que já existe é reaproveitado **sem mudança**:
- de `conciliacao.regras`: `chave`, `maior_requisicao`, `periodo`, `intervalo` e `texto_igual`;
- `conciliacao.extracao.impressao`;
- de `scpi.execucao`: `executar`, `trava` e `trava_importacao`;
- de `scpi.leitura`: `_tabela`, `decimal_br`, `data_br`, `ErroImportacao` e `NadaAExibir`;
- de `scpi.lancamento`: `Resumo` e `RegistroNaExecucao`;
- de `scpi.lancador`: a sessão e as funções de mensagem e de Salvar;
- `pedidos.andamento`, para o cartão da execução.

**Motivo**:
- A FR-031 e o SC-007 pedem que nada mude nas saídas. As consultas da conciliação de saídas
  (`lotes_conferidos`, `liberacao`, `conciliar_verificar` e a limpeza) leem `ConferenciaLote` e
  `RequisicaoOficial` sem filtro de domínio. Pôr as entradas nesses modelos exigiria um filtro novo
  em cada uma delas.
- O relatório de entradas tem colunas que as saídas não usam (`NUMPED`, `CODIF`, `DOCUM`, `DATAE`,
  `QUAN1`), e o vínculo das entradas é triplo.
- Um app próprio deixa a porta de gravação dos recebimentos num lugar só (`compras/servicos.py`),
  como o Princípio II pede para os pedidos.

**Alternativas**:
- Estender os modelos de `conciliacao` com um campo de domínio: tocaria toda consulta das saídas.
- Generalizar `scpi/lancamento.py` para os dois robôs: o Princípio III exige a ordem das gravações das
  saídas intacta e testada como está. O robô de entradas é um módulo paralelo, que copia essa ordem.

## R2. Identidade do pedido, do item e do exercício

**Decisão**:
- **Pedido**: o ano de origem e o número do `NUMPED` (`00514/26` → ano 2026, número 514), mais o
  **exercício** em que foi lido, que é o ano da sessão do SCPI (o ano corrente). A unicidade é
  (exercício, ano, número). O `ID_CADPED` não é guardado como identidade.
- **Item**: o pedido mais o `ITEM`. O mesmo `CADPRO` pode aparecer em dois itens (F17 do registro).
- **Virada do exercício**: os pedidos recriados no exercício novo (F13) viram pedidos novos no Central,
  com o mesmo ano de origem e número, o exercício novo e o "Já Entrou" do zero. Um recebimento pertence
  ao pedido de um exercício. O preparado num exercício que já passou fica bloqueado (R16 do registro).

**Motivo**: na virada, o "Já Entrou" do item recomeça. Com a chave só por (ano, número), a explicação do
"Já Entrou" (R19) veria uma queda e travaria todos os pedidos recriados.

**Alternativa**: o `ID_CADPED` como chave. Ele muda na recriação, e o relatório de entradas não o traz.

## R3. Fonte dos pedidos: o 07.13 com saldo a entregar

**Decisão**:
- **Download.** `scpi.relatorios.baixar_pedidos_compra()` gera o 07.13 "Relação de Pedidos (Condição
  da Entrega)":
  - Analítico, com "Apenas com saldo a entregar";
  - salvo em Salvar Arquivo › CSV (Dados), capturado pelo `interceptar_csv`.

  É o relatório conferido pelo Log, que não grava no pedido (F9). O 01.08.03 nunca é usado (F10). Os
  campos são achados pelo rótulo na tela, nunca pelo ID, como no Relatório de Produtos.
- **Leitura.** `scpi.leitura.ler_pedidos_compra(bytes)` é pura e tudo ou nada:
  - colunas obrigatórias: `NUMPED`, `DATPED`, `CODIF`, `NOME`, `ITEM`, `CADPRO`, `UNID1`,
    `TPCONTROLE_SALDO`, `QTD`, `PRCUNT`, `QTDANU`, `QTDENT`, `QTDFALTA` e `QTDPEDIDA`;
  - (`NUMPED`, `ITEM`) é único;
  - nos itens `Q`, `QTDFALTA` tem de ser igual a `QTD − QTDANU − QTDENT − QTDPEDIDA` (F24 do registro);
  - qualquer diferença, número ilegível ou relatório cortado (pela contagem de campos depois da
    recolagem) é `ErroImportacao`, e nada é gravado.
- **Gravação.** O `importar_pedidos_compra` grava numa transação, pela `scpi.execucao.executar` (tipo
  novo `PEDIDOS_COMPRA`):
  - atualiza os valores dos itens presentes e cria os novos;
  - marca `ausente_desde` no item e no pedido que sumiram;
  - nunca apaga nada (FR-005).

  Um item ausente tem saldo zero no SCPI: foi entregue, anulado ou excluído, e o relatório não diz
  qual.
- **Proteção contra relatório cortado** (Princípio IV): a importação que marcaria ausentes mais de 20%
  dos itens presentes na anterior aborta, salvo `--forcar`. É a mesma regra do cadastro.

**Motivo**: o 07.13 com saldo foi o único conferido no SCPI real: sai em cerca de 20 segundos, traz os
mesmos 2.878 itens da listagem e não grava (F9, F24 do registro). Sem o filtro de saldo, o
comportamento não foi visto. O desenho não depende dele: a prova de que nada entrou (R16) usa o "Já
Entrou" dos itens que ainda têm saldo, e o item que zerou fica sem prova, que é o lado seguro.

**Alternativas**:
- O 07.13 sem o filtro de saldo, que traria também os itens já entregues: não verificado. Fica como
  melhoria possível, sem mudar o modelo.
- O 01.08.03: grava no pedido (F10).

## R4. Item disponível para recebimento

**Decisão**: `compras.regras.disponibilidade(item)` (pura) diz se o item pode ser recebido e, se não
pode, por quê. O item é disponível quando:
- o saldo é controlado por quantidade (`TPCONTROLE_SALDO = Q`);
- o `CADPRO` está no cadastro (`Material` pelo `norm_u`, não oculto);
- o pedido é do exercício atual e estava presente na última importação, assim como o item;
- as quantidades do item têm até 3 casas decimais;
- o saldo do SCPI é maior que 0.

O cadastro já exclui serviços (grupo 800) e combustíveis (os tipos do cadastro), o que cobre o F12 sem
lista nova.

**Motivo**: a FR-003 pede quantidade e cadastro. O material oculto sumiu do cadastro do SCPI e não é
recebido. A quantidade com 4 casas não caberia nas 3 casas da FR-008.

**Alternativa**: filtrar por unidade (SV, H, MES). O cadastro já resolve isso, e uma lista de unidades
seria mais uma configuração.

## R5. Saldo livre e reservas

**Decisão**:
- **Saldo do SCPI** = `QTD − QTDANU − QTDENT − QTDPEDIDA`, o `QTDFALTA` da última importação.
- **Reservado** = a soma de três parcelas:
  - os itens dos recebimentos preparados, com erro, em lançamento ou em verificação;
  - os itens dos recebimentos lançados que ainda não foram refletidos;
  - as entradas fora do Central ainda não refletidas.
- **Refletido**: existe uma importação de pedidos bem-sucedida **começada depois** do
  `visivel_desde`, que é o momento a partir do qual o SCPI certamente tem a entrada:
  - lançado pelo robô: o `lancado_em`, gravado depois do Salvar;
  - ligado a uma requisição de uma extração (o "É esta" ou o lançado à mão): o início da extração;
  - entrada fora do Central: o início da extração em que ela apareceu.

  Importação começada antes não prova nada, e a reserva continua. O saldo livre fica menor, nunca maior.
- **Saldo livre** = saldo do SCPI − reservado, por item. É uma função pura
  (`compras.regras.saldo_livre`), usada na tela, na sugestão do "total" e na validação dentro da trava.
- **Entrada fora do Central com código repetido no pedido**: ela é ligada pelo código, porque o
  relatório não traz o item. Se o código está em dois itens, reserva em cada um, pelo lado seguro.
- **Sem sobreposição**: o robô de entradas e a importação de pedidos nunca rodam juntos (R9), então
  um lançamento do robô fica sempre antes ou depois de uma importação, sem ambiguidade.

**Motivo**: o exemplo 100 → 30 → 20 da spec. Sem contar o lançado ainda não importado, o "total"
sugeriria o que já entrou.

**Alternativa**: reservar só os preparados e esperar a importação. O "total" logo depois de um
lançamento sugeriria quantidade a mais. O SCPI recusaria (F2), mas só no Salvar, e o recebimento ficaria
com erro à toa.

## R6. Nota fiscal

**Decisão**:
- **Número**: só dígitos, até 12 (o tamanho do `DOCUM`), guardado sem os zeros à esquerda
  (`000000000501` → `501`). Vazio ou zero é recusado. O fornecedor é o `CODIF` do pedido (D3).
- **Unicidade no banco**: `Recebimento.chave_nf`, com o texto `"<codif>:<número>"`, é `unique` e
  `null=True`. O cancelamento de um recebimento que nunca chegou ao Salvar põe a chave em `NULL` e
  libera a NF. O número e o fornecedor continuam guardados em campos próprios.
- **Recusa amigável**: o serviço recusa antes, com o número do recebimento que já usa a NF, e o
  `IntegrityError` é só a última barreira (dois pedidos do mesmo fornecedor ao mesmo tempo).
- **"Teve tentativa"**: existe uma `TentativaEntrada` real que chegou ao `EM_LANCAMENTO`, com
  resultado lançada ou em verificação. A tentativa que parou antes do Salvar (erro ou ignorada) e a
  simulação não contam: nada foi salvo.

**Motivo**: o MySQL e o MariaDB não têm índice único parcial, e o Django ignora
`UniqueConstraint(condition=...)` nesses bancos (aviso `models.W036`). Já um índice único aceita
vários `NULL`. Assim o banco garante a NF única entre pedidos sem trava por fornecedor.

**Alternativa**: uma tabela de NFs usadas, com a linha apagada no cancelamento. É uma tabela a mais
para o mesmo efeito.

## R7. Concorrência, idempotência e edição

**Decisão**:
- **Porta única** (Princípio II, com a emenda de R23): `compras/servicos.py`, com
  `preparar_recebimento`, `editar_recebimento`, `cancelar_recebimento`, `resolver_recebimento`
  (liberar, ligar e cancelar), `travar_pedido` e `destravar_pedido`. Cada um roda numa transação com
  `select_for_update` no `PedidoCompra`, o que serializa todo o saldo do pedido (FR-011). A NF em outro
  pedido fica garantida pelo índice da R6.
- **Envio**: `Recebimento.envio` é um UUID gerado quando o formulário abre, como o `Pedido.id`. O
  reenvio igual devolve o mesmo recebimento, e o diferente é recusado como divergente.
- **Edição**: `Recebimento.versao` faz a concorrência otimista, como a `Pedido.versao`. A edição
  substitui os itens do recebimento e soma 1 na versão. Só vale até a primeira tentativa que chegou ao
  Salvar (FR-012); um recebimento com erro antes do Salvar pode ser corrigido e volta a preparado.
- **Robô**: guarda a versão que leu. O `_travar` só grava o `EM_LANCAMENTO` se o recebimento continua
  preparado, na mesma versão, e se o pedido não está travado.

**Motivo**: é o padrão do atendimento e da edição (`Pedido.versao`, `editar_atendimento`). A versão
dispensa recriar linhas com IDs novos, que é como as saídas fazem com a `LinhaSaida`.

**Alternativa**: travar por item do pedido. Exigiria travar várias linhas em ordem, e a soma por
pedido é o que importa.

## R8. Número do recebimento e marca nas Observações

**Decisão**:
- **Número**: cada recebimento tem `RC-<pk>` com 4 dígitos ou mais (`RC-0001`). Ele aparece nas telas
  e vai na marca.
- **Observações**: `Central Almoxarifado RC-0001`. Se houver observação do recebimento, ela vem num
  parágrafo novo, como `Obs.: <texto>`, numa linha só e com `;` trocado por `,`, como
  `conciliacao.regras.texto_observacoes`.
- **Leitura da marca**: um padrão próprio, `central\s+almoxarifado\s+(RC-[0-9]{1,9})\b`, sem
  distinguir maiúsculas. O `RE_LOTE_OBSERVADO` das saídas só casa com `P-` e `AV-`, então nada muda
  nelas.

**Motivo**: o prefixo é diferente dos lotes de saída (P9 do registro) e cabe nos 12 caracteres da
saída. O `pk` basta: lacuna na numeração dos recebimentos não importa, porque ninguém os confere em
sequência.

**Alternativa**: numerar pela `Sequencia` de `pedidos`. Ela serializa os envios de pedidos, e misturar
as duas sequências criaria contenção à toa.

## R9. Execução do robô e travas

**Decisão**:
- **Registro da execução**: a `pedidos.ExecucaoRobo` ganha `robo` (`SAIDAS`, o padrão, ou
  `ENTRADAS`). A migration `pedidos/0007` é aditiva, e as execuções existentes ficam `SAIDAS`.
- **Isolamento das saídas**: as consultas da aba Lançamento no SCPI passam a filtrar `robo=SAIDAS`,
  com o mesmo comportamento. Ganham esse filtro a última execução e o andamento da aba. A contagem de
  verificar e a fila leem as linhas de saída e não mudam.
- **Botão das saídas**: o que desabilita os dois botões é a trava ocupada
  (`ExecucaoRobo.trava_ocupada`). Com o robô de entradas rodando, a aba das saídas diz "O robô de
  entradas está lançando".
- **O que não muda**: o histórico de Automações mostra o robô de cada execução, e o
  `robos_em_andamento` cobre os dois sem mudança.
- **Travas**: o robô de entradas roda sob a mesma `TRAVA_LANCAMENTO` (FR-016). Ele também segura a
  trava da importação de pedidos (`trava_importacao(PEDIDOS_COMPRA)`) do começo ao fim: nenhuma
  importação de pedidos acontece durante um lançamento de entradas (R5, R19). Se a importação está
  rodando, o lançamento é recusado com a mensagem de importação em andamento.
- **Journal**: um próprio, `logs/lancar_entradas_journal.jsonl`.

**Motivo**: um registro só de execuções mantém um histórico só, um "em andamento" só e o
`deploy/atualizar.ps1`, que confere os robôs, sem mudança. O campo novo não muda as saídas.

**Alternativa**: um modelo de execução no app `compras`. Duplicaria o "em andamento", o histórico e o
`robos_em_andamento`, e um esquecimento deixaria o deploy recriar o `web` com o robô de entradas
rodando.

## R10. O robô de entradas

**Decisão**: o módulo `scpi/lancamento_entradas.py`, paralelo a `scpi/lancamento.py`, segue esta ordem
(o contrato completo está em [contracts/robo-entradas.md](contracts/robo-entradas.md)):

1. **Seleção.** Entram os recebimentos escolhidos que estão preparados e cujo pedido não está travado
   nem ausente, é do exercício atual e não tem outro recebimento em lançamento ou em verificação (R11).
   Os demais aparecem como bloqueados, com o motivo.
2. **Extração de antes** (FR-021). Sem ela, nada é lançado nem marcado.
3. **Cada recebimento**:
   - `abrir_pedido` devolve a tela "Escolha os Itens";
   - `conferir_tela`, que é pura (R11);
   - `preencher`: marca os itens, confirma os empenhos, preenche a grade, a data, a NF e as
     Observações, e confere tudo;
   - `_travar`: grava o `EM_LANCAMENTO` e a tentativa `VERIFICAR` com a foto na mesma transação;
   - journal;
   - `salvar`.

   Qualquer falha depois do clique leva a `VERIFICAR`. No sucesso, o número vai para o journal e
   depois para o banco (`LANCADO`, com `requisicao_scpi` e `lancado_em`). Se o banco recusar, a
   execução para com `FalhaCritica`.
4. **Extração de depois**, seguida da conciliação.

**Protocolo `SCPIEntradas`**: `abrir_pedido(rec) -> TelaItens`, `preencher(rec)`, `salvar() -> str`,
`depois_de_salvar()`, `encerrar_simulacao()`, `descartar(rec)` e `reiniciar()`. O Playwright o
implementa em produção (`scpi/lancador_entradas.py`, perfil `entradas`) e o simulado nos testes.

**Regras da navegação**:
- Em "Escolha os Itens", o item é achado pelo **número no pedido** (coluna Item), nunca pela posição.
  Os que não estão no recebimento são desmarcados.
- A grade renumera de 1 a n (F1). O robô a confere pelo código e pela ordem dos itens marcados.
- Se dois itens do recebimento têm o mesmo código e a grade não os distingue (a verificar no
  `--dry-run`), o robô recusa antes do Salvar, pelo lado seguro.
- A janela de empenhos é confirmada sem escolher nada (D7).

**Simulação**: abre, confere, preenche e cancela. Não grava nada no Central, não cria tentativa e não
extrai (FR-015).

**Motivo**: a mesma ordem do Princípio III, num módulo que não toca o das saídas.

**Alternativa**: um protocolo único com `preencher` fazendo tudo. A conferência da tela ficaria
escondida na navegação, que não tem teste; separada, ela é uma função pura testada.

## R11. Conferência antes do Salvar

**Decisão**:
- **A conferência.** `compras.regras.conferir_tela(esperado, tela)` é pura e devolve as divergências.
  Para cada item do recebimento, a tela tem de ter:
  - a linha com o número do item e o mesmo código;
  - o "Já Entrou" igual ao esperado;
  - a "Qtd. Saldo" igual à esperada;
  - um saldo que comporte a quantidade.
- **O esperado** é o valor da última importação mais os lançados do Central ainda não refletidos
  naquele item (R5).
- **Com divergência**: o recebimento fica com erro ("O SCPI mudou: item 13, Já Entrou 2 na tela,
  esperado 1"), o pedido fica travado (motivo `TELA`), a tela é descartada e nada é salvo
  (FR-018).
- **Pedido com outro recebimento em lançamento ou em verificação**: não lança mais nenhum recebimento
  até resolver. Se o SCPI salvou o primeiro e perdeu a resposta, o "Já Entrou" esperado do segundo
  ficaria ambíguo, e a terceira prova da liberação (R16) também. O recebimento aparece na fila como
  bloqueado ("o pedido tem um recebimento em verificação").

**Motivo**: o F3 mostra que o SCPI deixa passar um parcial repetido que caiba no saldo. Só o Central
impede a duplicação, e a tela é a única leitura do SCPI no momento do Salvar.

**Alternativa**: confiar só na importação diária. Uma entrada feita à mão de manhã passaria
despercebida até o dia seguinte.

## R12. Data da entrada e mensagens no Salvar

**Decisão**:
- **Data**: o robô digita a data do recebimento em "Data e Hora da Entrada" (D6) e mantém a hora que o
  SCPI sugere.
- **NF**: o robô digita o número sem os zeros à esquerda. O SCPI completa com zeros, como mostra o
  `DOCUM` de 12 dígitos. Isso se confere no `--dry-run`. Se o SCPI não completar, o robô digita os 12
  dígitos, e o modelo não muda.
- **Mensagens**: o aviso de data em outro mês é confirmado uma vez (`scpi.lancador.salvar_requisicao`,
  reaproveitada, F14). Qualquer outra mensagem no Salvar é resultado incerto e leva a `VERIFICAR`.
- **Janelas depois do Salvar** (lacuna L3 do registro): são fechadas por
  `fechar_janelas_pos_salvar`, como nas saídas, e conferidas no primeiro lançamento real.

**Motivo**: a navegação das saídas já trata essas mensagens. Reaproveitá-la evita uma segunda
interpretação do mesmo diálogo.

## R13. Registro oficial das entradas

**Decisão**:
- **Download.** `scpi.relatorios.baixar_entradas(de, ate)`:
  - abre Relatórios › Requisições › Relação de Requisições, com o rádio "Requisições de Entrada";
  - usa só o período, que filtra pela data da entrada (F5);
  - `NadaAExibir` quando o período não tem requisição.

  É uma função nova: a navegação das saídas (`_relacao_de_requisicoes`) não muda.
- **Leitura.** `scpi.leitura.ler_entradas(bytes)` é pura e tudo ou nada:
  - obrigatórias: `REQUI`, `ID_REQUI`, `DATAE`, `DTLAN`, `CODIF`, `DOCUM`, `NUMPED`,
    `OBS_CABECALHO`, `CADPRO` e `QUAN1`;
  - opcionais: `UNID1`, `SAID`, `TPREQUI`, `NPEDFILHO` e `RESPONSA`;
  - uma requisição por número, e cabeçalho que varia dentro dela é erro.
- **Modelos.** `ExtracaoEntradas`, `RequisicaoEntradaOficial` e `ItemEntradaOficial` espelham os da
  spec 010:
  - uma `Importacao` do tipo novo `ENTRADAS` por extração;
  - os motivos `ANTES`, `DEPOIS`, `DIARIA`, `MANUAL` e `ARQUIVO`;
  - o bruto em gzip com a impressão, e `mesmo_arquivo_que`;
  - o `maior_requisicao`.
- **O que entra na conciliação.** A extração guarda todas as entradas do período. Só as que têm
  `NUMPED` de um pedido conhecido entram na conciliação. Com saída (`SAID = S`) também conta: é a saída
  por pedido, que o Central não faz (D2), e que muda o "Já Entrou" igual. Por isso ela é entrada fora do
  Central (D4).

**Motivo**: é o desenho da spec 010, que já foi revisado. A mudança está nas colunas e no rádio.

**Alternativa**: filtrar o relatório por Nº Pedido. Exigiria uma extração por pedido e não mostraria a
entrada de um pedido que o Central ainda não conhece.

## R14. Piso e intervalo

**Decisão**:
- **Piso**: o maior número do relatório de entradas na extração de antes.
- **Intervalo**: `conciliacao.regras.intervalo`, que é genérica no identificador, aplicada às
  `TentativaEntrada` da execução.

**Motivo**: a numeração é a mesma das saídas (F6), então o piso das entradas fica abaixo do maior
número real. Isso só alarga o intervalo, e mais candidatas é o lado seguro.

**Alternativa**: tomar o piso como o máximo entre a extração de entradas e a última de saídas. A de
saídas pode ser antiga, e a regra ficaria com duas fontes.

## R15. Candidatas de um recebimento em verificação

**Decisão**: uma requisição de entrada oficial é candidata quando cumpre uma destas condições:
- tem a marca deste recebimento, ou a NF e o fornecedor dele, em qualquer número: é a "é esta";
- está no intervalo da tentativa, é do **mesmo pedido** e não tem a marca de outro recebimento.

A ordem vem da semelhança com a foto: marca, NF, códigos e quantidades. Uma candidata vista uma vez
continua bloqueando, como na spec 010.

**Motivo**:
- O pedido é a chave que o robô digita na pesquisa e confere na tela antes do Salvar (cabeçalho e
  itens). Uma requisição de outro pedido não pode ser esta tentativa.
- Sem o filtro do pedido, toda entrada manual do dia no intervalo aberto da última tentativa
  bloquearia a liberação para sempre. Em 2026 foram cerca de 1.700 entradas, só 197 por pedido.

**Alternativa**: toda requisição de entrada no intervalo, como nas saídas. Nas saídas o intervalo é
dominado pelo próprio robô; nas entradas, quase tudo no intervalo é digitado à mão.

## R16. Liberação para relançar: as três provas

**Decisão**: `compras.consultas.liberacao(recebimento)` só permite liberar com as três provas da
FR-025:

1. **Extração posterior**: uma extração de entradas bem-sucedida, com motivo diferente de `ARQUIVO`,
   começada depois da tentativa mais recente.
2. **Nenhuma candidata**: em nenhuma conferência da tentativa.
3. **"Já Entrou" esperado**: uma importação de pedidos bem-sucedida, começada depois da tentativa, em
   que cada item do recebimento está presente com o "Já Entrou" igual ao que a tela mostrou na
   conferência antes do Salvar. Esse valor fica gravado na foto da tentativa.

Regras que completam as provas:
- Nenhum outro recebimento do pedido é lançado enquanto este está em verificação (R11). Então
  qualquer diferença é falta de prova, e o item ausente também.
- Lacuna na numeração nunca conta (F6).
- Liberar devolve **o mesmo** recebimento a preparado, com a versão somada em 1 e a NF ainda
  reservada.
- **Cancelar** um recebimento em verificação exige as mesmas três provas. Sem elas, ele continua em
  verificação, e a saída é o "É esta" ou esperar a próxima extração e a próxima importação.

**O filtro sem período do 07.04.01** (pendência do checklist): não é usado. A terceira prova já não
depende da data digitada, que era o motivo da pendência (F6, F25). Ela fica fechada sem consultar o
SCPI.

**Motivo**: a terceira prova cobre o caso que o relatório não vê, a requisição com a data errada.

**Alternativas**:
- Comparar a importação posterior com a anterior, item por item: exigiria guardar uma foto de cada
  importação. A tela já é uma foto tirada no momento certo.
- Usar o filtro por Observação sem período: depende de o SCPI aceitar o filtro sem datas, o que não
  foi visto, e não cobre uma marca que não foi gravada.

## R17. Vereditos de um recebimento lançado

**Decisão**: `compras.regras.veredito_entrada` (pura) usa três vínculos: o número gravado, a marca e a
NF com o fornecedor.

| Situação | Veredito |
|---|---|
| A marca ou a NF com o fornecedor aparece em duas requisições | Duplicado, mesmo sem a marca do Central |
| O número aponta para uma requisição com a marca de outro recebimento | Duplicado |
| Dois vínculos achados apontam para requisições diferentes | Conflito |
| Nenhum vínculo achado e o relatório tem número maior que o do recebimento, ou uma conferência conclusiva anterior já achou a requisição | Não encontrado |
| Nenhum vínculo achado, fora o caso anterior | Aguardando |
| Os vínculos achados apontam todos para a mesma requisição | Comparação: Comprovado ou Divergente |

**Comparação**:
- **Campos**: fornecedor, NF, número do pedido, a data da entrada (`DATAE`) contra a data do
  recebimento, e a soma das quantidades por código (`norm_u`, `Decimal` exato).
- **Nunca**: a `DTLAN` (F5) e o empenho (D7).
- **Diferenças**: só o que difere é mostrado. Um vínculo que falta, como a marca ausente com o número e
  a NF certos, vira nota.

**Tipos de conferência e limites** (como a 010):
- os tipos `LANCAMENTO` (a primeira conclusiva), `REVISAO` (com `alterado_depois`) e `VERIFICAR`;
- só os recebimentos lançados com data no período e antes do início da extração;
- com `--arquivo`, só o primeiro veredito, sem verificação e sem revisão.

**Motivo**: a FR-022 exige os três vínculos. Com o código repetido no pedido, a soma por código é o
que o relatório permite comparar (F17 do registro).

**Alternativa**: generalizar `conciliacao.regras.veredito` para N vínculos. Mudaria a função das
saídas e os testes dela.

## R18. Entrada por pedido feita fora do Central (FR-028)

**Decisão**: para cada requisição de entrada oficial com o `NUMPED` de um pedido conhecido do
exercício, sem a marca do Central, ainda não ligada e com o número **acima do marco**:
- **Com um recebimento aberto do mesmo pedido, com a mesma NF e o mesmo fornecedor** (preparado, com
  erro ou em verificação): ele é ligado à requisição como lançado à mão. Fica com `via = MANUAL`, o
  número e o `visivel_desde`, que é o início da extração. Sai da fila, e o robô nunca o lança.
  **Antes de ligar, compara os itens e as quantidades** do recebimento com os da requisição oficial
  (por código, `norm_u`, soma exata). Se coincidem, liga como acima. Se divergem, **não liga como
  lançado**: trava o pedido (`FORA_DO_CENTRAL`, com a diferença no detalhe) e cria a
  `EntradaForaDoCentral` com as quantidades **oficiais**, que reservam o saldo até a próxima
  importação. O recebimento aberto continua aberto e bloqueado pela trava, para a pessoa decidir.
  Assim o Central nunca reserva menos do que o SCPI recebeu. Um
  recebimento em lançamento não é ligado: a conciliação não roda com lançamento em andamento.
- **Sem esse recebimento**: vira uma `EntradaForaDoCentral`, única por (ano, número) da requisição.
  Ela reserva o saldo até ser refletida (R5) e trava o pedido, com o motivo `FORA_DO_CENTRAL`.

**O marco** é o `maior_requisicao` da primeira extração de entradas bem-sucedida
(`compras.consultas.marco`). O que tem número até ele é história anterior ao Central: já está no "Já
Entrou" da base e nunca vira entrada fora do Central. A numeração cresce com o tempo, inclusive na virada
do ano, pela chave (ano, número). Uma entrada salva entre a importação de base e essa primeira extração
fica abaixo do marco, mas aparece na importação seguinte como "Já Entrou" não explicado (R19): é o lado
seguro.

Casos que também travam o pedido e geram aviso de saúde, sem ligar nada:
- uma requisição com a marca de um recebimento que não está lançado nem em verificação (motivo
  `MARCA_SEM_LANCAMENTO`);
- uma requisição cuja marca não é de recebimento nenhum.

**Motivo**: a D4 diz que a entrada feita direto no SCPI é exceção, e a NF com o fornecedor identifica
o recebimento (D3).

## R19. "Já Entrou" que o Central não explica (FR-029)

**Decisão**: a cada importação de pedidos bem-sucedida, a conferência roda por (pedido, código), para
os itens presentes nesta importação e na anterior.
- **A diferença**: Δ = a soma do `QTDENT` novo − a soma do anterior.
- **Explicado** quando `Δ − certos` é a soma de algum subconjunto dos incertos
  (`compras.regras.ja_entrou_explicado`, pura):
  - **certos**: os recebimentos lançados pelo robô entre os inícios das duas importações (pelo
    `lancado_em`). O robô e a importação nunca se sobrepõem (R9);
  - **incertos**: os recebimentos com tentativa em verificação nesse intervalo, que podem ter sido
    salvos ou não, e os ligados à mão e as entradas fora do Central com `visivel_desde` depois do início
    da anterior, porque a hora real da entrada é desconhecida.
- **Sem explicação**: aviso de saúde e trava do pedido (motivo `JA_ENTROU`), com o Δ e o explicado no
  detalhe. Um Δ negativo, de entrada excluída ou corrigida no SCPI, também trava.
- **Item que some do 07.13** (saldo zero): a entrada que o zerou pode ser anterior à janela diária e
  então a extração de entradas não a traz. Reconciliação: o item que sumiu entre duas importações, sem
  um recebimento do Central (`LANCADO` ou ligado) ou uma entrada fora do Central que o explique,
  **trava o pedido** (`JA_ENTROU`, com "item N saiu do saldo sem entrada conhecida: pode ser entrada
  retroativa, anulação ou exclusão") e gera aviso de saúde. O destravamento segue a R20, e a pessoa
  pode ampliar a janela do `conciliar_entradas --desde` para achar a entrada. Fica de fora só o que o
  Central não consegue distinguir: a primeira importação.
- **Fora da conferência**:
  - a primeira importação de um pedido ou de um exercício, que é a base.

**Motivo**: toda entrada feita fora do Central já trava o pedido por R18, então um falso alarme de
horário nesse caso não custa nada. O que não pode acontecer é uma trava falsa quando só o robô mexeu
no pedido, e os certos garantem isso.

**Alternativa**: explicar o "Já Entrou" pela soma das entradas do relatório desde 1º de janeiro. Exigiria
extrair o ano inteiro todo dia e guardar as requisições para sempre.

## R20. Travas do pedido

**Decisão**:
- **Registro**: `TravaPedido` guarda o pedido, o motivo (`TELA`, `JA_ENTROU`, `FORA_DO_CENTRAL` ou
  `MARCA_SEM_LANCAMENTO`), o detalhe, quando foi criada, a origem (execução, importação ou extração),
  e quando e por quem foi destravada, com o motivo informado.
- **Efeito**: o pedido está travado enquanto houver uma trava aberta. Travado, ele não aceita
  recebimento novo e não entra na fila do robô (FR-013). Editar e cancelar o que já existe continua
  permitido: o lançamento está bloqueado de qualquer jeito.
- **Destravar** (`compras.servicos.destravar_pedido`) é para quem opera automações e exige o motivo e
  uma importação de pedidos bem-sucedida começada depois da trava aberta mais recente. Fecha todas as
  travas abertas do pedido, e o saldo livre é recalculado pela importação nova.

**Motivo**: a FR-013 pede o motivo e a atualização posterior. Uma linha por trava guarda o histórico de
quem destravou e por quê.

**Alternativa**: um booleano no pedido. Perde o histórico e o motivo de cada trava.

## R21. Permissão e rotas

**Decisão**:
- **Permissão nova**: `contas.receber_compras`, "Receber compras (preparar, editar e cancelar
  recebimentos)". Entra em `Usuario.Meta.permissions` e em `contas.acesso.PERMISSOES_INTERNAS`, o que
  faz quem a tem contar como equipe, nunca como solicitante.
- **Migration** `contas/0007_receber_compras`: cria a permissão e a dá aos grupos Atendimento e Gestão.
  É uma migration de dados, conferida no fim, como a `0004_papeis`.
- **Rotas** em `REGRAS_POR_ROTA`:
  - as de `compras:*` exigem `receber_compras`;
  - as ações do robô e da conferência de entradas em `automacoes:*` exigem `operar_automacoes`.

  Nenhuma entra em `ROTAS_SEGURANCA_TRABALHO`.
- **Menu**: o item "Compras" em `ITENS_MENU`, com um ícone do `_icone.html`, e o atalho no detalhe do
  pedido para Automações só com `perms.contas.operar_automacoes`.

**Motivo**: a FR-030 e a spec 012. O teste que percorre as rotas (`tests/test_papeis_acesso.py`) pega a
rota esquecida.

## R22. Rotina diária e retenção

**Decisão**:
- **Rotina diária**: o `atualizar_catalogo` ganha dois passos depois de Requisições, nesta ordem e na
  mesma sessão do navegador:
  1. **Entradas**: a extração do 07.04.01, seguida da conciliação e da limpeza. O período vai do dia
     anterior ao menor destes valores até amanhã:
     - hoje − 9 dias;
     - a data de recebimento dos recebimentos lançados com `lancado_em` nos últimos 9 dias;
     - a data de recebimento dos recebimentos em verificação abertos.

     Assim um recebimento lançado hoje com data antiga continua coberto, e uma correção feita depois
     à mão no SCPI aparece como revisão (US4, cenário 6). Nas saídas a data filtrada é a do
     lançamento, e os 9 dias bastam;
  2. **Pedidos de compra**: o 07.13, seguido da explicação do "Já Entrou".

  Um passo que falha não desfaz os anteriores. O `deploy/crontab` continua às 07:15.
- **Retenção**: 60 dias para o bruto e para as requisições oficiais que nenhuma conferência liga, com
  as mesmas travas da limpeza da 010.

**Motivo**: com as entradas antes, a entrada fora do Central já está registrada e explicada quando a
importação a encontra no "Já Entrou" (R19).

## R23. Emenda da constituição (MINOR, 2.0.0 → 2.1.0)

**Decisão**: no PR 0, junto com a spec e este plano, os Princípios II e III passam a cobrir as entradas.

**Princípio II**, acréscimos:
- `compras/servicos.py` é o único lugar que grava recebimentos e travas de pedido, com transação e
  `select_for_update` no pedido de compra.
- Fora dele, só o robô de entradas grava em recebimentos, e só nos campos `status`,
  `requisicao_scpi`, `lancado_em`, `mensagem`, `via` e `visivel_desde`. A trava do pedido ele grava
  pela função do serviço.
- O reenvio igual de um recebimento não duplica: o identificador do envio decide.

**Princípio III**:
- passa a falar de "lote ou recebimento";
- o journal de cada robô é próprio;
- "uma execução de lançamento por vez, de saídas ou de entradas, com a mesma trava";
- a conferência antes do Salvar entra como garantia das entradas.

**Princípio I**: `compras/regras.py` entra na lista de módulos de regras puras.

**Motivo**: a governança exige a emenda antes do código que depende dela. É MINOR porque amplia
princípios sem redefinir nenhum.

## R24. Testes sem navegador

**Decisão**:
- **SCPI simulado** `tests/scpi_entradas_simulado.py`:
  - estado por pedido (quantidade, anulado, já entrou);
  - o registro do que foi salvo, as requisições à mão e o relatório de entradas e o 07.13 no formato
    real;
  - as falhas: `falha_antes`, `salva_e_falha`, `tela_mudou`, `perde_observacoes`, `nf_errada`,
    `entrada_manual` e `falhas_relatorio`.
- **CSVs sintéticos**: `tests/relacao_entradas.py` e `tests/relacao_pedidos_compra.py`. O CSV real
  tem nomes de pessoas e nunca entra no repositório.
- **Cenários**: `tests/compras_cenario.py`, com pedido importado, recebimento, tentativa em verificação
  e liberação comprovada.
- **Concorrência**: as duas pessoas ao mesmo tempo (US1, cenário 7) num teste com duas conexões e
  `transaction=True`, como os testes de travas existentes.

**Motivo**: o Princípio V. O simulado das saídas não muda.

## R25. O que só o SCPI real confirma

Pontos que os testes não alcançam. Todos são conferidos no [quickstart](quickstart.md) antes de
lançar de verdade, e nenhum muda a ordem das gravações:
- o ano que se digita na pesquisa de um pedido de exercício anterior (`00001/25` em 2026);
- a NF digitada sem os zeros à esquerda (R12);
- a hora da entrada sugerida pelo SCPI;
- as janelas depois do Salvar (L3 do registro);
- a latência até o relatório (L8 do registro);
- a ordem da grade com código repetido (R10);
- o rádio "Requisições de Entrada" e os campos de data do relatório (R13);
- os campos do 07.13 pelo rótulo (R3).

## R26. Interface

**Decisão**:
- **Área Compras** (`/painel/compras/`, papel Atendimento e Gestão):
  - a lista de pedidos com itens disponíveis, com busca por número, fornecedor e código;
  - o detalhe do pedido com itens, saldo livre, recebimentos e travas;
  - o formulário de recebimento "total" ou "parcial";
  - o detalhe do recebimento, com editar e cancelar.
- **Aba nova "Entradas no SCPI" em Automações** (papel Gestão):
  - a fila, com escolha, "Simular" e "Lançar no SCPI";
  - o andamento, pelo `pedidos.andamento`;
  - os recebimentos em verificação, com as candidatas, o "É esta", "Liberar" e "Cancelar";
  - os pedidos travados, com "Destravar";
  - a conferência com os vereditos e o "Conferir agora";
  - o "Atualizar pedidos".
- **Desenho**: segue o da aba Lançamento no SCPI. A interface passa pelas três skills (`clean-design`
  com o `docs/DESIGN.md`, `ui-ux-pro-max` e `frontend-design`). Telas e ações estão em
  [contracts/tela-e-acoes.md](contracts/tela-e-acoes.md).

**Motivo**: preparar o recebimento é trabalho do Atendimento, ao lado do painel. Lançar e conferir são
da Gestão, em Automações, como nas saídas.
