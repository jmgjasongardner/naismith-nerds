/* ==========================================================================
   Team Builder

   Pick an even number of players, then either lock people onto specific teams
   or let every legal split be enumerated and ranked by how close the projected
   spread is to zero.

   Locked players are honored exactly: enumeration only distributes the players
   left unassigned, and only into the seats the locks leave open. The old
   version regenerated from the full selection and quietly ignored the locks,
   which is why assignments appeared not to stick.
   ========================================================================== */

(function (window, document) {
  "use strict";

  var MAX_COMBOS_SHOWN = 300;

  function combinations(items, k) {
    var out = [];
    (function walk(start, picked) {
      if (picked.length === k) { out.push(picked.slice()); return; }
      // Stop early when too few items remain to ever reach k.
      if (items.length - start < k - picked.length) return;
      for (var i = start; i < items.length; i++) {
        picked.push(items[i]);
        walk(i + 1, picked);
        picked.pop();
      }
    })(0, []);
    return out;
  }

  function sum(players) {
    return players.reduce(function (total, p) { return total + p.rating; }, 0);
  }

  function fmt(value) {
    return (value > 0 ? "+" : "") + value.toFixed(2);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.getElementById("teamBuilder");
    if (!root) return;

    var roster = JSON.parse(document.getElementById("nn-roster").textContent);
    var state = {};   // player name -> "OFF" | "ON" | "T1" | "T2"
    roster.forEach(function (p) { state[p.player] = "OFF"; });

    var listEl    = document.getElementById("tbList");
    var searchEl  = document.getElementById("tbSearch");
    var summaryEl = document.getElementById("tbSummary");
    var combosEl  = document.getElementById("tbCombos");
    var noteEl    = document.getElementById("tbNote");

    function selected() {
      return roster.filter(function (p) { return state[p.player] !== "OFF"; });
    }

    function byStatus(status) {
      return roster.filter(function (p) { return state[p.player] === status; });
    }

    function renderList() {
      var needle = (searchEl.value || "").trim().toLowerCase();
      var visible = roster.filter(function (p) {
        return !needle || p.player.toLowerCase().indexOf(needle) !== -1;
      });

      listEl.innerHTML = visible.map(function (p) {
        var status = state[p.player];
        return (
          '<tr data-player="' + p.player.replace(/"/g, "&quot;") + '">' +
          '<td>' + p.player + "</td>" +
          '<td class="' + (p.rating > 0 ? "pos" : p.rating < 0 ? "neg" : "muted") + '">' +
            fmt(p.rating) + "</td>" +
          "<td>" + p.games + "</td>" +
          '<td><select class="select tb-status" aria-label="Status for ' + p.player + '">' +
            ['OFF', 'ON', 'T1', 'T2'].map(function (option) {
              var label = option === "T1" ? "Team 1" : option === "T2" ? "Team 2" : option;
              return '<option value="' + option + '"' +
                (status === option ? " selected" : "") + ">" + label + "</option>";
            }).join("") +
          "</select></td></tr>"
        );
      }).join("");
    }

    function renderSummary() {
      var chosen = selected();
      var t1 = byStatus("T1");
      var t2 = byStatus("T2");
      var free = byStatus("ON");

      summaryEl.innerHTML =
        '<div class="stat-row" style="margin:0">' +
        tile("Selected", chosen.length, chosen.length % 2 === 0 && chosen.length >= 2 && chosen.length <= 10
              ? (chosen.length / 2) + " per side" : "need an even 2–10") +
        tile("Team 1", t1.length, fmt(sum(t1))) +
        tile("Team 2", t2.length, fmt(sum(t2))) +
        tile("Unassigned", free.length, fmt(sum(free))) +
        tile("Spread", fmt(sum(t1) - sum(t2)), "Team 1 − Team 2") +
        "</div>";

      var ok = chosen.length >= 2 && chosen.length <= 10 && chosen.length % 2 === 0;
      var overfilled = t1.length > chosen.length / 2 || t2.length > chosen.length / 2;

      document.getElementById("tbGenerate").disabled = !ok || overfilled;

      if (!chosen.length) {
        noteEl.textContent = "Set players to ON, Team 1 or Team 2 to begin.";
      } else if (!ok) {
        noteEl.textContent =
          "Select an even number of players between 2 and 10 — currently " + chosen.length + ".";
      } else if (overfilled) {
        noteEl.textContent =
          "Too many players locked to one side for " + chosen.length + " players.";
      } else {
        noteEl.textContent =
          "Ready: " + chosen.length + " players, " + free.length + " left to distribute.";
      }
    }

    function tile(label, value, meta) {
      return (
        '<div class="stat-tile"><div class="stat-tile__label">' + label + "</div>" +
        '<div class="stat-tile__value">' + value + "</div>" +
        '<div class="stat-tile__meta">' + (meta || "") + "</div></div>"
      );
    }

    function generate() {
      var chosen = selected();
      var perSide = chosen.length / 2;
      var locked1 = byStatus("T1");
      var locked2 = byStatus("T2");
      var free = byStatus("ON");

      var need1 = perSide - locked1.length;
      var need2 = perSide - locked2.length;

      if (need1 < 0 || need2 < 0 || need1 + need2 !== free.length) {
        combosEl.innerHTML =
          '<div class="empty-state">Those locked assignments cannot fill two teams of ' +
          perSide + ".</div>";
        return;
      }

      var results = combinations(free, need1).map(function (pick) {
        var picked = new Set(pick.map(function (p) { return p.player; }));
        var team1 = locked1.concat(pick);
        var team2 = locked2.concat(free.filter(function (p) {
          return !picked.has(p.player);
        }));
        var spread = sum(team1) - sum(team2);
        return { team1: team1, team2: team2, spread: spread };
      });

      // Two complementary picks describe the same matchup with the sides
      // swapped; keep one of each pair unless a lock makes them distinct.
      if (!locked1.length && !locked2.length) {
        var seen = new Set();
        results = results.filter(function (r) {
          var key = r.team1.map(function (p) { return p.player; }).sort().join("|");
          var mirror = r.team2.map(function (p) { return p.player; }).sort().join("|");
          if (seen.has(mirror)) return false;
          seen.add(key);
          return true;
        });
      }

      results.sort(function (a, b) {
        return Math.abs(a.spread) - Math.abs(b.spread);
      });

      var total = results.length;
      var shown = results.slice(0, MAX_COMBOS_SHOWN);

      combosEl.innerHTML =
        '<div class="table-scroll"><table class="data"><thead><tr>' +
        "<th>#</th><th>Team 1</th><th>Rtg</th><th>Team 2</th><th>Rtg</th><th>Spread</th>" +
        "</tr></thead><tbody>" +
        shown.map(function (r, i) {
          var names = function (team) {
            return team.map(function (p) { return p.player; }).join(", ");
          };
          return (
            "<tr><td>" + (i + 1) + "</td>" +
            "<td>" + names(r.team1) + "</td>" +
            "<td>" + fmt(sum(r.team1)) + "</td>" +
            "<td>" + names(r.team2) + "</td>" +
            "<td>" + fmt(sum(r.team2)) + "</td>" +
            '<td class="' + (Math.abs(r.spread) < 0.5 ? "pos" : "") + '">' +
              fmt(r.spread) + "</td></tr>"
          );
        }).join("") +
        "</tbody></table></div>" +
        '<div class="table-foot">' +
        (total > shown.length
          ? "Showing the " + shown.length + " most balanced of " + total.toLocaleString() + " splits"
          : total.toLocaleString() + " possible split" + (total === 1 ? "" : "s")) +
        "</div>";
    }

    listEl.addEventListener("change", function (event) {
      var select = event.target.closest(".tb-status");
      if (!select) return;
      var name = select.closest("tr").dataset.player;
      state[name] = select.value;
      renderSummary();
    });

    searchEl.addEventListener("input", renderList);

    document.getElementById("tbGenerate").addEventListener("click", generate);

    document.getElementById("tbReset").addEventListener("click", function () {
      roster.forEach(function (p) { state[p.player] = "OFF"; });
      searchEl.value = "";
      combosEl.innerHTML = "";
      renderList();
      renderSummary();
    });

    renderList();
    renderSummary();
  });
})(window, document);
