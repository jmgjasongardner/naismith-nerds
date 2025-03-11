from flask import Flask, render_template
from flask_app.utility_imports import tooltips
# from collective_bball.eda_main import generate_stats
# from collective_bball.win_prob_log_reg import calculate_team_A_win_prob
from collective_bball.main import data  # Get precomputed `data`
from flask_app.web_data_loader import (
    format_stats_for_site,
    # get_model_outputs,
    # combine_tier_ratings,
    # calculate_game_spreads,
)
from flask_app.player_page_data_loader import (
    #create_player_games,
    load_player_bio_data,
    create_player_games_advanced,
)
import polars as pl
import os

app = Flask(__name__, static_folder="../static")

# Global storage for precomputed data
stats_data = None
games_data = None
ratings_data = None
best_lambda = None
ratings_with_small_samples = None
bios = None


def filter_dictionary(dictionary, player_name):
    return [entry for entry in dictionary if entry["Player"] == player_name]


# def aggregate_data():
#     stats, games = generate_stats(run_locally=False)
#     ratings, best_lambda, tiers, bios = get_model_outputs()
#     ratings_with_small_samples = combine_tier_ratings(
#         ratings=ratings, stats=stats, tiers=tiers
#     )
#
#     games_with_spreads = calculate_game_spreads(
#         games=games, ratings=ratings_with_small_samples
#     )
#     games_with_spreads_moneylines = calculate_team_A_win_prob(
#         games_with_spreads=games_with_spreads
#     )
#
#     stats_to_site = format_stats_for_site(stats.to_pandas())
#     ratings_to_site = ratings.to_pandas().to_dict(orient="records")
#
#     return (
#         stats_to_site,
#         games_with_spreads_moneylines,
#         ratings_to_site,
#         best_lambda,
#         ratings_with_small_samples,
#         bios,
#     )


@app.route("/")
def home():
    return render_template(
        "index.html",
        stats=format_stats_for_site(data.player_data.drop(['rating', 'tiered_rating', 'full_name', 'height', 'position'])),
        num_days=len(data.days),
        games=format_stats_for_site(data.games),
        ratings=format_stats_for_site(data.ratings),
        player_days=format_stats_for_site(data.player_days.drop('rating')),
        #player_games=format_stats_for_site(data.player_games),
        teammates=format_stats_for_site(data.teammates.drop(['player', 'teammate']).unique()),
        opponents=format_stats_for_site(data.opponents),
        #teammate_games=format_stats_for_site(data.teammate_games),
        #opponent_games=format_stats_for_site(data.opponent_games),
        days_of_week=format_stats_for_site(data.days_of_week),
        days=format_stats_for_site(data.days),
        best_lambda=data.best_lambda,
        main_tooltip=tooltips.main_tooltip,
    )


@app.route("/player/<player_name>")
def player_page(player_name):

    # win_pct, player_games_advanced, games_of_note = create_player_games_advanced(
    #     player_games=player_games, games_data=games_data
    # )

    # Check if the player's image exists in "static/player_pics/"
    image_path = f"static/player_pics/{player_name}.png"
    image_exists = os.path.exists(image_path)

    full_name, height_str, position = load_player_bio_data(
        player_name=player_name, player_data=data.player_data
    )

    return render_template(
        "player.html",
        player_name=player_name,
        full_name=full_name,
        height_str=height_str,
        position=position,
        image_exists=image_exists,
        image_path=image_path if image_exists else None,
        player_stats=format_stats_for_site(data.player_data.filter(pl.col('player') == player_name).drop(['player', 'rating', 'tiered_rating', 'full_name', 'height', 'position'])),
        player_rating=data.ratings.filter(pl.col('player') == player_name).with_columns(pl.col('rating').round(5)).to_pandas().to_dict(orient="records"),
        player_days=format_stats_for_site(
            data.player_days.filter(
                pl.col('player') == player_name).drop(['player', 'rating'])),
        player_games=format_stats_for_site(data.player_games.filter(pl.col('player') == player_name).drop(['rating', 'player'])),
        player_teammates=format_stats_for_site(
            data.teammates.filter(
                pl.col('player') == player_name).drop(['player', 'pairing'])),
        player_oppponents=format_stats_for_site(
            data.opponents.filter(
                pl.col('player') == player_name).drop(['player'])),

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
