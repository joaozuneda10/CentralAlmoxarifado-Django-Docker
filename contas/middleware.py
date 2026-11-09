"""Os dois filtros de acesso por rota (`contas.acesso`).

`RestringirSegurancaTrabalho` (spec 008) prende o usuário da Segurança do Trabalho às rotas da
lista dele. `ExigirPermissao` (spec 012) vem logo depois e aplica a todos os demais a tabela
`REGRAS_POR_ROTA`, negando por padrão a rota que não está nela. As views existentes não mudam: os
`login_required` e o `exige` da spec 009 continuam como segunda camada. `ExigirTrocaDeSenha` (spec
013) vem depois e prende o solicitante com a senha a trocar à página da troca.

Os dois rodam em `process_view`, quando a rota já foi resolvida (`request.resolver_match`); URL que
não resolve nem chega aqui e segue ao 404 do Django, onde não há o que proteger.
"""

from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.cache import add_never_cache_headers

from contas.acesso import (
    ADMIN,
    LOGADO,
    PUBLICA,
    ROTAS_SEGURANCA_TRABALHO,
    SEGURANCA,
    SOLICITANTE,
    Regra,
    da_seguranca_trabalho,
    eh_solicitante,
    pode,
    pode_abrir,
    ponto_de_partida,
    registrar_recusa,
    regra_da_rota,
    sem_papel,
)


class RestringirSegurancaTrabalho:
    """Nega por padrão ao grupo da Segurança do Trabalho tudo fora de `ROTAS_SEGURANCA_TRABALHO`."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not da_seguranca_trabalho(getattr(request, "user", None)):
            return None
        if request.resolver_match.view_name in ROTAS_SEGURANCA_TRABALHO:
            return None
        if request.method in ("GET", "HEAD"):
            return HttpResponseRedirect(reverse("pedidos:autorizacoes"))
        registrar_recusa(request, "grupo:Segurança do Trabalho")
        return HttpResponseForbidden("Acesso restrito às autorizações de EPIs.")


class ExigirPermissao:
    """Aplica `REGRAS_POR_ROTA` a cada rota nomeada (spec 012)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        regra = regra_da_rota(request.resolver_match.view_name)
        if regra in (PUBLICA, ADMIN, SEGURANCA):
            return None
        usuario = request.user
        if not usuario.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if regra == LOGADO:
            return None
        if regra == SOLICITANTE:
            # A equipe que abre "Meus pedidos" vai ao seu ponto de partida (spec 013, FR-024).
            return None if eh_solicitante(usuario) else redirect(ponto_de_partida(usuario))
        if isinstance(regra, Regra):
            if pode(usuario, regra):
                return None
            registrar_recusa(request, regra.falta(usuario))
            return recusa(request, regra.motivo)
        # Fora da tabela: nega por padrão, menos ao superusuário.
        if usuario.is_superuser:
            return None
        registrar_recusa(request, "rota-fora-da-tabela")
        return recusa(request, "Esta página não está liberada para o seu usuário.")


class ExigirTrocaDeSenha:
    """O solicitante com a senha a trocar (definida pelo almoxarifado) só abre a troca e o Sair
    (spec 013, FR-006). A equipe não é obrigada, mesmo com a marca ligada."""

    LIVRES = frozenset({"trocar_senha", "logout"})

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        usuario = getattr(request, "user", None)
        if not eh_solicitante(usuario) or not usuario.trocar_senha:
            return None
        if request.resolver_match.view_name in self.LIVRES:
            return None
        if request.method in ("GET", "HEAD"):
            return redirect("trocar_senha")
        return HttpResponseForbidden("Troque a senha antes de continuar.")


def recusa(request, motivo: str):
    """A página de acesso negado (403), sem cache. O solicitante a vê no layout público, com o
    caminho para "Meus pedidos"; a equipe, no layout do almoxarifado."""
    solicitante = eh_solicitante(request.user)
    resposta = TemplateResponse(
        request,
        "interface/acesso_negado_publico.html" if solicitante else "interface/acesso_negado.html",
        {
            "motivo": motivo,
            "solicitante": solicitante,
            "sem_papel": sem_papel(request.user),
            "volta_ao_painel": pode_abrir(request.user, "pedidos:painel"),
        },
        status=403,
    )
    add_never_cache_headers(resposta)
    return resposta
