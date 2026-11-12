"""Lançamento das entradas no SCPI sobre o banco: trava, um recebimento por requisição e o
resultado (spec 014, PR 4).

Paralelo a `scpi/lancamento.py`, que continua igual. A garantia é nunca lançar um recebimento duas
vezes, e ela vem da ordem das gravações (Princípio III), a mesma das saídas:
- `EM_LANCAMENTO` é confirmado no banco (transação fechada) antes do clique em Salvar, e só se o
  recebimento ainda está `PREPARADO`, na mesma versão, com o pedido sem trava;
- a tela do SCPI é conferida antes (`compras.regras.conferir_tela`): se o "Já Entrou" ou o saldo
  mudaram, o recebimento vai a `ERRO`, o pedido é travado e nada é salvo;
- qualquer falha depois do clique vira `VERIFICAR`, nunca `PREPARADO` nem `ERRO`;
- o número da requisição vai para o journal antes de ir para o banco. Se o banco não aceitar o
  resultado, a execução para (`FalhaCritica`) e o recebimento fica travado para conferência.

A navegação no SCPI fica atrás do protocolo `SCPIEntradas` (Playwright em
`scpi/lancador_entradas.py`, simulado nos testes).
"""

import json
import logging
from collections.abc import Callable, Collection
from contextlib import AbstractContextManager
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

from django.conf import settings
from django.db import Error, transaction
from django.utils import timezone

from catalogo.models import Importacao, trava_importacao
from compras import regras, robo
from compras.models import PedidoCompra, Recebimento, TentativaEntrada, TravaPedido
from compras.robo import Extrair
from compras.servicos import travar_pedido
from pedidos.models import TRAVA_LANCAMENTO, ExecucaoRobo
from scpi.execucao import PREFIXO_FALHA_INESPERADA, trava
from scpi.lancamento import (
    LancamentoEmAndamento,
    RegistroNaExecucao,
    Resumo,
    _encerrar,
    _encerrar_com_falha,
    _salvar_progresso,
    _salvar_resumo,
)
from scpi.leitura import ErroImportacao
from scpi.requisicoes import FalhaCritica

logger = logging.getLogger("scpi.lancamento_entradas")

# Último recurso se o banco cair entre o Salvar e a gravação do número: uma linha JSON por
# acontecimento, em `settings.LOG_DIR`.
JOURNAL = "lancar_entradas_journal.jsonl"

MENSAGEM_MUDOU = "O recebimento mudou durante a execução: não foi lançado."
MENSAGEM_LANCAMENTO = "Outro lançamento já está em andamento."
MENSAGEM_IMPORTACAO = "A importação de pedidos está em andamento."


class ImportacaoDePedidosEmAndamento(LancamentoEmAndamento):
    """A importação de pedidos de compra está rodando (trava do tipo ocupada)."""


class SCPIEntradas(Protocol):
    def abrir_pedido(self, rec: regras.RecebimentoParaLancar) -> regras.TelaItens:
        """Abre o pedido no SCPI e lê "Escolha os Itens". Levanta `ErroSCPI` (nada foi salvo)."""

    def preencher(self, rec: regras.RecebimentoParaLancar) -> None:
        """Desmarca os itens fora do recebimento, preenche a grade, a data, a NF e as
        Observações e confere tudo na tela. Levanta `ErroSCPI` (nada foi salvo)."""

    def salvar(self) -> str:
        """Clica em Salvar e devolve o nº da requisição. Levanta `ResultadoIncerto`."""

    def depois_de_salvar(self) -> None:
        """Volta ao formulário vazio depois de uma entrada salva."""

    def encerrar_simulacao(self) -> None:
        """Cancela o formulário preenchido, sem salvar."""

    def descartar(self, rec: regras.RecebimentoParaLancar) -> None:
        """Depois de `ErroSCPI`: print da tela e volta ao estado limpo."""

    def reiniciar(self) -> None:
        """Recarrega o SCPI depois de uma falha no Salvar ou depois dele."""


