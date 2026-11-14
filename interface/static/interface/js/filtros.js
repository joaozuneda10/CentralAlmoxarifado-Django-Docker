/*
 * Filtros recolhíveis — o formulário `form[data-filtros]` (histórico de Automações). Carregado com
 * `defer` no <head>.
 *
 * Melhoria progressiva: sem JavaScript o painel fica aberto e o botão "Filtrar" envia. Com ele,
 * o botão "Filtros" abre e fecha o painel (o estado fica guardado no navegador), a contagem
 * mostra quantos filtros do painel estão ativos e, com o painel fechado, cada filtro ativo vira
 * um chip que o remove. Remover um chip troca o valor do campo e dispara `change`, que o HTMX
 * do formulário já escuta (e o dropdown.js também, para atualizar o gatilho).
 *
 * O `form[data-filtros-auto]` (catálogo: Formulários e Curva ABC) é mais simples: sem painel, só
 * envia o formulário quando um campo muda.
 *
 * O `form[data-filtros-estado]` (painel de pedidos, spec 015) fica sempre à vista, em chips. O HTMX
 * troca só a lista, então o resto da tela é mantido daqui: depois de cada troca concluída, os
 * rótulos dos chips com lista ("Origem: Limpeza") e o `aria-current` dos indicadores passam a
 * mostrar o que foi enviado, e esses valores viram a última troca aplicada; na falha da requisição,
 * os campos voltam a ela, sem envio novo (contracts/painel.md).
 *
 * Os eventos são delegados no `document`: ao restaurar o histórico, o HTMX troca o <body> e os
 * elementos são outros.
 */
