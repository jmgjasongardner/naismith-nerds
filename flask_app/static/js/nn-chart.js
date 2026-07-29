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

    /* Everything data-bearing is clipped to the plot rectangle.
       The y-domain covers only the selected series, so unselected context
       lines routinely fall outside it — without clipping they render past the
       axis and wash over the x-labels. Zoomed selections overflow the same
       way. */
    var clipId = "nn-plot-clip-" + (LineChart._seq = (LineChart._seq || 0) + 1);
    var defs = el("defs", {}, svg);
    var clipPath = el("clipPath", { id: clipId }, defs);
    el("rect", { x: pad.l, y: pad.t, width: plotW, height: plotH }, clipPath);

    var dataLayer = el("g", { "clip-path": "url(#" + clipId + ")" }, svg);

    // Context lines first so selected series draw over them.
    if (config.selectable) {
      var group = el("g", {}, dataLayer);
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
      el("path", attrs, dataLayer);
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
     Player scatter

     One point per rated player, drawn as their photo. Which field goes on
     each axis and which drives the dot size are all chosen by the viewer,
     so this is really a small exploration tool rather than a fixed chart.
     ====================================================================== */

  function PlayerScatter(host, data) {
    this.host = host;
    this.fields = data.fields;
    this.players = data.players;

    var keys = data.fields.map(function (f) { return f.key; });
    var pick = function (wanted, fallback) {
      return keys.indexOf(wanted) !== -1 ? wanted : keys[fallback] || keys[0];
    };
    this.x = pick("rating", 0);
    this.y = pick("win_pct", 1);
    this.size = pick("games_played", 2);

    // Null means "fit to the data"; a pair means the viewer zoomed to a box.
    this.xDomain = null;
    this.yDomain = null;

    host.innerHTML = "";
    this.buildControls();
    this.plot = document.createElement("div");
    this.plot.className = "chart";
    host.appendChild(this.plot);
    this.render();
  }

  PlayerScatter.prototype.buildControls = function () {
    var self = this;
    var options = this.fields.map(function (f) {
      return '<option value="' + esc(f.key) + '">' + esc(f.label) + "</option>";
    }).join("");

    var bar = document.createElement("div");
    bar.className = "chart-toolbar";
    bar.innerHTML =
      ["x", "y", "size"].map(function (axis) {
        var label = axis === "size" ? "Dot size" : axis.toUpperCase() + " axis";
        return (
          '<label class="field">' + label +
          '<select class="select scatter-' + axis + '">' + options + "</select></label>"
        );
      }).join("") +
      '<button class="btn scatter-reset" type="button" hidden>Reset zoom</button>' +
      '<span class="chart-hint muted">Drag a box to zoom · double-click to reset · 20+ games</span>';
    this.host.appendChild(bar);

    ["x", "y", "size"].forEach(function (axis) {
      var select = bar.querySelector(".scatter-" + axis);
      select.value = self[axis];
      select.addEventListener("change", function () {
        self[axis] = this.value;
        // A zoom is expressed in the old field's units, so it cannot survive
        // an axis change.
        self.resetZoom(true);
      });
    });

    this.resetBtn = bar.querySelector(".scatter-reset");
    this.resetBtn.addEventListener("click", function () { self.resetZoom(); });
  };

  PlayerScatter.prototype.resetZoom = function (skipRenderGuard) {
    this.xDomain = null;
    this.yDomain = null;
    if (this.resetBtn) this.resetBtn.hidden = true;
    this.render();
  };

  PlayerScatter.prototype.zoomTo = function (xd, yd) {
    this.xDomain = xd;
    this.yDomain = yd;
    if (this.resetBtn) this.resetBtn.hidden = false;
    this.render();
  };

  PlayerScatter.prototype.field = function (key) {
    return this.fields.filter(function (f) { return f.key === key; })[0];
  };

  PlayerScatter.prototype.render = function () {
    var self = this;
    var keys = this.fields.map(function (f) { return f.key; });
    var xi = keys.indexOf(this.x), yi = keys.indexOf(this.y), si = keys.indexOf(this.size);
    var xf = this.field(this.x), yf = this.field(this.y), sf = this.field(this.size);

    var points = this.players.filter(function (p) {
      return p.v[xi] !== null && p.v[yi] !== null;
    });

    this.plot.innerHTML = "";
    this.plot.style.position = "relative";

    var width = Math.max(this.plot.clientWidth || this.host.clientWidth || 700, 300);
    var height = 520;
    var pad = { t: 16, r: 20, b: 52, l: 62 };
    var plotW = width - pad.l - pad.r;
    var plotH = height - pad.t - pad.b;

    var svg = el("svg", {
      viewBox: "0 0 " + width + " " + height, width: "100%", height: height,
      role: "img", "aria-label": yf.label + " versus " + xf.label
    }, this.plot);

    // One reusable clip so each photo renders as a circle.
    var defs = el("defs", {}, svg);
    var clip = el("clipPath", { id: "nn-dot-clip", clipPathUnits: "objectBoundingBox" }, defs);
    el("circle", { cx: 0.5, cy: 0.5, r: 0.5 }, clip);

    var tip = document.createElement("div");
    tip.className = "chart-tooltip";
    this.plot.appendChild(tip);

    function extent(index) {
      var lo = Infinity, hi = -Infinity;
      points.forEach(function (p) {
        var v = p.v[index];
        if (v === null || v === undefined) return;
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      });
      if (!isFinite(lo)) { lo = 0; hi = 1; }
      if (lo === hi) { lo -= 1; hi += 1; }
      var padding = (hi - lo) * 0.08;
      return [lo - padding, hi + padding];
    }

    var xd = this.xDomain || extent(xi);
    var yd = this.yDomain || extent(yi);

    function sx(v) { return pad.l + ((v - xd[0]) / (xd[1] - xd[0])) * plotW; }
    function sy(v) { return pad.t + (1 - (v - yd[0]) / (yd[1] - yd[0])) * plotH; }
    function invX(px) { return xd[0] + ((px - pad.l) / plotW) * (xd[1] - xd[0]); }
    function invY(py) { return yd[0] + (1 - (py - pad.t) / plotH) * (yd[1] - yd[0]); }

    function fmt(value, field) {
      if (value === null || value === undefined) return "—";
      if (field.type === "pct") return (value * 100).toFixed(field.dp) + "%";
      if (field.type === "int") return String(value);
      return Number(value).toFixed(field.dp);
    }

    /* Grid and axes */
    niceTicks(yd[0], yd[1], 5).forEach(function (t) {
      el("line", { x1: pad.l, x2: pad.l + plotW, y1: sy(t), y2: sy(t), class: "chart-grid" }, svg);
      el("text", { x: pad.l - 8, y: sy(t) + 3, "text-anchor": "end", class: "chart-label" },
        svg).textContent = fmt(t, yf);
    });
    niceTicks(xd[0], xd[1], 6).forEach(function (t) {
      el("line", { x1: sx(t), x2: sx(t), y1: pad.t, y2: pad.t + plotH, class: "chart-grid" }, svg);
      el("text", { x: sx(t), y: height - 30, "text-anchor": "middle", class: "chart-label" },
        svg).textContent = fmt(t, xf);
    });

    if (xd[0] < 0 && xd[1] > 0) {
      el("line", { x1: sx(0), x2: sx(0), y1: pad.t, y2: pad.t + plotH, class: "chart-zero" }, svg);
    }
    if (yd[0] < 0 && yd[1] > 0) {
      el("line", { x1: pad.l, x2: pad.l + plotW, y1: sy(0), y2: sy(0), class: "chart-zero" }, svg);
    }

    /* Dot radius. Min-max normalised rather than proportional, because a
       size field can be negative (rating) or near-constant, and area scaling
       on raw values would then break or collapse. */
    var sLo = Infinity, sHi = -Infinity;
    points.forEach(function (p) {
      var v = p.v[si];
      if (v === null || v === undefined) return;
      if (v < sLo) sLo = v;
      if (v > sHi) sHi = v;
    });
    var MIN_R = 9, MAX_R = 30;
    function radius(v) {
      if (v === null || v === undefined || sHi === sLo) return (MIN_R + MAX_R) / 2;
      // sqrt so the *area* tracks the value, which is how people read bubbles.
      var frac = Math.sqrt((v - sLo) / (sHi - sLo));
      return MIN_R + frac * (MAX_R - MIN_R);
    }

    // Points are clipped to the plot box so a zoom doesn't scatter photos
    // across the axes and margins.
    var clipId = "nn-scatter-clip-" + (PlayerScatter._seq = (PlayerScatter._seq || 0) + 1);
    var clipPath = el("clipPath", { id: clipId }, defs);
    el("rect", { x: pad.l, y: pad.t, width: plotW, height: plotH }, clipPath);
    var dataLayer = el("g", { "clip-path": "url(#" + clipId + ")" }, svg);

    function hideTip() { tip.setAttribute("data-visible", "false"); }

    // Biggest first, so small dots land on top and stay clickable.
    var ordered = points.slice().sort(function (a, b) {
      return radius(b.v[si]) - radius(a.v[si]);
    });

    ordered.forEach(function (p) {
      var r = radius(p.v[si]);
      var cx = sx(p.v[xi]), cy = sy(p.v[yi]);

      var g = el("a", {
        class: "scatter-dot", href: "/player/" + encodeURIComponent(p.n)
      }, dataLayer);

      if (p.i) {
        el("image", {
          href: "/static/player_pics_thumbs/" + encodeURIComponent(p.n) + ".webp",
          x: cx - r, y: cy - r, width: r * 2, height: r * 2,
          preserveAspectRatio: "xMidYMid slice",
          "clip-path": "url(#nn-dot-clip)"
        }, g);
      } else {
        el("circle", { cx: cx, cy: cy, r: r, class: "scatter-dot__fallback" }, g);
        el("text", {
          x: cx, y: cy + r * 0.3, "text-anchor": "middle",
          class: "scatter-dot__initials", "font-size": Math.max(9, r * 0.75)
        }, g).textContent = p.n.slice(0, 2).toUpperCase();
      }

      el("circle", { cx: cx, cy: cy, r: r, class: "scatter-dot__ring" }, g);

      g.addEventListener("mouseenter", function (event) {
        g.parentNode.appendChild(g);   // bring to front while hovered
        var box = svg.getBoundingClientRect();
        tip.innerHTML =
          '<div class="chart-tooltip__head">' + esc(p.n) + "</div>" +
          "<div>" + esc(xf.label) + " <strong>" + fmt(p.v[xi], xf) + "</strong></div>" +
          "<div>" + esc(yf.label) + " <strong>" + fmt(p.v[yi], yf) + "</strong></div>" +
          "<div>" + esc(sf.label) + " <strong>" + fmt(p.v[si], sf) + "</strong></div>";
        tip.setAttribute("data-visible", "true");
        var tb = tip.getBoundingClientRect();
        tip.style.left = Math.min(Math.max(event.clientX - box.left - tb.width / 2, 4),
          self.plot.clientWidth - tb.width - 4) + "px";
        tip.style.top = Math.max(event.clientY - box.top - tb.height - 14, 4) + "px";
      });
      g.addEventListener("mouseleave", hideTip);
    });

    /* The tooltip used to hang around until another dot was hovered, because
       only the dots dismissed it. Anything that means "I'm done looking"
       now clears it. */
    this.plot.addEventListener("mouseleave", hideTip);
    svg.addEventListener("mouseleave", hideTip);

    // Every axis change re-renders, so document-level listeners have to be
    // torn down or they pile up, each holding a detached tooltip.
    if (this._cleanup) this._cleanup();
    document.addEventListener("click", hideTip);
    window.addEventListener("scroll", hideTip, { passive: true });
    this._cleanup = function () {
      document.removeEventListener("click", hideTip);
      window.removeEventListener("scroll", hideTip);
    };

    /* Drag a box to zoom into it; double-click anywhere to zoom back out. */
    var band = el("rect", { class: "chart-band", opacity: 0 }, svg);
    var surface = el("rect", {
      x: pad.l, y: pad.t, width: plotW, height: plotH,
      fill: "transparent", style: "cursor:crosshair"
    }, svg);
    // Behind the dots, so clicking a player still opens their page.
    svg.insertBefore(surface, dataLayer);
    svg.insertBefore(band, dataLayer);

    var from = null;

    function pointAt(event) {
      var box = svg.getBoundingClientRect();
      var scale = width / box.width;
      return {
        px: Math.min(Math.max((event.clientX - box.left) * scale, pad.l), pad.l + plotW),
        py: Math.min(Math.max((event.clientY - box.top) * scale, pad.t), pad.t + plotH)
      };
    }

    function finish(event) {
      if (!from) return;
      var to = pointAt(event);
      var x0 = Math.min(from.px, to.px), x1 = Math.max(from.px, to.px);
      var y0 = Math.min(from.py, to.py), y1 = Math.max(from.py, to.py);
      from = null;
      band.setAttribute("opacity", 0);
      window.removeEventListener("mousemove", drag);
      window.removeEventListener("mouseup", finish);

      // Ignore an accidental nudge; a real box needs some area.
      if (x1 - x0 < 12 || y1 - y0 < 12) return;
      self.zoomTo([invX(x0), invX(x1)], [invY(y1), invY(y0)]);
    }

    function drag(event) {
      if (!from) return;
      var to = pointAt(event);
      band.setAttribute("x", Math.min(from.px, to.px));
      band.setAttribute("y", Math.min(from.py, to.py));
      band.setAttribute("width", Math.abs(to.px - from.px));
      band.setAttribute("height", Math.abs(to.py - from.py));
      band.setAttribute("opacity", 1);
    }

    svg.addEventListener("mousedown", function (event) {
      if (event.button !== 0) return;
      from = pointAt(event);
      hideTip();
      window.addEventListener("mousemove", drag);
      window.addEventListener("mouseup", finish);
      event.preventDefault();
    });

    svg.addEventListener("dblclick", function () { self.resetZoom(); });

    /* Axis titles */
    el("text", {
      x: pad.l + plotW / 2, y: height - 8, "text-anchor": "middle", class: "chart-axis-title"
    }, svg).textContent = xf.label;
    el("text", {
      x: 14, y: pad.t + plotH / 2, "text-anchor": "middle", class: "chart-axis-title",
      transform: "rotate(-90 14 " + (pad.t + plotH / 2) + ")"
    }, svg).textContent = yf.label;

    var note = this.host.querySelector(".scatter-note");
    if (!note) {
      note = document.createElement("p");
      note.className = "scatter-note muted";
      this.host.appendChild(note);
    }
    note.textContent =
      points.length + " players · dot size is " + sf.label + " · click any player to open their page";
  };

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

    "player-scatter": function (host, url) {
      return fetch(url).then(function (r) { return r.json(); }).then(function (data) {
        new PlayerScatter(host, data);
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
