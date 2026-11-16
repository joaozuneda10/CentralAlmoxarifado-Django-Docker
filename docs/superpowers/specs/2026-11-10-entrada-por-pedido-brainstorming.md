# Entrada de materiais por pedido de compra: material para o `speckit.specify`

Brainstorming com o usuário em 2026-11-10, antes da spec. Nada aqui foi implementado.

Fontes:
- a constituição e o template de spec do Spec Kit;
- o código e os testes da conciliação de saídas (spec 010);
- três CSVs do SCPI extraídos pelo usuário em 10/11/2026: a listagem de pedidos, as entradas de 01/01 a 09/11/2026 e as saídas de 01/10 a 09/11/2026. Os CSVs ficam **fora do repositório**, porque têm nomes de pessoas;
- as telas do SCPI observadas no Chrome do usuário. Do lado do Claude, só consultas; as inserções foram feitas pelo usuário e terminaram em Cancelar.

Marcas usadas no texto:
- **F** = fato observado (seção 8);
- **D** = decisão do usuário;
- **P** = proposta aprovada pelo usuário em 2026-11-10 (P1–P13);
- **L** = lacuna (seção 9).

## 1. Objetivo e escopo

O almoxarifado registra no Central o recebimento de uma nota fiscal de um pedido de compra, total ou parcial, depois de conferir o material. O robô lança a Requisição de Entrada por pedido no SCPI, com as garantias do Princípio III (D1). A conciliação compara cada lançamento com o registro oficial.

- **Dentro:**
  - pedidos e saldos importados do SCPI;
  - recebimento preparado pelo papel Atendimento (D8);
  - fila e robô em Automações (Gestão);
  - conciliação com o relatório de entradas;
  - tratamento de entrada feita fora do Central.
- **Fora (D2, D5, D7, P11):**
  - saída por pedido (entrada com saída direta para o centro), que fica para outra spec;
  - receber acima do pedido;
  - divergência entre nota e material: nada entra até resolver;
  - série e chave da NF-e;
  - escolha do empenho;
  - pedidos só de serviço ou de combustível.

## 2. Vocabulário

| Termo | Significado | Identidade |
|---|---|---|
| Pedido | Pedido de compra do SCPI, de um único fornecedor | `NUMPED` com o ano de origem (`00514/26`). **Nunca** o `ID_CADPED`, que muda quando o pedido passa para o exercício seguinte (F14) |
| Item do pedido | Linha do pedido: material, quantidade, preço | `NUMPED` + `ITEM` (`00514/26` item 13). O mesmo `CADPRO` pode aparecer em dois itens (F17) |
| Saldo do SCPI | Pedido − já entrou − já passado a subpedido, como na coluna "Qtd. Saldo" da tela (F7). A anulação entra via `QTDANU` | por item |
| Saldo livre | Saldo do SCPI − o que o Central já reservou | por item (P1) |
| Nota fiscal (NF) | Documento do fornecedor | fornecedor (`CODIF`) + número sem os zeros à esquerda (`DOCUM` `000000000501` = 501). Série fora da chave (D3, F6) |
| Recebimento | Registro do Central: uma NF de um pedido, com itens, quantidades e data do recebimento | identificador próprio do Central, que vai na marca. **Um recebimento = uma NF = um pedido = uma requisição** (D3, F6) |
| Requisição de entrada | Registro oficial do SCPI | `REQUI` (`003492/26`, numeração anual **compartilhada com as saídas**, F5) |
| Tentativa | Cada vez que o robô tenta salvar um recebimento, com a foto do que vai digitar | ordem dentro da execução |
| Marca | Texto "Central Almoxarifado <recebimento>" nas Observações. Prefixo distinto de `P-` e `AV-` | segundo vínculo (P9, F10) |
| Extração | Uma leitura guardada do relatório de entradas (07.04.01, "Requisições de Entrada"), com o período pela data da entrada | como a `ExtracaoOficial` da spec 010 |
| Entrada fora do Central | Requisição de entrada de um pedido sem marca do Central | exceção (D4) |