(function () {
  "use strict";

  var CHAVE = "filtros-painel-aberto";

  function lerAberto() {
    try {
      return localStorage.getItem(CHAVE) === "1";
    } catch (e) {
      return false;
    }
  }

  function gravarAberto(aberto) {
    try {
      localStorage.setItem(CHAVE, aberto ? "1" : "0");
    } catch (e) {
      /* sem armazenamento: o painel só não lembra o estado */
    }
  }

  function data(valor) {
    var p = /^(\d{4})-(\d{2})-(\d{2})$/.exec(valor || "");
    return p ? p[3] + "/" + p[2] + "/" + p[1] : valor;
  }

  function rotulo(form, campo) {
    var r = campo.id && form.querySelector('label[for="' + campo.id + '"]');
    return r ? r.textContent.trim() : campo.name;
  }

  // Os filtros ativos do painel (as buscas da barra ficam de fora: já aparecem no próprio campo).
  function ativos(form) {
    var lista = [];
    var painel = form.querySelector("[data-filtros-painel]");
    painel.querySelectorAll("select").forEach(function (s) {
      if (!s.value) return;
      lista.push({
        texto: rotulo(form, s) + ": " + s.options[s.selectedIndex].textContent.trim(),
        campos: [s],
      });
    });
    var de = form.elements.de;
    var ate = form.elements.ate;
    if (de && ate && (de.value || ate.value)) {
      var texto;
      if (de.value && ate.value) texto = data(de.value) + " a " + data(ate.value);
      else if (de.value) texto = "a partir de " + data(de.value);
      else texto = "até " + data(ate.value);
      lista.push({ texto: "Período: " + texto, campos: [de, ate] });
    }
    return lista;
  }

  function icone(tracos) {
    return (
      '<svg class="icone" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" ' +
      'focusable="false">' + tracos + "</svg>"
    );
  }
  var FECHAR = icone('<path d="M18 6 6 18"/><path d="m6 6 12 12"/>');

  function atualizar(form) {
    var painel = form.querySelector("[data-filtros-painel]");
    var botao = form.querySelector("[data-filtros-alternar]");
    var contagem = form.querySelector("[data-filtros-contagem]");
    var chips = form.querySelector("[data-filtros-chips]");
    var limpar = form.querySelector("[data-filtros-limpar]");
    var aberto = !painel.hidden;
    var lista = ativos(form);

    botao.setAttribute("aria-expanded", aberto ? "true" : "false");
    contagem.hidden = !lista.length;
    contagem.textContent = lista.length;
    botao.setAttribute(
      "aria-label",
      "Filtros" + (lista.length ? " (" + lista.length + (lista.length > 1 ? " ativos)" : " ativo)") : "")
    );
    var buscando = Array.prototype.some.call(form.querySelectorAll(".filtros-busca input"), function (c) {
      return c.value.trim();
    });
    limpar.hidden = !lista.length && !buscando;

    // Redesenhar apaga o chip com o foco: ele volta para o chip na mesma posição, ou para o
    // botão "Filtros" se não sobrou nenhum.
    var focado = chips.contains(document.activeElement)
      ? Number(document.activeElement.getAttribute("data-filtro-remover"))
      : -1;
    chips.textContent = "";
    chips.hidden = aberto || !lista.length;
    if (chips.hidden) {
      if (focado >= 0) botao.focus();
      return;
    }
    lista.forEach(function (item, i) {
      var li = document.createElement("li");
      var b = document.createElement("button");
      b.type = "button";
      b.className = "filtros-chip";
      b.setAttribute("data-filtro-remover", i);
      b.setAttribute("aria-label", "Remover filtro " + item.texto);
      var t = document.createElement("span");
      t.textContent = item.texto;
      b.appendChild(t);
      b.insertAdjacentHTML("beforeend", FECHAR);
      li.appendChild(b);
      chips.appendChild(li);
    });
    if (focado >= 0) chips.querySelectorAll("button")[Math.min(focado, lista.length - 1)].focus();
  }

  // `a[data-fechar-filtros]` (atalhos do painel): a página que o link abre chega com o painel de
  // filtros recolhido, mostrando só os chips, sem mudar o estado que o navegador lembra.
  var CHEGAR_FECHADO = "filtros-chegar-fechado";

  function chegouPorAtalho() {
    try {
      var sim = sessionStorage.getItem(CHEGAR_FECHADO) === "1";
      sessionStorage.removeItem(CHEGAR_FECHADO);
      return sim;
    } catch (e) {
      return false;
    }
  }

  document.addEventListener("click", function (e) {
    if (!(e.target.closest && e.target.closest("a[data-fechar-filtros]"))) return;
    // Só a navegação desta aba conta: Ctrl/Cmd/Shift/Alt+clique e o botão do meio abrem outra aba, e o
    // estado ficaria guardado aqui até a próxima página de filtros da aba original.
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    try {
      sessionStorage.setItem(CHEGAR_FECHADO, "1");
    } catch (erro) {
      /* sem armazenamento, o painel abre como estava */
    }
  });

  function iniciar() {
    var fechado = chegouPorAtalho();
    document.querySelectorAll("form[data-filtros]").forEach(function (form) {
      // O estado do painel só se define na primeira vez de cada formulário: uma troca do HTMX
      // depois (remover um chip, por exemplo) não o reabre.
      if (!form.hasAttribute("data-filtros-pronto")) {
        form.setAttribute("data-filtros-pronto", "");
        form.querySelector("[data-filtros-painel]").hidden = fechado || !lerAberto();
      }
      atualizar(form);
    });
  }

  document.addEventListener("click", function (e) {
    var alternar = e.target.closest("[data-filtros-alternar]");
    if (alternar) {
      var form = alternar.closest("form[data-filtros]");
      var painel = form.querySelector("[data-filtros-painel]");
      painel.hidden = !painel.hidden;
      gravarAberto(!painel.hidden);
      atualizar(form);
      return;
    }
    var remover = e.target.closest("[data-filtro-remover]");
    if (remover) {
      var f = remover.closest("form[data-filtros]");
      var item = ativos(f)[Number(remover.getAttribute("data-filtro-remover"))];
      if (!item) return;
      item.campos.forEach(function (c) {
        c.value = "";
      });
      // Um único `change`, para sair um único pedido do HTMX; o `atualizar` que ele provoca
      // redesenha os chips e cuida do foco.
      remover.focus();
      item.campos[item.campos.length - 1].dispatchEvent(new Event("change", { bubbles: true }));
    }
  });

  // `form[data-filtros-auto]` (filtros em página inteira, sem HTMX): escolher uma opção ou sair do
  // campo de busca com o texto alterado já envia o formulário, sem precisar do Enter. O botão
  // "Filtrar" só aparece sem JavaScript. O `change` do dropdown.js (que troca os `select`) também
  // chega aqui. Enquanto o texto é digitado nada é enviado: a página recarregaria e o foco se perderia.
  document.addEventListener("change", function (e) {
    var form = e.target.closest && e.target.closest("form[data-filtros-auto]");
    if (form && form.requestSubmit) form.requestSubmit();
  });

  ["change", "input"].forEach(function (tipo) {
    document.addEventListener(tipo, function (e) {
      var form = e.target.closest && e.target.closest("form[data-filtros]");
      if (form) atualizar(form);
    });
  });

  // ---- form[data-filtros-estado]: o painel de pedidos ------------------------------------------

  // Os valores do formulário, campo a campo (a busca do cabeçalho entra pelo atributo `form`).
  function valores(form) {
    var mapa = {};
    Array.prototype.forEach.call(form.elements, function (campo) {
      if (!campo.name || campo.disabled) return;
      if (campo.type === "radio") {
        if (!(campo.name in mapa)) mapa[campo.name] = "";
        if (campo.checked) mapa[campo.name] = campo.value;
      } else if (campo.type !== "submit" && campo.type !== "button") {
        mapa[campo.name] = campo.value;
      }
    });
    return mapa;
  }

  function periodo(de, ate) {
    if (de && ate) return data(de) + " a " + data(ate);
    if (de) return "a partir de " + data(de);
    if (ate) return "até " + data(ate);
    return "";
  }

  // O mesmo texto de `FiltrosPainel.rotulos_dos_chips`: o nome sozinho, ou "nome: valor".
  function mostrar(form, mapa) {
    form.querySelectorAll("[data-chip-nome]").forEach(function (rotulo) {
      var nome = rotulo.getAttribute("data-chip-nome");
      var texto = "";
      if (rotulo.hasAttribute("data-chip-periodo")) {
        texto = periodo(mapa.de, mapa.ate);
      } else {
        var select = rotulo.closest("details").querySelector("select");
        var opcao = select && mapa[select.name] && select.querySelector('option[value="' + CSS.escape(mapa[select.name]) + '"]');
        texto = opcao ? opcao.textContent.trim() : "";
      }
      rotulo.textContent = texto ? nome + ": " + texto : nome;
      var resumo = rotulo.closest("summary");
      if (resumo) resumo.classList.toggle("chip-ativo", Boolean(texto));
    });
    document.querySelectorAll(".indicador-link[data-indicador-campo]").forEach(function (link) {
      var atual = (mapa[link.getAttribute("data-indicador-campo")] || "") === link.getAttribute("data-indicador-valor");
      if (atual) link.setAttribute("aria-current", "true");
      else link.removeAttribute("aria-current");
    });
  }

  // Volta à última troca aplicada só o campo que ainda está como foi enviado: o que a pessoa mudou
  // depois do envio fica como ela deixou. O `select` só tem o gatilho do dropdown.js redesenhado.
  function desfazer(form, enviado, aplicado) {
    var atual = valores(form);
    Array.prototype.forEach.call(form.elements, function (campo) {
      var nome = campo.name;
      if (!nome || !(nome in aplicado) || atual[nome] !== enviado[nome]) return;
      if (campo.type === "radio") {
        campo.checked = campo.value === aplicado[nome];
      } else if (campo.type !== "submit" && campo.type !== "button") {
        campo.value = aplicado[nome];
        if (campo.tagName === "SELECT") campo.dispatchEvent(new Event("dropdown:atualizar"));
      }
    });
  }

  function formDoEstado(e) {
    var ctx = e.detail && e.detail.ctx;
    var origem = ctx && ctx.sourceElement;
    return origem && origem.matches && origem.matches("form[data-filtros-estado]") ? origem : null;
  }

  var envios = 0;

  document.addEventListener("htmx:config:request", function (e) {
    var form = formDoEstado(e);
    if (!form) return;
    envios += 1;
    e.detail.ctx.filtrosEstado = { numero: envios, enviado: valores(form) };
  });

  document.addEventListener("htmx:after:swap", function (e) {
    var form = formDoEstado(e);
    var estado = form && e.detail.ctx.filtrosEstado;
    if (!estado) return;
    form._filtrosAplicados = estado.enviado;
    mostrar(form, estado.enviado);
  });

  // Erro do servidor (4xx/5xx, que o `htmx-config` do base.html não deixa trocar a lista) ou da
  // rede. A requisição cancelada pelo `hx-sync` (um envio mais novo a substituiu) não desfaz nada.
  function falhou(e) {
    var form = formDoEstado(e);
    var estado = form && e.detail.ctx.filtrosEstado;
    if (!estado || estado.numero !== envios || !form._filtrosAplicados) return;
    if (e.detail.error && e.detail.error.name === "AbortError") return;
    desfazer(form, estado.enviado, form._filtrosAplicados);
    mostrar(form, form._filtrosAplicados);
  }
  document.addEventListener("htmx:response:error", falhou);
  document.addEventListener("htmx:error", falhou);

  function iniciarEstado() {
    document.querySelectorAll("form[data-filtros-estado]").forEach(function (form) {
      if (!form._filtrosAplicados) form._filtrosAplicados = valores(form);
    });
  }

  document.addEventListener("DOMContentLoaded", iniciar);
  document.addEventListener("htmx:after:swap", iniciar);
  document.addEventListener("DOMContentLoaded", iniciarEstado);
  document.addEventListener("htmx:after:swap", iniciarEstado);
})();
