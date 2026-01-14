/* ---------------------------------------------------------
   DATATABLES — Universal initialization
   Applies to: index.html, player.html, date.html
--------------------------------------------------------- */

$(document).ready(function () {

    /* ---------------------------------------------------------
       GLOBAL MIN-GAMES FILTER
    --------------------------------------------------------- */
    $.fn.dataTable.ext.search.push(function (settings, data, dataIndex) {

        const tableId = settings.nTable.id;

        // Apply filter only on pairings tables
        if (!["teammatesTable", "opponentsTable", "statsTable", "playerDaysTable"].includes(tableId)) {
            return true;
        }

        const gamesPlayed = parseInt(data[1]) || 0;
        const minGames = parseInt($("#minGamesPlayed").val()) || 0;

        return gamesPlayed >= minGames;
    });


    /* ---------------------------------------------------------
       Utility: Initialize a table ONLY if it exists
    --------------------------------------------------------- */
    function initTable(id, options = {}) {
        const element = document.getElementById(id);
        if (!element) return null;

        return $(`#${id}`).DataTable(Object.assign({
            pageLength: 25,
            responsive: true,
            autoWidth: false,

            dom: 'lBfrtip',
            buttons: [
                { extend: 'csvHtml5', text: 'Export csv', className: "btn btn-success" },
                { extend: 'colvis', text: 'View/Remove Columns', className: "btn btn-primary" }
            ]

        }, options));
    }


    /* ---------------------------------------------------------
       PAGE DETECTION USING BODY CLASS
    --------------------------------------------------------- */

    const body = document.body.classList;


    /* ---------------------------------------------------------
       INDEX PAGE TABLES (lazy-loaded by tab)
    --------------------------------------------------------- */
    if (body.contains("page-index")) {

        // Track which tables have been initialized
        const initializedTables = new Set();

        // Table configurations by tab
        const tableConfigs = {
            stats: [
                { id: "statsTable", options: { order: [[3, "desc"], [6, "desc"]] } }
            ],
            ratings: [
                { id: "ratingsTable", options: { order: [[1, "desc"]] } }
            ],
            games: [
                { id: "gamesTable", options: { order: [[14, "desc"], [15, "desc"]] } }
            ],
            player_days: [
                { id: "playerDaysTable", options: { order: [[1, "desc"], [4, "desc"], [6, "desc"], [0, "desc"]] } }
            ],
            player_pairings: [
                { id: "teammatesTable", options: { order: [[3, "desc"], [8, "desc"]] } },
                { id: "opponentsTable", options: { order: [[4, "desc"], [9, "desc"]] } }
            ],
            days: [
                { id: "daysOfWeekTable", options: { order: [[6, "desc"]] } },
                { id: "daysTable", options: { order: [[0, "desc"]] } }
            ]
        };

        // Initialize tables for a given tab
        function initTablesForTab(tabName) {
            const configs = tableConfigs[tabName];
            if (!configs) return;

            configs.forEach(config => {
                if (!initializedTables.has(config.id)) {
                    initTable(config.id, config.options);
                    initializedTables.add(config.id);
                }
            });
        }

        // Initialize only the active tab's table on page load (stats)
        initTablesForTab("stats");

        // Lazy-load tables when tabs are clicked
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                const target = tab.dataset.target;
                initTablesForTab(target);
            });
        });

    }


    /* ---------------------------------------------------------
       PLAYER PAGE TABLES
    --------------------------------------------------------- */
    if (body.contains("page-player")) {

        initTable("statsTable");
        initTable("daysTable",        { order: [[0, "desc"]] });
        initTable("gamesTable",        { order: [[0, "desc"], [1, "desc"]] });
        initTable("teammatesTable",        { order: [[1, "desc"], [3, "desc"]] });
        initTable("opponentsTable",        { order: [[1, "desc"], [3, "desc"]] });

    }


    /* ---------------------------------------------------------
       DATE PAGE TABLES
    --------------------------------------------------------- */
    if (body.contains("page-date")) {

        initTable("playersTable",  { order: [[11, "desc"]] });
        initTable("gamesTable",    { order: [[15, "desc"]] });

    }


    /* ---------------------------------------------------------
       TRIGGER FILTER REDRAW WHEN MIN-GAMES CHANGES (debounced)
    --------------------------------------------------------- */
    let filterTimeout = null;
    $("#minGamesPlayed").on("input", function () {
        // Debounce: wait 250ms after user stops typing
        clearTimeout(filterTimeout);
        filterTimeout = setTimeout(function() {
            // Only redraw tables that have been initialized as DataTables
            const tableIds = ["teammatesTable", "opponentsTable", "statsTable", "playerDaysTable"];
            tableIds.forEach(id => {
                const $table = $(`#${id}`);
                if ($table.length && $.fn.DataTable.isDataTable($table)) {
                    $table.DataTable().draw();
                }
            });
        }, 250);
    });


});
