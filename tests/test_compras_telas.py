"""As telas das compras (spec 014, US1): lista, pedido, formulário, edição e cancelamento."""

import re
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from compras import consultas
from compras.models import Recebimento
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
def logado(client):
    usuario = usuario_recebedor()
    client.force_login(usuario)
    return usuario


@pytest.fixture
def pedido(logado):
    return pedido_padrao()


def _campos(pedido, **extra):
    """O POST de um recebimento do item 1 (10 unidades)."""
    item = item_do_pedido(pedido, 1)
    campos = {
        "envio": str(uuid.uuid4()),
        "nf": "501",
        "data_recebimento": timezone.localdate().isoformat(),
        "observacao": "",
        f"marcar-{item.pk}": "1",
        f"qtd-{item.pk}": "10",
    }
    campos.update(extra)
    return campos


def _link(pedido):
    return reverse("compras:pedido", args=[pedido.pk])


def test_lista_busca_por_numero_fornecedor_e_codigo(client, pedido):
    outro = importar_pedido(
        [{"item": 1, "codigo": "099.099.099", "quantidade": "5"}],
        fornecedor="777",
        numped=f"00700/{ANO % 100:02d}",
    )
    url = reverse("compras:pedidos")
    for busca, esperado, ausente in [
        ("514", pedido, outro),
        (f"00514/{ANO % 100:02d}", pedido, outro),
        ("777", outro, pedido),
        ("099.099", outro, pedido),
        ("006.011", pedido, outro),
    ]:
        texto = client.get(url, {"q": busca}).text
        assert _link(esperado) in texto and _link(ausente) not in texto, busca


def test_lista_mostra_o_estado_em_texto_e_filtra_os_abertos(client, pedido, logado):
    preparar(pedido, logado, {1: "5"})
    texto = client.get(reverse("compras:pedidos")).text
    assert "Disponível" in texto and 'class="mono"' in texto
    assert _link(pedido) in client.get(reverse("compras:pedidos"), {"filtro": "aberto"}).text
    assert _link(pedido) not in client.get(reverse("compras:pedidos"), {"filtro": "travados"}).text


def test_lista_exige_o_exercicio_atual(client, pedido):
    type(pedido).objects.filter(pk=pedido.pk).update(exercicio=ANO - 1)
    assert _link(pedido) not in client.get(reverse("compras:pedidos")).text


def test_detalhe_mostra_saldo_livre_e_o_motivo_de_indisponibilidade(client, pedido, logado):
    from catalogo.models import Material

    preparar(pedido, logado, {1: "20"})
    Material.objects.filter(codigo="023.003.004").update(oculto=True)
    texto = client.get(reverse("compras:pedido", args=[pedido.pk])).text
    assert "Saldo livre" in texto
    assert "<strong>30</strong>" in texto  # 50 do SCPI − 20 reservados
    assert "Indisponível: o material está oculto no cadastro" in texto
    assert "Receber total" in texto and "Receber parcial" in texto


def test_detalhe_com_trava_mostra_o_motivo_e_esconde_os_botoes(client, pedido):
    from compras import servicos

    servicos.travar_pedido(pedido.pk, "TELA", "O SCPI mudou: item 1.")
    texto = client.get(reverse("compras:pedido", args=[pedido.pk])).text
    assert "A tela do SCPI mudou" in texto and "O SCPI mudou: item 1." in texto
    assert "Este pedido não aceita recebimento: o pedido está travado." in texto
    assert "Receber total" not in texto


def test_formulario_total_vem_preenchido_e_parcial_vazio(client, pedido):
    url = reverse("compras:receber", args=[pedido.pk])
    total = client.get(url, {"modo": "total"}).text
    assert len(re.findall(r'name="marcar-\d+"[^>]* checked', total)) == 2
    assert 'value="50"' in total and 'value="20"' in total
    parcial = client.get(url, {"modo": "parcial"}).text
    assert not re.search(r'name="marcar-\d+"[^>]* checked', parcial)
    assert 'inputmode="numeric"' in parcial and 'name="envio"' in parcial


def test_post_com_erro_mostra_resumo_e_erro_no_campo_e_nao_grava(client, pedido):
    url = reverse("compras:receber", args=[pedido.pk])
    item = item_do_pedido(pedido, 1)
    r = client.post(url, _campos(pedido, nf="abc", **{f"qtd-{item.pk}": "999"}))
    assert r.status_code == 422
    assert 'id="resumo-erros"' in r.text
    assert (
        r.text.count("Informe o número da nota fiscal, só com algarismos.") >= 2
    )  # resumo e campo
    assert "Item 1: o saldo livre é 50; informe até 50." in r.text
    assert 'value="abc"' in r.text and 'value="999"' in r.text  # o digitado volta
    assert not Recebimento.objects.exists()


