"""Importação dos pedidos de compra (07.13, spec 014): grava os pedidos e os itens do SCPI.

Nada é apagado: o pedido e o item que somem do relatório ficam com `ausente_desde`, e o que volta
a aparecer o limpa (FR-005, Princípio IV). A gravação roda dentro da transação que a
`scpi.execucao.executar` abre; um `ErroImportacao` desfaz tudo.
"""

from collections.abc import Callable
from decimal import Decimal

from django.utils import timezone

from catalogo.models import Importacao
from compras.models import ItemPedidoCompra, PedidoCompra
from compras.regras import rotulo_pedido, subconjunto_que_explica
from pedidos.regras import norm_u
from scpi.execucao import Resultado, executar
from scpi.leitura import ErroImportacao, LinhaPedidoCompra, NadaAExibir, ler_pedidos_compra

# Fração máxima dos itens presentes na importação anterior que pode sumir de uma vez; acima disso o
# relatório provavelmente veio cortado e a importação aborta (salvo `forcar`), como o cadastro.
LIMITE_SUMIDOS = 0.2
# O 07.13 só traz itens com saldo: o item recebido por completo some do relatório, e isso é o fluxo
# normal. Com poucos itens presentes, uma fração alta é só um dia comum; o corte só vale a partir
# deste número de itens sumidos.
MINIMO_SUMIDOS = 10
LOTE = 1000

CAMPOS_ITEM = (
    "codigo",
    "unidade",
    "controle",
    "quantidade",
    "anulado",
    "ja_entrou",
    "ja_entrou_anterior",
    "pedida",
    "saldo_scpi",
    "preco",
    "ausente_desde",
)
CAMPOS_PEDIDO = ("data", "fornecedor_codigo", "fornecedor_nome", "atualizado_por", "ausente_desde")


def _max(modelo, campo: str) -> int:
    return modelo._meta.get_field(campo).max_length


def _exigir_que_cabe(texto: str, limite: int, descricao: str) -> str:
    """Identificador (código de fornecedor ou de material) nunca é cortado: dois identificadores
    diferentes passariam a ter o mesmo valor gravado."""
    if len(texto) > limite:
        raise ErroImportacao(
            f"Pedidos de compra: {descricao} '{texto}' passa de {limite} caracteres; "
            "nada foi gravado."
        )
    return texto


def _cortar(texto: str, limite: int, descricao: str, avisos: list[str]) -> str:
    if len(texto) > limite:
        avisos.append(f"Texto cortado em {descricao} ({limite} caracteres): {texto[:30]}…")
        return texto[:limite]
    return texto


