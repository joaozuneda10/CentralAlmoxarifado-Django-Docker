"""Spec 015 (entrega 2): os contadores do menu (FR-013, research R7)."""

import re
from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from compras.models import Recebimento
from pedidos.models import ExecucaoRobo
from tests.cenario import criar_pedido
from tests.compras_cenario import pedido_padrao, preparar, usuario_recebedor
from tests.papeis import dar_papeis, usuario_com

pytestmark = pytest.mark.django_db

PAINEL = reverse("pedidos:painel")
AUTOMACOES = reverse("automacoes:pagina")


def contador(html, url):
    """O número do contador do item do menu que leva a `url`, ou None sem contador."""
    item = re.search(
        rf'<a class="app-menu-item" href="{re.escape(url)}"[^>]*>(.*?)</a>', html, re.S
    )
    assert item, url
    achado = re.search(
        r'<span class="app-menu-contador"><span aria-hidden="true">([0-9]+)</span>'
        r'<span class="visually-hidden">([^<]*)</span></span>',
        item.group(1),
    )
    return (int(achado.group(1)), achado.group(2)) if achado else None


def _pagina(client, url=None):
    # Uma página que não é o painel, para conferir que o contador vale em toda a área interna.
    return client.get(url or reverse("catalogo:curva")).text


def _recebimento(status, usuario=None):
    usuario = usuario or usuario_recebedor(username="88001")
    recebimento = preparar(pedido_padrao(), usuario, {1: "5"})
    Recebimento.objects.filter(pk=recebimento.pk).update(status=status)
    return recebimento


def _execucao(robo):
    return ExecucaoRobo.objects.create(robo=robo, log="10:00:01")


def test_sem_nada_pendente_nenhum_contador(client, usuario_logado):
    html = _pagina(client)
    assert contador(html, PAINEL) is None
    assert contador(html, AUTOMACOES) is None


def test_contador_do_painel_e_igual_ao_cartao_aguardando(client, usuario_logado):
    criar_pedido()
    criar_pedido()
    criar_pedido(atendido=True)
    html = _pagina(client)
    assert contador(html, PAINEL) == (2, ", 2 para atender")
    painel = client.get(PAINEL).text
    cartao = painel[painel.index('data-indicador="atendimento"') :]
    assert re.search(r'<p class="indicador-numero">\s*2\s*</p>', cartao)
    assert contador(painel, PAINEL) == (2, ", 2 para atender")


def test_contador_de_automacoes_soma_requisicoes_e_recebimentos(client, usuario_logado):
    criar_pedido(atendido=True, linhas=[("VERIFICAR", "")])
    criar_pedido(atendido=True, linhas=[("ERRO", "")])
    criar_pedido(atendido=True, linhas=[("PENDENTE", "")])  # fila, não trava
    _recebimento(Recebimento.Status.VERIFICAR)
    assert contador(_pagina(client), AUTOMACOES) == (3, ", 3 travas para conferir")


def test_contador_de_automacoes_no_singular(client, usuario_logado):
    _recebimento(Recebimento.Status.ERRO)
    assert contador(_pagina(client), AUTOMACOES) == (1, ", 1 trava para conferir")


def test_lote_com_dois_estados_conta_uma_vez(client, usuario_logado):
    criar_pedido(atendido=True, linhas=[("VERIFICAR", ""), ("EM_LANCAMENTO", "")])
    assert contador(_pagina(client), AUTOMACOES)[0] == 1


def test_em_lancamento_so_conta_sem_o_robo_daquele_tipo_rodando(client, usuario_logado):
    criar_pedido(atendido=True, linhas=[("EM_LANCAMENTO", "")])
    _recebimento(Recebimento.Status.EM_LANCAMENTO)
    # Sem execução: os dois em lançamento são travas (o robô morreu no meio).
    assert contador(_pagina(client), AUTOMACOES)[0] == 2
    # Com o robô de saídas rodando, a requisição em lançamento é ele trabalhando.
    saidas = _execucao(ExecucaoRobo.Robo.SAIDAS)
    assert contador(_pagina(client), AUTOMACOES)[0] == 1
    saidas.delete()
    # O de entradas rodando não muda as requisições, só os recebimentos.
    _execucao(ExecucaoRobo.Robo.ENTRADAS)
    assert contador(_pagina(client), AUTOMACOES)[0] == 1


