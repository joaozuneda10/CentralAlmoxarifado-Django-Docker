"""A entrada por pedido feita fora do Central, o "Já Entrou" que ele não explica e o
destravamento (US5, PR 6)."""

from decimal import Decimal

import pytest
from django.core.management import call_command
from django.utils import timezone

from compras import consultas, importacao, servicos
from compras.models import EntradaForaDoCentral, IncertoConsumido, Recebimento, TravaPedido
from pedidos.models import ExecucaoRobo
from scpi import relatorios
from scpi.lancamento_entradas import executar_lancamento_entradas
from tests.compras_cenario import pedido_padrao, preparar, usuario_recebedor
from tests.scpi_entradas_simulado import SCPIEntradasSimulado

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _log_na_pasta_temporaria(journal):
    return journal


@pytest.fixture
def usuario():
    return usuario_recebedor()


@pytest.fixture
def pedido():
    return pedido_padrao()


@pytest.fixture
def scpi(pedido, monkeypatch):
    simulado = SCPIEntradasSimulado()
    simulado.pedido(
        pedido.ano, pedido.numero, {1: ("006.011.020", "100"), 2: ("023.003.004", "20")}
    )
    simulado.pedidos[(pedido.ano, pedido.numero)][1]["ja_entrou"] = Decimal("50")
    monkeypatch.setattr(relatorios, "baixar_entradas", simulado.relatorio_entradas)
    return simulado


@pytest.fixture
def com_marco(scpi, pedido):
    """A primeira extração de entradas, que fixa o marco: o que tem número até ela é história."""
    scpi.entrada_manual((pedido.ano, pedido.numero), {2: "1"}, data=timezone.localdate(), nf="111")
    scpi.pedidos[(pedido.ano, pedido.numero)][2]["ja_entrou"] = Decimal("0")  # base sem o 1
    call_command("conciliar_entradas")
    assert consultas.marco() == "003492/26"


def _livre(pedido, item):
    return {linha.numero: linha for linha in consultas.saldos_do_pedido(pedido)}[item].saldo_livre


def _importar_pedidos(scpi):
    imp = importacao.importar(scpi.relatorio_pedidos, forcar=True)
    assert imp.situacao == "SUCESSO", imp.erro
    return imp


# --- entradas feitas fora do Central ----------------------------------------------------------


def test_nf_desconhecida_vira_entrada_fora_do_central_reserva_e_trava(pedido, scpi, com_marco):
    _importar_pedidos(scpi)
    scpi.entrada_manual((pedido.ano, pedido.numero), {1: "8"}, data=timezone.localdate(), nf="900")
    livre_antes = _livre(pedido, 1)
    call_command("conciliar_entradas")
    (entrada,) = EntradaForaDoCentral.objects.all()
    assert (entrada.pedido, entrada.numero, entrada.ano) == (pedido, 3493, 2026)
    assert entrada.itens == [{"codigo": "006.011.020", "quantidade": "8"}]
    (trava,) = TravaPedido.objects.filter(motivo="FORA_DO_CENTRAL")
    assert trava.pedido == pedido and trava.aberta and "003493" in trava.detalhe
    assert _livre(pedido, 1) == livre_antes - 8  # reserva até o SCPI refletir
    assert consultas.estado_do_pedido(pedido) == "travado"


def test_a_reserva_acaba_quando_uma_importacao_posterior_reflete_a_entrada(pedido, scpi, com_marco):
    _importar_pedidos(scpi)
    scpi.entrada_manual((pedido.ano, pedido.numero), {1: "8"}, data=timezone.localdate(), nf="900")
    call_command("conciliar_entradas")
    assert _livre(pedido, 1) == 42
    _importar_pedidos(scpi)  # o SCPI já reflete o 8: o saldo do SCPI caiu para 42
    assert _livre(pedido, 1) == 42  # sem reservar duas vezes


def test_a_mesma_requisicao_em_duas_extracoes_nao_duplica(pedido, scpi, com_marco):
    scpi.entrada_manual((pedido.ano, pedido.numero), {1: "8"}, data=timezone.localdate(), nf="900")
    call_command("conciliar_entradas")
    call_command("conciliar_entradas")
    assert EntradaForaDoCentral.objects.count() == 1
    assert TravaPedido.objects.filter(motivo="FORA_DO_CENTRAL").count() == 1


def test_a_entrada_com_saida_tambem_conta(pedido, scpi, com_marco):
    scpi.entrada_manual((pedido.ano, pedido.numero), {1: "3"}, data=timezone.localdate(), nf="901")
    call_command("conciliar_entradas")
    assert EntradaForaDoCentral.objects.count() == 1


