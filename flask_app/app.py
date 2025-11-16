from flask import Flask, render_template
from flask_app.utility_imports import tooltips
import logging

logging.basicConfig(level=logging.DEBUG)
import duckdb
import psutil

# from collective_bball.eda_main import generate_stats
# from collective_bball.win_prob_log_reg import calculate_team_A_win_prob
# logging.debug("app.py pre data load")
from collective_bball.main import data  # Get precomputed `data`
from collective_bball.plots import Plots  # to generate player-specific plots
from flask_app.web_data_loader import (
    format_stats_for_site,
    # get_model_outputs,
    # combine_tier_ratings,
    # calculate_game_spreads,
)
from flask_app.player_page_data_loader import (
    # create_player_games,
    load_player_bio_data,
    create_player_games_advanced,
)
import polars as pl
import os

# logging.debug(f"app.py post data load: {data is not None}")

app = Flask(__name__, static_folder="../static")
app.config["DATA_CACHED"] = data
# logging.debug(f"player data head outside funs: {data.player_data.head(5)}")


def filter_dictionary(dictionary, player_name):
    return [entry for entry in dictionary if entry["Player"] == player_name]


def log_memory_usage():
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    # logging.debug(f"Memory usage: {memory_info.rss / 1024 ** 2} MB")


@app.route("/")
def home():
    data_cached = app.config["DATA_CACHED"]

    # Precompute all data before returning
    # logging.debug('computing pre-processed')
    log_memory_usage()
    stats = format_stats_for_site(
        data_cached.player_data.drop(
            ["rating", "tiered_rating", "full_name", "height", "position", "resident"]
        ),
        does_player_image_exist_row=True,
    )
    # logging.debug('computed stats')
    log_memory_usage()
    num_days = len(data_cached.days)
    games = format_stats_for_site(
        data_cached.games.with_columns(
            pl.when(pl.col("first_poss") == 1)
            .then(pl.lit("A"))
            .when(pl.col("first_poss") == -1)
            .then(pl.lit("B"))
            .otherwise(pl.lit("Idk"))
            .alias("first_poss")
        ).drop(
            [
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
        )
    )
    # logging.debug('computed games')
    log_memory_usage()
    ratings = format_stats_for_site(
        data_cached.ratings.filter(~pl.col("player").str.contains("Tier")).with_columns(
            pl.col("rating").round(5)
        ),
        does_player_image_exist_row=True,
    )
    # logging.debug('computed ratings')
    log_memory_usage()
    player_days = format_stats_for_site(
        data_cached.player_days.drop("rating", "resident")
    )
    # logging.debug('computed player days')
    log_memory_usage()
    teammates = format_stats_for_site(
        data_cached.teammates.drop(["player", "teammate"]).unique()
    )
    # logging.debug('computed teammates')
    log_memory_usage()
    opponents = format_stats_for_site(data_cached.opponents)
    days_of_week = format_stats_for_site(data_cached.days_of_week)
    days = format_stats_for_site(data_cached.days)
    # logging.debug('computed opponents, days')
    log_memory_usage()
    best_lambda = data_cached.best_lambda
    main_tooltip = tooltips.main_tooltip
    # logging.debug('computed all pre-processed')
    log_memory_usage()

    # Return only after all data is prepared
    return render_template(
        "index.html",
        stats=stats,
        num_days=num_days,
        games=games,
        ratings=ratings,
        player_days=player_days,
        teammates=teammates,
        opponents=opponents,
        days_of_week=days_of_week,
        days=days,
        best_lambda=best_lambda,
        main_tooltip=main_tooltip,
        plot_ratings=data_cached.plot_ratings,
        plot_rapm_apm=data_cached.plot_rapm_apm,
    )


@app.route("/player/<player_name>")
def player_page(player_name):

    # win_pct, player_games_advanced, games_of_note = create_player_games_advanced(
    #     player_games=player_games, games_data=games_data
    # )

    # Check if the player's image exists in "static/player_pics/"
    # logging.debug('starting player page')
    data_cached = app.config["DATA_CACHED"]
    image_path = f"static/player_pics/{player_name}.png"
    image_exists = os.path.exists(image_path)
    # logging.debug('image exists')

    # logging.debug('loading player bio data')
    full_name, height_str, position = load_player_bio_data(
        player_name=player_name, player_data=data_cached.player_data
    )
    conn = duckdb.connect("bball_database.duckdb")
    plots = Plots(conn)
    player_rating_over_time = plots.plot_player_ratings_time(
        player_name=player_name
    ).to_html(full_html=False, include_plotlyjs="cdn")
    player_games_rolling = plots.plot_player_rolling_avg(
        player_name=player_name,
        player_games=data_cached.player_games.filter(pl.col("player") == player_name),
    ).to_html(full_html=False, include_plotlyjs="cdn")

    # logging.debug('computed player bio data')

    return render_template(
        "player.html",
        player_name=player_name,
        full_name=full_name,
        height_str=height_str,
        position=position,
        image_exists=image_exists,
        image_path=image_path if image_exists else None,
        player_rating_over_time_html=player_rating_over_time,
        player_games_rolling_html=player_games_rolling,
        player_stats=format_stats_for_site(
            data_cached.player_data.filter(pl.col("player") == player_name).drop(
                [
                    "player",
                    "rating",
                    "tiered_rating",
                    "full_name",
                    "height",
                    "position",
                    "resident",
                ]
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
        # player_games_advanced=player_games_advanced.to_pandas().to_dict(
        #     orient="records"
        # ),
        # games_of_note=games_of_note.to_pandas()
        # .drop(["Date", "Team", "Favorite"], axis=1)
        # .to_dict(orient="records"),
        main_tooltip=tooltips.main_tooltip,
    )


@app.route("/date/<date>")
def date_page(date):
    data_cached = app.config["DATA_CACHED"]

    return render_template(
        "date.html",
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
            data_cached.games.filter(pl.col("game_date") == date).drop(
                ["game_date", "day"]
            )
        ),
        main_tooltip=tooltips.main_tooltip,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