def test_execucao_antiga_sem_fim_nao_conta_como_em_andamento(client, usuario_logado):
    criar_pedido(atendido=True, linhas=[("EM_LANCAMENTO", "")])
    execucao = _execucao(ExecucaoRobo.Robo.SAIDAS)
    ExecucaoRobo.objects.filter(pk=execucao.pk).update(inicio=timezone.now() - timedelta(minutes=5))
    assert contador(_pagina(client), AUTOMACOES)[0] == 1


def test_o_cartao_do_robo_continua_contando_o_em_lancamento_sempre(client, usuario_logado):
    criar_pedido(atendido=True, linhas=[("EM_LANCAMENTO", "")])
    _execucao(ExecucaoRobo.Robo.SAIDAS)
    html = client.get(PAINEL).text
    cartao = html[html.index('data-indicador="robo"') :]
    cartao = cartao[: cartao.index("</section>")]
    assert "1 para conferir" in cartao
    assert contador(html, AUTOMACOES) is None


def test_o_cartao_do_robo_nao_soma_os_recebimentos(client, usuario_logado):
    _recebimento(Recebimento.Status.VERIFICAR)
    html = client.get(PAINEL).text
    cartao = html[html.index('data-indicador="robo"') :]
    cartao = cartao[: cartao.index("</section>")]
    assert "para conferir" not in cartao
    assert contador(html, AUTOMACOES)[0] == 1


def test_contadores_so_para_quem_abre_o_item(client):
    criar_pedido()
    criar_pedido(atendido=True, linhas=[("ERRO", "")])
    client.force_login(dar_papeis(usuario_com(), "Atendimento"))
    html = _pagina(client, PAINEL)
    assert contador(html, PAINEL) == (1, ", 1 para atender")
    assert AUTOMACOES not in html  # o item nem aparece


def test_gestao_ve_so_o_de_automacoes(client):
    criar_pedido()
    criar_pedido(atendido=True, linhas=[("ERRO", "")])
    client.force_login(dar_papeis(usuario_com(), "Gestão"))
    html = _pagina(client)
    assert f'href="{PAINEL}"' not in html.split('class="app-menu"')[1].split("</nav>")[0]
    assert contador(html, AUTOMACOES)[0] == 1


def test_quem_so_recebe_compras_nao_ve_contador(client):
    criar_pedido()
    criar_pedido(atendido=True, linhas=[("ERRO", "")])
    _recebimento(Recebimento.Status.VERIFICAR)
    usuario = usuario_com(username="55001")
    usuario.user_permissions.add(Permission.objects.get(codename="receber_compras"))
    client.force_login(usuario)
    html = client.get(reverse("compras:pedidos")).text
    assert "app-menu-contador" not in html


def test_o_item_compras_usa_o_icone_do_caminhao():
    from interface.navegacao import ITENS_MENU

    compras = next(i for i in ITENS_MENU if i.rota == "compras:pedidos")
    assert compras.icone == "caminhao"


def test_o_painel_nao_conta_duas_vezes(client, usuario_logado, monkeypatch):
    """A view do painel e o menu leem as mesmas parcelas da memória da requisição: cada contagem
    roda uma vez por página."""
    from pedidos import consultas

    chamadas = []

    def espiar(nome):
        original = getattr(consultas, nome)

        def espiao(*args, **kwargs):
            chamadas.append((nome, args, tuple(sorted(kwargs.items()))))
            return original(*args, **kwargs)

        monkeypatch.setattr(consultas, nome, espiao)

    espiar("contar_aguardando")
    espiar("contar_lotes_travados")
    criar_pedido()
    criar_pedido(atendido=True, linhas=[("ERRO", "")])
    html = client.get(PAINEL).text
    assert contador(html, PAINEL)[0] == 1 and contador(html, AUTOMACOES)[0] == 1
    assert len(chamadas) == len(set(chamadas)), chamadas
    assert [c[0] for c in chamadas].count("contar_aguardando") == 1


def test_o_trecho_do_htmx_nao_conta_nada(client, usuario_logado, monkeypatch):
    from pedidos import consultas

    def proibido(*a, **k):
        raise AssertionError("o trecho do HTMX não desenha o menu")

    monkeypatch.setattr(consultas, "contar_aguardando", proibido)
    monkeypatch.setattr(consultas, "contar_lotes_travados", proibido)
    criar_pedido()
    assert client.get(PAINEL, HTTP_HX_REQUEST="true").status_code == 200
