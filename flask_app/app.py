import subprocess
from flask import Flask, render_template
from utility_imports import tooltips

from collective_bball.web_data_loader import get_stats, get_ratings

app = Flask(__name__, static_folder="../static")

# Global storage for precomputed data
stats_data = None
games_data = None
ratings_data = None
best_alpha = None


def run_rapm_model():
    subprocess.run(
        [
            "python",
            "-m",
            "collective_bball.rapm_model_main",
        ],
        check=True,
    )


def filter_dictionary(dictionary, player_name):
    return [entry for entry in dictionary if entry["Player"] == player_name]


def aggregate_data():
    stats, games = get_stats()  # Pull stats dict
    ratings, best_alpha = get_ratings()

    return stats, games, ratings, best_alpha


@app.route("/")
def home():
    global stats_data, games_data, ratings_data, best_alpha  # Use global variables

    run_rapm_model()  # Run the model before fetching the data

    # Store computed data in global variables
    stats_data, games_data, ratings_data, best_alpha = aggregate_data()

    return render_template(
        "index.html",
        stats=stats_data,
        games=games_data,
        ratings=ratings_data,
        best_alpha=best_alpha,
        main_tooltip=tooltips.main_tooltip
    )


@app.route("/player/<player_name>")
def player_page(player_name):
    global stats_data, games_data, ratings_data  # Access precomputed data

    if stats_data is None or games_data is None or ratings_data is None:
        return "Data not loaded. Please visit the homepage first.", 500

    filtered_games = [
        game for game in games_data
        if player_name in {game["A1"], game["A2"], game["A3"], game["A4"], game["A5"],
                           game["B1"], game["B2"], game["B3"], game["B4"], game["B5"]}
    ]

    return render_template(
        "player.html",
        player_name=player_name,
        player_stats=filter_dictionary(stats_data, player_name),
        player_rating=filter_dictionary(ratings_data, player_name),
        player_games=filtered_games,
        main_tooltip=tooltips.main_tooltip
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=4010, debug=True)