## 3. Vínculos

- **Pedido 1 — N itens.** Pedido 1 — N recebimentos (até 15 requisições num pedido em 2026, F2).
- **Recebimento 1 — 1 NF.** O Central recusa uma segunda vez a mesma NF do mesmo fornecedor (P4: depois de uma tentativa, nunca libera).
- **Recebimento 1 — 0..1 requisição oficial**, ligada por **três vínculos** que têm de apontar para a mesma requisição (P9):
  1. o número gravado pelo robô;
  2. a marca nas Observações;
  3. a NF + fornecedor (`DOCUM` + `CODIF`).
- **Item do recebimento → item do pedido.** O vínculo existe na tela "Escolha os Itens", onde aparecem os números do pedido. Depois disso, a grade da entrada e o relatório renumeram os itens e só trazem o `CADPRO` (F7). Quando o código se repete no pedido, o relatório não diz qual item entrou. Esse caso nunca teve entrada (F17), e então a conciliação compara a **soma por código**.

## 4. Estados

**Recebimento**, com os nomes das saídas entre parênteses:

| Estado | Reserva saldo? | Para onde vai |
|---|---|---|
| Preparado (`PENDENTE`) | sim | Em lançamento; Cancelado; Com erro (validação do lote) |
| Em lançamento (`EM_LANCAMENTO`), gravado antes do Salvar | sim | Lançado; Em verificação |
| Lançado (`LANCADA`), com o número | sim, até o SCPI refletir | (conciliação) |
| Em verificação (`VERIFICAR`), falha depois do clique | **sim** | Lançado ("É esta"); Preparado (liberado, só com prova, P9); Cancelado |
| Com erro (`ERRO`), falha antes do Salvar, nada gravado | sim | Preparado (corrigido); Cancelado |
| Cancelado (`NAO_LANCAR`) | não | — (a NF só volta a ficar livre se nunca houve tentativa, P4) |

**Veredito da conciliação** (spec 010, P9): Aguardando, Comprovado, Divergente, Não encontrado, Conflito, Duplicado. Há um caso novo: **"Lançada fora do Central"**, para a requisição oficial de um pedido conhecido que não tem a marca (D4).

**Pedido no Central:**
- **Disponível:** está no exercício atual e tem saldo livre.
- **Travado:** uma diferença não explicada, vinda da conferência antes do Salvar ou da importação (P8, D4), bloqueia novos lançamentos até alguém conferir.
- **Fora do exercício** (P12).

## 5. Regras

