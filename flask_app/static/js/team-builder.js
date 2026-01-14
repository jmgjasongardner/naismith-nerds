/* ---------------------------------------------------------
   TEAM BUILDER — Player selection and team generation
   Applies to: index.html Team Builder tab
--------------------------------------------------------- */

document.addEventListener("DOMContentLoaded", function () {

    // Only run on pages with team builder
    const table = document.getElementById("teamBuilderTable");
    if (!table) return;

    // DOM elements
    const tbody = table.querySelector("tbody");
    const rows = tbody.querySelectorAll("tr");

    const searchInput = document.getElementById("playerSearch");
    const generateBtn = document.getElementById("generateBtn");
    const resetBtn = document.getElementById("resetBtn");
    const returnBtn = document.getElementById("returnBtn");

    const numPlayersSpan = document.getElementById("numPlayersOnCourt");
    const team1TotalSpan = document.getElementById("team1Total");
    const team2TotalSpan = document.getElementById("team2Total");
    const onTotalSpan = document.getElementById("onTotal");
    const spreadTotalSpan = document.getElementById("spreadTotal");
    const comboCountSpan = document.getElementById("comboCount");

    const selectionView = document.getElementById("selectionView");
    const combosView = document.getElementById("combosView");
    const combosTableBody = document.querySelector("#combosTable tbody");

    // Status cycle order
    const STATUS_CYCLE = ["OFF", "ON", "Team 1", "Team 2"];

    // CSS class mapping
    const STATUS_CLASS = {
        "OFF": "off",
        "ON": "on",
        "Team 1": "team1",
        "Team 2": "team2"
    };

    /* ---------------------------------------------------------
       UPDATE ROW STYLING BASED ON STATUS
    --------------------------------------------------------- */
    function updateRowStyle(row, status) {
        row.classList.remove("off", "on", "team1", "team2");
        row.classList.add(STATUS_CLASS[status]);
    }

    /* ---------------------------------------------------------
       GET PLAYER DATA FROM ALL VISIBLE ROWS
    --------------------------------------------------------- */
    function getPlayerData() {
        const players = [];
        rows.forEach(row => {
            const name = row.dataset.player;
            const rating = parseFloat(row.dataset.rating);
            const select = row.querySelector(".status-select");
            const status = select.value;
            const visible = row.style.display !== "none";
            players.push({ name, rating, status, row, select, visible });
        });
        return players;
    }

    /* ---------------------------------------------------------
       CALCULATE AND UPDATE SUMMARY DISPLAYS
    --------------------------------------------------------- */
    function updateSummary() {
        const players = getPlayerData();

        const activePlayers = players.filter(p => p.status !== "OFF");
        const team1Players = players.filter(p => p.status === "Team 1");
        const team2Players = players.filter(p => p.status === "Team 2");
        const onPlayers = players.filter(p => p.status === "ON");

        const team1Rating = team1Players.reduce((sum, p) => sum + p.rating, 0);
        const team2Rating = team2Players.reduce((sum, p) => sum + p.rating, 0);
        const onRating = onPlayers.reduce((sum, p) => sum + p.rating, 0);
        const spread = team1Rating - team2Rating;

        numPlayersSpan.textContent = activePlayers.length;
        team1TotalSpan.textContent = team1Rating.toFixed(2);
        team2TotalSpan.textContent = team2Rating.toFixed(2);
        onTotalSpan.textContent = onRating.toFixed(2);
        spreadTotalSpan.textContent = spread.toFixed(2);
    }

    /* ---------------------------------------------------------
       CYCLE STATUS ON ROW CLICK
    --------------------------------------------------------- */
    function cycleStatus(row) {
        const select = row.querySelector(".status-select");
        const currentIndex = STATUS_CYCLE.indexOf(select.value);
        const nextIndex = (currentIndex + 1) % STATUS_CYCLE.length;
        select.value = STATUS_CYCLE[nextIndex];
        updateRowStyle(row, select.value);
        updateSummary();
    }

    /* ---------------------------------------------------------
       SEARCH FILTER
    --------------------------------------------------------- */
    function filterPlayers() {
        const query = searchInput.value.toLowerCase();
        rows.forEach(row => {
            const name = row.dataset.player.toLowerCase();
            row.style.display = name.includes(query) ? "" : "none";
        });
    }

    /* ---------------------------------------------------------
       RESET ALL PLAYERS TO OFF
    --------------------------------------------------------- */
    function resetTeams() {
        rows.forEach(row => {
            const select = row.querySelector(".status-select");
            select.value = "OFF";
            updateRowStyle(row, "OFF");
            row.style.display = "";
        });
        searchInput.value = "";
        updateSummary();
    }

    /* ---------------------------------------------------------
       GENERATE COMBINATIONS (n choose k)
    --------------------------------------------------------- */
    function combinations(arr, k) {
        if (k === 0) return [[]];
        if (arr.length === 0) return [];
        if (k > arr.length) return [];

        const [first, ...rest] = arr;
        const withFirst = combinations(rest, k - 1).map(c => [first, ...c]);
        const withoutFirst = combinations(rest, k);
        return [...withFirst, ...withoutFirst];
    }

    /* ---------------------------------------------------------
       GENERATE TEAMS AND SHOW ALL COMBINATIONS
    --------------------------------------------------------- */
    function generateTeams() {
        const players = getPlayerData();

        const locked1 = players.filter(p => p.status === "Team 1");
        const locked2 = players.filter(p => p.status === "Team 2");
        const onPlayers = players.filter(p => p.status === "ON");

        const totalActive = locked1.length + locked2.length + onPlayers.length;

        // Validate: must be even number, 2-10 players
        if (totalActive < 2 || totalActive > 10 || totalActive % 2 !== 0) {
            alert("Please select an even number of players (2, 4, 6, 8, or 10).");
            return;
        }

        const teamSize = totalActive / 2;
        const slots1 = teamSize - locked1.length;
        const slots2 = teamSize - locked2.length;

        // Validate: locked players don't exceed team size
        if (slots1 < 0) {
            alert("Too many players locked to Team 1. Max " + teamSize + " per team.");
            return;
        }
        if (slots2 < 0) {
            alert("Too many players locked to Team 2. Max " + teamSize + " per team.");
            return;
        }

        // Validate: enough ON players to fill slots
        if (onPlayers.length !== slots1 + slots2) {
            alert("Number of ON players (" + onPlayers.length + ") must equal remaining slots (" + (slots1 + slots2) + ").");
            return;
        }

        // Generate all ways to pick slots1 players for Team 1 from ON players
        const combos = combinations(onPlayers, slots1);

        // Calculate ratings and spreads for each combination
        const results = combos.map(team1Add => {
            const team1All = [...locked1, ...team1Add];
            const team1Names = new Set(team1Add.map(p => p.name));
            const team2Add = onPlayers.filter(p => !team1Names.has(p.name));
            const team2All = [...locked2, ...team2Add];

            const team1Rating = team1All.reduce((s, p) => s + p.rating, 0);
            const team2Rating = team2All.reduce((s, p) => s + p.rating, 0);
            const spread = team1Rating - team2Rating;

            return {
                team1: team1All.map(p => p.name).sort().join(", "),
                team1Rating: team1Rating.toFixed(2),
                team2: team2All.map(p => p.name).sort().join(", "),
                team2Rating: team2Rating.toFixed(2),
                spread: spread.toFixed(2),
                absSpread: Math.abs(spread)
            };
        });

        // Sort by absolute spread (most balanced first)
        results.sort((a, b) => a.absSpread - b.absSpread);

        // Populate combos table
        combosTableBody.innerHTML = "";
        results.forEach((r, i) => {
            const tr = document.createElement("tr");
            tr.innerHTML =
                "<td>" + (i + 1) + "</td>" +
                "<td>" + r.team1 + "</td>" +
                "<td>" + r.team1Rating + "</td>" +
                "<td>" + r.team2 + "</td>" +
                "<td>" + r.team2Rating + "</td>" +
                "<td>" + r.spread + "</td>" +
                "<td>" + r.absSpread.toFixed(2) + "</td>";
            combosTableBody.appendChild(tr);
        });

        // Update combo count
        comboCountSpan.textContent = results.length + " combination(s)";

        // Switch views
        selectionView.style.display = "none";
        combosView.style.display = "block";
        generateBtn.style.display = "none";
        resetBtn.style.display = "none";
        returnBtn.style.display = "inline-block";
    }

    /* ---------------------------------------------------------
       RETURN TO SELECTION VIEW
    --------------------------------------------------------- */
    function returnToSelection() {
        selectionView.style.display = "block";
        combosView.style.display = "none";
        generateBtn.style.display = "inline-block";
        resetBtn.style.display = "inline-block";
        returnBtn.style.display = "none";
        comboCountSpan.textContent = "";
    }

    /* ---------------------------------------------------------
       EVENT LISTENERS
    --------------------------------------------------------- */

    // Row click to cycle status (except when clicking the select dropdown)
    rows.forEach(row => {
        row.addEventListener("click", function(e) {
            if (e.target.tagName !== "SELECT" && e.target.tagName !== "OPTION") {
                cycleStatus(row);
            }
        });

        // Select change also updates styling and summary
        const select = row.querySelector(".status-select");
        select.addEventListener("change", function() {
            updateRowStyle(row, this.value);
            updateSummary();
        });
    });

    // Search input
    searchInput.addEventListener("input", filterPlayers);

    // Button handlers
    generateBtn.addEventListener("click", generateTeams);
    resetBtn.addEventListener("click", resetTeams);
    returnBtn.addEventListener("click", returnToSelection);

    /* ---------------------------------------------------------
       INITIALIZE
    --------------------------------------------------------- */
    updateSummary();
    rows.forEach(row => {
        updateRowStyle(row, row.querySelector(".status-select").value);
    });

});