def gravar(
    linhas: list[LinhaPedidoCompra],
    importacao: Importacao,
    *,
    exercicio: int,
    forcar: bool = False,
) -> Resultado:
    """Cria os pedidos e itens novos, atualiza os presentes (guardando o `ja_entrou_anterior`) e
    marca `ausente_desde` nos que sumiram. Só mexe nos pedidos do `exercicio`. Sem linhas (o SCPI
    confirmou que nenhum pedido tem saldo), todos os presentes sumiram e o corte se aplica."""
    avisos: list[str] = []
    for linha in linhas:
        if linha.data.year > exercicio or linha.ano > exercicio:
            raise ErroImportacao(
                f"Pedidos de compra: o pedido {rotulo_pedido(linha.ano, linha.numero)} é de "
                f"{linha.data:%d/%m/%Y}, depois do exercício {exercicio}; confira o arquivo. "
                "Nada foi gravado."
            )
    existentes = {(p.ano, p.numero): p for p in PedidoCompra.objects.filter(exercicio=exercicio)}
    itens_antes = {
        (i.pedido_id, i.item): i
        for i in ItemPedidoCompra.objects.filter(pedido__exercicio=exercicio)
    }
    chaves_novas = {(linha.ano, linha.numero, linha.item) for linha in linhas}
    presentes_antes = [i for i in itens_antes.values() if i.ausente_desde_id is None]
    mapa_pedido = {p.pk: (p.ano, p.numero) for p in existentes.values()}
    sumiram = [
        i for i in presentes_antes if (*mapa_pedido[i.pedido_id], i.item) not in chaves_novas
    ]
    corte = len(sumiram) >= MINIMO_SUMIDOS and len(sumiram) > LIMITE_SUMIDOS * len(presentes_antes)
    if corte and not forcar:
        raise ErroImportacao(
            f"Pedidos de compra: o relatório não traz {len(sumiram)} dos {len(presentes_antes)} "
            "itens presentes na importação anterior (mais de 20%). Nada foi alterado; confira "
            "o relatório do SCPI ou rode com --forcar."
        )

    # Pedidos: um por (ano, número), com os dados do primeiro item (a leitura já garantiu um só
    # fornecedor por pedido).
    por_pedido: dict[tuple[int, int], LinhaPedidoCompra] = {}
    for linha in linhas:
        por_pedido.setdefault((linha.ano, linha.numero), linha)
    criar_pedidos, atualizar_pedidos = [], []
    for chave_pedido, linha in por_pedido.items():
        valores = {
            "data": linha.data,
            "fornecedor_codigo": _exigir_que_cabe(
                linha.fornecedor_codigo,
                _max(PedidoCompra, "fornecedor_codigo"),
                "o código do fornecedor",
            ),
            "fornecedor_nome": _cortar(
                linha.fornecedor_nome,
                _max(PedidoCompra, "fornecedor_nome"),
                "o nome do fornecedor",
                avisos,
            ),
            "atualizado_por": importacao,
            "ausente_desde": None,
        }
        pedido = existentes.get(chave_pedido)
        if pedido is None:
            criar_pedidos.append(
                PedidoCompra(
                    exercicio=exercicio, ano=chave_pedido[0], numero=chave_pedido[1], **valores
                )
            )
        else:
            for campo, valor in valores.items():
                setattr(pedido, campo, valor)
            atualizar_pedidos.append(pedido)
    PedidoCompra.objects.bulk_create(criar_pedidos, batch_size=LOTE)
    PedidoCompra.objects.bulk_update(atualizar_pedidos, CAMPOS_PEDIDO, batch_size=LOTE)
    pedidos = {(p.ano, p.numero): p for p in PedidoCompra.objects.filter(exercicio=exercicio)}

    # Pedidos ausentes: presentes antes (sem `ausente_desde`) e fora do relatório.
    ausentes = [
        p for k, p in existentes.items() if p.ausente_desde_id is None and k not in por_pedido
    ]
    PedidoCompra.objects.filter(pk__in=[p.pk for p in ausentes]).update(ausente_desde=importacao)

    # Itens.
    deltas: dict[tuple[int, str], Decimal] = {}
    criar_itens, atualizar_itens = [], []
    for linha in linhas:
        pedido = pedidos[(linha.ano, linha.numero)]
        valores = {
            "codigo": _exigir_que_cabe(
                linha.codigo, _max(ItemPedidoCompra, "codigo"), "o código do material"
            ),
            "unidade": _cortar(
                linha.unidade, _max(ItemPedidoCompra, "unidade"), "a unidade", avisos
            ),
            "controle": linha.controle,
            "quantidade": linha.quantidade,
            "anulado": linha.anulado,
            "ja_entrou": linha.ja_entrou,
            "pedida": linha.pedida,
            "saldo_scpi": linha.saldo,
            "preco": linha.preco,
            "ausente_desde": None,
        }
        antes = itens_antes.get((pedido.pk, linha.item))
        if antes is None:
            criar_itens.append(
                ItemPedidoCompra(pedido=pedido, item=linha.item, ja_entrou_anterior=None, **valores)
            )
        else:
            valores["ja_entrou_anterior"] = antes.ja_entrou
            if antes.ausente_desde_id is None:  # presente nesta importação e na anterior
                codigo_antes, codigo_agora = norm_u(antes.codigo), norm_u(linha.codigo)
                # O "Já Entrou" se compara por (pedido, código). Se o SCPI trocou o material do
                # item, o que saiu do código antigo e o que entrou no novo são variações de
                # códigos diferentes: a queda no antigo é delta negativo e trava.
                if codigo_antes == codigo_agora:
                    variacoes = [(codigo_agora, linha.ja_entrou - antes.ja_entrou)]
                else:
                    variacoes = [(codigo_antes, -antes.ja_entrou), (codigo_agora, linha.ja_entrou)]
                for codigo, variacao in variacoes:
                    chave_delta = (pedido.pk, codigo)
                    deltas[chave_delta] = deltas.get(chave_delta, Decimal(0)) + variacao
            for campo, valor in valores.items():
                setattr(antes, campo, valor)
            atualizar_itens.append(antes)
    ItemPedidoCompra.objects.bulk_create(criar_itens, batch_size=LOTE)
    ItemPedidoCompra.objects.bulk_update(atualizar_itens, CAMPOS_ITEM, batch_size=LOTE)
    ItemPedidoCompra.objects.filter(pk__in=[i.pk for i in sumiram]).update(ausente_desde=importacao)

    _explicar_ja_entrou(importacao, exercicio, deltas, avisos)
    if sumiram or ausentes:
        avisos.append(
            f"{len(sumiram)} {'item' if len(sumiram) == 1 else 'itens'} e "
            f"{len(ausentes)} {'pedido' if len(ausentes) == 1 else 'pedidos'} não vieram no "
            "relatório e ficaram como ausentes (nada foi apagado)."
        )
    return Resultado(len(linhas), avisos)


