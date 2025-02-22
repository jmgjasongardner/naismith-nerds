from flask import Flask, render_template
from flask_app.utility_imports import tooltips
from collective_bball.eda_main import generate_stats
from flask_app.web_data_loader import format_stats_for_site, get_model_outputs, combine_tier_ratings, calculate_game_spreads
from flask_app.player_page_data_loader import create_player_games

app = Flask(__name__, static_folder="../static")

# Global storage for precomputed data
stats_data = None
games_data = None
ratings_data = None
best_lambda = None


def filter_dictionary(dictionary, player_name):
    return [entry for entry in dictionary if entry["Player"] == player_name]


def aggregate_data():
    stats, games = generate_stats(run_locally=False)
    ratings, best_lambda, tiers = get_model_outputs()
    ratings_with_small_samples = combine_tier_ratings(ratings=ratings, stats=stats, tiers=tiers)

    games_with_spreads = calculate_game_spreads(games=games, ratings=ratings_with_small_samples)


    stats_to_site = format_stats_for_site(stats.to_pandas())
    ratings_to_site = ratings.to_pandas().to_dict(orient="records")

    return stats_to_site, games_with_spreads, ratings_to_site, best_lambda


@app.route("/")
def home():
    global stats_data, games_data, ratings_data, best_lambda  # Use global variables

    # Store computed data in global variables
    stats_data, games_data, ratings_data, best_lambda = aggregate_data()

    return render_template(
        "index.html",
        stats=stats_data,
        games=games_data.to_pandas().drop('Date', axis = 1).to_dict(orient="records"),
        ratings=ratings_data,
        best_lambda=best_lambda,
        main_tooltip=tooltips.main_tooltip
    )


@app.route("/player/<player_name>")
def player_page(player_name):
    global stats_data, games_data, ratings_data  # Access precomputed data

    if stats_data is None or games_data is None or ratings_data is None:
        return "Data not loaded. Please visit the homepage first.", 500

    player_rating = filter_dictionary(ratings_data, player_name)
    if player_rating == []: # TODO: Fix with logic to calculate player rating overall for tiers calc
        player_rating = [{'Player': player_name, 'Rating': 0}]

    player_games = create_player_games(games_data=games_data, player_name=player_name, player_rating=list(player_rating[0].values())[1])

    return render_template(
        "player.html",
        player_name=player_name,
        player_stats=filter_dictionary(stats_data, player_name),
        player_rating=filter_dictionary(ratings_data, player_name),
        player_games=player_games.to_pandas().drop(['Date', 'Team'], axis = 1).to_dict(orient="records"),
        main_tooltip=tooltips.main_tooltip
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=4010, debug=True)
