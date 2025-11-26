/* ---------------------------------------------------------
   DATATABLES — Universal initialization
   Applies to: index.html, player.html, date.html
--------------------------------------------------------- */

$(document).ready(function () {

    /* ---------------------------------------------------------
       GLOBAL MIN-GAMES FILTER — ONLY for player pairings
       (teammatesTable and opponentsTable)
    --------------------------------------------------------- */
    $.fn.dataTable.ext.search.push(function (settings, data, dataIndex) {

        const tableId = settings.nTable.id;

        // Apply filter only on pairings tables
        if (!["teammatesTable", "opponentsTable"].includes(tableId)) {
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
            fixedHeader: true,
            autoWidth: false,
            scrollCollapse: true,

            dom: 'lBfrtip',
            buttons: [
                { extend: 'csvHtml5', text: 'Export csv', className: "btn btn-success" },
                { extend: 'colvis', text: 'View/Remove Columns', className: "btn btn-primary" }
            ],

            fixedColumns: {
                leftColumns: 1
            }

        }, options));
    }


    /* ---------------------------------------------------------
       PAGE DETECTION USING BODY CLASS
    --------------------------------------------------------- */

    const body = document.body.classList;


    /* ---------------------------------------------------------
       INDEX PAGE TABLES
    --------------------------------------------------------- */
    if (body.contains("page-index")) {

        initTable("statsTable",        { order: [[3, "desc"], [6, "desc"]] });
        initTable("ratingsTable",      { order: [[1, "desc"]] });
        initTable("gamesTable",        { order: [[14, "desc"], [15, "desc"]] });
        initTable("playerDaysTable",   { order: [[1, "desc"], [4, "desc"], [6, "desc"], [0, "desc"]] });
        initTable("teammatesTable",    { order: [[3, "desc"], [8, "desc"]] });
        initTable("opponentsTable",    { order: [[4, "desc"], [9, "desc"]] });
        initTable("daysOfWeekTable",   { order: [[6, "desc"]] });
        initTable("daysTable",         { order: [[0, "desc"]] });

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
       TRIGGER FILTER REDRAW WHEN MIN-GAMES CHANGES
    --------------------------------------------------------- */
    $("#minGamesPlayed").on("input", function () {

        const teammates = $("#teammatesTable").DataTable();
        const opponents = $("#opponentsTable").DataTable();

        if (teammates) teammates.draw();
        if (opponents) opponents.draw();
    });

});
