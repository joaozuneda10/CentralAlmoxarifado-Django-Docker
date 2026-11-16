/*
 * Formulário "Receber total" (spec 014, US1): o total abre com os itens e as quantidades travados
 * e só se altera por uma ação explícita da pessoa ("Alterar itens e quantidades"); "Voltar ao
 * total" restaura o que o servidor sugeriu (`data-sugerido` de cada caixa e campo) e trava de novo.
 * O `form[data-total]` marca o modo total; ele abre travado quando tem também `data-total-travado`
 * (o servidor só o põe se o formulário é exatamente o total) e livre, com o "Voltar ao total",
 * quando uma recusa devolveu quantidades editadas. Sem JavaScript os campos ficam livres, o aviso
 * e os botões ficam escondidos, e o servidor valida as quantidades de qualquer jeito.
 * Carregado no <head> com defer.
 */
(function () {
  "use strict";

  function iniciar(form) {
    var tabela = form.querySelector("#total-itens");
    var aviso = form.querySelector("[data-total-aviso]");
    var textoTravado = form.querySelector("[data-total-texto-travado]");
    var textoLiberado = form.querySelector("[data-total-texto-liberado]");
    var alterar = form.querySelector("[data-total-alterar]");
    var voltar = form.querySelector("[data-total-voltar]");
    var anuncio = form.querySelector("[data-total-anuncio]");
    if (!tabela || !aviso || !textoTravado || !textoLiberado || !alterar || !voltar) return;

    var caixas = Array.prototype.slice.call(tabela.querySelectorAll('input[type="checkbox"]'));
    var campos = Array.prototype.slice.call(
      tabela.querySelectorAll('input[type="text"][name^="qtd-"]')
    );

    // Caixa travada: o clique não a altera (`disabled` não enviaria o valor).
    function barrar(evento) {
      if (form.hasAttribute("data-total-travado")) evento.preventDefault();
    }
    caixas.forEach(function (c) { c.addEventListener("click", barrar); });

    function travar(travado, mensagem) {
      if (travado) form.setAttribute("data-total-travado", "");
      else form.removeAttribute("data-total-travado");
      caixas.forEach(function (c) { c.setAttribute("aria-readonly", travado ? "true" : "false"); });
      campos.forEach(function (c) { c.readOnly = travado; });
      alterar.hidden = !travado;
      voltar.hidden = travado;
      textoTravado.hidden = !travado;
      textoLiberado.hidden = travado;
      aviso.classList.toggle("aviso-atencao", !travado);
      aviso.classList.toggle("aviso-info", travado);
      aviso.hidden = false;
      if (anuncio && mensagem) anuncio.textContent = mensagem;
    }

    alterar.addEventListener("click", function () {
      travar(false, "Itens e quantidades liberados para alteração.");
      if (campos.length) campos[0].focus();
    });
    voltar.addEventListener("click", function () {
      caixas.forEach(function (c) { c.checked = c.hasAttribute("data-sugerido"); });
      campos.forEach(function (c) { c.value = c.getAttribute("data-sugerido") || ""; });
      travar(true, "Voltou ao total: itens e quantidades travados.");
      alterar.focus();
    });

    travar(form.hasAttribute("data-total-travado"), "");
  }

  document.addEventListener("DOMContentLoaded", function () {
    var form = document.querySelector("form[data-total]");
    if (form) iniciar(form);
  });
})();