AbrirSCPIEntradas = Callable[[], AbstractContextManager[SCPIEntradas]]


def _progresso(rotulo: str, rec=None, resultado="aguardando", mensagem=""):
    """O item de um recebimento no `Resumo.lotes` (o mesmo desenho das saídas, com o rótulo
    `RC-…` no lugar do lote)."""
    return {
        "lote": rotulo,
        "recebedor": f"NF {rec.nf}" if rec else "",
        "centro": rec.pedido_rotulo if rec else "",
        "itens": len(rec.itens) if rec else 0,
        "resultado": resultado,
        "requisicao": "",
        "mensagem": mensagem[:300],
        "inicio": "",
        "fim": "",
    }


def _journal(evento: str, rec: regras.RecebimentoParaLancar, execucao_id: int | None, **extra):
    """Acrescenta um acontecimento ao journal. Falha ao gravá-lo só vai para o log: o journal
    nunca impede que o resultado chegue ao banco."""
    registro = {
        "ts": timezone.localtime().isoformat(),
        "evento": evento,
        "execucao": execucao_id,
        "recebimento": rec.rotulo,
        "versao": rec.versao,
        **extra,
    }
    try:
        with open(Path(settings.LOG_DIR) / JOURNAL, "a", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps(registro, ensure_ascii=False, default=str) + "\n")
    except OSError:
        logger.exception("Não foi possível gravar %s no journal (%s).", evento, rec.rotulo)


def _gravar(
    rec: regras.RecebimentoParaLancar, status: str, *, execucao_id: int, critico: bool, **campos
) -> None:
    """Grava o resultado no recebimento, com valores absolutos pelo `id`. Se o banco recusar, o
    que se queria gravar vai para o journal. Com `critico` (resultado de um Salvar), a execução
    para: continuar arriscaria lançar sem registrar."""
    try:
        Recebimento.objects.filter(pk=rec.id).update(status=status, **campos)
    except Exception as exc:
        _journal(
            "falha_banco", rec, execucao_id, valores={"status": status, **campos}, erro=repr(exc)
        )
        if critico:
            raise FalhaCritica(
                f"não foi possível gravar {status} para {rec}: {exc}. Registro salvo em "
                f"{JOURNAL}: confira no SCPI e resolva o recebimento à mão."
            ) from exc
        logger.error("✘ %s: não foi possível gravar %s: %s", rec, status, exc)


def _travar(
    rec: regras.RecebimentoParaLancar,
    execucao: ExecucaoRobo,
    ordem: int,
    tela: regras.TelaItens,
) -> bool:
    """Grava `EM_LANCAMENTO` se o recebimento ainda está `PREPARADO`, na mesma versão, com o
    pedido sem trava aberta e sem outro recebimento em lançamento ou em verificação (travados com
    `select_for_update`), junto com a tentativa (resultado `VERIFICAR`, o lado seguro se o
    processo morrer, com a foto e a tela lida). A transação fecha aqui, antes do clique."""
    agora = timezone.localtime()
    try:
        with transaction.atomic():
            atual = Recebimento.objects.select_for_update().filter(pk=rec.id).first()
            pedido = PedidoCompra.objects.select_for_update().get(pk=rec.pedido_id)
            if atual is None or atual.status != Recebimento.Status.PREPARADO:
                return False
            if atual.versao != rec.versao:
                return False
            if TravaPedido.objects.filter(pedido=pedido, destravada_em__isnull=True).exists():
                return False
            if (
                Recebimento.objects.filter(pedido=pedido, status__in=robo.EM_ABERTO)
                .exclude(pk=rec.id)
                .exists()
            ):
                return False
            Recebimento.objects.filter(pk=rec.id).update(
                status=Recebimento.Status.EM_LANCAMENTO,
                mensagem=f"Em lançamento desde {agora:%d/%m/%Y %H:%M} (execução #{execucao.pk}).",
            )
            robo.registrar_tentativa(
                execucao, ordem, rec, TentativaEntrada.Resultado.VERIFICAR, tela
            )
    except Error as exc:  # inclui InterfaceError (conexão já fechada)
        raise FalhaCritica(f"não foi possível travar o recebimento {rec}: {exc}.") from exc
    return True