| # | Regra | Base |
|---|---|---|
| R1 | O recebimento leva pedido, número da NF, **data do recebimento** (no máximo hoje e não antes do pedido), itens e quantidades, quem preparou e uma observação opcional. Não leva série, chave nem empenho | D6, D7, P3 |
| R2 | **"Total" sugere o saldo livre de cada item.** "Parcial" escolhe itens e baixa quantidades. Nenhum item fica acima do saldo livre | P1, F7, F8 |
| R3 | Saldo livre = item − `QTDANU` − já entrou no SCPI − já passado a subpedido − o reservado pelo Central (Preparado, Em lançamento, Em verificação, Com erro e Lançado ainda não refletido) | P1, F2, F7, F15 |
| R4 | Quantidade decimal pt-BR ("1.5" é recusado), maior que 0, **até 3 casas** em qualquer unidade | P2, F16, Princípio I |
| R5 | Preparar, editar e cancelar travam a linha do pedido no banco (porta única, `select_for_update`). Duas pessoas nunca reservam o mesmo saldo | Princípio II, P1 |
| R6 | A mesma NF do mesmo fornecedor não entra duas vezes. O cancelamento só a libera se nunca houve tentativa | D3, F6, P4 |
| R7 | O robô segue o caminho Inserir › por pedido › pedido + ano › marca **só os itens do recebimento** › confirma a janela de empenhos sem escolher › QTD de cada item › data da entrada › NF › Observações com a marca › Salvar | F7, F9, D7 |
| R8 | **Conferência antes do Salvar.** Para cada item, o saldo e o "Já Entrou" da tela são comparados com o esperado. Se forem diferentes, o robô desiste sem salvar, o recebimento fica Com erro ("o SCPI mudou") e o pedido fica travado | P8, D4, F8 |
| R9 | `EM_LANCAMENTO` gravado antes do Salvar; falha depois do clique vira Em verificação; o número vai ao journal antes do banco; uma execução por vez, **com a mesma trava do robô de saídas** | Princípio III, P6, F5 |
| R10 | O lançamento real só roda com `LANCAMENTO_REAL`. A simulação vai até a grade e cancela, sem gravar nada no pedido e sem extrair | P6, P7, F13 |
| R11 | Extração do relatório de entradas **antes** de cada execução real (é o piso; sem ela, nada é lançado), **depois** dela e na rotina diária. O período vai do dia anterior à data de entrada mais antiga envolvida até o dia seguinte a hoje | P9, F3, spec 010 |
| R12 | Veredito: os três vínculos da seção 3 apontam para a mesma requisição. Ela é comparada em fornecedor, NF, pedido, data da entrada (`DATAE`, **nunca** `DTLAN`, F4), `CADPRO` e quantidade (soma por código). O empenho não é conferido | P9, D7, F4 |
| R13 | Um recebimento Em verificação só é liberado para relançar (o **mesmo** recebimento) com uma extração começada depois da tentativa, nenhuma candidata no intervalo e o "Já Entrou" do item igual ao esperado. Uma candidata vista uma vez continua bloqueando | P9, spec 010 |
| R14 | Requisição oficial do pedido sem marca: com a NF + fornecedor de um recebimento aberto, ela é esse recebimento, feito à mão ("É esta"), e o robô nunca o relança. Sem isso, é "Lançada fora do Central": ela reduz o saldo e trava o pedido até conferência | D3, D4, F6 |
| R15 | Pedidos: carga inicial completa e atualização diária pelo **07.13 "Relação de Pedidos (Condição da Entrega)"**, Analítico, com "Apenas com saldo a entregar", em CSV (Dados). Ele não grava no pedido (F23). **Nunca o 01.08.03 Imprimir Pedidos.** O recebido vem do relatório de entradas. Importação que diverge do `QTDENT` gera aviso de saúde e trava o pedido | P10, F2, F12, Princípio IV |
| R16 | Só se prepara recebimento de pedido presente no exercício atual. Um recebimento não lançado na virada do ano fica bloqueado até a nova carga | P12, F14 |
| R17 | Depois de lançado, o Central não edita. A correção é feita à mão no SCPI e aparece na conciliação | P5 |
| R18 | Permissões: preparar, editar e cancelar exigem a permissão nova "receber compras", dos papéis Atendimento e Gestão (D8 ampliada pelo usuário). A fila e o lançamento ficam em Automações (`operar_automacoes`, papel Gestão). Rota nova entra em `REGRAS_POR_ROTA` | D8, spec 012 |
| R19 | Entra no Central só o item com **saldo controlado por quantidade** (`TPCONTROLE_SALDO = Q`) e cujo `CADPRO` esteja no cadastro de materiais do Central, que vem só dos tipos Produtos, Peças, Lubrificantes e Pneus. Item controlado por valor (`T`), serviço e combustível ficam fora | P13, P11, F24 |

## 6. Exemplos numéricos

**Pedido P, item X, 100 un** (P1, R3, R13):