def _explicar_ja_entrou(importacao, exercicio, deltas, avisos: list[str]) -> None:
    """O "Já Entrou" que o Central não explica trava o pedido (R19, FR-029).

    Por (pedido, código), o aumento do `QTDENT` entre esta importação e a anterior é explicado pelos
    recebimentos lançados pelo robô entre as duas (os certos) e, de modo opcional, por algum
    subconjunto dos que têm hora incerta: em verificação, ligados à mão e entradas fora do Central.
    Cada incerto explica um aumento uma vez só (`IncertoConsumido`), senão um único recebimento em
    verificação absolveria aumentos sucessivos feitos à mão.
    Sem explicação (ou com o delta negativo, de entrada excluída ou corrigida no SCPI), o pedido é
    travado com o motivo `JA_ENTROU` e um aviso vai para o resultado. A primeira importação do
    exercício é a base e não confere nada."""
    from compras.models import (
        EntradaForaDoCentral,
        IncertoConsumido,
        ItemRecebimento,
        Recebimento,
        TravaPedido,
    )
    from compras.servicos import travar_pedido

    anterior = (
        Importacao.objects.filter(
            tipo=Importacao.Tipo.PEDIDOS_COMPRA,
            situacao=Importacao.Situacao.SUCESSO,
            exercicio=exercicio,
        )
        .exclude(pk=importacao.pk)
        .order_by("-inicio")
        .first()
    )
    if anterior is None or not deltas:
        return
    inicio_antes, inicio_agora = anterior.inicio, importacao.inicio
    por_pedido: dict[int, list[str]] = {}
    for (pedido_id, codigo), delta in deltas.items():
        certos = Decimal(0)
        # Cada recebimento (e cada entrada de fora) é uma requisição só: entra ou não entra
        # inteiro no subconjunto, então as linhas do mesmo código somam antes de enumerar.
        por_origem: dict[tuple[str, int], Decimal] = {}
        for linha in ItemRecebimento.objects.filter(
            recebimento__pedido_id=pedido_id
        ).select_related("recebimento", "item"):
            if norm_u(linha.item.codigo) != codigo:
                continue
            r = linha.recebimento
            lancado = r.status == Recebimento.Status.LANCADO
            # Hora certa: o robô salvou e gravou o número na hora (`visivel_desde` é o próprio
            # `lancado_em`). O ligado pelo "É esta" também tem `via=ROBO`, mas o `lancado_em` dele
            # é o da resolução, e a entrada pode já estar refletida numa importação anterior.
            certo = lancado and r.via == Recebimento.Via.ROBO and r.visivel_desde == r.lancado_em
            if certo and r.lancado_em and inicio_antes <= r.lancado_em < inicio_agora:
                certos += linha.quantidade
            elif r.status == Recebimento.Status.VERIFICAR or (
                lancado
                and not certo
                and (
                    (r.visivel_desde and r.visivel_desde >= inicio_antes)
                    or (r.lancado_em and r.lancado_em >= inicio_antes)
                )
            ):
                chave = ("recebimento", r.pk)
                por_origem[chave] = por_origem.get(chave, Decimal(0)) + linha.quantidade
        for entrada in EntradaForaDoCentral.objects.filter(
            pedido_id=pedido_id, visivel_desde__gte=inicio_antes
        ):
            quantidade = sum(
                (
                    Decimal(str(i["quantidade"]))
                    for i in entrada.itens
                    if norm_u(i["codigo"]) == codigo
                ),
                Decimal(0),
            )
            if quantidade:
                por_origem[("entrada", entrada.pk)] = quantidade
        # O incerto que já explicou um aumento deste código não explica outro (R19).
        consumidos = IncertoConsumido.objects.filter(pedido_id=pedido_id, codigo=codigo)
        ja_usados = {("recebimento", c.recebimento_id) for c in consumidos if c.recebimento_id} | {
            ("entrada", c.entrada_id) for c in consumidos if c.entrada_id
        }
        origens = sorted(k for k in por_origem if k not in ja_usados)
        usados = subconjunto_que_explica(delta, certos, [por_origem[k] for k in origens])
        if usados is not None:
            IncertoConsumido.objects.bulk_create(
                IncertoConsumido(
                    pedido_id=pedido_id,
                    codigo=codigo,
                    recebimento_id=origens[i][1] if origens[i][0] == "recebimento" else None,
                    entrada_id=origens[i][1] if origens[i][0] == "entrada" else None,
                    importacao=importacao,
                )
                for i in usados
            )
            continue
        por_pedido.setdefault(pedido_id, []).append(
            f"{codigo}: o Já Entrou subiu {format(delta.normalize(), 'f')} e o Central explica "
            f"{format(certos.normalize(), 'f')}"
        )
    for pedido_id, detalhes in por_pedido.items():
        pedido = PedidoCompra.objects.get(pk=pedido_id)
        if TravaPedido.objects.filter(
            pedido_id=pedido_id, motivo=TravaPedido.Motivo.JA_ENTROU, destravada_em__isnull=True
        ).exists():
            continue
        travar_pedido(
            pedido_id,
            TravaPedido.Motivo.JA_ENTROU,
            "; ".join(detalhes),
            importacao=importacao,
        )
        avisos.append(f"Pedido {pedido.rotulo} travado: o Já Entrou mudou sem o Central explicar.")


