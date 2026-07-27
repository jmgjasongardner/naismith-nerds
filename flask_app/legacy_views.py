"""
The original Naismith Nerds site, preserved verbatim at /classic.

This is the version Jason Gardner designed and built solo between January 2025
and July 2026, before any agentic coding. The templates under
templates/legacy/ and the stylesheets/scripts under static/css/styles.css and
static/js/ are unchanged from that build; the only edits were namespacing
url_for() endpoints onto this blueprint so the two sites can coexist.

The exact pre-agentic source is pinned at the git tag `v1-solo-build`.

Do not refactor this module to share code with the new site. Its whole job is
to keep working exactly as it did, and drift is the thing we are guarding
against. It is fed by the same live data, so it stays current.
"""

import polars as pl
from flask import Blueprint, current_app, render_template

from collective_bball.paths import player_photo_path, player_thumb_path
from flask_app.player_page_data_loader import load_player_bio_data
from flask_app.utility_imports import tooltips
from flask_app.web_data_loader import format_stats_for_site

legacy = Blueprint("legacy", __name__, url_prefix="/classic")


# Columns the original site dropped before rendering. Kept as module constants
# so the three views stay in sync the way they did when they were inline.
_GAME_DROP_COLS = [
    "winning_score",
    "games_waited_B",
    "games_waited_A",
    "consecutive_games_B",
    "consecutive_games_A",
    "total_games_played_diff",
    "consecutive_games_waited_diff",
    "consecutive_games_played_diff",
    "total_games_played_diff_sq",
    "consecutive_games_waited_diff_sq",
    "consecutive_games_played_diff_sq",
]

_PLAYER_BIO_DROP_COLS = [
    "rating",
    "tiered_rating",
    "full_name",
    "height",
    "position",
    "resident",
    "birthday",
]


def _first_poss_label(df: pl.DataFrame) -> pl.DataFrame:
    """A/B/Idk label for first possession, as the original site displayed it."""
    return df.with_columns(
        pl.when(pl.col("first_poss") == 1)
        .then(pl.lit("A"))
        .when(pl.col("first_poss") == -1)
        .then(pl.lit("B"))
        .otherwise(pl.lit("Idk"))
        .alias("first_poss")
    )


def prepare_home_page_data(data_cached) -> dict:
    """Pre-shape every home page table. This is the ~66 MB render the original
    site did on every request; we now do it once and cache it."""

    players_with_images = {
        name
        for name in data_cached.player_data["player"].to_list()
        if player_thumb_path(name).exists()
    }

    def add_has_img(rows):
        for row in rows:
            row["has_img"] = row.get("Player", "") in players_with_images
        return rows

    stats = format_stats_for_site(data_cached.player_data.drop(_PLAYER_BIO_DROP_COLS))
    add_has_img(stats)

    games = format_stats_for_site(
        _first_poss_label(data_cached.games).drop(_GAME_DROP_COLS)
    )

    ratings = format_stats_for_site(
        data_cached.ratings.filter(~pl.col("player").str.contains("Tier"))
        .with_columns(pl.col("rating").round(5))
        .join(
            data_cached.player_data.select(["player", "active_player"]),
            on="player",
            how="left",
        )
    )
    add_has_img(ratings)

    return {
        "stats": stats,
        "num_days": len(data_cached.days),
        "games": games,
        "ratings": ratings,
        "player_days": format_stats_for_site(
            data_cached.player_days.drop("rating", "resident")
        ),
        "teammates": format_stats_for_site(
            data_cached.teammates.drop(["player", "teammate"]).unique("pairing")
        ),
        "opponents": format_stats_for_site(data_cached.opponents),
        "days_of_week": format_stats_for_site(data_cached.days_of_week),
        "days": format_stats_for_site(data_cached.days),
        "best_lambda": data_cached.best_lambda,
        "plot_ratings": data_cached.plot_ratings,
        "plot_rapm_apm": data_cached.plot_rapm_apm,
    }


