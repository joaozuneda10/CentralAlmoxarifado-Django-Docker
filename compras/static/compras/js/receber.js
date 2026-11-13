/*
 * Formulário "Receber total" (spec 014, US1): o total abre com os itens e as quantidades travados
 * e só se altera por uma ação explícita da pessoa ("Alterar itens e quantidades"); "Voltar ao
 * total" restaura o que foi sugerido e trava de novo. O servidor só marca o formulário com
 * `data-total-travado` quando ele é exatamente o total sugerido; sem JavaScript os campos ficam
 * livres (os botões ficam escondidos) e o servidor valida as quantidades de qualquer jeito.
 * Carregado no <head> com defer.
 */
(function () {
  "use strict";

  function iniciar(form) {
    var tabela = form.querySelector("#total-itens");
    var aviso = form.querySelector("[data-total-aviso]");
    var texto = form.querySelector("[data-total-texto]");
    var alterar = form.querySelector("[data-total-alterar]");
    var voltar = form.querySelector("[data-total-voltar]");
    var anuncio = form.querySelector("[data-total-anuncio]");
    if (!tabela || !aviso || !alterar || !voltar) return;

    var caixas = Array.prototype.slice.call(tabela.querySelectorAll('input[type="checkbox"]'));
    var campos = Array.prototype.slice.call(
      tabela.querySelectorAll('input[type="text"][name^="qtd-"]')
    );
    // O que o servidor sugeriu: é o que "Voltar ao total" restaura.
    var sugerido = {
      marcadas: caixas.map(function (c) { return c.checked; }),
      quantidades: campos.map(function (c) { return c.value; }),
    };
    var textoTotal = texto.innerHTML;
    var textoLiberado =
      "<strong>Itens e quantidades liberados.</strong> O que ficar abaixo do saldo livre " +
      "continua livre para outra nota fiscal.";

    // Caixa travada: o clique não a altera (`disabled` não enviaria o valor).
    function barrar(evento) {
      if (form.dataset.totalTravado !== undefined) evento.preventDefault();
    }
    caixas.forEach(function (c) { c.addEventListener("click", barrar); });

    function travar(travado, mensagem) {
      if (travado) form.setAttribute("data-total-travado", "");
      else form.removeAttribute("data-total-travado");
      caixas.forEach(function (c) { c.setAttribute("aria-readonly", travado ? "true" : "false"); });
      campos.forEach(function (c) { c.readOnly = travado; });
      alterar.hidden = !travado;
      voltar.hidden = travado;
      texto.innerHTML = travado ? textoTotal : textoLiberado;
      aviso.classList.toggle("aviso-atencao", !travado);
      aviso.classList.toggle("aviso-info", travado);
      if (anuncio && mensagem) anuncio.textContent = mensagem;
    }

    alterar.addEventListener("click", function () {
      travar(false, "Itens e quantidades liberados para alteração.");
      if (campos.length) campos[0].focus();
    });
    voltar.addEventListener("click", function () {
      caixas.forEach(function (c, i) { c.checked = sugerido.marcadas[i]; });
      campos.forEach(function (c, i) { c.value = sugerido.quantidades[i]; });
      travar(true, "Voltou ao total: itens e quantidades travados.");
      alterar.focus();
    });

    travar(true, "");
  }

  document.addEventListener("DOMContentLoaded", function () {
    var form = document.querySelector("form[data-total-travado]");
    if (form) iniciar(form);
  });
})();
