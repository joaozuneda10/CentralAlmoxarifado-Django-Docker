"""Itens da barra lateral da área do almoxarifado.

Cada subprojeto acrescenta seus destinos a `ITENS_MENU`. A barra só espelha o que cada rota
permite (`contas.acesso.pode_abrir`, a tabela de rotas da spec 012); quem decide o acesso é a rota.
"""

from dataclasses import dataclass
from functools import cached_property

from django.urls import reverse

from contas.acesso import da_seguranca_trabalho, eh_solicitante, pode_abrir, ponto_de_partida


@dataclass(frozen=True)
class ItemMenu:
    rotulo: str
    rota: str
    icone: str = ""
    # Quem vê o item: o almoxarifado (os usuários de sempre) ou a Segurança do Trabalho (spec 008).
    para: str = "almoxarifado"


ITENS_MENU: tuple[ItemMenu, ...] = (
    ItemMenu("Painel", "pedidos:painel", "painel"),
    ItemMenu("Saída avulsa", "pedidos:avulsa", "saida"),
    ItemMenu("Automações", "automacoes:pagina", "robo"),
    ItemMenu("Compras", "compras:pedidos", "caminhao"),
    ItemMenu("Curva ABC", "catalogo:curva", "grafico"),
    ItemMenu("Formulários", "catalogo:formularios", "caixa-check"),
    ItemMenu("Cadastros", "admin:index", "cadastros"),
    ItemMenu("Autorizações", "pedidos:autorizacoes", "escudo", para="seguranca"),
)


class Contadores:
    """As parcelas dos contadores do menu e dos cartões do painel (spec 015, research R7), uma vez
    por requisição e só quando lidas: nada conta se o template não desenha o menu (os trechos do
    HTMX não desenham). As importações ficam dentro: `compras` depende de `pedidos`, e
    `interface` é só apresentação."""

    @cached_property
    def pedidos_aguardando(self) -> int:
        from pedidos import consultas

        return consultas.contar_aguardando()

    @cached_property
    def requisicoes_travadas(self) -> int:
        """Como o cartão do robô conta hoje: inclui o `EM_LANCAMENTO` sempre."""
        from pedidos import consultas

        return consultas.contar_lotes_travados()

    @cached_property
    def requisicoes_a_conferir(self) -> int:
        """As travadas, sem o `EM_LANCAMENTO` enquanto o robô de saídas roda: aí é ele trabalhando.
        A conferência da execução (`IS_USED_LOCK`) só roda com algum lote em lançamento."""
        from pedidos import consultas
        from pedidos.models import ExecucaoRobo

        if not self.requisicoes_travadas:
            return 0
        if consultas.ha_lote_em_lancamento() and (
            ExecucaoRobo.em_andamento(robo=ExecucaoRobo.Robo.SAIDAS).exists()
        ):
            return consultas.contar_lotes_travados(com_em_lancamento=False)
        return self.requisicoes_travadas

    @cached_property
    def recebimentos_a_conferir(self) -> int:
        from compras import consultas
        from pedidos.models import ExecucaoRobo

        rodando = consultas.ha_recebimento_em_lancamento() and (
            ExecucaoRobo.em_andamento(robo=ExecucaoRobo.Robo.ENTRADAS).exists()
        )
        return consultas.contar_recebimentos_travados(com_em_lancamento=not rodando)

    @property
    def travas_a_conferir(self) -> int:
        return self.requisicoes_a_conferir + self.recebimentos_a_conferir


def contadores(request) -> Contadores:
    """Os contadores desta requisição (o menu e a view do painel leem os mesmos)."""
    if not hasattr(request, "_contadores"):
        request._contadores = Contadores()
    return request._contadores


# O contador de cada item: a parcela (lida só quando o template a desenha; o template do Django
# chama o que é chamável) e o texto para o leitor de tela.
_CONTADORES = {
    "pedidos:painel": (lambda c: c.pedidos_aguardando, "atender"),
    "automacoes:pagina": (lambda c: c.travas_a_conferir, "travas"),
}


def menu(request) -> dict:
    """Context processor: `menu` para usuário autenticado; nada para anônimo."""
    usuario = getattr(request, "user", None)  # ausente se o middleware de auth não rodou
    if usuario is None or not usuario.is_authenticated:
        return {}
    correspondencia = getattr(request, "resolver_match", None)
    atual = correspondencia.view_name if correspondencia else None
    seguranca = da_seguranca_trabalho(usuario)
    memoria = contadores(request)

    def contador(rota):
        valor, tipo = _CONTADORES.get(rota, (None, ""))
        return (lambda: valor(memoria)) if valor else None, tipo

    return {
        "menu": [
            {
                "rotulo": item.rotulo,
                "url": reverse(item.rota),
                "icone": item.icone,
                "atual": item.rota == atual,
                # Só aparece para quem abre o item: a lista já é só do que a tabela de rotas abre.
                "contador": contador(item.rota)[0],
                "contador_tipo": contador(item.rota)[1],
            }
            for item in ITENS_MENU
            # A Segurança do Trabalho só vê o que é dela; os demais, o que a tabela de rotas lhes
            # abre (spec 012; "Cadastros", o admin, segue o `is_staff`).
            if (item.para == "seguranca") == seguranca
            and (seguranca or pode_abrir(usuario, item.rota))
        ],
        # A marca do menu leva ao ponto de partida de cada um: o painel, ou a fila de autorização.
        "menu_inicio": reverse(ponto_de_partida(usuario)),
        # O layout público mostra "Meus pedidos" e "Sair" ao solicitante (spec 013).
        "solicitante_logado": eh_solicitante(usuario),
    }