def _tentativa_sem_salvar(
    execucao: ExecucaoRobo,
    ordem: int,
    rec: regras.RecebimentoParaLancar,
    resultado: str,
    tela: regras.TelaItens | None = None,
) -> None:
    """Registra a tentativa que não chegou ao Salvar (erro antes do clique ou recebimento que
    mudou). Falha aqui só vai para o log: nada foi salvo, e o registro não protege nada."""
    try:
        robo.registrar_tentativa(execucao, ordem, rec, resultado, tela)
    except Exception:
        logger.exception("Não foi possível registrar a tentativa de %s.", rec)


def _lancar_um(
    rec: regras.RecebimentoParaLancar,
    scpi: SCPIEntradas,
    execucao: ExecucaoRobo,
    resumo: Resumo,
    ordem: int,
) -> None:
    """Processa um recebimento. O resultado vai para o item dele no `Resumo.lotes` logo depois
    da gravação, antes da limpeza da tela do SCPI (`descartar`, `reiniciar`, `depois_de_salvar`):
    se ela falhar, o cartão já mostra o que aconteceu com o recebimento."""
    simulacao = execucao.simulacao
    progresso = resumo.lotes[ordem - 1]

    def concluir(resultado: str, numero: str = "", mensagem: str = "") -> None:
        progresso.update(
            resultado=resultado,
            requisicao=numero,
            mensagem=mensagem[:300],
            fim=timezone.now().isoformat(),
        )
        _salvar_progresso(execucao, resumo)

    # O que mudou desde a seleção (um recebimento anterior desta execução, uma edição, uma trava):
    # confere de novo, antes de abrir o SCPI, e refaz o esperado da tela com o estado de agora.
    atual = Recebimento.objects.select_related("pedido").filter(pk=rec.id).first()
    motivo = robo.motivo_de_bloqueio(atual) if atual else "o recebimento não existe mais"
    if not motivo and atual.versao != rec.versao:
        motivo = MENSAGEM_MUDOU
    if motivo:
        resumo.ignoradas += 1
        logger.warning("⚠ %s: %s; não lançado", rec, motivo)
        if not simulacao:
            _tentativa_sem_salvar(execucao, ordem, rec, TentativaEntrada.Resultado.IGNORADA)
        concluir("ignorada", mensagem=motivo[:1].upper() + motivo[1:])
        return
    rec = robo.para_lancar(atual)

    try:
        tela = scpi.abrir_pedido(rec)
    except Exception as exc:  # ErroSCPI ou outra: nada foi salvo, seguro tentar de novo
        _falha_antes_do_salvar(rec, exc, scpi, execucao, resumo, ordem, concluir)
        return

    divergencias = regras.conferir_tela(rec.esperado, tela)
    if divergencias:
        mensagem = " ".join(divergencias)
        resumo.falhas += 1
        logger.error("✘ %s: %s", rec, mensagem)
        if not simulacao:
            _gravar(
                rec,
                Recebimento.Status.ERRO,
                execucao_id=execucao.pk,
                mensagem=mensagem[:500],
                critico=False,
            )
            try:
                travar_pedido(
                    rec.pedido_id,
                    TravaPedido.Motivo.TELA,
                    mensagem,
                    execucao=execucao,
                    recebimento_id=rec.id,
                )
            except Exception:
                logger.exception("Não foi possível travar o pedido %s.", rec.pedido_rotulo)
            _tentativa_sem_salvar(execucao, ordem, rec, TentativaEntrada.Resultado.ERRO, tela)
        concluir("erro", mensagem=mensagem)
        scpi.descartar(rec)
        return

    try:
        scpi.preencher(rec)
    except Exception as exc:
        _falha_antes_do_salvar(rec, exc, scpi, execucao, resumo, ordem, concluir, tela)
        return

    if simulacao:
        scpi.encerrar_simulacao()
        resumo.simuladas += 1
        logger.info("◇ simulação: %s preenchido e descartado, sem salvar", rec)
        concluir("simulada")
        return

    if not _travar(rec, execucao, ordem, tela):
        logger.warning("⚠ %s: o recebimento mudou durante a execução; não lançado", rec)
        resumo.ignoradas += 1
        _tentativa_sem_salvar(execucao, ordem, rec, TentativaEntrada.Resultado.IGNORADA, tela)
        concluir("ignorada", mensagem=MENSAGEM_MUDOU)
        scpi.descartar(rec)
        return

    _journal("em_lancamento", rec, execucao.pk)
    try:
        numero = scpi.salvar()
    except Exception as exc:  # qualquer falha depois do clique: a requisição pode existir
        resumo.verificar += 1
        logger.error("⚠ %s: resultado incerto, conferir no SCPI: %s", rec, exc)
        _journal("incerto", rec, execucao.pk, erro=repr(exc))
        _gravar(
            rec,
            Recebimento.Status.VERIFICAR,
            execucao_id=execucao.pk,
            mensagem=f"Resultado incerto: {exc}"[:500],
            critico=True,
        )
        concluir("verificar", mensagem=f"Resultado incerto: {exc}")
        scpi.reiniciar()
        return

    agora = timezone.now()
    _journal("lancada", rec, execucao.pk, requisicao=numero)
    _gravar(
        rec,
        Recebimento.Status.LANCADO,
        execucao_id=execucao.pk,
        requisicao_scpi=numero,
        lancado_em=agora,
        via=Recebimento.Via.ROBO,
        visivel_desde=agora,
        mensagem="",
        critico=True,
    )
    robo.tentativa_lancada(execucao, rec.id, numero)
    resumo.lancadas += 1
    logger.info("✔ lançada no SCPI: requisição %s (%s)", numero, rec)
    concluir("lancada", numero)
    try:
        scpi.depois_de_salvar()
    except Exception as exc:
        logger.warning("Aviso: o SCPI não voltou ao formulário (%s); reiniciando.", exc)
        scpi.reiniciar()