def test_a_requisicao_abaixo_do_marco_e_ignorada(pedido, scpi, com_marco):
    scpi.salvas[0].requisicao = "003490/26"  # história anterior ao marco
    call_command("conciliar_entradas")
    assert not EntradaForaDoCentral.objects.exists() and not TravaPedido.objects.exists()


def test_entrada_de_outro_pedido_ou_sem_pedido_nao_vira_nada(pedido, scpi, com_marco):
    scpi.pedido(2026, 999, {1: ("006.011.020", "100")})
    scpi.entrada_manual((2026, 999), {1: "1"}, data=timezone.localdate(), nf="902")  # não conhecido
    call_command("conciliar_entradas")
    assert not EntradaForaDoCentral.objects.exists()


@pytest.mark.parametrize("status", ["PREPARADO", "ERRO", "VERIFICAR"])
def test_a_nf_de_um_recebimento_aberto_liga_a_mao_e_sai_da_fila(
    pedido, usuario, scpi, com_marco, status
):
    r = preparar(pedido, usuario, {1: "10"}, nf="900")
    Recebimento.objects.filter(pk=r.pk).update(status=status)
    scpi.entrada_manual((pedido.ano, pedido.numero), {1: "10"}, data=timezone.localdate(), nf="900")
    call_command("conciliar_entradas")
    r.refresh_from_db()
    assert (r.status, r.via, r.requisicao_scpi) == ("LANCADO", "MANUAL", "003493/26")
    assert r.visivel_desde is not None and not EntradaForaDoCentral.objects.exists()
    assert not TravaPedido.objects.filter(motivo="FORA_DO_CENTRAL").exists()


def test_a_marca_de_um_recebimento_nao_lancado_trava_o_pedido(pedido, usuario, scpi, com_marco):
    r = preparar(pedido, usuario, {1: "10"}, nf="900")  # PREPARADO: nunca foi lançado
    scpi.entrada_manual((pedido.ano, pedido.numero), {1: "10"}, data=timezone.localdate(), nf="900")
    scpi.salvas[-1].observacoes = f"Central Almoxarifado {r.rotulo}"
    call_command("conciliar_entradas")
    (trava,) = TravaPedido.objects.filter(motivo="MARCA_SEM_LANCAMENTO")
    assert trava.pedido == pedido and r.rotulo in trava.detalhe
    r.refresh_from_db()
    assert r.status == "PREPARADO"  # nada foi ligado


def test_a_marca_sem_lancamento_nao_repete_a_trava_aberta_em_outra_conciliacao(
    pedido, usuario, scpi, com_marco
):
    r = preparar(pedido, usuario, {1: "10"}, nf="900")
    scpi.entrada_manual((pedido.ano, pedido.numero), {1: "10"}, data=timezone.localdate(), nf="900")
    scpi.salvas[-1].observacoes = f"Central Almoxarifado {r.rotulo}"
    call_command("conciliar_entradas")
    call_command("conciliar_entradas")  # outra extração lista a mesma requisição com a mesma marca
    assert TravaPedido.objects.filter(motivo="MARCA_SEM_LANCAMENTO").count() == 1


def test_a_marca_do_recebimento_lancado_pelo_robo_nao_e_entrada_de_fora(
    pedido, usuario, scpi, com_marco
):
    r = preparar(pedido, usuario, {1: "10"}, nf="900")
    execucao = ExecucaoRobo.objects.create(robo="ENTRADAS")
    executar_lancamento_entradas(
        execucao, scpi.abrir, recebimentos=[r.rotulo], extrair=scpi.relatorio_entradas
    )
    assert not EntradaForaDoCentral.objects.exists()
    assert not TravaPedido.objects.filter(
        motivo__in=["FORA_DO_CENTRAL", "MARCA_SEM_LANCAMENTO"]
    ).exists()


# --- o "Já Entrou" que o Central não explica --------------------------------------------------


def test_ja_entrou_explicado_pelo_que_o_robo_lancou_nao_trava(pedido, usuario, scpi):
    _importar_pedidos(scpi)  # a base já existe no pedido_padrao: esta é a segunda importação
    r = preparar(pedido, usuario, {1: "10"})
    execucao = ExecucaoRobo.objects.create(robo="ENTRADAS")
    executar_lancamento_entradas(
        execucao, scpi.abrir, recebimentos=[r.rotulo], extrair=scpi.relatorio_entradas
    )
    imp = _importar_pedidos(scpi)  # o SCPI subiu 10, e o robô lançou 10
    assert not TravaPedido.objects.filter(motivo="JA_ENTROU").exists()
    assert not any("travado" in a for a in imp.avisos)


