"""
JSON endpoints backing the tables.

Payloads are column-oriented: one spec describing the columns, then rows as
plain arrays. Repeating a key on every row, as a list of objects would, roughly
triples the size of the larger tables for no benefit.

Serialized payloads are cached per dataset per data version and gzipped, so a
tab that has been opened once is served straight from memory. The cache is
keyed on DataStore.version, so a hot swap invalidates everything at once.
"""

import gzip
import hashlib
import json
import logging
from typing import Callable, Dict

import polars as pl
from flask import Blueprint, Response, current_app, jsonify, request

from collective_bball.paths import player_thumb_path
from flask_app.columns import label_for, round_floats, spec_for, type_for

logger = logging.getLogger(__name__)

api = Blueprint("api", __name__, url_prefix="/api")

# Below this size, gzip costs more than it saves.
GZIP_MIN_BYTES = 1024

# Columns that exist to drive the model, not to be read in a table.
_GAME_INTERNALS = [
    "winning_score",
    "games_waited_A",
    "games_waited_B",
    "consecutive_games_A",
    "consecutive_games_B",
    "total_games_played_diff",
    "consecutive_games_waited_diff",
    "consecutive_games_played_diff",
    "total_games_played_diff_sq",
    "consecutive_games_waited_diff_sq",
    "consecutive_games_played_diff_sq",
]

_PLAYER_BIO = ["full_name", "height", "position", "birthday", "tiered_rating"]