def _falha_antes_do_salvar(rec, exc, scpi, execucao, resumo, ordem, concluir, tela=None) -> None:
    """A falha de `abrir_pedido` ou de `preencher`: nada foi salvo, seguro tentar de novo."""
    resumo.falhas += 1
    mensagem = str(exc) or type(exc).__name__
    logger.error("✘ %s: %s", rec, mensagem)
    if not execucao.simulacao:
        _gravar(
            rec,
            Recebimento.Status.ERRO,
            execucao_id=execucao.pk,
            mensagem=mensagem[:500],
            critico=False,
        )
        _tentativa_sem_salvar(execucao, ordem, rec, TentativaEntrada.Resultado.ERRO, tela)
    concluir("erro", mensagem=mensagem)
    scpi.descartar(rec)


def lancar(
    execucao: ExecucaoRobo,
    abrir_scpi: AbrirSCPIEntradas,
    *,
    recebimentos: Collection[str],
    extrair: Extrair,
) -> Resumo:
    """Lança no SCPI os `recebimentos` escolhidos (`RC-0001`; só os aptos), um por requisição, e
    devolve o resumo.

    Os bloqueados entram no resumo como `ignorada`, com o motivo, e não mudam. Na simulação,
    nenhum estado muda, nenhuma tentativa nem extração acontece e o Salvar nunca é chamado. Na
    execução real, o registro oficial é extraído antes (sem ele, `ExtracaoAntesFalhou` e nada
    muda) e depois do lançamento."""
    simulacao = execucao.simulacao
    resumo = Resumo()
    selecao = robo.selecionar(recebimentos, timezone.localdate())
    aptos = selecao.aptos
    resumo.lotes = [
        *(_progresso(rec.rotulo, rec) for rec in aptos),
        *(
            _progresso(rotulo, resultado="ignorada", mensagem=motivo[:1].upper() + motivo[1:])
            for rotulo, motivo in selecao.bloqueados
        ),
    ]
    for rotulo, motivo in selecao.bloqueados:
        logger.warning("⚠ %s não vai ao SCPI: %s", rotulo, motivo)
        resumo.ignoradas += 1

    periodo = None
    if aptos and not simulacao:
        resumo.fase = "antes"
        _salvar_progresso(execucao, resumo)
        periodo = robo.periodo_da_execucao(aptos, timezone.localdate())
        robo.extrair_antes(execucao, periodo, extrair)  # sem ela, nada abaixo acontece

    resumo.requisicoes = len(aptos)
    resumo.fase = "lancando"
    _salvar_resumo(execucao, resumo)
    if not aptos:
        logger.info("Nada a lançar.")
        return resumo

    with abrir_scpi() as scpi:
        for ordem, rec in enumerate(aptos, start=1):
            resumo.lotes[ordem - 1].update(resultado="andamento", inicio=timezone.now().isoformat())
            _salvar_progresso(execucao, resumo)
            logger.info("→ (%d/%d) %s", ordem, len(aptos), rec)
            _lancar_um(rec, scpi, execucao, resumo, ordem)
            resumo.processadas += 1
            _salvar_resumo(execucao, resumo)

    if periodo is not None:
        resumo.fase = "depois"
        _salvar_progresso(execucao, resumo)
        robo.extrair_depois(execucao, periodo, extrair)
    return resumo