def test_ja_entrou_que_sobe_sem_explicacao_trava_o_pedido_e_avisa(pedido, scpi):
    _importar_pedidos(scpi)
    scpi.pedidos[(pedido.ano, pedido.numero)][1]["ja_entrou"] += Decimal("7")  # alguém lançou à mão
    imp = _importar_pedidos(scpi)
    (trava,) = TravaPedido.objects.filter(motivo="JA_ENTROU")
    assert trava.pedido == pedido and trava.importacao == imp and "subiu 7" in trava.detalhe
    assert any("Já Entrou mudou sem o Central explicar" in a for a in imp.avisos)
    again = _importar_pedidos(scpi)  # sem mudança: não abre outra trava
    assert (
        TravaPedido.objects.filter(motivo="JA_ENTROU").count() == 1 and again.situacao == "SUCESSO"
    )


def test_ja_entrou_que_cai_trava_tambem(pedido, scpi):
    _importar_pedidos(scpi)
    scpi.pedidos[(pedido.ano, pedido.numero)][1]["ja_entrou"] -= Decimal("5")  # excluída no SCPI
    _importar_pedidos(scpi)
    assert TravaPedido.objects.filter(motivo="JA_ENTROU").count() == 1


def test_item_que_troca_de_material_com_o_mesmo_ja_entrou_trava_o_pedido(pedido, scpi):
    _importar_pedidos(scpi)
    # o SCPI corrige o material do item 1 e o "Já Entrou" continua o mesmo: o que saiu do
    # código antigo e o que entrou no novo não se anulam, são códigos diferentes
    scpi.pedidos[(pedido.ano, pedido.numero)][1]["codigo"] = "006.011.099"
    imp = _importar_pedidos(scpi)
    (trava,) = TravaPedido.objects.filter(motivo="JA_ENTROU")
    assert trava.pedido == pedido and "006.011.020" in trava.detalhe
    assert any("Já Entrou mudou sem o Central explicar" in a for a in imp.avisos)


def test_o_recebimento_incerto_explica_um_aumento_so_uma_vez(pedido, usuario, scpi):
    _importar_pedidos(scpi)
    r = preparar(pedido, usuario, {1: "10"}, nf="901")
    Recebimento.objects.filter(pk=r.pk).update(status="VERIFICAR")  # pode ter salvado ou não
    linhas = scpi.pedidos[(pedido.ano, pedido.numero)]
    linhas[1]["ja_entrou"] += Decimal("10")
    _importar_pedidos(scpi)  # o aumento de 10 é do recebimento em verificação
    assert not TravaPedido.objects.filter(motivo="JA_ENTROU").exists()
    assert IncertoConsumido.objects.filter(recebimento=r, pedido=pedido).count() == 1
    linhas[1]["ja_entrou"] += Decimal("10")  # outras 10, lançadas à mão: não há outro incerto
    imp = _importar_pedidos(scpi)
    (trava,) = TravaPedido.objects.filter(motivo="JA_ENTROU")
    assert trava.pedido == pedido and "subiu 10" in trava.detalhe
    assert any("Já Entrou mudou sem o Central explicar" in a for a in imp.avisos)


def test_as_linhas_do_mesmo_codigo_de_um_recebimento_nao_explicam_em_partes(pedido, usuario, scpi):
    linhas = scpi.pedidos[(pedido.ano, pedido.numero)]
    linhas[2]["codigo"] = linhas[1]["codigo"]  # dois itens do pedido com o mesmo material
    _importar_pedidos(scpi)
    r = preparar(pedido, usuario, {1: "4", 2: "6"}, nf="902")  # uma requisição só, de 10
    Recebimento.objects.filter(pk=r.pk).update(status="VERIFICAR")
    linhas[1]["ja_entrou"] += Decimal("4")
    _importar_pedidos(scpi)  # 4 não é soma de recebimentos: só o de 10 inteiro explicaria
    assert TravaPedido.objects.filter(motivo="JA_ENTROU").count() == 1
    assert not IncertoConsumido.objects.exists()


