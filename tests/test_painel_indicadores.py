"""Spec 015 (entrega 2): os cartões de indicadores do painel (FR-015, FR-018b a FR-018d)."""

import re
from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from pedidos.models import AutorizacaoPedido
from pedidos.regras import EPIS, texto_envio_mais_antigo
from tests.cenario import criar_pedido

PAINEL = reverse("pedidos:painel")
LANCAMENTOS = reverse("automacoes:pagina") + "?aba=lancamento"


# --- regras.texto_envio_mais_antigo (puro) ---------------------------------------------------


@pytest.mark.parametrize(
    ("envio", "hoje", "texto"),
    [
        (date(2026, 11, 14), date(2026, 11, 14), "enviado hoje"),
        (date(2026, 11, 13), date(2026, 11, 14), "enviado ontem"),
        (date(2026, 11, 10), date(2026, 11, 14), "há 4 dias"),
        (date(2026, 10, 30), date(2026, 11, 2), "há 3 dias"),  # virada de mês
        (date(2026, 10, 31), date(2026, 11, 1), "enviado ontem"),
        (date(2025, 12, 31), date(2026, 1, 2), "há 2 dias"),  # virada de ano
    ],
)
def test_texto_envio_mais_antigo(envio, hoje, texto):
    assert texto_envio_mais_antigo(envio, hoje) == texto


# --- Cartões --------------------------------------------------------------------------------


def _pagina(client):
    return client.get(PAINEL).text


def indicador(html, nome):
    """O trecho do cartão `data-indicador="<nome>"`, até o próximo cartão ou o fim da seção."""
    inicio = html.find(f'data-indicador="{nome}"')
    if inicio < 0:
        return None
    resto = html[inicio:]
    fim = min(
        (i for i in (resto.find('data-indicador="', 1), resto.find("</section>")) if i > 0),
        default=len(resto),
    )
    return resto[:fim]


def numero(cartao):
    return re.search(r'<p class="indicador-numero">\s*([0-9]+)\s*</p>', cartao).group(1)


def _epi(situacao):
    from django.contrib.auth import get_user_model

    pedido = criar_pedido(origem=EPIS)
    decidido = situacao != "AGUARDANDO"
    quem = get_user_model().objects.get_or_create(username="70001")[0] if decidido else None
    AutorizacaoPedido.objects.create(
        pedido=pedido,
        situacao=situacao,
        decidido_por=quem,
        decidido_em=timezone.now() if decidido else None,
        motivo="Sem laudo" if situacao == "RECUSADO" else "",
    )
    return pedido


@pytest.mark.django_db
def test_os_indicadores_ficam_numa_secao_fora_do_formulario_de_filtros(client, usuario_logado):
    html = _pagina(client)
    assert '<section class="indicadores" aria-label="Resumo">' in html
    secao = html[html.index('class="indicadores"') : html.index('id="filtros-painel"')]
    assert "<form" in secao  # o do "Lançar no SCPI"
    assert html.index("</section>", html.index('class="indicadores"')) < html.index(
        'id="filtros-painel"'
    )


@pytest.mark.django_db
def test_mais_antigo_aguardando_e_o_envio_mais_velho_em_dias_de_calendario(client, usuario_logado):
    criar_pedido(criado_em=timezone.now() - timedelta(days=3))
    criar_pedido()
    cartao = indicador(_pagina(client), "atendimento")
    assert numero(cartao) == "2"
    assert "há 3 dias" in cartao


@pytest.mark.django_db
def test_mais_antigo_ignora_aguardando_autorizacao_e_recusado(client, usuario_logado):
    antigo = _epi("AGUARDANDO")
    antigo.criado_em = timezone.now() - timedelta(days=9)
    antigo.save(update_fields=["criado_em"])
    recusado = _epi("RECUSADO")
    recusado.criado_em = timezone.now() - timedelta(days=5)
    recusado.save(update_fields=["criado_em"])
    criar_pedido()
    cartao = indicador(_pagina(client), "atendimento")
    assert numero(cartao) == "1"
    assert "enviado hoje" in cartao and "dias" not in cartao


@pytest.mark.django_db
def test_sem_pedido_aguardando_o_mais_antigo_some_e_o_texto_e_o_de_hoje(client, usuario_logado):
    criar_pedido(atendido=True)
    cartao = indicador(_pagina(client), "atendimento")
    assert numero(cartao) == "0"
    assert "Nenhum pedido aguardando." in cartao
    assert "enviado" not in cartao and "há " not in cartao
    assert 'aria-disabled="true"' in cartao  # o "Atender" desabilitado, como hoje


