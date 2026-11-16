"""O que o solicitante vê de um pedido (spec 013, "Meus pedidos"; spec 011, consulta pública).

Cada função devolve um dicionário fechado: o template nunca recebe o `Pedido`, e por isso não tem
como mostrar o que é da equipe (quem atendeu ou decidiu, o recebedor, o centro de custo, a placa, o
tipo de saída, o SCPI, o número da requisição, os materiais acrescentados pelo almoxarifado).
Espera o pedido com `select_related("atendimento", "autorizacao")` e `prefetch_related("itens")`.
"""

from django.utils import timezone

from pedidos.fluxos import fluxo_da_origem
from pedidos.models import ItemPedido
from pedidos.regras import ConsultaPublica, texto_consulta_publica

POR_PAGINA = 20


def situacao_para_solicitante(pedido) -> ConsultaPublica:
    """O selo, a frase e o motivo da recusa: o mesmo texto da consulta pública (spec 011)."""
    autorizacao = pedido.autorizacao_ou_none
    atendimento = pedido.atendimento_ou_none
    decidido_em = autorizacao.decidido_em if autorizacao else None
    return texto_consulta_publica(
        pedido.situacao,
        autorizacao=autorizacao.situacao if autorizacao else None,
        motivo=autorizacao.motivo if autorizacao else "",
        decidido_em=timezone.localdate(decidido_em) if decidido_em else None,
        saida_em=atendimento.data_efetiva if atendimento else None,
    )


def _cabecalho(pedido) -> dict:
    return {
        "numero": pedido.numero,
        "formulario": fluxo_da_origem(pedido.origem).titulo,
        "enviado_em": timezone.localdate(pedido.criado_em),
        "consulta": situacao_para_solicitante(pedido),
    }


def linha_da_lista(pedido) -> dict:
    """Uma linha de "Meus pedidos": número, formulário, data e situação."""
    return _cabecalho(pedido)


def apresentar(pedido) -> dict:
    """A página do pedido: o cabeçalho, o que o solicitante informou e os materiais que ele pediu,
    com a quantidade entregue e a troca. O material só acrescentado pelo almoxarifado não entra;
    o que entrou no lugar de um pedido aparece só como "trocado por", pelo nome."""
    itens = list(pedido.itens.all())
    trocas = {
        i.no_lugar_de_id: i.material
        for i in itens
        if i.origem == ItemPedido.Origem.ALMOXARIFADO and i.no_lugar_de_id
    }
    atendido = pedido.atendimento_ou_none is not None
    return {
        **_cabecalho(pedido),
        "destino": pedido.destino,
        "obs": pedido.obs,
        "ocorrencia": pedido.ocorrencia,
        "atendido": atendido,
        "itens": [
            {
                "material": i.material,
                "unidade": i.unidade,
                "qtd_pedida": i.qtd_pedida,
                "qtd_entregue": i.qtd_entregue if atendido else None,
                "trocado_por": trocas.get(i.pk),
            }
            for i in itens
            if i.origem == ItemPedido.Origem.PEDIDO
        ],
    }
