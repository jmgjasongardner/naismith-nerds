from flask import Flask, render_template
from flask_app.utility_imports import tooltips
import logging
logging.basicConfig(level=logging.DEBUG)

# from collective_bball.eda_main import generate_stats
# from collective_bball.win_prob_log_reg import calculate_team_A_win_prob
#logging.debug("app.py pre data load")
from collective_bball.main import data  # Get precomputed `data`
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

logging.debug(f"app.py post data load: {data is not None}")

app = Flask(__name__, static_folder="../static")
app.config["DATA_CACHED"] = data
#logging.debug(f"player data head outside funs: {data.player_data.head(5)}")

def filter_dictionary(dictionary, player_name):
    return [entry for entry in dictionary if entry["Player"] == player_name]


@app.route("/")
def home():
    data_cached = app.config["DATA_CACHED"]
    # logging.debug(f"ratings head in home: {data_cached.ratings.head(5)}")
    # logging.debug(f"ratings sample dict in home: {format_stats_for_site(data_cached.ratings.head(5))}")
    # games_sample = data_cached.games[:5]  # Only take the first 5 games
    # logging.debug(f"games sample df in home: {games_sample}")
    # logging.debug(f"games sample dict in home: {format_stats_for_site(games_sample)}")
    # logging.debug(f"games dict in home: {format_stats_for_site(data_cached.games)}")
    return render_template(
        "index.html",
        stats=format_stats_for_site(
            data_cached.player_data.drop(
                ["rating", "tiered_rating", "full_name", "height", "position"]
            )
        ),
        num_days=len(data_cached.days),
        games=format_stats_for_site(data_cached.games),
        ratings=format_stats_for_site(data_cached.ratings),
        player_days=format_stats_for_site(data_cached.player_days.drop("rating")),
        teammates=format_stats_for_site(
            data_cached.teammates.drop(["player", "teammate"]).unique()
        ),
        opponents=format_stats_for_site(data_cached.opponents),
        days_of_week=format_stats_for_site(data_cached.days_of_week),
        days=format_stats_for_site(data_cached.days),
        best_lambda=data_cached.best_lambda,
        main_tooltip=tooltips.main_tooltip,
    )


@app.route("/player/<player_name>")
def player_page(player_name):

    # win_pct, player_games_advanced, games_of_note = create_player_games_advanced(
    #     player_games=player_games, games_data=games_data
    # )

    # Check if the player's image exists in "static/player_pics/"
    data_cached = app.config["DATA_CACHED"]
    image_path = f"static/player_pics/{player_name}.png"
    image_exists = os.path.exists(image_path)

    full_name, height_str, position = load_player_bio_data(
        player_name=player_name, player_data=data_cached.player_data
    )

    return render_template(
        "player.html",
        player_name=player_name,
        full_name=full_name,
        height_str=height_str,
        position=position,
        image_exists=image_exists,
        image_path=image_path if image_exists else None,
        player_stats=format_stats_for_site(
            data_cached.player_data.filter(pl.col("player") == player_name).drop(
                ["player", "rating", "tiered_rating", "full_name", "height", "position"]
            )
        ),
        player_rating=data_cached.ratings.filter(pl.col("player") == player_name)
        .with_columns(pl.col("rating").round(5))
        .to_dicts(),
        player_days=format_stats_for_site(
            data_cached.player_days.filter(pl.col("player") == player_name).drop(
                ["player", "rating"]
            )
        ),
        player_games=format_stats_for_site(
            data_cached.player_games.filter(pl.col("player") == player_name).drop(
                ["rating", "player"]
            )
        ),
        player_teammates=format_stats_for_site(
            data_cached.teammates.filter(pl.col("player") == player_name).drop(
                ["player", "pairing"]
            )
        ),
        player_oppponents=format_stats_for_site(
            data_cached.opponents.filter(pl.col("player") == player_name).drop(["player"])
        ),
        # player_games_advanced=player_games_advanced.to_pandas().to_dict(
        #     orient="records"
        # ),
        # games_of_note=games_of_note.to_pandas()
        # .drop(["Date", "Team", "Favorite"], axis=1)
        # .to_dict(orient="records"),
        main_tooltip=tooltips.main_tooltip,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=4010, debug=True)
