/* ==========================================================================
   Charts — plain SVG, no library.

   Replaces the Plotly blobs the old site inlined (5.2 MB and 4.9 MB of JSON
   in the HTML). These fetch compact data and draw it.

   Color rules follow the project's data-viz standard:
     - categorical hues assigned in fixed slot order, never cycled blindly
     - past 8 selected series, hues repeat but each repeat carries a distinct
       dash pattern, so identity never rests on color alone
     - unselected series stay as recessive context lines rather than becoming
       86 competing colors, which is what the old chart did
     - magnitude uses one hue, light to dark
   ========================================================================== */

(function (window, document) {
  "use strict";

  var NN = (window.NN = window.NN || {});

  // Validated categorical order. Light and dark are the same eight hues
  // stepped for their own surface, not an automatic flip.
  var SERIES_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
                      "#e87ba4", "#008300", "#4a3aa7", "#e34948"];
  var SERIES_DARK  = ["#3987e5", "#d95926", "#199e70", "#c98500",
                      "#d55181", "#008300", "#9085e9", "#e66767"];

  // One hue, light to dark, for continuous magnitude.
  var SEQ_LIGHT = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"];
  var SEQ_DARK  = ["#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"];

  // Secondary encoding once the eight hues are exhausted.
  var DASHES = ["", "7 3", "2 3", "9 3 2 3"];

  var DEFAULT_SELECTED = 8;

  function isDark() {
    var explicit = document.documentElement.getAttribute("data-theme");
    if (explicit) return explicit === "dark";
    return !window.matchMedia("(prefers-color-scheme: light)").matches;
  }

  function palette() { return isDark() ? SERIES_DARK : SERIES_LIGHT; }
  function sequential() { return isDark() ? SEQ_DARK : SEQ_LIGHT; }

  function styleFor(index) {
    var hues = palette();
    return {
      color: hues[index % hues.length],
      dash: DASHES[Math.floor(index / hues.length) % DASHES.length]
    };
  }

  function esc(v) {
    return String(v).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function el(tag, attrs, parent) {
    var node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (var key in attrs) node.setAttribute(key, attrs[key]);
    if (parent) parent.appendChild(node);
    return node;
  }

  function niceTicks(min, max, count) {
    if (min === max) { min -= 1; max += 1; }
    var raw = (max - min) / count;
    var mag = Math.pow(10, Math.floor(Math.log10(raw)));
    var step = mag;
    [1, 2, 2.5, 5, 10].some(function (m) {
      if (mag * m >= raw) { step = mag * m; return true; }
      return false;
    });
    var ticks = [];
    for (var t = Math.ceil(min / step) * step; t <= max + 1e-9; t += step) {
      ticks.push(Math.round(t * 1e6) / 1e6);
    }
    return ticks;
  }

  /* ======================================================================
     Line chart

     Holds its own state — which series are selected, what x-range is zoomed
     to — and redraws from it, so selection and zoom are just state changes.
     ====================================================================== */

  function LineChart(host, config) {
    this.host = host;
    this.config = config;
    this.height = config.height || 400;

    var names = config.series.map(function (s) { return s.name; });
    this.selected = config.selectable
      ? names.slice(0, Math.min(DEFAULT_SELECTED, names.length))
      : names;

    this.x0 = 0;
    this.x1 = config.x.length - 1;

    host.innerHTML = "";
    if (config.selectable) this.buildToolbar();

    this.plot = document.createElement("div");
    this.plot.className = "chart";
    host.appendChild(this.plot);

    this.legendBox = document.createElement("div");
    this.legendBox.className = "chart-legend";
    host.appendChild(this.legendBox);

    this.render();
  }

  /* -- selection UI ----------------------------------------------------- */

  LineChart.prototype.buildToolbar = function () {
    var self = this;
    var bar = document.createElement("div");
    bar.className = "chart-toolbar";
    bar.innerHTML =
      '<div class="chart-picker">' +
        '<button class="btn chart-picker__toggle" type="button" aria-expanded="false">' +
          'Select players <span class="chart-picker__count"></span>' +
        "</button>" +
        '<div class="chart-picker__menu" hidden>' +
          '<input class="input chart-picker__search" type="search" placeholder="Search…" aria-label="Search players">' +
          '<div class="chart-picker__actions">' +
            '<button class="btn chart-picker__top" type="button">Top 8</button>' +
            '<button class="btn chart-picker__none" type="button">Clear</button>' +
          "</div>" +
          '<div class="chart-picker__list"></div>' +
        "</div>" +
      "</div>" +
      '<button class="btn chart-reset" type="button" hidden>Reset zoom</button>' +
      '<span class="chart-hint muted">Drag across the chart to zoom · double-click to reset</span>';
    this.host.appendChild(bar);

    this.picker = bar.querySelector(".chart-picker");
    this.pickerMenu = bar.querySelector(".chart-picker__menu");
    this.pickerList = bar.querySelector(".chart-picker__list");
    this.pickerCount = bar.querySelector(".chart-picker__count");
    this.resetBtn = bar.querySelector(".chart-reset");

    var toggle = bar.querySelector(".chart-picker__toggle");
    toggle.addEventListener("click", function () {
      var opening = self.pickerMenu.hidden;
      self.pickerMenu.hidden = !opening;
      toggle.setAttribute("aria-expanded", opening ? "true" : "false");
      if (opening) bar.querySelector(".chart-picker__search").focus();
    });

    document.addEventListener("click", function (event) {
      if (!self.picker.contains(event.target)) {
        self.pickerMenu.hidden = true;
        toggle.setAttribute("aria-expanded", "false");
      }
    });

    bar.querySelector(".chart-picker__search").addEventListener("input", function () {
      self.renderPickerList(this.value.trim().toLowerCase());
    });

    bar.querySelector(".chart-picker__top").addEventListener("click", function () {
      self.selected = self.config.series.slice(0, DEFAULT_SELECTED)
        .map(function (s) { return s.name; });
      self.renderPickerList("");
      self.scheduleRender();
    });

    bar.querySelector(".chart-picker__none").addEventListener("click", function () {
      self.selected = [];
      self.renderPickerList("");
      self.scheduleRender();
    });

    this.pickerList.addEventListener("change", function (event) {
      var box = event.target.closest("input[type=checkbox]");
      if (!box) return;
      if (box.checked) {
        if (self.selected.indexOf(box.value) === -1) self.selected.push(box.value);
      } else {
        self.selected = self.selected.filter(function (n) { return n !== box.value; });
      }
      self.scheduleRender();
    });

    this.resetBtn.addEventListener("click", function () { self.resetZoom(); });

    this.renderPickerList("");
  };

  LineChart.prototype.renderPickerList = function (needle) {
    var self = this;
    var rows = this.config.series.filter(function (s) {
      return !needle || s.name.toLowerCase().indexOf(needle) !== -1;
    });

    this.pickerList.innerHTML = rows.map(function (s) {
      var on = self.selected.indexOf(s.name) !== -1;
      return (
        '<label class="chart-picker__item">' +
        '<input type="checkbox" value="' + esc(s.name) + '"' + (on ? " checked" : "") + ">" +
        "<span>" + esc(s.name) + "</span></label>"
      );
    }).join("") || '<div class="search__empty">No matches</div>';
  };

  /* -- zoom ------------------------------------------------------------- */

  LineChart.prototype.zoomTo = function (i0, i1) {
    if (i1 - i0 < 1) return;   // keep at least two points, or there is no line
    this.x0 = Math.max(0, Math.floor(i0));
    this.x1 = Math.min(this.config.x.length - 1, Math.ceil(i1));
    if (this.resetBtn) this.resetBtn.hidden = false;
    this.render();
  };

  LineChart.prototype.resetZoom = function () {
    this.x0 = 0;
    this.x1 = this.config.x.length - 1;
    if (this.resetBtn) this.resetBtn.hidden = true;
    this.render();
  };

  /* -- drawing ---------------------------------------------------------- */

  /* Coalesce redraws into one animation frame.
     Every checkbox toggle changes state, and a full redraw walks all 86
     series. Ticking several boxes quickly used to queue a redraw each time
     and lock the page up; now they collapse into a single frame. */
  LineChart.prototype.scheduleRender = function () {
    var self = this;
    if (this._pending) return;
    this._pending = true;
    // A timer rather than requestAnimationFrame: rAF is suspended in a
    // background or throttled tab, which would leave the chart permanently
    // stale against a selection the user had already changed.
    window.setTimeout(function () {
      self._pending = false;
      try {
        self.render();
      } catch (error) {
        console.error("[nn-chart] render failed:", error);
      }
    }, 0);
  };

  LineChart.prototype.render = function () {
    var self = this;
    var config = this.config;

    var selectedSet = {};
    this.selected.forEach(function (name, i) { selectedSet[name] = i; });

    this.plot.innerHTML = "";
    this.plot.style.position = "relative";

    var width = Math.max(this.plot.clientWidth || this.host.clientWidth || 700, 300);
    var height = this.height;
    var pad = { t: 12, r: 16, b: 34, l: 48 };
    var plotW = width - pad.l - pad.r;
    var plotH = height - pad.t - pad.b;

    var svg = el("svg", {
      viewBox: "0 0 " + width + " " + height,
      width: "100%", height: height,
      role: "img", "aria-label": config.label || "chart"
    }, this.plot);

    var tip = document.createElement("div");
    tip.className = "chart-tooltip";
    this.plot.appendChild(tip);

    var i0 = this.x0, i1 = this.x1, span = i1 - i0;

    // Y domain covers only what is on screen and, when a selection exists,
    // only the selected series — so zooming actually magnifies instead of
    // leaving everything squashed against one edge.
    var lo = Infinity, hi = -Infinity;
    var anySelected = this.selected.length > 0;
    config.series.forEach(function (s) {
      if (config.selectable && anySelected && selectedSet[s.name] === undefined) return;
      for (var i = i0; i <= i1; i++) {
        var v = s.v[i];
        if (v === null || v === undefined) continue;
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
    });
    if (!isFinite(lo)) { lo = -1; hi = 1; }
    var padY = (hi - lo) * 0.1 || 0.5;
    lo -= padY; hi += padY;

    function sx(i) { return pad.l + (span <= 0 ? plotW / 2 : ((i - i0) / span) * plotW); }
    function sy(v) { return pad.t + (1 - (v - lo) / (hi - lo)) * plotH; }

    niceTicks(lo, hi, 5).forEach(function (tick) {
      var y = sy(tick);
      el("line", { x1: pad.l, x2: pad.l + plotW, y1: y, y2: y, class: "chart-grid" }, svg);
      el("text", { x: pad.l - 7, y: y + 3, "text-anchor": "end", class: "chart-label" },
        svg).textContent = tick;
    });

    if (lo < 0 && hi > 0) {
      el("line", { x1: pad.l, x2: pad.l + plotW, y1: sy(0), y2: sy(0), class: "chart-zero" }, svg);
    }

    var every = Math.max(1, Math.ceil((span + 1) / 6));
    for (var t = i0; t <= i1; t += every) {
      el("text", { x: sx(t), y: height - 10, "text-anchor": "middle", class: "chart-label" },
        svg).textContent = config.formatX ? config.formatX(config.x[t]) : config.x[t];
    }

    function path(series) {
      var d = "", pen = false;
      for (var i = i0; i <= i1; i++) {
        var v = series.v[i];
        if (v === null || v === undefined) { pen = false; continue; }
        d += (pen ? "L" : "M") + sx(i).toFixed(1) + " " + sy(v).toFixed(1) + " ";
        pen = true;
      }
      return d;
    }

    // Context lines first so selected series draw over them.
    if (config.selectable) {
      var group = el("g", {}, svg);
      config.series.forEach(function (s) {
        if (selectedSet[s.name] !== undefined) return;
        el("path", { d: path(s), class: "chart-line-context" }, group);
      });
    }

    var drawn = [];
    this.selected.forEach(function (name, idx) {
      var series = config.series.filter(function (s) { return s.name === name; })[0];
      if (!series) return;
      var style = styleFor(idx);
      var attrs = { d: path(series), class: "chart-line", stroke: style.color };
      if (style.dash) attrs["stroke-dasharray"] = style.dash;
      el("path", attrs, svg);
      drawn.push({ name: name, series: series, style: style });
    });

    /* Legend: always present, names in ink with a color swatch beside them. */
    this.legendBox.innerHTML = drawn.length
      ? drawn.map(function (d) {
          return (
            '<button class="chart-legend__item" type="button" data-name="' + esc(d.name) +
            '" title="Click to remove">' +
            '<span class="chart-legend__swatch" style="background:' + d.style.color + '"></span>' +
            "<span>" + esc(d.name) + "</span></button>"
          );
        }).join("")
      : '<span class="muted" style="font-size:.8rem">No players selected</span>';

    this.legendBox.onclick = function (event) {
      var btn = event.target.closest(".chart-legend__item");
      if (!btn || !config.selectable) return;
      self.selected = self.selected.filter(function (n) { return n !== btn.dataset.name; });
      if (self.pickerList) self.renderPickerList("");
      self.scheduleRender();
    };

    /* Crosshair, tooltip, and drag-to-zoom. */
    var band = el("rect", {
      x: pad.l, y: pad.t, width: 0, height: plotH, class: "chart-band", opacity: 0
    }, svg);
    var rule = el("line", {
      y1: pad.t, y2: pad.t + plotH, class: "chart-crosshair", opacity: 0
    }, svg);
    var hit = el("rect", {
      x: pad.l, y: pad.t, width: plotW, height: plotH,
      fill: "transparent", style: "cursor:crosshair"
    }, svg);

    function indexAt(clientX) {
      var box = svg.getBoundingClientRect();
      var px = (clientX - box.left) * (width / box.width);
      var i = Math.round(((px - pad.l) / plotW) * span + i0);
      return Math.min(Math.max(i, i0), i1);
    }

    var dragFrom = null;

    function finishDrag(event) {
      if (dragFrom === null) return;
      var to = indexAt(event.clientX);
      var a = Math.min(dragFrom, to), b = Math.max(dragFrom, to);
      dragFrom = null;
      band.setAttribute("opacity", 0);
      window.removeEventListener("mouseup", finishDrag);
      if (b - a >= 1) self.zoomTo(a, b);
    }

    hit.addEventListener("mousedown", function (event) {
      dragFrom = indexAt(event.clientX);
      band.setAttribute("opacity", 1);
      band.setAttribute("x", sx(dragFrom));
      band.setAttribute("width", 0);
      window.addEventListener("mouseup", finishDrag);
      event.preventDefault();
    });

    hit.addEventListener("mousemove", function (event) {
      var idx = indexAt(event.clientX);

      if (dragFrom !== null) {
        var a = Math.min(dragFrom, idx), b = Math.max(dragFrom, idx);
        band.setAttribute("x", sx(a));
        band.setAttribute("width", Math.max(0, sx(b) - sx(a)));
        return;
      }

      rule.setAttribute("x1", sx(idx));
      rule.setAttribute("x2", sx(idx));
      rule.setAttribute("opacity", 1);

      var rows = drawn.map(function (d) {
        var v = d.series.v[idx];
        if (v === null || v === undefined) return null;
        return '<div><span class="chart-tooltip__dot" style="background:' + d.style.color +
          '"></span>' + esc(d.name) + " <strong>" +
          (v > 0 ? "+" : "") + v.toFixed(2) + "</strong></div>";
      }).filter(Boolean).slice(0, 12);

      if (!rows.length) { tip.setAttribute("data-visible", "false"); return; }

      var box = svg.getBoundingClientRect();
      tip.innerHTML =
        '<div class="chart-tooltip__head">' +
        esc(config.formatX ? config.formatX(config.x[idx]) : config.x[idx]) +
        "</div>" + rows.join("");
      tip.setAttribute("data-visible", "true");
      var tb = tip.getBoundingClientRect();
      tip.style.left = Math.min(
        Math.max(sx(idx) * (box.width / width) - tb.width / 2, 4),
        self.plot.clientWidth - tb.width - 4
      ) + "px";
      tip.style.top = Math.max(event.clientY - box.top - tb.height - 12, 4) + "px";
    });

    hit.addEventListener("mouseleave", function () {
      rule.setAttribute("opacity", 0);
      tip.setAttribute("data-visible", "false");
    });

    hit.addEventListener("dblclick", function () { self.resetZoom(); });

    if (this.pickerCount) {
      this.pickerCount.textContent =
        "(" + this.selected.length + " of " + config.series.length + ")";
    }
  };

  /* ======================================================================
     Scatter
     ====================================================================== */

  function scatterChart(host, config) {
    host.innerHTML = "";
    host.style.position = "relative";

    var width = Math.max(host.clientWidth || 700, 300);
    var height = config.height || 440;
    var pad = { t: 14, r: 18, b: 48, l: 52 };
    var plotW = width - pad.l - pad.r;
    var plotH = height - pad.t - pad.b;

    var svg = el("svg", {
      viewBox: "0 0 " + width + " " + height, width: "100%", height: height,
      role: "img", "aria-label": config.label || "scatter"
    }, host);

    var tip = document.createElement("div");
    tip.className = "chart-tooltip";
    host.appendChild(tip);

    var points = config.points;
    var all = points.map(function (p) { return p.x; })
      .concat(points.map(function (p) { return p.y; }));
    var span = Math.max(Math.abs(Math.min.apply(null, all)),
                        Math.abs(Math.max.apply(null, all))) * 1.08;
    var lo = -span, hi = span;

    function sx(v) { return pad.l + ((v - lo) / (hi - lo)) * plotW; }
    function sy(v) { return pad.t + (1 - (v - lo) / (hi - lo)) * plotH; }

    niceTicks(lo, hi, 5).forEach(function (tick) {
      el("line", { x1: pad.l, x2: pad.l + plotW, y1: sy(tick), y2: sy(tick), class: "chart-grid" }, svg);
      el("text", { x: pad.l - 7, y: sy(tick) + 3, "text-anchor": "end", class: "chart-label" },
        svg).textContent = tick;
      el("text", { x: sx(tick), y: height - 24, "text-anchor": "middle", class: "chart-label" },
        svg).textContent = tick;
    });

    el("line", {
      x1: sx(lo), y1: sy(lo), x2: sx(hi), y2: sy(hi),
      class: "chart-ref", "stroke-dasharray": "5 4"
    }, svg);

    var maxGames = Math.max.apply(null, points.map(function (p) { return p.g; }));
    var ramp = sequential();
    var wins = points.map(function (p) { return p.w || 0; });
    var wLo = Math.min.apply(null, wins), wHi = Math.max.apply(null, wins);

    points.forEach(function (p) {
      var r = 4 + Math.sqrt(p.g / maxGames) * 11;
      var frac = wHi > wLo ? ((p.w || 0) - wLo) / (wHi - wLo) : 0.5;
      var dot = el("circle", {
        cx: sx(p.x), cy: sy(p.y), r: r,
        fill: ramp[Math.min(ramp.length - 1, Math.floor(frac * ramp.length))],
        class: "chart-bubble"
      }, svg);

      dot.addEventListener("mouseenter", function (event) {
        var box = svg.getBoundingClientRect();
        tip.innerHTML =
          '<div class="chart-tooltip__head">' + esc(p.n) + "</div>" +
          "<div>Rating <strong>" + (p.y > 0 ? "+" : "") + p.y.toFixed(2) + "</strong></div>" +
          "<div>APM <strong>" + (p.x > 0 ? "+" : "") + p.x.toFixed(2) + "</strong></div>" +
          "<div>" + p.g + " games · " + ((p.w || 0) * 100).toFixed(1) + "% wins</div>";
        tip.setAttribute("data-visible", "true");
        var tb = tip.getBoundingClientRect();
        tip.style.left = Math.min(Math.max(event.clientX - box.left - tb.width / 2, 4),
          host.clientWidth - tb.width - 4) + "px";
        tip.style.top = Math.max(event.clientY - box.top - tb.height - 12, 4) + "px";
      });
      dot.addEventListener("mouseleave", function () {
        tip.setAttribute("data-visible", "false");
      });
    });

    el("text", {
      x: pad.l + plotW / 2, y: height - 6, "text-anchor": "middle", class: "chart-axis-title"
    }, svg).textContent = config.xLabel || "";
    el("text", {
      x: 12, y: pad.t + plotH / 2, "text-anchor": "middle", class: "chart-axis-title",
      transform: "rotate(-90 12 " + (pad.t + plotH / 2) + ")"
    }, svg).textContent = config.yLabel || "";
  }

  /* ======================================================================
     Loaders
     ====================================================================== */

  var loaders = {
    "ratings-history": function (host, url) {
      return fetch(url).then(function (r) { return r.json(); }).then(function (data) {
        new LineChart(host, {
          x: data.dates,
          series: data.series,
          height: 420,
          selectable: true,
          label: "Player ratings over time",
          formatX: function (d) { return String(d).slice(0, 7); }
        });
      });
    },

    "rapm-apm": function (host, url) {
      return fetch(url).then(function (r) { return r.json(); }).then(function (data) {
        scatterChart(host, {
          points: data.points,
          label: "Regularized rating versus raw APM",
          xLabel: "APM — avg score diff minus teammate/opponent gap",
          yLabel: "RAPM rating"
        });
      });
    },

    "player-rolling": function (host, url) {
      return fetch(url).then(function (r) { return r.json(); }).then(function (data) {
        new LineChart(host, {
          x: data.x,
          series: data.series,
          height: 360,
          label: "Rolling averages",
          formatX: function (v) { return "G" + v; }
        });
      });
    },

    "player-rating": function (host, url) {
      return fetch(url).then(function (r) { return r.json(); }).then(function (data) {
        if (!data.points || data.points.length < 2) {
          host.innerHTML = '<div class="empty-state">Not enough rating history yet.</div>';
          return;
        }
        new LineChart(host, {
          x: data.points.map(function (p) { return p[0]; }),
          series: [{ name: data.player, v: data.points.map(function (p) { return p[1]; }) }],
          height: 300,
          label: data.player + " rating over time",
          formatX: function (d) { return String(d).slice(0, 7); }
        });
      });
    }
  };

  NN.renderChart = function (host) {
    if (host.dataset.rendered === "1") return;
    host.dataset.rendered = "1";
    host.innerHTML = '<div class="loading">Loading chart</div>';

    var loader = loaders[host.dataset.chart];
    if (!loader) { host.innerHTML = ""; return; }

    loader(host, host.dataset.url).catch(function (error) {
      host.innerHTML = '<div class="empty-state">Could not load this chart.<br>' +
        '<span class="muted">' + esc(error.message) + "</span></div>";
    });
  };

  // Redraw on theme change so the palette re-steps for the new surface.
  new MutationObserver(function () {
    document.querySelectorAll("[data-chart][data-rendered='1']").forEach(function (host) {
      host.dataset.rendered = "0";
      NN.renderChart(host);
    });
  }).observe(document.documentElement, {
    attributes: true, attributeFilter: ["data-theme"]
  });
})(window, document);