| Momento | Central | SCPI "Já Entrou" | Saldo livre |
|---|---|---|---|
| Importado | — | 0 | 100 |
| NF A, 30 conferidos | R1 Preparado (30) | 0 | 70 |
| Robô salva R1 | R1 Lançado, `003900/26` | 30 | 70 |
| NF B, 20 conferidos | R2 Preparado (20) | 30 | 50 |
| O Salvar de R2 falha | R2 Em verificação | 30 ou 50 | 50 |
| A extração posterior acha a marca ou a NF B, ou o "Já Entrou" chega a 50 | R2 Lançado com o número achado | 50 | 50 |
| A extração posterior não acha nada no intervalo e o "Já Entrou" continua 30 | R2 liberado (Preparado de novo) | 30 | 50 |

- "Total" numa terceira nota sugere **50**, e não 100 nem 70.
- Se R2 foi salvo e a resposta se perdeu, relançar os 20 **passaria no SCPI**, porque o saldo dele é 50 e os 20 cabem (F8). Só o Central (R13) impede a duplicação.

**Caso real, pedido `00361/26`** (F21): o item 29 (`016.002.147`) pediu 30, que entraram em duas notas:
- 10 na `002680/26` (NF `000000000498`, 25/08/2026);
- 20 na `003492/26` (NF `000000000501`, 19/10/2026).

A `003492/26` mostra na tela Data Requisição `05/08/2026`, que é a data do pedido (F4).

**Caso real, pedido `00514/26`** (F7, F8): de 27 itens, 7 têm saldo, e o "total" do SCPI soma `4.278,00`. No item `020.001.010` (pedido 3, já entrou 2, saldo 1), digitar 2 é **recusado**.

**Duas pessoas ao mesmo tempo:** A e B abrem o item X com saldo livre de 50 e pedem "total". A grava primeiro (trava a linha) e reserva 50. B recebe a recusa com o saldo livre atualizado (0). Nada fica reservado em dobro.

## 7. Critérios de aceitação

1. **Dado** um item com 100 pedidos, 30 já entrados no SCPI e 20 reservados num recebimento Preparado, **quando** o Atendimento prepara "total" com outra NF, **então** a quantidade sugerida é 50.
2. **Dado** saldo livre de 50, **quando** alguém informa 51, **então** o recebimento é recusado com o saldo livre na mensagem, e nada é gravado.
3. **Dado** um recebimento com a NF 501 do fornecedor 19502 que já teve uma tentativa, **quando** alguém prepara outro com a NF `000000000501` do mesmo fornecedor, **então** é recusado, mesmo que o primeiro esteja Cancelado.
4. **Dadas** duas pessoas preparando "total" do mesmo item ao mesmo tempo, **quando** as duas enviam, **então** uma grava e a outra é recusada, e a soma reservada nunca passa do saldo.
5. **Dado** um recebimento em lançamento real, **quando** o Salvar falha depois do clique, **então** ele fica Em verificação, continua reservando o saldo e não volta à fila.
6. **Dado** um recebimento Em verificação, **quando** uma extração começada depois da tentativa traz uma requisição com a marca dele ou com a NF + fornecedor dele, **então** ele é ligado a ela como Lançado e nunca é relançado.
7. **Dado** um recebimento Em verificação, **quando** a extração posterior não tem candidata no intervalo e o "Já Entrou" do item é o esperado, **então** a liberação para relançar é permitida. Sem extração posterior, ela é recusada.
8. **Dado** um recebimento na fila, **quando** a tela "Escolha os Itens" mostra um "Já Entrou" maior que o esperado, **então** o robô não clica em Salvar, o recebimento fica Com erro e o pedido fica travado.
9. **Dada** uma requisição oficial do pedido sem marca e com a NF de um recebimento Preparado, **quando** a conciliação roda, **então** o recebimento é ligado a ela ("É esta") e sai da fila.
10. **Dada** uma requisição oficial do pedido sem marca e com uma NF desconhecida, **quando** a conciliação roda, **então** ela aparece como "Lançada fora do Central", o saldo livre cai e o pedido fica travado.
11. **Dado** um recebimento Lançado, **quando** a requisição oficial tem os três vínculos iguais e o mesmo fornecedor, NF, pedido, `DATAE`, códigos e quantidades, **então** o veredito é Comprovado. Com uma quantidade diferente, o veredito é Divergente e mostra a diferença.
12. **Dado** `LANCAMENTO_REAL` desligado, **quando** se pede o lançamento real, **então** ele é recusado. A simulação preenche, cancela e não extrai.
13. **Dada** uma data de recebimento futura ou anterior à data do pedido, ou uma quantidade com 4 casas ou "1.5", **quando** se prepara o recebimento, **então** ele é recusado.
14. **Dado** um usuário sem a permissão "receber compras", **quando** ele abre a rota de preparar, **então** recebe 403. Sem `operar_automacoes`, a fila de entradas não lança.
15. **Dada** uma importação de pedidos com `QTDENT` maior que a soma das entradas conhecidas de um item, **quando** ela termina, **então** há aviso de saúde e o pedido fica travado.

