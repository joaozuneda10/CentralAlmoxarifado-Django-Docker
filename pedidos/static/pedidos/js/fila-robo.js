/*
 * Fila do robô na aba Lançamento no SCPI: marcar as requisições a processar. Marcar a linha,
 * "marcar todas" no cabeçalho, contagem no `aria-live` e botões só com seleção. Com o lançamento
 * real liberado, o botão "Lançar no SCPI" abre antes a confirmação (#dialogo-lancar, dialogo.js).
 * Carregado no <head> com defer. Sem JavaScript, as caixas e os botões enviam o formulário e o
 * servidor recusa o envio sem requisição marcada ou com uma que já saiu da fila.
 *
 * Serve também à aba Entradas no SCPI (spec 014), pelos atributos do <form data-fila-robo>:
 * `data-fila-campo` (o name das caixas, "lotes" por padrão), `data-fila-um` e `data-fila-varios`
 * (o que está marcado: "requisição selecionada" / "requisições selecionadas"),
 * `data-fila-conf-um` e `data-fila-conf-varios` (a frase da confirmação, com `{}` no lugar da
 * lista) e `data-fila-dialogo` (o id do diálogo, "dialogo-lancar" por padrão). Sem eles, o
 * comportamento é o das saídas.
 */
(function () {
  "use strict";

  function plural(n, um, varios) {
    return n === 1 ? um : varios;
  }

  function campoDe(form) {
    return form.dataset.filaCampo || "lotes";
  }

  function sincronizar(form) {
    var campo = campoDe(form);
    var caixas = Array.prototype.slice.call(
      form.querySelectorAll('tbody input[name="' + campo + '"]')
    );
    var marcadas = caixas.filter(function (c) { return c.checked; });
    var n = marcadas.length;
    caixas.forEach(function (c) {
      var linha = c.closest("tr");
      if (linha) linha.classList.toggle("marcada", c.checked);
    });
    var todas = form.querySelector("[data-fila-todas]");
    if (todas) {
      todas.checked = caixas.length > 0 && n === caixas.length;
      todas.indeterminate = n > 0 && n < caixas.length;
    }
    var contagem = form.querySelector("[data-fila-contagem]");
    if (contagem && caixas.length) {
      var texto = n
        ? n + " de " + caixas.length + " " + plural(
            n,
            form.dataset.filaUm || "requisição selecionada",
            form.dataset.filaVarios || "requisições selecionadas"
          )
        : (form.dataset.filaNenhum || "Nenhuma requisição selecionada");
      var apoio = n ? "" : "Marque na lista o que o robô deve processar.";
      contagem.textContent = texto;
      if (apoio) {
        var small = document.createElement("small");
        small.textContent = apoio;
        contagem.appendChild(small);
      }
    }
    var sem = !caixas.length || caixas[0].disabled;
    form.querySelectorAll("[data-requer-selecao]").forEach(function (b) {
      b.disabled = sem || n === 0;
    });
    var dialogoDaFila = document.getElementById(form.dataset.filaDialogo || "dialogo-lancar");
    var confirmacao = dialogoDaFila && dialogoDaFila.querySelector("[data-fila-confirmacao]");
    if (confirmacao) {
      var lista = marcadas.map(function (c) { return c.value; }).join(", ");
      var modelo = n === 1
        ? form.dataset.filaConfUm || "A requisição {} será lançada de verdade no SCPI. Não dá para desfazer por aqui."
        : form.dataset.filaConfVarios || "As requisições {} serão lançadas de verdade no SCPI. Não dá para desfazer por aqui.";
      confirmacao.textContent = n ? modelo.replace("{}", lista) : "";
    }
  }

  // Até 1286px a barra lateral vira um cabeçalho fixo (layouts.css) que cobriria a barra da fila
  // ao rolar: a barra da fila gruda logo abaixo dele (`--fila-topo`, pedidos.css).
  var CABECALHO_FIXO = window.matchMedia("(max-width: 1286px)");

  function ajustarTopo() {
    var cabecalho = document.querySelector(".app-lateral");
    var altura = cabecalho && CABECALHO_FIXO.matches ? cabecalho.getBoundingClientRect().height : 0;
    document.documentElement.style.setProperty("--fila-topo", altura + "px");
  }

  function preparar() {
    document.querySelectorAll("form[data-fila-robo]").forEach(sincronizar);
    ajustarTopo();
  }

  window.addEventListener("resize", ajustarTopo);
  if (window.ResizeObserver) {
    var observado = document.querySelector(".app-lateral");
    if (observado) new ResizeObserver(ajustarTopo).observe(observado);
  }

  document.addEventListener("DOMContentLoaded", preparar);
  document.addEventListener("htmx:after:swap", preparar);

  document.addEventListener("change", function (e) {
    var form = e.target.closest && e.target.closest("form[data-fila-robo]");
    if (!form) return;
    if (e.target.matches("[data-fila-todas]")) {
      form.querySelectorAll('tbody input[name="' + campoDe(form) + '"]:not(:disabled)').forEach(function (c) {
        c.checked = e.target.checked;
      });
    }
    sincronizar(form);
  });

  // Clicar na linha alterna a caixa (o número do pedido segue sendo um link).
  document.addEventListener("click", function (e) {
    var alvo = e.target;
    if (!alvo.closest) return;
    var linha = alvo.closest("tr[data-fila-linha]");
    if (linha && !alvo.closest("a, label, input, button")) {
      var formDaLinha = linha.closest("form[data-fila-robo]");
      var caixa = linha.querySelector('input[name="' + (formDaLinha ? campoDe(formDaLinha) : "lotes") + '"]');
      if (caixa && !caixa.disabled) {
        caixa.checked = !caixa.checked;
        caixa.dispatchEvent(new Event("change", { bubbles: true }));
      }
      return;
    }
    // Lançamento real: confirma antes de enviar.
    var lancar = alvo.closest("[data-confirmar-lancamento]");
    if (lancar && !lancar.disabled) {
      var formDoBotao = lancar.closest("form[data-fila-robo]");
      var dialogo = document.getElementById(
        (formDoBotao && formDoBotao.dataset.filaDialogo) || "dialogo-lancar"
      );
      if (dialogo && typeof dialogo.showModal === "function") {
        e.preventDefault();
        if (!dialogo.open) dialogo.showModal();
      }
    }
  });
})();

/*
 * Registro técnico do acompanhamento (pedidos/_andamento.html): a seção da aba se recarrega a cada
 * 3 s enquanto o robô roda, e o <details> voltaria fechado e rolado para o topo. Guarda antes da
 * troca se ele estava aberto e onde estava a rolagem (no fim, segue o fim) e reaplica depois.
 */
(function () {
  "use strict";

  var guardado = null;

  function registro() {
    return document.querySelector("[data-registro-tecnico]");
  }

  document.addEventListener("htmx:before:swap", function () {
    var detalhes = registro();
    if (!detalhes) return;
    var pre = detalhes.querySelector("pre");
    guardado = {
      aberto: detalhes.open,
      topo: pre ? pre.scrollTop : 0,
      noFim: pre ? pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 4 : true,
    };
  });

  document.addEventListener("htmx:after:swap", function () {
    var detalhes = registro();
    if (!detalhes || !guardado) return;
    detalhes.open = guardado.aberto;
    var pre = detalhes.querySelector("pre");
    if (pre) pre.scrollTop = guardado.noFim ? pre.scrollHeight : guardado.topo;
    guardado = null;
  });
})();
