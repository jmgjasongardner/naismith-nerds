/* ==========================================================================
   Data table

   Fetches a column-oriented payload, then sorts, filters and renders it.

   Only the rows near the viewport are in the DOM. Two spacer rows stand in for
   everything scrolled past and everything still below, so the scrollbar
   reflects the whole dataset while the row count stays constant. Without this
   the Opponents table alone would put 10,441 rows on the page.
   ========================================================================== */

(function (window, document) {
  "use strict";

  var OVERSCAN = 8;          // rows rendered beyond the viewport, each way
  var FALLBACK_ROW_H = 33;   // used until a real row can be measured

  function esc(value) {
    return String(value).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function initials(name) {
    return String(name).slice(0, 2).toUpperCase();
  }

  /* -- cell rendering ---------------------------------------------------- */

  function formatNumber(value, dp) {
    if (value === null || value === undefined || value === "") return "";
    var num = Number(value);
    if (!isFinite(num)) return "";
    return num.toFixed(dp);
  }

  function renderCell(value, col) {
    if (value === null || value === undefined || value === "") {
      return '<span class="muted">—</span>';
    }

    switch (col.type) {
      case "player": {
        var name = esc(value);
        var avatar = window.NN.hasThumb(value)
          ? '<img loading="lazy" src="/static/player_pics_thumbs/' +
            encodeURIComponent(value) + '.webp" alt="">'
          : '<span class="avatar-fallback">' + esc(initials(value)) + "</span>";
        return (
          '<a class="cell-player" href="/player/' + encodeURIComponent(value) + '">' +
          avatar + "<span>" + name + "</span></a>"
        );
      }
      case "pairing": {
        // "A - B" — link each name to its own page rather than the pair.
        var names = String(value).split(" - ");
        return names.map(function (name) {
          return '<a href="/player/' + encodeURIComponent(name) + '">' + esc(name) + "</a>";
        }).join(' <span class="muted">–</span> ');
      }
      case "date":
        return '<a href="/date/' + encodeURIComponent(value) + '">' + esc(value) + "</a>";
      case "pct":
        return formatNumber(Number(value) * 100, col.dp || 1) + "%";
      case "signed": {
        var n = Number(value);
        var cls = n > 0 ? "pos" : n < 0 ? "neg" : "muted";
        var sign = n > 0 ? "+" : "";
        return '<span class="' + cls + '">' + sign + formatNumber(n, col.dp || 2) + "</span>";
      }
      case "num":
        return formatNumber(value, col.dp || 2);
      case "int":
        return String(value);
      case "bool":
        return value ? "Yes" : "No";
      default:
        return esc(value);
    }
  }

  /* -- the table --------------------------------------------------------- */

  function DataTable(root, options) {
    this.root = root;
    this.url = options.url;
    this.name = options.name;
    this.defaultSort = options.defaultSort || null;

    this.cols = [];
    this.rows = [];      // every row, as loaded
    this.view = [];      // indices into rows, after filter + sort
    this.sortIndex = -1;
    this.sortDesc = true;
    this.rowHeight = FALLBACK_ROW_H;
    this.loaded = false;
    this.loading = false;

    this.filters = { query: "", minGames: 0, activeOnly: false };

    this.root.innerHTML = '<div class="loading">Loading</div>';
  }

  DataTable.prototype.load = function () {
    var self = this;
    if (this.loaded || this.loading) return Promise.resolve();
    this.loading = true;

    return fetch(this.url)
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(function (payload) {
        self.cols = payload.cols;
        self.rows = payload.rows;
        self.loaded = true;
        self.loading = false;

        self.colIndex = {};
        self.cols.forEach(function (col, i) { self.colIndex[col.key] = i; });

        self.buildShell();

        var initial = self.defaultSort && self.colIndex[self.defaultSort] !== undefined
          ? self.colIndex[self.defaultSort]
          : -1;
        if (initial >= 0) {
          self.sortIndex = initial;
          self.sortDesc = true;
        }
        self.apply();
      })
      .catch(function (error) {
        self.loading = false;
        self.root.innerHTML =
          '<div class="empty-state">Could not load this table.<br>' +
          '<span class="muted">' + esc(error.message) + "</span></div>";
      });
  };

  DataTable.prototype.buildShell = function () {
    var head = this.cols.map(function (col, i) {
      return (
        '<th data-i="' + i + '"' +
        (col.tip ? ' title="' + esc(col.tip) + '"' : "") +
        ">" + esc(col.label) + '<span class="sort-ind"></span></th>'
      );
    }).join("");

    this.root.innerHTML =
      '<div class="table-scroll">' +
        '<table class="data">' +
          "<thead><tr>" + head + "</tr></thead>" +
          '<tbody><tr class="spacer-top"><td colspan="' + this.cols.length + '"></td></tr>' +
          '<tr class="spacer-bot"><td colspan="' + this.cols.length + '"></td></tr></tbody>' +
        "</table>" +
      "</div>" +
      '<div class="table-foot"><span class="row-count"></span>' +
      '<span class="spacer"></span>' +
      '<button class="btn btn-csv" type="button">Export CSV</button></div>';

    this.scroller = this.root.querySelector(".table-scroll");
    this.tbody = this.root.querySelector("tbody");
    this.spacerTop = this.root.querySelector(".spacer-top");
    this.spacerBot = this.root.querySelector(".spacer-bot");
    this.countEl = this.root.querySelector(".row-count");

    var self = this;

    this.root.querySelector("thead").addEventListener("click", function (event) {
      var th = event.target.closest("th");
      if (!th) return;
      var index = Number(th.dataset.i);
      if (self.sortIndex === index) {
        self.sortDesc = !self.sortDesc;
      } else {
        self.sortIndex = index;
        // Names read best A-Z; measurements read best highest-first.
        var type = self.cols[index].type;
        self.sortDesc = !(type === "player" || type === "text");
      }
      self.apply();
    });

    this.scroller.addEventListener("scroll", function () {
      self.paint();
    }, { passive: true });

    this.root.querySelector(".btn-csv").addEventListener("click", function () {
      self.exportCsv();
    });
  };

  DataTable.prototype.setFilters = function (filters) {
    Object.assign(this.filters, filters);
    if (this.loaded) this.apply();
  };

  DataTable.prototype.matches = function (row) {
    var f = this.filters;

    if (f.minGames > 0) {
      var gi = this.colIndex.games_played;
      if (gi !== undefined && Number(row[gi]) < f.minGames) return false;
    }

    if (f.activeOnly) {
      var ai = this.colIndex.active_player;
      if (ai !== undefined && !row[ai]) return false;
    }

    if (f.query) {
      var needle = f.query.toLowerCase();
      var found = false;
      for (var i = 0; i < row.length; i++) {
        var type = this.cols[i].type;
        if (type !== "player" && type !== "text" && type !== "date") continue;
        if (row[i] && String(row[i]).toLowerCase().indexOf(needle) !== -1) {
          found = true;
          break;
        }
      }
      if (!found) return false;
    }

    return true;
  };

  DataTable.prototype.apply = function () {
    var self = this;

    this.view = [];
    for (var i = 0; i < this.rows.length; i++) {
      if (this.matches(this.rows[i])) this.view.push(i);
    }

    if (this.sortIndex >= 0) {
      var si = this.sortIndex;
      var dir = this.sortDesc ? -1 : 1;
      var numeric = ["int", "num", "signed", "pct"].indexOf(this.cols[si].type) !== -1;

      this.view.sort(function (a, b) {
        var x = self.rows[a][si];
        var y = self.rows[b][si];

        // Missing values sort last regardless of direction.
        var xEmpty = x === null || x === undefined || x === "";
        var yEmpty = y === null || y === undefined || y === "";
        if (xEmpty && yEmpty) return 0;
        if (xEmpty) return 1;
        if (yEmpty) return -1;

        if (numeric) return (Number(x) - Number(y)) * dir;
        return String(x).localeCompare(String(y)) * dir;
      });
    }

    this.root.querySelectorAll("thead th").forEach(function (th, i) {
      var indicator = th.querySelector(".sort-ind");
      indicator.textContent = i === self.sortIndex ? (self.sortDesc ? "▼" : "▲") : "";
      th.setAttribute("aria-sort",
        i === self.sortIndex ? (self.sortDesc ? "descending" : "ascending") : "none");
    });

    this.countEl.textContent =
      this.view.length.toLocaleString() +
      (this.view.length === this.rows.length
        ? " rows"
        : " of " + this.rows.length.toLocaleString() + " rows");

    this.scroller.scrollTop = 0;
    this.paint(true);
  };

  DataTable.prototype.paint = function (force) {
    var total = this.view.length;

    if (total === 0) {
      this.spacerTop.style.display = "none";
      this.spacerBot.style.display = "none";
      this.clearRows();
      if (!this.emptyRow) {
        this.emptyRow = document.createElement("tr");
        this.emptyRow.innerHTML =
          '<td colspan="' + this.cols.length + '">' +
          '<div class="empty-state">Nothing matches these filters.</div></td>';
      }
      this.tbody.insertBefore(this.emptyRow, this.spacerBot);
      return;
    }
    if (this.emptyRow && this.emptyRow.parentNode) {
      this.tbody.removeChild(this.emptyRow);
    }
    this.spacerTop.style.display = "";
    this.spacerBot.style.display = "";

    var viewportH = this.scroller.clientHeight || 500;
    var scrollTop = this.scroller.scrollTop;

    var first = Math.max(0, Math.floor(scrollTop / this.rowHeight) - OVERSCAN);
    var visible = Math.ceil(viewportH / this.rowHeight) + OVERSCAN * 2;
    var last = Math.min(total, first + visible);

    if (!force && this.firstRendered === first && this.lastRendered === last) return;
    this.firstRendered = first;
    this.lastRendered = last;

    var html = "";
    for (var i = first; i < last; i++) {
      var row = this.rows[this.view[i]];
      html += "<tr>";
      for (var c = 0; c < this.cols.length; c++) {
        html += "<td>" + renderCell(row[c], this.cols[c]) + "</td>";
      }
      html += "</tr>";
    }

    this.clearRows();
    var fragment = document.createElement("tbody");
    fragment.innerHTML = html;
    while (fragment.firstChild) {
      this.tbody.insertBefore(fragment.firstChild, this.spacerBot);
    }

    this.spacerTop.firstElementChild.style.height = first * this.rowHeight + "px";
    this.spacerBot.firstElementChild.style.height =
      Math.max(0, (total - last) * this.rowHeight) + "px";

    // Measure a real row once so the spacers match actual layout.
    if (!this.measured) {
      var sample = this.spacerTop.nextElementSibling;
      if (sample && sample !== this.spacerBot) {
        var height = sample.getBoundingClientRect().height;
        if (height > 4 && Math.abs(height - this.rowHeight) > 0.5) {
          this.rowHeight = height;
          this.measured = true;
          this.paint(true);
          return;
        }
        this.measured = true;
      }
    }
  };

  DataTable.prototype.clearRows = function () {
    var node = this.spacerTop.nextElementSibling;
    while (node && node !== this.spacerBot) {
      var next = node.nextElementSibling;
      this.tbody.removeChild(node);
      node = next;
    }
  };

  DataTable.prototype.exportCsv = function () {
    var self = this;
    var lines = [this.cols.map(function (col) { return '"' + col.label + '"'; }).join(",")];

    this.view.forEach(function (index) {
      var row = self.rows[index];
      lines.push(row.map(function (value) {
        if (value === null || value === undefined) return "";
        var text = String(value);
        return /[",\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
      }).join(","));
    });

    var blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
    var link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "naismith-nerds-" + this.name + ".csv";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);
  };

  window.NN = window.NN || {};
  window.NN.DataTable = DataTable;
})(window, document);
