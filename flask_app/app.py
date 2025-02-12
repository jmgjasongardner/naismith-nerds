import subprocess
from flask import Flask, render_template
from collective_bball.web_data_loader import get_stats, get_ratings

app = Flask(__name__, static_folder="../static")


# Run rapm_model_main.py with specific arguments
def run_rapm_model():
    subprocess.run(
        [
            "python",
            "-m",
            "collective_bball.rapm_model_main",
        ],
        check=True,
    )


@app.route("/")
def home():
    run_rapm_model()  # Run the model before fetching the data

    stats_data, games_data = get_stats()  # Pull stats dict
    players_data, best_alpha = get_ratings()

    return render_template(
        "index.html", stats=stats_data, games=games_data, players=players_data, best_alpha=best_alpha
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=4010, debug=True)