## 8. Fatos observados

| # | Fato | Fonte |
|---|---|---|
| F1 | Listagem: 837 pedidos, 3.191 itens; (`ID_CADPED`, `ITEM`) é único; um fornecedor por pedido; 690 itens em SV, H, MES e M³XKM | CSV de pedidos |
| F2 | `QTDENT` = soma de `QUAN1` das entradas em **2.186 de 2.186** itens de pedidos de 2026 e em 43 de 43 dos pedidos de 2025 recriados. 156 pedidos com entrada nos dois relatórios. 197 entradas por pedido em 2026 (116 para o estoque e 81 por saída); até 15 por pedido | CSVs |
| F3 | O relatório de entradas tem as mesmas 65 colunas do de saídas, com `QUAN1`. **O período filtra por `DATAE`** (o usuário extraiu a partir de 01/10/2026). `GRUPO` = `DATAE`. `DTPAG` só aparece quando `SAID=S` | CSV, tela 07.04.01, usuário |
| F4 | Na entrada por pedido, `DTLAN` (Data Requisição) **é a data do pedido** (23 de 23 em out–nov; `003492/26` = `05/08/2026`). A data da entrada é `DATAE` | CSV, tela |
| F5 | **A numeração é a mesma das saídas.** Na faixa 3286–3866: 215 entradas, 474 saídas, 121 nos dois relatórios e 13 números sem requisição (3330–3333, 3394, 3395, 3404, 3487, 3535, 3553, 3693–3695) | CSVs |
| F6 | 1.752 NFs (`CODIF` + `DOCUM`) em 2026, **nenhuma em duas requisições nem em dois pedidos**. Toda entrada por pedido tem NF e o fornecedor do pedido. `DOCUM` tem 12 dígitos. A aba NF-e (série, chave, DANFE) existe na tela, mas não sai no relatório. `DTEMISSAONF` está sempre vazia | CSVs, tela |
| F7 | Caminho na tela: Inserir › "por pedido" › Pesquisa Pedido de Compra (número + ano) › "Escolha os Itens" (só itens com saldo, todos marcados; colunas Qtd., Já Entrou, Já Pedida, Qtd. Saldo; números do pedido) › janela de empenhos › grade com **QTD = saldo** e itens renumerados de 1 a n | tela (`00388/26`, `00514/26`) |
| F8 | **O SCPI recusa QTD acima do saldo** ("Quantidade de entrada é maior que quantidade do pedido!…"): `376` em 375 (`00388/26`) e `2` com saldo 1 (`00514/26`). Quantidade a mais só num "registro novo" | tela |
| F9 | O pedido preenche Data Requisição, Tipo `OUTRA`, fornecedor, centro, interessado e empenho, sem edição. Ficam editáveis: Data e Hora da Entrada (vem com hoje), Nota Fiscal, Observações e Recebimento | tela |
| F10 | O campo Observações existe e sai em `OBS_CABECALHO`; está vazio em 196 de 197 entradas por pedido de 2026. A pesquisa da entrada e o relatório filtram por Observação, NF e Nº Pedido | CSV, telas |
| F11 | A saída por pedido é a Requisição de Saída com "Entrada" **marcada sozinha**. Gera `SAID=S` e aparece nos dois relatórios (121 de 121) | tela, usuário, CSVs |
| F12 | **O 01.08.03 Imprimir Pedidos grava no pedido.** O Log (tabela CADPED) mostra, em 10/11/2026 às 14:50 (hora do servidor), `IPE` +1 por item e `DATEMI` de vazio para 10/11/2026 (`00388/26`, `00441/26`; o `00514/26` só no `IPE`). 774 dos 837 pedidos estavam sem Data Emissão | Log do SCPI, CSV |
| F13 | Inserir por pedido e Cancelar **não grava nada no pedido**: o Log do `00388/26` e o do `00514/26` só mostram as alterações das 14:50 | Log |
| F14 | Os pedidos de 2025 foram recriados no exercício de 2026 em 10/03/2026: mesmo `NUMPED`, `ID_CADPED` novo, `QTDENT` só do exercício | CSVs |
| F15 | Anulação parcial: o `00330/26` tem `QTDANU=2` no item 92 (em 12/08/2026) e recebeu a `003036/26` em 17/09/2026 | CSVs |
| F16 | 30 linhas de entrada por pedido com quantidade fracionária (quase todas em `T`), com até 3 casas | CSV |
| F17 | O código se repete em dois itens nos pedidos `00109/25`, `00388/26` (`004.000.003`, 1125 + 375) e `00191/25`. Nenhum deles recebeu. A tela "Escolha os Itens" mostra as duas linhas separadas | CSV, tela |
| F18 | Pedido excluído some: o `00137/26` e o `00490/26` não existem, então a listagem estava completa | tela |
| F19 | Um pedido pode ter vários empenhos (o `00514/26` tem 1250, 1251 e 1252); o primeiro vem selecionado | tela |
| F20 | Da conciliação de saídas (spec 010), reaproveitáveis: estados e ordem das gravações, foto da tentativa, extração de antes e de depois, intervalo e candidatas, vereditos, correção de vínculo, retenção. **Novo para as entradas:** o terceiro vínculo (NF), a data por `DATAE`, a conferência antes do Salvar e o `QTDENT` como segunda vista | código e testes de `conciliacao/` e `scpi/lancamento.py` |
| F21 | Exemplo real de parcial: o `00361/26`, item 29 (detalhado na seção 6) | tela, CSV |
| F23 | **O 07.13 "Relação de Pedidos (Condição da Entrega)" serve de fonte e não grava no pedido.** Gerado em 10/11/2026 às 16:33 só para o `00514/26` (Analítico, "Apenas com saldo a entregar"), o Log do pedido continuou só com as alterações das 14:50. O CSV (Dados) tem 79 colunas, uma linha por item com saldo, entre elas `NUMPED`, `DATPED`, `DATENT`, `CODIF`, `ITEM`, `CADPRO`, `UNID1`, `TPCONTROLE_SALDO`/`CONTROLE_SALDO` (`Q`, "Quantidade"), `QTD`, `QTDANU`, `QTDENT`, **`QTDFALTA`** (o saldo: 1, 1, 1, 2, 1, 1, 3, igual à "Qtd. Saldo" da tela), **`QTDPEDIDA`** (subpedido), `QTDFALTAPED`, `EMPENHO` (`1250-OR,1251-OR,1252-OR`) e `FICHA` | tela, Log, CSV |
| F24 | **O 07.13 completo** ("Apenas com saldo a entregar", Analítico) saiu em cerca de 20 s: 152 páginas, CSV de 2.878 linhas, 695 pedidos e (`NUMPED`, `ITEM`) único. São **os mesmos 2.878 itens com saldo** da listagem das 14:36, com o mesmo saldo. As exceções são 102 itens com `TPCONTROLE_SALDO = T` ("Valor Total"), em que o saldo é em valor (`QTDFALTA` 0, `PRCTOTFALTA` > 0). Nos 2.776 itens `Q`, `QTDFALTA` = `QTD` − `QTDANU` − `QTDENT` (`QTDPEDIDA` = 0 em todos). Há unidades de serviço entre eles (398 em SV, 155 em H, 78 em MES). O Log do `00388/26` continuou só com as alterações das 14:50 | CSV, Log |
| F25 | **Número faltando no relatório não prova exclusão.** Consultados no Localizar da Entrada e da Saída, com "sem saída" desmarcada, em 10/11/2026: a `003553/26` **existe**, uma entrada de combustível com data de entrada **10/12/2006** (erro de digitação) e por isso fora de qualquer período do relatório; a `003693/26` e a `003330/26` não existem em nenhuma das duas, ou seja, foram excluídas. A requisição excluída simplesmente some: não sobra registro de situação, e as telas de requisição não têm o botão Log (08. Utilitários só tem Importação/Atualização) | telas |
| F22 | Depois do Salvar, o número da entrada aparece **no mesmo lugar** que o da saída: o campo Requisição do cabeçalho, onde a `003492/26` aparece ao ser carregada. O robô de saídas já lê esse campo em `salvar_requisicao` (`scpi/lancador.py`), que também confirma o aviso de data em outro mês e trata qualquer outra mensagem como resultado incerto | usuário, tela, código |

