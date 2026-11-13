"""O serviço dos recebimentos (`compras.servicos`): US1, cenários 1 a 8."""

import threading
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connections
from django.utils import timezone

from catalogo.models import Importacao
from compras import consultas, regras, servicos
from compras.models import ItemRecebimento, Recebimento
from pedidos.regras import qtd_br
from tests.compras_cenario import (
    ANO,
    DATA_DO_PEDIDO,
    importar_pedido,
    item_do_pedido,
    pedido_padrao,
    preparar,
    usuario_recebedor,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def usuario():
    return usuario_recebedor()


@pytest.fixture
def pedido():
    return pedido_padrao()


def _itens(pedido, **por_numero):
    """{número → quantidade} (`n1="10"`) em {id do item → quantidade}."""
    ids = {i.item: i.pk for i in pedido.itens.all()}
    return {ids[int(chave[1:])]: q for chave, q in por_numero.items()}


def _preparar_resp(pedido, usuario, nf="501", envio=None, itens=None, **kw):
    return servicos.preparar_recebimento(
        pedido.pk,
        usuario,
        envio=envio or uuid.uuid4(),
        nf=nf,
        data_recebimento=kw.pop("data", timezone.localdate()),
        observacao=kw.pop("observacao", ""),
        itens=itens if itens is not None else _itens(pedido, n1="10"),
        **kw,
    )


def _livre(pedido, numero):
    return {linha.numero: linha for linha in consultas.saldos_do_pedido(pedido)}[numero].saldo_livre


def _erros(resposta):
    return {(e.campo, e.mensagem) for e in resposta.erros}


# --- cenário 1: "total" e saldo livre ----------------------------------------------------------


def test_total_sugere_o_saldo_livre_de_cada_item_e_o_saldo_vira_reservado(pedido, usuario):
    linhas = consultas.saldos_do_pedido(pedido)
    sugestao = regras.sugestao_total(linhas)
    assert {linhas_.numero: sugestao[linhas_.item_id] for linhas_ in linhas} == {
        1: Decimal("50"),
        2: Decimal("20"),
    }
    resposta = _preparar_resp(pedido, usuario, itens={i: qtd_br(q) for i, q in sugestao.items()})
    assert resposta.ok and resposta.recebimento.status == "PREPARADO"
    assert resposta.mensagem == f"{resposta.recebimento.rotulo} preparado: vai para a fila do robô."
    assert _livre(pedido, 1) == 0 and _livre(pedido, 2) == 0


def test_o_recebimento_guarda_nf_sem_zeros_fornecedor_e_quem_preparou(pedido, usuario):
    resposta = _preparar_resp(pedido, usuario, nf="000000000501", observacao="  portaria  ")
    r = resposta.recebimento
    assert (r.nf, r.chave_nf, r.fornecedor_codigo) == ("501", "19502:501", "19502")
    assert (r.observacao, r.preparado_por, r.versao) == ("portaria", usuario, 1)
    assert r.rotulo == f"RC-{r.pk:04d}"


def test_acima_do_saldo_livre_e_recusado_e_nada_e_gravado(pedido, usuario):
    resposta = _preparar_resp(pedido, usuario, itens=_itens(pedido, n1="51"))
    assert not resposta.ok
    assert (
        f"item-{item_do_pedido(pedido, 1).pk}",
        "Item 1: o saldo livre é 50; informe até 50.",
    ) in _erros(resposta)
    assert not Recebimento.objects.exists() and not ItemRecebimento.objects.exists()


def test_parcial_reserva_so_o_que_foi_pedido(pedido, usuario):
    preparar(pedido, usuario, {1: "20"})
    assert _livre(pedido, 1) == Decimal("30") and _livre(pedido, 2) == Decimal("20")


def test_saldo_livre_100_30_20(usuario):
    pedido = importar_pedido([{"item": 1, "codigo": "006.011.020", "quantidade": "100"}])
    preparar(pedido, usuario, {1: "30"}, nf="1")
    preparar(pedido, usuario, {1: "20"}, nf="2")
    assert _livre(pedido, 1) == Decimal("50")


# --- NF única -------------------------------------------------------------------------------


def test_nf_repetida_do_mesmo_fornecedor_e_recusada_com_e_sem_zeros(pedido, usuario):
    primeiro = preparar(pedido, usuario, {1: "5"}, nf="501")
    for nf in ("501", "000501"):
        resposta = _preparar_resp(pedido, usuario, nf=nf, itens=_itens(pedido, n2="5"))
        assert not resposta.ok
        assert (
            "nf",
            f"A NF 501 deste fornecedor já está no recebimento {primeiro.rotulo}.",
        ) in _erros(resposta)


def test_a_mesma_nf_de_outro_fornecedor_vale(pedido, usuario):
    preparar(pedido, usuario, {1: "5"}, nf="501")
    outro = importar_pedido(
        [{"item": 1, "codigo": "006.011.020", "quantidade": "10"}],
        fornecedor="777",
        numped=f"00515/{ANO % 100:02d}",
    )
    assert preparar(outro, usuario, {1: "5"}, nf="501").chave_nf == "777:501"


def test_nf_de_recebimento_cancelado_sem_tentativa_fica_livre(pedido, usuario):
    primeiro = preparar(pedido, usuario, {1: "5"}, nf="501")
    assert servicos.cancelar_recebimento(primeiro.pk, usuario, motivo="NF errada").ok
    primeiro.refresh_from_db()
    assert primeiro.status == "CANCELADO" and primeiro.chave_nf is None and primeiro.nf == "501"
    assert preparar(pedido, usuario, {1: "5"}, nf="501").chave_nf == "19502:501"


def test_nf_de_cancelado_depois_de_tentativa_continua_usada(pedido, usuario):
    """Um recebimento cancelado depois de uma tentativa em verificação (criado direto no banco)
    mantém a `chave_nf`: a NF não volta a ficar livre."""
    Recebimento.objects.create(
        pedido=pedido,
        nf="501",
        fornecedor_codigo="19502",
        chave_nf="19502:501",
        data_recebimento=timezone.localdate(),
        status="CANCELADO",
        preparado_por=usuario,
    )
    resposta = _preparar_resp(pedido, usuario, nf="501")
    assert not resposta.ok and "nf" in {e.campo for e in resposta.erros}


# --- datas e quantidades ---------------------------------------------------------------------


def test_datas_fora_do_intervalo_sao_recusadas(pedido, usuario):
    hoje = timezone.localdate()
    futura = _preparar_resp(pedido, usuario, data=hoje + timedelta(days=1))
    assert ("data_recebimento", "A data do recebimento não pode ser depois de hoje.") in _erros(
        futura
    )
    antes = _preparar_resp(pedido, usuario, data=DATA_DO_PEDIDO - timedelta(days=1))
    assert any("antes da data do pedido" in m for _, m in _erros(antes))
    assert _preparar_resp(pedido, usuario, data=DATA_DO_PEDIDO).ok


@pytest.mark.parametrize("texto", ["1.5", "0", "-2", "1,2345", "abc", ""])
def test_quantidades_invalidas_sao_recusadas(pedido, usuario, texto):
    resposta = _preparar_resp(pedido, usuario, itens=_itens(pedido, n1=texto))
    assert not resposta.ok and not Recebimento.objects.exists()


def test_quantidade_fracionada_ate_tres_casas_e_aceita(pedido, usuario):
    r = preparar(pedido, usuario, {1: "1,5"})
    assert r.itens.get().quantidade == Decimal("1.500")


def test_nenhum_item_e_recusado(pedido, usuario):
    resposta = _preparar_resp(pedido, usuario, itens={})
    assert ("itens", "Marque ao menos um item.") in _erros(resposta)


def test_item_de_outro_pedido_e_recusado(pedido, usuario):
    outro = importar_pedido([{"item": 1, "codigo": "006.011.020"}], numped=f"00515/{ANO % 100:02d}")
    resposta = _preparar_resp(pedido, usuario, itens={item_do_pedido(outro, 1).pk: "1"})
    assert not resposta.ok and any("não é deste pedido" in m for _, m in _erros(resposta))


# --- edição e cancelamento ------------------------------------------------------------------


def _editar(recebimento, usuario, **kw):
    padrao = dict(
        versao=recebimento.versao,
        nf=recebimento.nf,
        data_recebimento=recebimento.data_recebimento,
        observacao=recebimento.observacao,
        itens={i.item_id: str(i.quantidade).replace(".", ",") for i in recebimento.itens.all()},
    )
    padrao.update(kw)
    return servicos.editar_recebimento(recebimento.pk, usuario, **padrao)


def test_editar_ajusta_o_saldo_e_soma_a_versao(pedido, usuario):
    r = preparar(pedido, usuario, {1: "40"})
    assert _livre(pedido, 1) == 10
    resposta = _editar(r, usuario, itens=_itens(pedido, n1="45", n2="3"))
    assert resposta.ok
    r.refresh_from_db()
    assert (r.versao, r.alterado_por) == (2, usuario)
    assert _livre(pedido, 1) == 5 and _livre(pedido, 2) == 17


def test_editar_nao_conta_a_propria_reserva(pedido, usuario):
    r = preparar(pedido, usuario, {1: "50"})
    assert _editar(r, usuario, itens=_itens(pedido, n1="50")).ok


def test_editar_com_a_versao_antiga_e_recusado(pedido, usuario):
    r = preparar(pedido, usuario, {1: "10"})
    assert _editar(r, usuario, itens=_itens(pedido, n1="11")).ok
    resposta = _editar(r, usuario, versao=1, itens=_itens(pedido, n1="12"))
    assert not resposta.ok and resposta.motivo == "versao"
    assert resposta.mensagem == servicos.MENSAGEM_VERSAO


def test_reenvio_igual_da_edicao_e_sucesso(pedido, usuario):
    r = preparar(pedido, usuario, {1: "10"})
    novos = _itens(pedido, n1="11")
    assert _editar(r, usuario, itens=novos).ok
    reenvio = _editar(r, usuario, versao=1, itens=novos)
    assert reenvio.ok and reenvio.reenvio


def test_editar_depois_de_tentativa_e_recusado(pedido, usuario):
    r = preparar(pedido, usuario, {1: "10"})
    Recebimento.objects.filter(pk=r.pk).update(status="VERIFICAR")
    r.refresh_from_db()
    resposta = _editar(r, usuario)
    assert not resposta.ok and resposta.motivo == "tentativa"
    assert resposta.mensagem == servicos.MENSAGEM_TENTATIVA


def test_cancelar_depois_de_tentativa_e_recusado(pedido, usuario):
    r = preparar(pedido, usuario, {1: "10"})
    Recebimento.objects.filter(pk=r.pk).update(status="VERIFICAR", chave_nf="19502:501")
    resposta = servicos.cancelar_recebimento(r.pk, usuario, motivo="x")
    assert not resposta.ok and resposta.motivo == "tentativa"


def test_cancelar_exige_motivo_e_libera_o_saldo(pedido, usuario):
    r = preparar(pedido, usuario, {1: "50"})
    assert servicos.cancelar_recebimento(r.pk, usuario, motivo="  ").motivo == "motivo"
    assert servicos.cancelar_recebimento(r.pk, usuario, motivo="NF devolvida").ok
    assert _livre(pedido, 1) == 50


def test_editar_um_erro_o_devolve_a_fila(pedido, usuario):
    r = preparar(pedido, usuario, {1: "10"})
    Recebimento.objects.filter(pk=r.pk).update(status="ERRO", mensagem="falha")
    r.refresh_from_db()
    assert _editar(r, usuario).ok
    r.refresh_from_db()
    assert (r.status, r.mensagem) == ("PREPARADO", "")


# --- reenvio com o mesmo `envio` ------------------------------------------------------------


def test_reenvio_de_recebimento_cancelado_nao_informa_sucesso(pedido, usuario):
    envio = uuid.uuid4()
    primeiro = _preparar_resp(pedido, usuario, envio=envio)
    assert servicos.cancelar_recebimento(primeiro.recebimento.pk, usuario, motivo="NF devolvida").ok
    segundo = _preparar_resp(pedido, usuario, envio=envio)
    assert not segundo.ok and segundo.motivo == "cancelado"
    assert "foi cancelado" in segundo.mensagem and segundo.recebimento == primeiro.recebimento
    assert Recebimento.objects.count() == 1 and _livre(pedido, 1) == 50


def test_reenvio_igual_devolve_o_mesmo_recebimento(pedido, usuario):
    envio = uuid.uuid4()
    primeiro = _preparar_resp(pedido, usuario, envio=envio)
    segundo = _preparar_resp(pedido, usuario, envio=envio)
    assert segundo.ok and segundo.reenvio and segundo.recebimento == primeiro.recebimento
    assert Recebimento.objects.count() == 1 and _livre(pedido, 1) == 40


def test_reenvio_diferente_e_divergente(pedido, usuario):
    envio = uuid.uuid4()
    primeiro = _preparar_resp(pedido, usuario, envio=envio)
    segundo = _preparar_resp(pedido, usuario, envio=envio, itens=_itens(pedido, n1="11"))
    assert not segundo.ok and segundo.divergente
    assert segundo.mensagem == (
        "Este recebimento já foi gravado com outros dados. "
        f"Abra o {primeiro.recebimento.rotulo} para conferir."
    )
    assert Recebimento.objects.count() == 1


# --- pedido que não aceita recebimento ------------------------------------------------------


def test_pedido_travado_recusa(pedido, usuario):
    servicos.travar_pedido(pedido.pk, "TELA", "o SCPI mudou")
    resposta = _preparar_resp(pedido, usuario)
    assert ("pedido", "Este pedido não aceita recebimento: o pedido está travado.") in _erros(
        resposta
    )


def test_pedido_ausente_e_de_outro_exercicio_recusam(pedido, usuario):
    imp = Importacao.objects.create(tipo="PEDIDOS_COMPRA")
    type(pedido).objects.filter(pk=pedido.pk).update(ausente_desde=imp)
    pedido.refresh_from_db()
    assert any("não veio" in m for _, m in _erros(_preparar_resp(pedido, usuario)))
    type(pedido).objects.filter(pk=pedido.pk).update(ausente_desde=None, exercicio=ANO - 1)
    pedido.refresh_from_db()
    assert any("outro exercício" in m for _, m in _erros(_preparar_resp(pedido, usuario)))


def test_anulacao_depois_do_preparado_pede_conferencia_e_zera_o_saldo_livre(pedido, usuario):
    preparar(pedido, usuario, {1: "50"})
    # O SCPI anulou 30: o saldo caiu para 20, e o reservado (50) passou dele.
    item = item_do_pedido(pedido, 1)
    item.anulado, item.saldo_scpi = Decimal("30"), Decimal("20")
    item.save()
    assert consultas.estado_do_pedido(pedido) == "precisa_conferencia"
    assert _livre(pedido, 1) == 0
    assert not _preparar_resp(pedido, usuario, nf="9", itens=_itens(pedido, n1="1")).ok


def test_item_indisponivel_e_recusado_com_o_motivo(pedido, usuario):
    from catalogo.models import Material

    Material.objects.filter(codigo="006.011.020").update(oculto=True)
    resposta = _preparar_resp(pedido, usuario)
    assert any("oculto" in m for _, m in _erros(resposta))


# --- destravar ----------------------------------------------------------------------------


def test_destravar_exige_motivo_e_importacao_posterior(pedido, usuario):
    servicos.travar_pedido(pedido.pk, "TELA", "o SCPI mudou")
    assert servicos.destravar_pedido(pedido.pk, usuario, motivo="").motivo == "motivo"
    antes = servicos.destravar_pedido(pedido.pk, usuario, motivo="conferi no SCPI")
    assert not antes.ok and antes.motivo == "importacao"
    assert "antes da trava" in antes.mensagem
    importar_pedido([{"item": 1, "codigo": "006.011.020"}])  # uma importação depois da trava
    depois = servicos.destravar_pedido(pedido.pk, usuario, motivo="conferi no SCPI")
    assert depois.ok and not consultas.travas_abertas(pedido)


# --- concorrência (cenário 7) -----------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_duas_pessoas_ao_mesmo_tempo_nunca_reservam_mais_que_o_saldo():
    usuario = usuario_recebedor()
    pedido = pedido_padrao()
    item_id = item_do_pedido(pedido, 1).pk
    largada = threading.Barrier(2)
    respostas = []

    def tentar(nf):
        try:
            largada.wait()
            respostas.append(
                servicos.preparar_recebimento(
                    pedido.pk,
                    usuario,
                    envio=uuid.uuid4(),
                    nf=nf,
                    data_recebimento=timezone.localdate(),
                    itens={item_id: "50"},
                )
            )
        finally:
            connections.close_all()

    threads = [threading.Thread(target=tentar, args=(nf,)) for nf in ("1", "2")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(r.ok for r in respostas) == [False, True]
    recusa = next(r for r in respostas if not r.ok)
    assert any("o saldo livre é 0" in e.mensagem for e in recusa.erros)
    reservado = sum(i.quantidade for i in ItemRecebimento.objects.all())
    assert reservado <= item_do_pedido(pedido, 1).saldo_scpi


# --- a importação de outro exercício não libera a reserva ---------------------------------------


def _lancado_visivel_agora(pedido, usuario):
    """Lançado e visível no SCPI depois da importação que criou o pedido: só uma importação
    começada daqui em diante o libera."""
    r = preparar(pedido, usuario, {1: "10"})
    Recebimento.objects.filter(pk=r.pk).update(
        status="LANCADO",
        requisicao_scpi="000123/26",
        visivel_desde=timezone.now(),
    )
    return r


def test_importacao_de_outro_exercicio_nao_libera_a_reserva_do_lancado(pedido, usuario):
    _lancado_visivel_agora(pedido, usuario)
    Importacao.objects.create(
        tipo=Importacao.Tipo.PEDIDOS_COMPRA,
        situacao=Importacao.Situacao.SUCESSO,
        exercicio=ANO - 1,
    )
    assert _livre(pedido, 1) == 40


def test_importacao_do_mesmo_exercicio_libera_a_reserva_do_lancado(pedido, usuario):
    _lancado_visivel_agora(pedido, usuario)
    Importacao.objects.create(
        tipo=Importacao.Tipo.PEDIDOS_COMPRA, situacao=Importacao.Situacao.SUCESSO, exercicio=ANO
    )
    assert _livre(pedido, 1) == 50


def test_importacao_sem_exercicio_registrado_vale_para_qualquer_um(pedido, usuario):
    _lancado_visivel_agora(pedido, usuario)
    Importacao.objects.create(
        tipo=Importacao.Tipo.PEDIDOS_COMPRA, situacao=Importacao.Situacao.SUCESSO
    )
    assert _livre(pedido, 1) == 50


# --- "teve tentativa" pela tentativa do robô (PR 4) ----------------------------------------


def _tentativa(r, resultado):
    from compras.models import TentativaEntrada
    from pedidos.models import ExecucaoRobo

    execucao = ExecucaoRobo.objects.create(robo="ENTRADAS")
    return TentativaEntrada.objects.create(
        execucao=execucao, ordem=1, recebimento=r, versao=r.versao, resultado=resultado
    )


@pytest.mark.parametrize("resultado", ["LANCADA", "VERIFICAR"])
def test_tentativa_lancada_ou_a_verificar_trava_a_edicao_e_o_cancelamento(
    pedido, usuario, resultado
):
    r = preparar(pedido, usuario, {1: "10"})
    _tentativa(r, resultado)
    assert servicos.tem_tentativa(r)
    assert _editar(r, usuario).motivo == "tentativa"
    assert servicos.cancelar_recebimento(r.pk, usuario, motivo="x").motivo == "tentativa"


@pytest.mark.parametrize("resultado", ["ERRO", "IGNORADA"])
def test_tentativa_que_nao_passou_pelo_salvar_nao_conta(pedido, usuario, resultado):
    r = preparar(pedido, usuario, {1: "10"})
    _tentativa(r, resultado)
    assert not servicos.tem_tentativa(r)
    assert servicos.cancelar_recebimento(r.pk, usuario, motivo="NF devolvida").ok
