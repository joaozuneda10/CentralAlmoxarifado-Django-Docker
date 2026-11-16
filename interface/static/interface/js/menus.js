/*
 * Menus em `<details data-menu>` (spec 015): o ⋮ de cada linha da lista do painel e os chips com
 * lista dos filtros. Carregado com `defer` no <head>.
 *
 * Melhoria progressiva: sem JavaScript o `<details>` abre e fecha sozinho, e os itens são links e
 * campos comuns. Com ele:
 * - abrir um menu fecha os outros;
 * - o Esc fecha o aberto e devolve o foco ao `summary` (o Esc que o dropdown.js usa para fechar a
 *   própria lista não chega aqui);
 * - o clique fora fecha;
 * - escolher uma opção num chip com lista (`select`) fecha o chip; nos campos de data, não (o
 *   período tem dois).
 *
 * Os eventos são delegados no `document`: ao restaurar o histórico, o HTMX troca o <body> e os
 * elementos são outros.
 */
(function () {
  "use strict";

  function abertos() {
    return document.querySelectorAll("details[data-menu][open]");
  }

  function fechar(menu, devolverFoco) {
    menu.open = false;
    if (devolverFoco) {
      var resumo = menu.querySelector("summary");
      if (resumo) resumo.focus();
    }
  }

  // O `toggle` não sobe pela árvore: escutado na captura.
  document.addEventListener(
    "toggle",
    function (e) {
      var menu = e.target;
      if (!(menu instanceof HTMLDetailsElement) || !menu.hasAttribute("data-menu") || !menu.open) return;
      abertos().forEach(function (outro) {
        if (outro !== menu && !outro.contains(menu)) outro.open = false;
      });
    },
    true
  );

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape" || e.defaultPrevented) return;
    var menu = document.activeElement && document.activeElement.closest
      ? document.activeElement.closest("details[data-menu][open]")
      : null;
    if (!menu) {
      var lista = abertos();
      menu = lista.length ? lista[lista.length - 1] : null;
    }
    if (!menu) return;
    e.preventDefault();
    fechar(menu, true);
  });

  document.addEventListener("click", function (e) {
    abertos().forEach(function (menu) {
      if (!menu.contains(e.target)) fechar(menu, false);
    });
  });

  document.addEventListener("change", function (e) {
    if (!(e.target instanceof HTMLSelectElement)) return;
    var menu = e.target.closest("details.chip-menu[data-menu][open]");
    if (menu) fechar(menu, true);
  });
})();