## 9. Lacunas que ainda impedem uma spec verificável

| # | Lacuna | O que decide | Como fechar |
|---|---|---|---|
| L1 | **Fechada**: o 07.13 é a fonte (F23, F24), e a P13 foi aprovada (R19) | R15, R19 | — |
| L2 | **Fechada** (F25). Consequência: a requisição excluída some, e a requisição com data errada fica fora do período. As duas parecem iguais no relatório, então lacuna na numeração é sempre **falta de evidência**, nunca prova. Por isso a R13 exige também o "Já Entrou", que não depende da data. Fica para o plano verificar se o 07.04.01 aceita filtro só por Nº Pedido ou por Observação, sem período, como prova independente da data | R13, Não encontrado | — |
| L3 | Falta saber se abre alguma janela de impressão ou de etiquetas depois do Salvar da entrada. O lugar do número já se sabe (F22). O aviso de data em outro mês **aparece**, confirmado pelo usuário: o robô o confirma uma vez, como na saída, e qualquer outra mensagem é resultado incerto | R7, R9 | observar a próxima entrada real |
| L4 | Se o SCPI confere o saldo de novo no Salvar quando duas telas foram abertas antes | R8 | não se testa em produção; tratar como desconhecido (o Central serializa e o robô confere antes) |
| L5 | "Já Pedida" e subpedido: se a listagem traz essa quantidade, e como um subpedido aparece | R3 | CSV do L1 e um pedido com subpedido |
| L6 | A virada do exercício: quando os pedidos migram (foi em 10/03 em 2026) e o que o SCPI aceita até lá | R16 | perguntar ao setor de Compras |
| L7 | Pedido "Não empenhado" (legenda da tela): aceita entrada? | R2 | consultar um pedido assim |
| L8 | Latência entre o Salvar e o relatório (não medida, como nas saídas) | R11, Aguardando | medir na primeira simulação real |
| L9 | A constituição fala de `pedidos/servicos.py` e de `LinhaSaida`. As entradas pedem uma emenda **MINOR** que estenda os Princípios II e III ao novo domínio | conformidade do plano | PR de emenda junto com a spec |

Fora da spec, para o usuário: o efeito do 01.08.03 de 10/11/2026 (F12) talvez precise ser avisado ao setor de Compras. O Log guarda o valor antigo de cada pedido.