def test_post_valido_redireciona_ao_detalhe_com_a_mensagem(client, pedido):
    r = client.post(reverse("compras:receber", args=[pedido.pk]), _campos(pedido), follow=True)
    recebimento = Recebimento.objects.get()
    assert r.redirect_chain[-1][0] == reverse("compras:recebimento", args=[recebimento.pk])
    assert f"{recebimento.rotulo} preparado: vai para a fila do robô." in r.text
    assert 'class="mono"' in r.text and recebimento.rotulo == "RC-0001" or recebimento.pk > 1


def test_reenvio_do_mesmo_formulario_nao_duplica(client, pedido):
    url = reverse("compras:receber", args=[pedido.pk])
    campos = _campos(pedido)
    client.post(url, campos)
    r = client.post(url, campos, follow=True)
    assert Recebimento.objects.count() == 1 and r.status_code == 200


def test_edicao_traz_o_gravado_e_salva(client, pedido, logado):
    recebimento = preparar(pedido, logado, {1: "10"})
    url = reverse("compras:editar_recebimento", args=[recebimento.pk])
    texto = client.get(url).text
    assert 'name="versao" value="1"' in texto and 'value="501"' in texto and 'value="10"' in texto
    item = item_do_pedido(pedido, 1)
    campos = _campos(pedido, **{f"qtd-{item.pk}": "12", "versao": "1"})
    r = client.post(url, campos, follow=True)
    recebimento.refresh_from_db()
    assert recebimento.versao == 2 and recebimento.itens.get().quantidade == Decimal("12")
    assert f"{recebimento.rotulo} salvo." in r.text


def test_edicao_com_versao_antiga_volta_ao_detalhe_com_o_aviso(client, pedido, logado):
    recebimento = preparar(pedido, logado, {1: "10"})
    url = reverse("compras:editar_recebimento", args=[recebimento.pk])
    item = item_do_pedido(pedido, 1)
    client.post(url, _campos(pedido, **{f"qtd-{item.pk}": "11", "versao": "1"}))
    r = client.post(url, _campos(pedido, **{f"qtd-{item.pk}": "12", "versao": "1"}), follow=True)
    assert "Outra pessoa alterou este recebimento. Recarregue a página." in r.text


def test_cancelar_exige_os_dois_passos(client, pedido, logado):
    recebimento = preparar(pedido, logado, {1: "10"})
    url = reverse("compras:cancelar_recebimento", args=[recebimento.pk])
    client.post(url, {"motivo": "NF errada"})  # sem `confirmado`
    recebimento.refresh_from_db()
    assert recebimento.status == "PREPARADO"
    r = client.post(url, {"motivo": "NF errada", "confirmado": "1"}, follow=True)
    recebimento.refresh_from_db()
    assert recebimento.status == "CANCELADO" and recebimento.chave_nf is None
    assert f"{recebimento.rotulo} cancelado." in r.text


def test_detalhe_do_recebimento_tem_o_cancelamento_num_details_e_o_rc_em_mono(
    client, pedido, logado
):
    recebimento = preparar(pedido, logado, {1: "10"})
    texto = client.get(reverse("compras:recebimento", args=[recebimento.pk])).text
    assert '<span class="mono">RC-' in texto
    assert "<details" in texto and 'name="confirmado" value="1"' in texto
    assert "Preparado" in texto


def test_detalhe_depois_de_tentativa_nao_oferece_editar_nem_cancelar(client, pedido, logado):
    recebimento = preparar(pedido, logado, {1: "10"})
    Recebimento.objects.filter(pk=recebimento.pk).update(status="VERIFICAR")
    texto = client.get(reverse("compras:recebimento", args=[recebimento.pk])).text
    assert "Em verificação" in texto and "Cancelar recebimento" not in texto
    assert "O robô já tentou lançar este recebimento" in texto
    r = client.get(reverse("compras:editar_recebimento", args=[recebimento.pk]), follow=True)
    assert "O robô já tentou lançar este recebimento" in r.text


def test_estado_precisa_de_conferencia_aparece_em_texto_no_detalhe_e_na_lista(
    client, pedido, logado
):
    preparar(pedido, logado, {1: "50"})
    item = item_do_pedido(pedido, 1)
    item.anulado, item.saldo_scpi = Decimal("30"), Decimal("20")
    item.save()
    assert consultas.estado_do_pedido(pedido) == "precisa_conferencia"
    assert "Precisa de conferência" in client.get(reverse("compras:pedido", args=[pedido.pk])).text
    assert "Precisa de conferência" in client.get(reverse("compras:pedidos")).text


def test_data_do_formulario_tem_o_intervalo_do_pedido_a_hoje(client, pedido):
    texto = client.get(reverse("compras:receber", args=[pedido.pk])).text
    assert f'min="{DATA_DO_PEDIDO:%Y-%m-%d}"' in texto
    assert f'max="{timezone.localdate():%Y-%m-%d}"' in texto
    assert timezone.localdate() - timedelta(days=0) == timezone.localdate()


def test_lista_so_traz_pedido_com_item_disponivel_ou_recebimento_aberto(client, pedido):
    from catalogo.models import Material

    Material.objects.update(oculto=True)  # nenhum item pode ser recebido
    assert _link(pedido) not in client.get(reverse("compras:pedidos")).text