def _first_poss_label(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(
        pl.when(pl.col("first_poss") == 1)
        .then(pl.lit("A"))
        .when(pl.col("first_poss") == -1)
        .then(pl.lit("B"))
        .otherwise(pl.lit("—"))
        .alias("first_poss")
    )


def _order(df: pl.DataFrame, first: list) -> pl.DataFrame:
    """Move key columns to the front; the first becomes the pinned column."""
    present = [c for c in first if c in df.columns]
    return df.select(present + [c for c in df.columns if c not in present])


# -- dataset registry ------------------------------------------------------

def _stats(data) -> pl.DataFrame:
    """The Players table.

    Rating is deliberately absent. Players under 20 games don't get their own
    coefficient — they inherit their tier's — so publishing the column here
    would broadcast the substituted value as if it were that player's own.
    The Ratings tab still carries ratings, and only for players who earned one.
    """
    drop = [c for c in _PLAYER_BIO + ["rating"] if c in data.player_data.columns]
    return _order(
        data.player_data.drop(drop),
        ["player", "wins", "losses", "win_pct", "games_played"],
    ).sort(["wins", "win_pct"], descending=[True, True])


def _ratings(data) -> pl.DataFrame:
    return (
        data.ratings.filter(~pl.col("player").str.contains("Tier"))
        .join(
            data.player_data.select(["player", "games_played", "active_player"]),
            on="player",
            how="left",
        )
        .sort("rating", descending=True)
    )


def _games(data) -> pl.DataFrame:
    return _order(
        _first_poss_label(data.games).drop(
            [c for c in _GAME_INTERNALS if c in data.games.columns]
        ),
        ["game_date", "game_num", "winner", "a_score", "b_score"],
    ).sort(["game_date", "game_num"], descending=[True, True])


def _player_days(data) -> pl.DataFrame:
    return _order(
        data.player_days.drop(["rating", "resident"]),
        ["player", "game_date", "games_played", "wins", "losses"],
    ).sort(["game_date", "wins"], descending=[True, True])


def _teammates(data) -> pl.DataFrame:
    return _order(
        data.teammates.drop(["player", "teammate"]).unique("pairing"),
        ["pairing", "games_played", "wins", "losses", "win_pct"],
    ).sort(["games_played", "win_pct"], descending=[True, True])


def _opponents(data) -> pl.DataFrame:
    return _order(
        data.opponents,
        ["player", "opponent", "games_played", "wins", "losses", "win_pct"],
    ).sort(["games_played", "win_pct"], descending=[True, True])


def _days(data) -> pl.DataFrame:
    return _order(data.days, ["game_date", "day", "num_players", "num_games"])


def _days_of_week(data) -> pl.DataFrame:
    return _order(data.days_of_week, ["day", "num_players", "num_games"])


DATASETS: Dict[str, Callable] = {
    "stats": _stats,
    "ratings": _ratings,
    "games": _games,
    "player_days": _player_days,
    "teammates": _teammates,
    "opponents": _opponents,
    "days": _days,
    "days_of_week": _days_of_week,
}


# -- serialisation ---------------------------------------------------------

def _serialize(df: pl.DataFrame) -> bytes:
    df = round_floats(df)
    payload = {
        "cols": spec_for(df),
        "rows": [list(row) for row in df.iter_rows()],
        "count": df.height,
    }
    return json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")


def _cache_key(name: str, version: int) -> str:
    return f"{name}@{version}"


def _cached_payload(name: str, builder: Callable) -> bytes:
    store = current_app.config["DATA_STORE"]
    cache = current_app.config.setdefault("API_CACHE", {})
    key = _cache_key(name, store.version)

    if key in cache:
        return cache[key]

    payload = _serialize(builder(store.data))

    # Drop entries from superseded versions only. Clearing everything would
    # evict the eight league-wide tables each time a player page is opened.
    suffix = f"@{store.version}"
    for stale in [k for k in cache if not k.endswith(suffix)]:
        del cache[stale]

    cache[key] = payload
    logger.debug("Cached %s payload (%d KB)", name, len(payload) // 1024)
    return payload


def payload_etag(payload: bytes) -> str:
    """Validator derived from the bytes actually being sent.

    This must not be built from DataStore.version. That counter starts at 1 in
    every new process, so after a restart a completely different dataset would
    reuse the previous ETag, browsers would revalidate, get a 304, and keep
    rendering data and columns that no longer exist. Hashing the payload means
    the validator can only match when the content genuinely matches.
    """
    return 'W/"%s"' % hashlib.sha1(payload).hexdigest()[:16]


def _json_response(payload: bytes) -> Response:
    """Return JSON, gzipped when it is worth it and the client accepts it."""
    accepts_gzip = "gzip" in request.headers.get("Accept-Encoding", "")

    if accepts_gzip and len(payload) >= GZIP_MIN_BYTES:
        body = gzip.compress(payload, compresslevel=6)
        response = Response(body, mimetype="application/json")
        response.headers["Content-Encoding"] = "gzip"
    else:
        response = Response(payload, mimetype="application/json")

    response.headers["Vary"] = "Accept-Encoding"
    response.headers["ETag"] = payload_etag(payload)
    # Always revalidate. The payload is small and gzipped, and a matching ETag
    # still costs only a 304, so there is no reason to let a browser serve a
    # stale table without asking.
    response.headers["Cache-Control"] = "no-cache"
    return response


# -- routes ----------------------------------------------------------------

@api.route("/table/<name>")
def table(name: str):
    builder = DATASETS.get(name)
    if builder is None:
        return jsonify({"error": f"unknown dataset '{name}'"}), 404

    payload = _cached_payload(name, builder)

    etag = payload_etag(payload)
    if request.headers.get("If-None-Match") == etag:
        return Response(status=304)

    return _json_response(payload)


def _player_game_log(data, name: str) -> pl.DataFrame:
    """A player's games. `winner` is 1/0 in the model; show it as W/L."""
    return _order(
        data.player_games.filter(pl.col("player") == name)
        .drop(["player", "rating", "resident"])
        .with_columns(
            pl.when(pl.col("winner") == 1)
            .then(pl.lit("W"))
            .otherwise(pl.lit("L"))
            .alias("winner")
        ),
        ["game_date", "game_num", "winner", "team", "team_score", "opp_score"],
    ).sort(["game_date", "game_num"], descending=[True, True])


PLAYER_SCOPED = {
    "games": _player_game_log,
    "days": lambda data, name: _order(
        data.player_days.filter(pl.col("player") == name).drop(
            ["player", "rating", "resident"]
        ),
        ["game_date", "day", "games_played", "wins", "losses"],
    ).sort("game_date", descending=True),
    "teammates": lambda data, name: _order(
        data.teammates.filter(pl.col("player") == name).drop(["player", "pairing"]),
        ["teammate", "games_played", "wins", "losses", "win_pct"],
    ).sort(["games_played", "win_pct"], descending=[True, True]),
    "opponents": lambda data, name: _order(
        data.opponents.filter(pl.col("player") == name).drop(["player"]),
        ["opponent", "games_played", "wins", "losses", "win_pct"],
    ).sort(["games_played", "win_pct"], descending=[True, True]),
}

DATE_SCOPED = {
    # Sorted by Gospel descending: who most outperformed expectation that day,
    # which is the same measure that decides the day's MVP and LVP.
    "players": lambda data, date: _order(
        data.player_days.filter(pl.col("game_date") == date).drop(
            ["game_date", "day", "rating", "resident"]
        ),
        [
            "player",
            "result_vs_expectation_avg",
            "games_played",
            "wins",
            "losses",
            "win_pct",
        ],
    ).sort(
        ["result_vs_expectation_avg", "player"], descending=[True, False], nulls_last=True
    ),
    "games": lambda data, date: _order(
        _first_poss_label(data.games.filter(pl.col("game_date") == date)).drop(
            [c for c in _GAME_INTERNALS if c in data.games.columns] + ["game_date"]
        ),
        ["game_num", "winner", "a_score", "b_score"],
    ).sort("game_num"),
}


# How lopsided the nine other players were. Bands are round numbers close to
# the actual quintiles of other_9_players_quality_diff, so each holds a
# meaningful share of games rather than being empty at the edges.
# The cutoff is carried in the label so the bucket is self-explanatory without
# needing the legend.
ADVANTAGE_BANDS = [
    (None, -3.0, "Much worse team (under −3)"),
    (-3.0, -1.0, "Worse team (−3 to −1)"),
    (-1.0, 1.0, "Even matchup (−1 to +1)"),
    (1.0, 3.0, "Better team (+1 to +3)"),
    (3.0, None, "Much better team (over +3)"),
]

# 1 -> 1st, 2 -> 2nd, and so on, for rank labels.
ORDINALS = {
    1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th",
    6: "6th", 7: "7th", 8: "8th", 9: "9th", 10: "10th",
}

# Total rating of the other nine on the floor. Other9 measures the gap between
# the two sides; this measures the level both sides are playing at, which is a
# separate question — the two correlate at only about -0.1. Bands sit near the
# quintiles of the observed distribution.
COURT_QUALITY_BANDS = [
    (None, -1.0, "Weakest games (under −1)"),
    (-1.0, 1.0, "Weak games (−1 to +1)"),
    (1.0, 3.0, "Average games (+1 to +3)"),
    (3.0, 5.0, "Strong games (+3 to +5)"),
    (5.0, None, "Strongest games (over +5)"),
]

# How many of the five opponents out-rate the player.
OPPONENTS_BETTER = {
    0: "Better than all 5 opponents",
    1: "Better than 4 of 5",
    2: "Better than 3 of 5",
    3: "Better than 2 of 5",
    4: "Better than 1 of 5",
    5: "Worse than all 5 opponents",
}

SPLIT_KINDS = {
    "team_rank": ("team_rank", "Rank on own team"),
    "court_rank": ("court_rank", "Rank among all ten"),
    "vs_opponents": ("vs_opponents", "Rank versus opponents"),
    "advantage": ("advantage", "Team advantage"),
    "court_quality": ("court_quality", "Overall on-court quality"),
}


def _banded(column: str, bands) -> pl.Expr:
    """Bucket a numeric column into labelled bands."""
    expr = pl.when(pl.col(column) < bands[0][1]).then(pl.lit(bands[0][2]))
    for low, high, label in bands[1:-1]:
        expr = expr.when(
            (pl.col(column) >= low) & (pl.col(column) < high)
        ).then(pl.lit(label))
    return expr.otherwise(pl.lit(bands[-1][2])).alias("split")


def _split_label(kind: str) -> pl.Expr:
    """Readable bucket name for each split."""
    if kind == "team_rank":
        return (
            pl.when(pl.col("team_rank") == 1).then(pl.lit("1st — best on team"))
            .when(pl.col("team_rank") == 2).then(pl.lit("2nd — second option"))
            .when(pl.col("team_rank") == 3).then(pl.lit("3rd — middle option"))
            .when(pl.col("team_rank") == 4).then(pl.lit("4th — fourth option"))
            .when(pl.col("team_rank") == 5).then(pl.lit("5th — last option"))
            .otherwise(pl.lit("Unranked"))
            .alias("split")
        )

    if kind == "court_rank":
        return (
            pl.when(pl.col("court_rank") == 1).then(pl.lit("1st — best on court"))
            .when(pl.col("court_rank") == 10).then(pl.lit("10th — last on court"))
            .otherwise(
                pl.col("court_rank").replace_strict(ORDINALS, default="?")
                + pl.lit(" on court")
            )
            .alias("split")
        )

    if kind == "vs_opponents":
        return (
            pl.col("opps_better")
            .replace_strict(OPPONENTS_BETTER, default="Roster error")
            .alias("split")
        )

    if kind == "court_quality":
        return _banded("court_quality", COURT_QUALITY_BANDS)

    return _banded("other_9_players_quality_diff", ADVANTAGE_BANDS)


def _player_splits(data, player_name: str, kind: str) -> pl.DataFrame:
    """Aggregate a player's games into buckets, one row per bucket."""
    sort_col = {
        "team_rank": "team_rank",
        "court_rank": "court_rank",
        "vs_opponents": "opps_better",
    }.get(kind)

    games = data.player_games.filter(pl.col("player") == player_name).with_columns(
        # Opponents who out-rate this player. court_rank counts everyone on the
        # floor rated above them and team_rank counts just their own side, so
        # the difference is exactly the opponents above them — no second join.
        (pl.col("court_rank") - pl.col("team_rank")).alias("opps_better"),
        # The talent level of the other nine, as opposed to the gap between
        # the sides that other_9_players_quality_diff measures.
        (pl.col("teammate_quality") + pl.col("opp_quality")).alias("court_quality"),
    ).with_columns(_split_label(kind))

    if sort_col:
        games = games.with_columns(pl.col(sort_col).alias("_order"))
    else:
        # Order bands weakest-to-strongest, not alphabetically.
        bands = COURT_QUALITY_BANDS if kind == "court_quality" else ADVANTAGE_BANDS
        order = {label: i for i, (_, _, label) in enumerate(bands)}
        games = games.with_columns(
            pl.col("split").replace_strict(order, default=99).alias("_order")
        )

    return (
        games.group_by(["split", "_order"])
        .agg(
            pl.len().alias("games_played"),
            pl.col("winner").sum().cast(pl.Int32).alias("wins"),
            pl.col("score_diff").mean().round(2).alias("avg_score_diff"),
            pl.col("proj_score_diff").mean().round(2).alias("proj_score_diff"),
            pl.col("result_vs_expectation").mean().round(2).alias("result_vs_expectation"),
            pl.col("win_prob").mean().round(3).alias("win_prob"),
            pl.col("teammate_quality").mean().round(2).alias("teammate_quality"),
            pl.col("opp_quality").mean().round(2).alias("opp_quality"),
            pl.col("other_9_players_quality_diff")
            .mean()
            .round(2)
            .alias("other_9_players_quality_diff"),
            pl.col("court_quality").mean().round(2).alias("court_quality"),
        )
        .with_columns(
            (pl.col("games_played") - pl.col("wins")).cast(pl.Int64).alias("losses"),
            (pl.col("wins") / pl.col("games_played")).round(4).alias("win_pct"),
        )
        .sort("_order")
        .drop("_order")
        .select(
            [
                "split", "games_played", "wins", "losses", "win_pct", "win_prob",
                "result_vs_expectation", "avg_score_diff", "proj_score_diff",
                "other_9_players_quality_diff", "court_quality",
                "teammate_quality", "opp_quality",
            ]
        )
    )


@api.route("/player/<player_name>/splits/<kind>")
def player_splits(player_name: str, kind: str):
    if kind not in SPLIT_KINDS:
        return jsonify({"error": f"unknown split '{kind}'"}), 404
    return _json_response(
        _cached_payload(
            f"splits:{player_name}:{kind}",
            lambda data: _player_splits(data, player_name, kind),
        )
    )


@api.route("/player/<player_name>/<dataset>")
def player_table(player_name: str, dataset: str):
    builder = PLAYER_SCOPED.get(dataset)
    if builder is None:
        return jsonify({"error": f"unknown player dataset '{dataset}'"}), 404
    store = current_app.config["DATA_STORE"]
    return _json_response(
        _cached_payload(
            f"player:{player_name}:{dataset}",
            lambda data: builder(data, player_name),
        )
    )


@api.route("/date/<date>/<dataset>")
def date_table(date: str, dataset: str):
    builder = DATE_SCOPED.get(dataset)
    if builder is None:
        return jsonify({"error": f"unknown date dataset '{dataset}'"}), 404
    return _json_response(
        _cached_payload(f"date:{date}:{dataset}", lambda data: builder(data, date))
    )


@api.route("/search")
def search():
    """Index for the header search: every player and every game date."""
    store = current_app.config["DATA_STORE"]
    cache = current_app.config.setdefault("API_CACHE", {})
    key = _cache_key("__search", store.version)
    if key not in cache:
        data = store.data
        players = (
            data.player_data.select(
                ["player", "full_name", "games_played", "rating", "active_player"]
            )
            .sort("games_played", descending=True)
            .to_dicts()
        )
        entries = [
            {
                "t": "p",
                "n": row["player"],
                "f": row.get("full_name") or "",
                "g": row["games_played"],
                "r": round(row["rating"], 2) if row["rating"] is not None else None,
                "a": bool(row.get("active_player")),
                "i": player_thumb_path(row["player"]).exists(),
            }
            for row in players
        ]
        entries += [
            {"t": "d", "n": row["game_date"], "f": row["day"], "g": row["num_games"]}
            for row in data.days.select(["game_date", "day", "num_games"])
            .sort("game_date", descending=True)
            .to_dicts()
        ]
        cache[key] = json.dumps(
            {"entries": entries}, separators=(",", ":"), default=str
        ).encode("utf-8")

    return _json_response(cache[key])


@api.route("/charts/ratings-history")
def chart_ratings_history():
    """Every player's rating trajectory.

    Sent as a shared date axis plus one nullable series per player, which is
    far smaller than repeating the date on every point. Players are ordered by
    current rating so the front end can color the leaders and leave the rest
    as recessive context.
    """
    store = current_app.config["DATA_STORE"]
    cache = current_app.config.setdefault("API_CACHE", {})
    key = _cache_key("__ratings_history", store.version)

    if key not in cache:
        with store.db() as conn:
            rows = conn.execute(
                "SELECT player, date, rating FROM ratings "
                "WHERE player NOT ILIKE '%tier%' ORDER BY date"
            ).fetchall()

        dates = sorted({str(date) for _player, date, _rating in rows})
        date_index = {date: i for i, date in enumerate(dates)}

        series = {}
        for player, date, rating in rows:
            series.setdefault(player, [None] * len(dates))[
                date_index[str(date)]
            ] = round(float(rating), 3)

        # Order by most recent rating so slot 1 is the current leader.
        current = {
            row["player"]: row["rating"]
            for row in store.data.ratings.to_dicts()
            if row["rating"] is not None
        }
        ordered = sorted(
            series.items(),
            key=lambda item: current.get(item[0], -99),
            reverse=True,
        )

        cache[key] = json.dumps(
            {
                "dates": dates,
                "series": [{"name": name, "v": values} for name, values in ordered],
            },
            separators=(",", ":"),
        ).encode("utf-8")

    return _json_response(cache[key])


# Every numeric field worth putting on an axis of the player scatter. Order
# matters: it is the order of the dropdowns.
SCATTER_FIELDS = [
    "rating",
    "win_pct",
    "games_played",
    "wins",
    "losses",
    "days_played",
    "result_vs_expectation",
    "avg_score_diff",
    "proj_score_diff",
    "expected_win_pct",
    "other_9_players_quality_diff",
    "team_quality",
    "teammate_quality",
    "opp_quality",
    "mvps",
    "lvps",
    "mvp_pct",
    "lvp_pct",
    "games_played_per_day",
    "pct_games_favorite",
    "pct_games_better_teammates",
    "pct_positive_teammates",
    "pct_total_games_played",
    "pct_total_days_played",
    "first_game_of_day_rate",
    "last_game_of_day_rate",
    "mon_rate",
    "wed_rate",
    "sat_rate",
]


@api.route("/charts/player-scatter")
def chart_player_scatter():
    """Every rated player as a point, with any field selectable per axis.

    Restricted to players carrying their own rating. Tiered players share a
    group estimate, so plotting them against rating would cluster them at
    identical x-values that describe the tier rather than the player.
    """
    store = current_app.config["DATA_STORE"]
    cache = current_app.config.setdefault("API_CACHE", {})
    key = _cache_key("__scatter", store.version)

    if key not in cache:
        data = store.data
        available = [f for f in SCATTER_FIELDS if f in data.player_data.columns]

        rated = round_floats(
            data.player_data.filter(pl.col("tiered_rating") == 0).select(
                ["player"] + available
            )
        )

        dtypes = dict(zip(rated.columns, rated.dtypes))
        fields = [
            {
                "key": f,
                "label": label_for(f),
                "type": type_for(f, dtypes[f]),
                "dp": 1 if type_for(f, dtypes[f]) == "pct" else 2,
            }
            for f in available
        ]

        players = [
            {
                "n": row["player"],
                "i": player_thumb_path(row["player"]).exists(),
                "v": [row[f] for f in available],
            }
            for row in rated.to_dicts()
        ]

        cache[key] = json.dumps(
            {"fields": fields, "players": players}, separators=(",", ":"), default=str
        ).encode("utf-8")

    return _json_response(cache[key])


@api.route("/charts/rapm-apm")
def chart_rapm_apm():
    """Regularized rating against raw result-versus-expectation.

    Only untiered players: a tiered rating is a group estimate, so plotting it
    against that player's own APM would compare two different things.
    """
    store = current_app.config["DATA_STORE"]

    def build(data):
        return data.player_data.filter(pl.col("tiered_rating") == 0).select(
            ["player", "result_vs_expectation", "rating", "games_played", "win_pct"]
        )

    df = round_floats(build(store.data))
    payload = json.dumps(
        {
            "points": [
                {
                    "n": row["player"],
                    "x": row["result_vs_expectation"],
                    "y": row["rating"],
                    "g": row["games_played"],
                    "w": row["win_pct"],
                }
                for row in df.to_dicts()
                if row["result_vs_expectation"] is not None and row["rating"] is not None
            ]
        },
        separators=(",", ":"),
    ).encode("utf-8")
    return _json_response(payload)


@api.route("/player/<player_name>/rolling")
def player_rolling(player_name: str):
    """Rolling averages over a player's career, for the player-page chart."""
    window = min(max(int(request.args.get("window", 20)), 2), 100)
    store = current_app.config["DATA_STORE"]

    metrics = {
        "result_vs_expectation": "Result vs expectation",
        "other_9_players_quality_diff": "Other 9 quality diff",
        "teammate_quality": "Teammate quality",
        "opp_quality": "Opponent quality",
        "winner": "Win rate",
    }

    df = (
        store.data.player_games.filter(pl.col("player") == player_name)
        .sort("player_game_num")
        .with_columns(
            [
                pl.col(col).rolling_mean(window_size=window).round(3).alias(col)
                for col in metrics
            ]
        )
        .select(["player_game_num", "game_date"] + list(metrics))
    )

    payload = json.dumps(
        {
            "window": window,
            "x": df["player_game_num"].to_list(),
            "dates": df["game_date"].to_list(),
            "series": [
                {"name": label, "v": df[col].to_list()}
                for col, label in metrics.items()
            ],
        },
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return _json_response(payload)


@api.route("/player/<player_name>/rating-history")
def player_rating_history(player_name: str):
    """Rating over time for the player page chart.

    Read from DuckDB, which is where the historical ratings snapshots live.
    """
    store = current_app.config["DATA_STORE"]
    with store.db() as conn:
        rows = conn.execute(
            "SELECT date, rating FROM ratings WHERE player = ? ORDER BY date",
            [player_name],
        ).fetchall()

    payload = json.dumps(
        {
            "player": player_name,
            "points": [[str(date), round(float(rating), 3)] for date, rating in rows],
        },
        separators=(",", ":"),
    ).encode("utf-8")
    return _json_response(payload)