def importar(
    obter_csv: Callable[[], bytes],
    *,
    forcar: bool = False,
    exercicio: int | None = None,
    de_arquivo: bool = False,
) -> Importacao:
    """Baixa (ou lê) o relatório e o grava numa `Importacao` do tipo `PEDIDOS_COMPRA`, com a trava
    do tipo.

    O exercício é o ano corrente, tomado uma vez aqui: o login do SCPI abre a sessão no ano de
    hoje, e se o ano virar no meio da importação ela é recusada, para não gravar um exercício no
    outro. Com `exercicio` explícito (CSV de outro ano, que o comando só aceita com `--arquivo`),
    nada disso se confere. O aviso "Nada a exibir" do SCPI é um relatório vazio confirmado: nenhum
    pedido tem saldo, e o que estava presente some, sob o mesmo corte.

    `de_arquivo` marca a importação de um CSV já baixado: não se sabe quando ele foi exportado,
    e ela não serve de prova do "Já Entrou" de depois de uma tentativa (`consultas.liberacao`)."""
    automatico = exercicio is None
    exercicio = timezone.localdate().year if automatico else exercicio
    criada: list[Importacao] = []
    vazio: list[bool] = []

    def registrar(importacao: Importacao) -> None:
        importacao.exercicio = exercicio
        importacao.de_arquivo = de_arquivo
        importacao.save(update_fields=["exercicio", "de_arquivo"])
        criada.append(importacao)

    def obter() -> bytes:
        try:
            conteudo = obter_csv()
        except NadaAExibir:
            vazio.append(True)
            conteudo = b""
        if automatico and timezone.localdate().year != exercicio:
            raise ErroImportacao(
                "Pedidos de compra: o ano virou durante a importação; rode de novo para o novo "
                "exercício. Nada foi gravado."
            )
        return conteudo

    def gravar_csv(conteudo: bytes) -> Resultado:
        linhas = [] if vazio else ler_pedidos_compra(conteudo).linhas
        return gravar(linhas, criada[0], exercicio=exercicio, forcar=forcar)

    return executar(Importacao.Tipo.PEDIDOS_COMPRA, obter, gravar_csv, ao_criar=registrar)