def executar_lancamento_entradas(
    execucao: ExecucaoRobo,
    abrir_scpi: AbrirSCPIEntradas,
    *,
    recebimentos: Collection[str],
    extrair: Extrair,
) -> ExecucaoRobo:
    """Roda `lancar` sob a trava única do lançamento e a da importação de pedidos (nenhuma
    importação de pedidos acontece durante um lançamento de entradas) e registra o resultado na
    execução. `extrair(de, ate)` baixa o relatório de entradas: `relatorios.baixar_entradas` em
    produção, o SCPI simulado nos testes."""
    with trava(TRAVA_LANCAMENTO) as obtida:
        if not obtida:
            _encerrar(execucao, ExecucaoRobo.Situacao.FALHA, erro=MENSAGEM_LANCAMENTO)
            raise LancamentoEmAndamento(execucao.erro)
        with trava(trava_importacao(Importacao.Tipo.PEDIDOS_COMPRA)) as importacao_livre:
            if not importacao_livre:
                _encerrar(execucao, ExecucaoRobo.Situacao.FALHA, erro=MENSAGEM_IMPORTACAO)
                raise ImportacaoDePedidosEmAndamento(execucao.erro)

            registro = RegistroNaExecucao(execucao)
            logger.addHandler(registro)
            try:
                resumo = lancar(execucao, abrir_scpi, recebimentos=recebimentos, extrair=extrair)
            except (FalhaCritica, ErroImportacao) as exc:
                logger.error("✘ Execução interrompida: %s", exc)
                _encerrar_com_falha(execucao, str(exc))
                raise
            except Exception as exc:
                logger.exception("✘ Falha inesperada no lançamento de entradas")
                _encerrar_com_falha(execucao, f"{PREFIXO_FALHA_INESPERADA} {exc}")
                raise
            finally:
                logger.removeHandler(registro)

    pendencias = resumo.falhas or resumo.verificar
    _encerrar(
        execucao,
        ExecucaoRobo.Situacao.ATENCAO if pendencias else ExecucaoRobo.Situacao.SUCESSO,
        resumo=asdict(resumo),
    )
    return execucao