def test_a_primeira_importacao_do_exercicio_e_a_base_e_nao_confere():
    from tests.relacao_pedidos_compra import ItemPedidoCSV, csv_pedidos

    itens = [ItemPedidoCSV("00700/26", 1, "006.011.020", quantidade="100", ja_entrou="50")]
    imp = importacao.importar(lambda: csv_pedidos(itens))
    assert imp.situacao == "SUCESSO" and not TravaPedido.objects.exists()


# --- destravar ---------------------------------------------------------------------------------


def test_destravar_recalcula_o_saldo_depois_de_uma_importacao_posterior(pedido, usuario, scpi):
    _importar_pedidos(scpi)
    scpi.pedidos[(pedido.ano, pedido.numero)][1]["ja_entrou"] += Decimal("7")
    _importar_pedidos(scpi)
    assert consultas.estado_do_pedido(pedido) == "travado"
    assert servicos.destravar_pedido(pedido.pk, usuario, motivo="").motivo == "motivo"
    sem = servicos.destravar_pedido(pedido.pk, usuario, motivo="conferi no SCPI")
    assert not sem.ok and sem.motivo == "importacao"
    _importar_pedidos(scpi)  # a importação posterior à trava
    ok = servicos.destravar_pedido(pedido.pk, usuario, motivo="conferi no SCPI")
    assert ok.ok
    assert consultas.estado_do_pedido(pedido) == "disponivel"
    assert _livre(pedido, 1) == 43  # saldo do SCPI de agora (50 − 7), sem reservas


# --- correções da revisão ---------------------------------------------------------------------


def test_primeira_extracao_vazia_fixa_o_marco(pedido, scpi):
    """A primeira extração sem nenhuma entrada já é o marco: a entrada feita à mão depois dela é
    de fora do Central, e não história."""
    call_command("conciliar_entradas")
    assert consultas.marco() == consultas.MARCO_VAZIO
    _importar_pedidos(scpi)
    scpi.entrada_manual((pedido.ano, pedido.numero), {1: "8"}, data=timezone.localdate(), nf="900")
    call_command("conciliar_entradas")
    assert consultas.marco() == consultas.MARCO_VAZIO
    assert EntradaForaDoCentral.objects.count() == 1
    assert TravaPedido.objects.filter(motivo="FORA_DO_CENTRAL").count() == 1


def test_entrada_de_fora_sem_a_trava_nao_fica_gravada(pedido, scpi, com_marco, monkeypatch):
    """Se a trava do pedido falha, o registro da entrada também não fica: a conferência seguinte
    refaz os dois."""
    scpi.entrada_manual((pedido.ano, pedido.numero), {1: "8"}, data=timezone.localdate(), nf="900")
    original = servicos.travar_pedido

    def falha(*args, **kwargs):
        raise RuntimeError("o banco caiu")

    monkeypatch.setattr(servicos, "travar_pedido", falha)
    with pytest.raises(Exception):  # noqa: B017, PT011 (o comando sai com erro)
        call_command("conciliar_entradas")
    assert not EntradaForaDoCentral.objects.exists()
    monkeypatch.setattr(servicos, "travar_pedido", original)
    call_command("conciliar_entradas")
    assert EntradaForaDoCentral.objects.count() == 1
    assert TravaPedido.objects.filter(motivo="FORA_DO_CENTRAL").count() == 1


def test_e_esta_de_uma_entrada_ja_refletida_nao_trava_o_pedido(pedido, usuario, scpi, com_marco):
    """Salvar incerto de 10; a importação seguinte já reflete os 10; depois o "É esta" liga a
    requisição. A importação de depois não vê mudança, e o Central não a conta de novo."""
    from compras.models import CandidataEntrada

    _importar_pedidos(scpi)
    r = preparar(pedido, usuario, {1: "10"}, nf="501")
    scpi.salva_e_falha.add(r.rotulo)
    execucao = ExecucaoRobo.objects.create(robo="ENTRADAS")
    executar_lancamento_entradas(
        execucao, scpi.abrir, recebimentos=[r.rotulo], extrair=scpi.relatorio_entradas
    )
    _importar_pedidos(scpi)  # já reflete os 10
    assert not TravaPedido.objects.filter(motivo="JA_ENTROU").exists()
    candidata = CandidataEntrada.objects.filter(conferencia__recebimento=r).first()
    resposta = servicos.resolver_recebimento(
        r.pk, usuario, acao="e_esta", requisicao_id=candidata.requisicao_id
    )
    assert resposta.ok, resposta.mensagem
    _importar_pedidos(scpi)  # nada mudou no SCPI
    assert not TravaPedido.objects.filter(motivo="JA_ENTROU").exists()