def _home_page_data() -> dict:
    """Build the home page tables on first visit and cache them until the
    underlying data is hot-swapped."""
    store = current_app.config["DATA_STORE"]
    cached = current_app.config.get("LEGACY_HOME_PAGE_DATA")
    if cached is not None and cached["version"] == store.version:
        return cached["data"]

    data = prepare_home_page_data(store.data)
    current_app.config["LEGACY_HOME_PAGE_DATA"] = {
        "version": store.version,
        "data": data,
    }
    return data


@legacy.route("/")
def home():
    cached = _home_page_data()

    return render_template(
        "legacy/index.html",
        stats=cached["stats"],
        num_days=cached["num_days"],
        games=cached["games"],
        ratings=cached["ratings"],
        player_days=cached["player_days"],
        teammates=cached["teammates"],
        opponents=cached["opponents"],
        days_of_week=cached["days_of_week"],
        days=cached["days"],
        best_lambda=cached["best_lambda"],
        main_tooltip=tooltips.main_tooltip,
        plot_ratings=cached["plot_ratings"],
        plot_rapm_apm=cached["plot_rapm_apm"],
    )


@legacy.route("/player/<player_name>")
def player_page(player_name):
    # Imported here rather than at module scope so a normal boot never pays
    # plotly's import cost; only a visit to a classic player page does.
    from collective_bball.plots import Plots

    data_cached = current_app.config["DATA_STORE"].data

    image_exists = player_photo_path(player_name).exists()

    full_name, height_str, position, birthday = load_player_bio_data(
        player_name=player_name, player_data=data_cached.player_data
    )

    with current_app.config["DATA_STORE"].db() as conn:
        plots = Plots(conn)
        player_rating_over_time = plots.plot_player_ratings_time(
            player_name=player_name
        ).to_html(full_html=False, include_plotlyjs="cdn")
        player_games_rolling = plots.plot_player_rolling_avg(
            player_name=player_name,
            player_games=data_cached.player_games.filter(
                pl.col("player") == player_name
            ),
        ).to_html(full_html=False, include_plotlyjs="cdn")

    return render_template(
        "legacy/player.html",
        player_name=player_name,
        full_name=full_name,
        height_str=height_str,
        position=position,
        birthday=birthday,
        image_exists=image_exists,
        player_rating_over_time_html=player_rating_over_time,
        player_games_rolling_html=player_games_rolling,
        player_stats=format_stats_for_site(
            data_cached.player_data.filter(pl.col("player") == player_name).drop(
                ["player"] + _PLAYER_BIO_DROP_COLS
            )
        ),
        player_rating=data_cached.ratings.filter(pl.col("player") == player_name)
        .with_columns(pl.col("rating").round(5))
        .to_dicts(),
        player_days=format_stats_for_site(
            data_cached.player_days.filter(pl.col("player") == player_name).drop(
                ["player", "rating", "resident"]
            )
        ),
        player_games=format_stats_for_site(
            data_cached.player_games.filter(pl.col("player") == player_name)
            .drop(["rating", "player", "resident"])
            .with_columns(pl.col("win_prob").round(3))
        ),
        player_teammates=format_stats_for_site(
            data_cached.teammates.filter(pl.col("player") == player_name).drop(
                ["player", "pairing"]
            )
        ),
        player_oppponents=format_stats_for_site(
            data_cached.opponents.filter(pl.col("player") == player_name).drop(
                ["player"]
            )
        ),
        main_tooltip=tooltips.main_tooltip,
    )


@legacy.route("/date/<date>")
def date_page(date):
    data_cached = current_app.config["DATA_STORE"].data

    return render_template(
        "legacy/date.html",
        date=date,
        day_of_week=data_cached.games.filter(pl.col("game_date") == date)
        .select("day")
        .item(0, 0),
        day_data=format_stats_for_site(
            data_cached.days.filter(pl.col("game_date") == date).drop(
                ["game_date", "day"]
            )
        ),
        player_day=format_stats_for_site(
            data_cached.player_days.filter(pl.col("game_date") == date).drop(
                ["game_date", "day", "rating", "resident"]
            ),
            does_player_image_exist_row=True,
        ),
        day_games=format_stats_for_site(
            _first_poss_label(
                data_cached.games.filter(pl.col("game_date") == date)
            ).drop(_GAME_DROP_COLS)
        ),
        main_tooltip=tooltips.main_tooltip,
    )