@pytest.mark.django_db
def test_mais_n_aguardando_autorizacao_conta_so_os_aguardando(client, usuario_logado):
    _epi("AGUARDANDO")
    _epi("AGUARDANDO")
    _epi("RECUSADO")
    _epi("AUTORIZADO")
    cartao = indicador(_pagina(client), "atendimento")
    assert "+2 aguardando autorização" in cartao
    assert f'href="{PAINEL}?autorizacao=aguardando#pedidos"' in cartao
    # Não entra no número principal: ainda não podem ser atendidos.
    assert numero(cartao) == "1"  # só o autorizado


@pytest.mark.django_db
def test_sem_aguardando_autorizacao_a_nota_some(client, usuario_logado):
    _epi("AUTORIZADO")
    cartao = indicador(_pagina(client), "atendimento")
    assert "aguardando autorização" not in cartao


@pytest.mark.django_db
def test_cartoes_de_atendimento_e_recibos_levam_aos_filtros_de_hoje(client, usuario_logado):
    criar_pedido()
    criar_pedido(atendido=True)
    html = _pagina(client)
    atendimento = indicador(html, "atendimento")
    recibos = indicador(html, "recibos")
    assert f'href="{PAINEL}?situacao=aguardando#pedidos"' in atendimento
    assert "Atender" in atendimento
    assert numero(recibos) == "1"
    assert f'href="{PAINEL}?recibo=pendente#pedidos"' in recibos and "Imprimir" in recibos


@pytest.mark.django_db
def test_recibos_com_zero_tem_o_texto_de_hoje(client, usuario_logado):
    recibos = indicador(_pagina(client), "recibos")
    assert numero(recibos) == "0" and "Nenhum recibo pendente." in recibos
    assert "?recibo=pendente" not in recibos.split('class="indicador-acao"')[1]


@pytest.mark.django_db
def test_cartao_da_saude_soma_erros_e_avisos_e_leva_a_lista(client, usuario_logado):
    # Sem importação alguma, a saúde do catálogo avisa (o mesmo da lista no fim da página).
    from catalogo.saude import saude_do_catalogo

    itens = [i for i in saude_do_catalogo() if i.nivel != "ok"]
    erros = sum(1 for i in itens if i.nivel == "erro")
    avisos = sum(1 for i in itens if i.nivel == "aviso")
    html = _pagina(client)
    cartao = indicador(html, "saude")
    assert numero(cartao) == str(erros + avisos)
    assert f"{erros} {'erro' if erros == 1 else 'erros'}" in cartao
    assert f"{avisos} {'aviso' if avisos == 1 else 'avisos'}" in cartao
    assert 'href="#saude"' in cartao and "Ver avisos" in cartao
    assert ("indicador-critico" in cartao) == (erros > 0)
    assert '<section class="cartao saude-painel" id="saude">' in html


@pytest.mark.django_db
def test_cartao_do_robo_leva_a_aba_lancamento_e_mantem_o_para_conferir(client, usuario_logado):
    criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    criar_pedido(atendido=True, linhas=[("ERRO", "")])
    cartao = indicador(_pagina(client), "robo")
    assert numero(cartao) == "1"  # o número não soma as travadas (FR-018c)
    assert f'href="{LANCAMENTOS}"' in cartao  # o clique no cartão
    assert "1 para conferir" in cartao and f'href="{LANCAMENTOS}#travas"' in cartao
    assert "indicador-critico" in cartao
    assert reverse("automacoes:lancar") in cartao


@pytest.mark.django_db
def test_cartao_do_robo_com_zero_tem_o_texto_de_hoje(client, usuario_logado):
    cartao = indicador(_pagina(client), "robo")
    assert numero(cartao) == "0" and "Nada aguardando o robô." in cartao
    assert "para conferir" not in cartao and "indicador-critico" not in cartao


@pytest.mark.django_db
def test_cartao_do_robo_so_para_quem_opera_automacoes(client):
    from tests.papeis import dar_papeis, usuario_com

    client.force_login(dar_papeis(usuario_com(), "Atendimento"))
    html = _pagina(client)
    assert indicador(html, "robo") is None
    assert indicador(html, "atendimento") and indicador(html, "saude")


@pytest.mark.django_db
def test_saida_avulsa_vira_o_botao_flutuante(client, usuario_logado):
    html = _pagina(client)
    assert re.search(
        rf'<a class="fab nao-imprimir" href="{reverse("pedidos:avulsa")}">.*?Saída avulsa</a>',
        html,
        re.S,
    )
    secao = html[html.index('class="indicadores"') :]
    secao = secao[: secao.index("</section>")]
    assert reverse("pedidos:avulsa") not in secao
