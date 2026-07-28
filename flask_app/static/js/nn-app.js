/* ==========================================================================
   Application shell: theme, avatars, tabs, search.
   ========================================================================== */

(function (window, document) {
  "use strict";

  var NN = (window.NN = window.NN || {});

  /* -- theme ------------------------------------------------------------- */

  var THEME_KEY = "nn-theme";

  function currentTheme() {
    var stored = document.documentElement.getAttribute("data-theme");
    if (stored) return stored;
    return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }

  function setTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem(THEME_KEY, theme); } catch (e) { /* private mode */ }
  }

  NN.toggleTheme = function () {
    setTheme(currentTheme() === "dark" ? "light" : "dark");
  };

  /* -- avatars ----------------------------------------------------------- */

  /* Which players have a thumbnail is baked into the page as JSON, so tables
     never request an image that would 404 and never wait on a round trip. */
  var thumbs = null;

  NN.hasThumb = function (name) {
    if (thumbs === null) {
      var node = document.getElementById("nn-thumbs");
      try {
        thumbs = new Set(node ? JSON.parse(node.textContent) : []);
      } catch (e) {
        thumbs = new Set();
      }
    }
    return thumbs.has(name);
  };

  /* -- tabs -------------------------------------------------------------- */

  /* Each tab owns a dataset that is fetched the first time the tab is shown.
     Opening the page therefore costs one small request, not eight large ones. */
  function initTabs(container) {
    var tabs = Array.prototype.slice.call(container.querySelectorAll("[role=tab]"));
    if (!tabs.length) return;

    function show(tab) {
      tabs.forEach(function (other) {
        var selected = other === tab;
        other.setAttribute("aria-selected", selected ? "true" : "false");
        other.tabIndex = selected ? 0 : -1;
        var panel = document.getElementById(other.getAttribute("aria-controls"));
        if (panel) {
          panel.hidden = !selected;
          if (selected) NN.activatePanel(panel);
        }
      });
      if (history.replaceState) {
        history.replaceState(null, "", "#" + tab.dataset.key);
      }
    }

    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () { show(tab); });
      tab.addEventListener("keydown", function (event) {
        var index = tabs.indexOf(tab);
        var next = null;
        if (event.key === "ArrowRight") next = tabs[(index + 1) % tabs.length];
        if (event.key === "ArrowLeft") next = tabs[(index - 1 + tabs.length) % tabs.length];
        if (next) { event.preventDefault(); next.focus(); show(next); }
      });
    });

    function showByKey(key) {
      var match = tabs.filter(function (t) { return t.dataset.key === key; })[0];
      if (match) { show(match); return true; }
      return false;
    }

    function currentHashKey() {
      return decodeURIComponent(window.location.hash.replace("#", ""));
    }

    /* The header links point at /#games and friends. When you are already on
       the page, the browser only moves the hash and fires no navigation, so
       nothing used to happen. React to the hash instead. */
    window.addEventListener("hashchange", function () {
      if (showByKey(currentHashKey())) {
        // Header links sit above the fold; bring the data into view.
        container.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });

    if (!showByKey(currentHashKey())) show(tabs[0]);
  }

  /* -- table wiring ------------------------------------------------------ */

  var tablesByPanel = new WeakMap();

  NN.activatePanel = function (panel) {
    // Charts render on first reveal; measuring width in a hidden panel gives 0.
    if (NN.renderChart) {
      panel.querySelectorAll("[data-chart]").forEach(NN.renderChart);
    }

    var hosts = panel.querySelectorAll("[data-table]");

    // Row filters are shared across a panel group, but mean nothing on a panel
    // that holds only charts, so hide them there.
    var controls = panel.parentNode.querySelector(".controls");
    if (controls) controls.hidden = hosts.length === 0;

    var built = tablesByPanel.get(panel);

    if (!built) {
      built = [];
      Array.prototype.forEach.call(hosts, function (host) {
        var table = new NN.DataTable(host, {
          name: host.dataset.table,
          url: host.dataset.url || "/api/table/" + host.dataset.table,
          defaultSort: host.dataset.sort || null
        });
        built.push(table);
      });
      tablesByPanel.set(panel, built);
    }

    built.forEach(function (table) {
      table.load().then(function () { applyFilters(table); });
    });
  };

  /* Filters live outside the panels and apply to whichever tables are open. */
  var filterState = { query: "", minGames: 0, activeOnly: false };

  function applyFilters(table) {
    table.setFilters(filterState);
  }

  function allTables() {
    var result = [];
    document.querySelectorAll("[role=tabpanel]").forEach(function (panel) {
      var built = tablesByPanel.get(panel);
      if (built) result = result.concat(built);
    });
    return result;
  }

  function wireFilters() {
    var query = document.getElementById("filterQuery");
    var minGames = document.getElementById("filterMinGames");
    var activeOnly = document.getElementById("filterActive");

    function push() {
      allTables().forEach(applyFilters);
    }

    var timer = null;
    if (query) {
      query.addEventListener("input", function () {
        clearTimeout(timer);
        timer = setTimeout(function () {
          filterState.query = query.value.trim();
          push();
        }, 180);
      });
    }
    if (minGames) {
      minGames.addEventListener("input", function () {
        clearTimeout(timer);
        timer = setTimeout(function () {
          filterState.minGames = Number(minGames.value) || 0;
          push();
        }, 180);
      });
    }
    if (activeOnly) {
      activeOnly.addEventListener("change", function () {
        filterState.activeOnly = activeOnly.checked;
        push();
      });
    }
  }

  /* -- tooltips ----------------------------------------------------------- */

  /* Any element with data-tip gets a hover/focus tooltip.
     A native title attribute was the first attempt: it takes about a second to
     appear, can't be styled, and never shows on touch. This one is also
     position:fixed and attached to <body>, so it escapes the panel's
     overflow:hidden instead of being clipped by it. */
  function initTooltips() {
    var tip = document.createElement("div");
    tip.className = "nn-tip";
    tip.setAttribute("role", "tooltip");
    document.body.appendChild(tip);

    var current = null;

    function show(host) {
      var text = host.getAttribute("data-tip");
      if (!text) return;
      current = host;
      tip.textContent = text;
      tip.setAttribute("data-visible", "true");

      var anchor = host.getBoundingClientRect();
      var box = tip.getBoundingClientRect();
      var margin = 8;

      var left = anchor.left + anchor.width / 2 - box.width / 2;
      left = Math.min(Math.max(left, margin), window.innerWidth - box.width - margin);

      // Prefer above; flip below when there isn't room.
      var top = anchor.top - box.height - 8;
      if (top < margin) top = anchor.bottom + 8;

      tip.style.left = left + "px";
      tip.style.top = top + "px";
    }

    function hide() {
      current = null;
      tip.setAttribute("data-visible", "false");
    }

    document.addEventListener("mouseover", function (event) {
      var host = event.target.closest("[data-tip]");
      if (host && host !== current) show(host);
    });

    document.addEventListener("mouseout", function (event) {
      if (event.target.closest("[data-tip]")) hide();
    });

    // Keyboard and touch: focus opens it, a second tap or Escape closes it.
    document.addEventListener("focusin", function (event) {
      var host = event.target.closest("[data-tip]");
      if (host) show(host);
    });
    document.addEventListener("focusout", hide);

    document.addEventListener("click", function (event) {
      var host = event.target.closest("[data-tip]");
      if (!host) { hide(); return; }
      event.preventDefault();
      if (current === host) hide();
      else show(host);
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") hide();
    });

    window.addEventListener("scroll", hide, { passive: true });
  }

  /* -- search ------------------------------------------------------------ */

  function initSearch() {
    var input = document.getElementById("siteSearch");
    var results = document.getElementById("searchResults");
    if (!input || !results) return;

    var entries = null;
    var cursor = -1;
    var shown = [];

    function ensureIndex() {
      if (entries) return Promise.resolve(entries);
      return fetch("/api/search")
        .then(function (r) { return r.json(); })
        .then(function (payload) {
          entries = payload.entries;
          return entries;
        })
        .catch(function () { entries = []; return entries; });
    }

    function score(entry, needle) {
      var name = entry.n.toLowerCase();
      var full = (entry.f || "").toLowerCase();
      if (name === needle) return 0;
      if (name.indexOf(needle) === 0) return 1;
      if (full.indexOf(needle) === 0) return 2;
      if (name.indexOf(needle) !== -1) return 3;
      if (full.indexOf(needle) !== -1) return 4;
      return -1;
    }

    function render(list) {
      shown = list;
      cursor = -1;

      if (!input.value.trim()) { results.innerHTML = ""; return; }
      if (!list.length) {
        results.innerHTML = '<div class="search__empty">No players or dates found</div>';
        return;
      }

      results.innerHTML = list.map(function (entry, i) {
        if (entry.t === "p") {
          var avatar = entry.i
            ? '<img src="/static/player_pics_thumbs/' +
              encodeURIComponent(entry.n) + '.webp" alt="">'
            : '<span class="avatar-fallback">' +
              entry.n.slice(0, 2).toUpperCase() + "</span>";
          return (
            '<div class="search__item" role="option" data-i="' + i + '">' + avatar +
            "<span>" + entry.n + (entry.f ? ' <span class="muted">' + entry.f + "</span>" : "") +
            '</span><span class="meta">' + entry.g + " G" +
            (entry.r !== null && entry.r !== undefined ? " · " + entry.r : "") +
            "</span></div>"
          );
        }
        return (
          '<div class="search__item" role="option" data-i="' + i + '">' +
          '<span class="avatar-fallback">' + (entry.f || "") + "</span>" +
          "<span>" + entry.n + '</span><span class="meta">' + entry.g + " games</span></div>"
        );
      }).join("");
    }

    function go(entry) {
      if (!entry) return;
      window.location.href =
        entry.t === "p"
          ? "/player/" + encodeURIComponent(entry.n)
          : "/date/" + encodeURIComponent(entry.n);
    }

    function update() {
      var needle = input.value.trim().toLowerCase();
      if (!needle) { render([]); return; }

      ensureIndex().then(function (all) {
        var scored = [];
        for (var i = 0; i < all.length; i++) {
          var s = score(all[i], needle);
          if (s >= 0) scored.push([s, all[i]]);
        }
        scored.sort(function (a, b) {
          if (a[0] !== b[0]) return a[0] - b[0];
          return (b[1].g || 0) - (a[1].g || 0);
        });
        render(scored.slice(0, 8).map(function (pair) { return pair[1]; }));
      });
    }

    input.addEventListener("focus", ensureIndex);
    input.addEventListener("input", update);

    input.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        if (!shown.length) return;
        cursor += event.key === "ArrowDown" ? 1 : -1;
        if (cursor < 0) cursor = shown.length - 1;
        if (cursor >= shown.length) cursor = 0;
        results.querySelectorAll(".search__item").forEach(function (node, i) {
          node.setAttribute("aria-selected", i === cursor ? "true" : "false");
        });
      } else if (event.key === "Enter") {
        event.preventDefault();
        go(shown[cursor >= 0 ? cursor : 0]);
      } else if (event.key === "Escape") {
        input.value = "";
        render([]);
        input.blur();
      }
    });

    results.addEventListener("mousedown", function (event) {
      var item = event.target.closest(".search__item");
      if (item) { event.preventDefault(); go(shown[Number(item.dataset.i)]); }
    });

    document.addEventListener("click", function (event) {
      if (!event.target.closest(".search")) render([]);
    });

    // "/" focuses search, the way it does on most stats sites.
    document.addEventListener("keydown", function (event) {
      if (event.key === "/" && document.activeElement !== input &&
          !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) {
        event.preventDefault();
        input.focus();
      }
    });
  }

  /* -- boot -------------------------------------------------------------- */

  document.addEventListener("DOMContentLoaded", function () {
    var toggle = document.getElementById("themeToggle");
    if (toggle) toggle.addEventListener("click", NN.toggleTheme);

    document.querySelectorAll("[role=tablist]").forEach(function (list) {
      initTabs(list.parentNode);
    });

    // Standalone tables that aren't inside a tab panel.
    document.querySelectorAll("[data-table]").forEach(function (host) {
      if (host.closest("[role=tabpanel]")) return;
      var table = new NN.DataTable(host, {
        name: host.dataset.table,
        url: host.dataset.url || "/api/table/" + host.dataset.table,
        defaultSort: host.dataset.sort || null
      });
      table.load();
    });

    // Charts outside any tab panel.
    document.querySelectorAll("[data-chart]").forEach(function (host) {
      if (host.closest("[role=tabpanel]")) return;
      if (NN.renderChart) NN.renderChart(host);
    });

    wireFilters();
    initSearch();
    initTooltips();
  });
})(window, document);
