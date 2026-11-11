# Contrato: o robô de entradas

Módulo `scpi/lancamento_entradas.py`, paralelo a `scpi/lancamento.py`, que continua igual. A ordem das
gravações é a do Princípio III e não admite exceção ([R10](../research.md#r10-o-robô-de-entradas),
[R11](../research.md#r11-conferência-antes-do-salvar)).

## Protocolo `SCPIEntradas`

| Método | Faz | Falha |
|---|---|---|
| `abrir_pedido(rec) -> TelaItens` | Inserir › "por pedido" › Pesquisa Pedido de Compra (número + ano) › lê "Escolha os Itens": para cada linha, o número do item, o código, Qtd., Já Entrou, Já Pedida e Qtd. Saldo | `ErroSCPI`: nada foi salvo |
| `preencher(rec)` | desmarca os itens fora do recebimento, confirma os empenhos sem escolher, preenche a QTD de cada linha da grade, a data da entrada, a NF e as Observações, e confere tudo na tela | `ErroSCPI`: nada foi salvo |
| `salvar() -> str` | clica em Salvar, confirma uma vez o aviso de data em outro mês e lê o número no campo Requisição | qualquer exceção: **resultado incerto** |
| `depois_de_salvar()` | fecha as janelas que abrirem e volta ao formulário | registra e chama `reiniciar` |
| `encerrar_simulacao()` | cancela o formulário preenchido sem salvar | |
| `descartar(rec)` | cancela o que estiver aberto | |
| `reiniciar()` | reabre o módulo, como depois de um lançamento | |

`TelaItens` é um dado puro: uma lista de `LinhaTela(item, codigo, quantidade, ja_entrou, ja_pedida,
saldo)`.

Implementações:
- produção: `scpi/lancador_entradas.py` (Playwright, perfil `entradas`), sobre a sessão e as funções
  de mensagem de `scpi/lancador.py`;
- testes: `tests/scpi_entradas_simulado.py`.

## O recebimento que o robô recebe (`RecebimentoParaLancar`)

Dado puro, montado pela seleção. Tem:
- `id`, `rotulo` (`RC-0001`) e `versao`;
- o pedido: ano, número e rótulo;
- fornecedor, NF e data;
- `observacoes`, o texto já montado com a marca;
- os itens: número no pedido, código e quantidade;
- o esperado por item: "Já Entrou" e saldo ([R11](../research.md#r11-conferência-antes-do-salvar)).

## Ordem

1. **Trava.** `TRAVA_LANCAMENTO` (a mesma das saídas) e a trava da importação de pedidos. Sem uma
   delas, a execução termina `FALHA`, com "Outro lançamento já está em andamento." ou "A importação
   de pedidos está em andamento.", e nada muda.
2. **Seleção.** Dos recebimentos escolhidos, entram os que estão `PREPARADO`, com pedido
   disponível (não travado, presente na última importação, do exercício atual) e sem outro
   recebimento do pedido `EM_LANCAMENTO` ou `VERIFICAR`. Os demais entram no resumo como `ignorada`,
   com o motivo, e não mudam. **A seleção não substitui a revalidação**: o `_travar` refaz a
   condição de cada recebimento dentro da sua transação, com `select_for_update` no pedido, antes de
   cada lançamento. Se um recebimento anterior desta execução (ou de qualquer outra) deixou o pedido
   com outro recebimento `EM_LANCAMENTO` ou `VERIFICAR`, ou travado, o seguinte vira `ignorada`, e
   nada é salvo.
3. **Extração de antes** (só no real). Período: do dia anterior à data de recebimento mais antiga,
   entre os escolhidos e os recebimentos em verificação abertos, até amanhã. Até 3 tentativas. Sem
   nenhuma bem-sucedida, `ExtracaoAntesFalhou`: a execução termina `FALHA` e nada muda. O piso é o
   `maior_requisicao` dela. **Leitura oficial da NF**: com a extração de antes em mãos, o robô procura,
   para cada recebimento escolhido, uma requisição de entrada oficial do mesmo fornecedor e da mesma NF
   (qualquer item, qualquer pedido, sem a marca do Central). Essa leitura **não depende do período
   da extração principal**: ela usa uma extração própria do relatório de entradas (motivo `ANTES`),
   do **1º de janeiro do exercício até amanhã**, feita uma vez por execução real, porque a NF pode
   ter entrado à mão numa data anterior ao período e em outro pedido do mesmo fornecedor. Se o
   07.04.01 aceitar o filtro só por NF, sem período, a leitura passa a usá-lo (R25); até lá, vale
   a janela do exercício. **Limites assumidos**: (1) o Central só
   trabalha com pedidos do exercício atual e com a NF de um fornecedor nesse exercício; uma NF igual
   de exercício anterior é outra nota (o fornecedor não repete o número) e fica fora desta leitura; se
   ocorrer, a conciliação acusa "Duplicado pela NF". (2) A leitura é **uma por execução**, não uma
   por Salvar: o relatório leva dezenas de segundos (latência L8, ainda não medida), então repeti-la
   antes de cada Salvar alargaria a janela em vez de fechá-la. A proteção do instante do Salvar é a
   reconferência da tela (do pedido); uma entrada manual da mesma NF em **outro pedido**, feita depois
   desta leitura, não é impedida e é detectada pela extração de depois (Duplicado pela NF, com o
   pedido travado), o risco residual do SC-001. Se existe, o recebimento é `ignorada`
   ("a NF já entrou no SCPI: requisição <número>") e o pedido é travado (`FORA_DO_CENTRAL`), para a
   conciliação ligar ou tratar (R18). Isso cobre a entrada manual da mesma NF em **outro item**, que a
   tela de itens não mostra.
4. **Para cada recebimento, em ordem**:
   0. **Revalida o pedido antes de abrir o SCPI.** Lê, no banco, se o recebimento ainda está
      `PREPARADO` e se o pedido segue sem trava e sem outro recebimento `EM_LANCAMENTO` ou
      `VERIFICAR` (o que o recebimento anterior desta execução pode ter deixado). Se não, o
      resultado é `ignorada` com o motivo, e o SCPI nem é aberto: a tela de um pedido que o
      recebimento anterior já mudou nunca é conferida contra um esperado que não vale mais. É uma
      leitura rápida; quem decide de verdade é o `_travar`.
   1. `abrir_pedido`. Uma falha leva o recebimento a `ERRO`, cria a tentativa `ERRO` e chama
      `descartar`. **Toda gravação de `ERRO` (aqui, no `conferir_tela` e no `preencher`) é
      condicional e atômica**: um `UPDATE` que só vale se o recebimento ainda está `PREPARADO` e na
      `versao` selecionada. Se mudou (editado, cancelado ou ligado à mão no meio do caminho), o
      estado atual é preservado, o resultado é `ignorada` ("o recebimento mudou") e a operação é
      descartada. Na simulação nenhum estado do Central muda.
   2. `conferir_tela(esperado, tela)`, que é pura. O `esperado` é calculado **no momento de cada
      recebimento**, não na seleção: o "Já Entrou" da última importação mais as quantidades que o
      robô acabou de lançar (`LANCADO`, ainda não refletidos) no mesmo pedido e item. Assim, dois
      recebimentos do mesmo pedido com o mesmo item na mesma execução não fazem o segundo falhar por
      um esperado desatualizado. A tela é conferida em **todos os itens do pedido**, não só nos do
      recebimento: um "Já Entrou" maior em qualquer item é divergência, mesmo que a entrada manual
      tenha sido de outro item. Como a tela só lista item com saldo, o item que ainda devia ter saldo
      e **não aparece** também é divergência (a entrada manual o esgotou); o item cujo saldo esperado
      já é zero pode faltar sem divergir (R11). Com divergência:
      - o recebimento vai a `ERRO`, com a mensagem "O SCPI mudou: …";
      - `compras.servicos.travar_pedido(TELA)`;
      - a tentativa é criada como `ERRO`, e o robô chama `descartar`.

      **Não salva.** **Na simulação, nada disso é gravado**: a divergência entra só no resumo e no
      log da execução, e o robô chama `descartar`.
   3. `preencher`. Uma falha leva a `ERRO`, cria a tentativa `ERRO` e chama `descartar`.
      **Reconferência imediatamente antes do Salvar**: depois de preencher, o robô faz uma **leitura
      somente de consulta** da grade de itens (`ler_tela`: nenhum clique, nenhuma digitação, nenhum
      campo alterado, então o formulário preenchido e os dados do recebimento ficam intactos). A
      leitura traz todas as linhas da grade, inclusive as dos itens desmarcados, e o robô roda o
      `conferir_tela` outra vez com o mesmo `esperado`; a ausência de uma linha só é divergência
      pelo critério do R11 (item que ainda devia ter saldo), nunca por ela mesma. **Ponto a confirmar
      no `--dry-run` real (R25)**: se a grade ainda mostra os itens desmarcados depois do
      preenchimento. Se **não** mostrar, a leitura de todos os itens do pedido passa a ser a de
      `abrir_pedido` (tela "Escolha os Itens", antes de desmarcar), e esta reconferência cobre só os
      itens marcados; nenhum clique é dado para recuperar os desmarcados, para não perder o
      formulário. **Limite do plano B**: uma entrada manual em um item desmarcado, feita depois do
      `abrir_pedido`, não é vista pela reconferência; é detectada pela extração de depois ("Já
      Entrou" não explicado, com o pedido travado), não impedida. É o mesmo risco residual do SC-001.
      **Quem detecta e quando**: o "Já Entrou" não explicado é achado na **próxima importação de
      pedidos** (R19, `importar_pedidos_compra` ou a rotina diária), e o Duplicado pela NF, na
      **conciliação** da extração de depois; as duas são do PR 6. Entre o PR 5 e o PR 6 não há
      detecção automática: vale a regra operacional da aba e a conferência manual do quickstart. Com divergência, o tratamento é o do passo 2 (`ERRO`, `travar_pedido(TELA)`,
      tentativa `ERRO` e `descartar`) no lançamento real, e nada é salvo. Na simulação, o modo é
      verificado primeiro: a divergência é registrada no resumo e no log da execução, o robô chama `descartar` e segue para
      o próximo recebimento, sem mudar estado, trava nem tentativa. Reduz a janela para uma entrada manual feita
      no meio do preenchimento; o que ainda escapar entre esta leitura e o Salvar é detectado pela
      extração de depois (Duplicado ou "Já Entrou" não explicado), não impedido.
   4. Na simulação: `encerrar_simulacao` e o resultado `simulada`. Nada é gravado no Central.
   5. `_travar`, numa transação com `select_for_update` no recebimento e no pedido. Ela só passa se o
      recebimento está `PREPARADO`, na mesma versão, o pedido não está travado **e nenhum outro
      recebimento do pedido está `EM_LANCAMENTO` ou `VERIFICAR`** (a revalidação definitiva, que a
      leitura do passo 0 apenas antecipa). Grava o
      `EM_LANCAMENTO` e a `TentativaEntrada` `VERIFICAR`, com a foto e a tela lida, e **fecha a
      transação antes do clique**. Se não passa, o resultado é `ignorada` ("o recebimento mudou"),
      com a tentativa `IGNORADA` e `descartar`. Erro de banco é `FalhaCritica`.
   6. Journal `em_lancamento`.
   7. `salvar`. **Qualquer** exceção:
      - journal `incerto`;
      - o recebimento vai a `VERIFICAR`, com "Resultado incerto: …", de forma crítica;
      - `reiniciar`.
   8. Com o número em mãos:
      - journal `lancada`, com o número;
      - o recebimento vai a `LANCADO`, com `requisicao_scpi`, `lancado_em`, `via=ROBO` e
        `visivel_desde=lancado_em`, de forma crítica;
      - a tentativa vai a `LANCADA`, com o número;
      - `depois_de_salvar`.

      Se o banco recusar, `FalhaCritica`, e a execução para com o recebimento travado.
5. **Extração de depois** (só no real), seguida da conciliação das entradas. Uma falha vai para o log
   e não piora a execução.

## Garantias (testadas com o simulado)

| Cenário | Resultado |
|---|---|
| Falha antes do Salvar (abrir, conferir, preencher) | `ERRO`; nada salvo no simulado; a NF continua reservada, mas sem tentativa real (pode ser editado e cancelado) |
| Tela diferente do esperado | `ERRO`, pedido travado, nada salvo |
| Salvou e perdeu a resposta (`salva_e_falha`) | `VERIFICAR`; o simulado tem a requisição; o recebimento não volta à fila |
| Processo morre depois do `_travar` | `EM_LANCAMENTO` com a tentativa `VERIFICAR`; nunca volta a `PREPARADO` sozinho |
| Recebimento editado entre a seleção e o `_travar` | `ignorada`; nada salvo |
| Banco recusa a gravação do número | `FalhaCritica`; o número está no journal |
| Simulação | nenhuma tentativa, nenhum estado muda, nenhuma extração, nenhuma requisição no simulado |
| Lançamento real bloqueado (`LANCAMENTO_REAL` desligado) | recusado antes de criar a execução; só "Simular" |
| Robô de saídas rodando | recusado pela trava |
| Segundo recebimento do mesmo pedido com o primeiro em `VERIFICAR` | `ignorada` ("o pedido tem um recebimento em verificação") |

## Journal

`logs/lancar_entradas_journal.jsonl` (`LOG_DIR`). Uma linha JSON por evento (`em_lancamento`,
`incerto` ou `lancada`), com a execução, o recebimento, a versão e o número. É gravado antes do banco.

## Resumo da execução

O mesmo `Resumo` das saídas (`ExecucaoRobo.resumo`): `fase` e `lotes`, um item por recebimento
escolhido, com o rótulo `RC-…` no lugar do lote. Os resultados são `aguardando`, `andamento`,
`lancada`, `verificar`, `erro`, `ignorada` e `simulada`. Assim o `pedidos.andamento.acompanhamento`
monta o cartão sem mudança.
