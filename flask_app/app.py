from flask import Flask, render_template, jsonify, request, redirect, url_for
from flask_app.utility_imports import tooltips

import duckdb
import psutil
import polars as pl
import os
from io import BytesIO

from datetime import datetime
import zoneinfo

from collective_bball.main import data, create_data
from collective_bball.plots import Plots

from flask_app.web_data_loader import format_stats_for_site
from flask_app.player_page_data_loader import (
    load_player_bio_data,
    create_player_games_advanced,
)


# ---------------------------------------------------------
# Flask App Configuration
# ---------------------------------------------------------
app = Flask(__name__, static_folder="static")
app.config["DATA_CACHED"] = data


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
def filter_dictionary(dictionary, player_name):
    return [entry for entry in dictionary if entry["Player"] == player_name]


def log_memory_usage():
    process = psutil.Process(os.getpid())
    process.memory_info()  # rss available if needed


# ---------------------------------------------------------
# Pre-compute home page data (called once at startup)
# ---------------------------------------------------------
def _prepare_home_page_data(data_cached):
    """Pre-compute all formatted data for home page to avoid per-request processing."""

    # Pre-compute which players have images (avoid repeated os.path.exists calls)
    player_names = data_cached.player_data["player"].to_list()
    players_with_images = set()
    for name in player_names:
        img_path = os.path.join("flask_app", "static", "player_pics_thumbs", f"{name}.webp")
        if os.path.exists(img_path):
            players_with_images.add(name)

    # Helper to add has_img without os.path.exists per row
    def add_has_img(rows):
        for row in rows:
            row["has_img"] = row.get("Player", "") in players_with_images
        return rows

    stats = format_stats_for_site(
        data_cached.player_data.drop([
            "rating", "tiered_rating", "full_name", "height", "position", "resident", "birthday"
        ])
    )
    add_has_img(stats)

    games = format_stats_for_site(
        data_cached.games.with_columns(
            pl.when(pl.col("first_poss") == 1)
            .then(pl.lit("A"))
            .when(pl.col("first_poss") == -1)
            .then(pl.lit("B"))
            .otherwise(pl.lit("Idk"))
            .alias("first_poss")
        ).drop([
            "winning_score", "games_waited_B", "games_waited_A",
            "consecutive_games_B", "consecutive_games_A",
            "total_games_played_diff", "consecutive_games_waited_diff",
            "consecutive_games_played_diff", "total_games_played_diff_sq",
            "consecutive_games_waited_diff_sq", "consecutive_games_played_diff_sq",
        ])
    )

    ratings = format_stats_for_site(
        data_cached.ratings.filter(~pl.col("player").str.contains("Tier")).with_columns(
            pl.col("rating").round(5)
        ).join(
            data_cached.player_data.select(["player", "active_player"]),
            on="player",
            how="left"
        )
    )
    add_has_img(ratings)

    player_days = format_stats_for_site(data_cached.player_days.drop("rating", "resident"))
    teammates = format_stats_for_site(data_cached.teammates.drop(["player", "teammate"]).unique("pairing"))
    opponents = format_stats_for_site(data_cached.opponents)
    days_of_week = format_stats_for_site(data_cached.days_of_week)
    days = format_stats_for_site(data_cached.days)

    return {
        "stats": stats,
        "num_days": len(data_cached.days),
        "games": games,
        "ratings": ratings,
        "player_days": player_days,
        "teammates": teammates,
        "opponents": opponents,
        "days_of_week": days_of_week,
        "days": days,
        "best_lambda": data_cached.best_lambda,
        "plot_ratings": data_cached.plot_ratings,
        "plot_rapm_apm": data_cached.plot_rapm_apm,
    }


# Pre-compute home page data at startup
app.config["HOME_PAGE_DATA"] = _prepare_home_page_data(data)


# ---------------------------------------------------------
# API: Birthdays
# ---------------------------------------------------------
@app.route("/api/birthdays")
def birthday_api():
    data_cached = app.config["DATA_CACHED"]

    bday_rows = format_stats_for_site(
        data_cached.player_data.select(["player", "birthday"]).drop_nulls()
    )
    today = datetime.now(zoneinfo.ZoneInfo("America/New_York")).date()

    processed = []

    for row in bday_rows:
        player = row["Player"]
        raw = row["birthday"]

        if not raw:
            continue

        # Parse birthday
        try:
            bday = datetime.strptime(raw, "%Y-%m-%d").date()
            has_year = True
        except ValueError:
            bday = datetime.strptime(raw, "%m-%d").date().replace(year=today.year)
            has_year = False

        this_year = bday.replace(year=today.year)
        days_since = (this_year - today).days

        next_birthday = (
            bday.replace(year=today.year + 1) if days_since < 0 else this_year
        )
        days_until = (next_birthday - today).days

        if -7 <= days_since <= 0:
            days_diff = days_since
        else:
            days_diff = days_until

        if has_year:
            age = today.year - bday.year + 1
            if days_since >= -7:
                age -= 1

            if age % 10 == 1 and age % 100 != 11:
                suffix = "st"
            elif age % 10 == 2 and age % 100 != 12:
                suffix = "nd"
            elif age % 10 == 3 and age % 100 != 13:
                suffix = "rd"
            else:
                suffix = "th"

            label = f"{player}'s {age}{suffix} birthday!"
        else:
            label = f"{player}'s birthday!"

        display_date = next_birthday.strftime("%b %d")

        if -7 <= days_since <= -2:
            display_day_text = f"{-days_diff} days ago"
        elif days_since == -1:
            display_day_text = "Yesterday!"
        elif days_since == 0:
            display_day_text = "🎉Today!!🥳"
        elif days_since == 1:
            display_day_text = "Tomorrow!"
        else:
            display_day_text = f"{days_diff} days from now"

        processed.append(
            {
                "raw": raw,
                "display_date": display_date,
                "days_away": days_diff,
                "days_from_today": display_day_text,
                "label": label,
            }
        )

    processed.sort(key=lambda x: x["days_away"])
    return jsonify(processed)


# ---------------------------------------------------------
# HOME PAGE
# ---------------------------------------------------------
@app.route("/")
def home():
    # Use pre-computed data (no per-request processing)
    cached = app.config["HOME_PAGE_DATA"]
    main_tooltip = tooltips.main_tooltip

    return render_template(
        "index.html",
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
        main_tooltip=main_tooltip,
        plot_ratings=cached["plot_ratings"],
        plot_rapm_apm=cached["plot_rapm_apm"],
    )


# ---------------------------------------------------------
# PLAYER PAGE
# ---------------------------------------------------------
@app.route("/player/<player_name>")
def player_page(player_name):
    data_cached = app.config["DATA_CACHED"]

    image_path = f"flask_app/static/player_pics/{player_name}.png"
    image_exists = os.path.exists(image_path)

    full_name, height_str, position, birthday = load_player_bio_data(
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

    return render_template(
        "player.html",
        player_name=player_name,
        full_name=full_name,
        height_str=height_str,
        position=position,
        birthday=birthday,
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
                    "birthday",
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
        main_tooltip=tooltips.main_tooltip,
    )


# ---------------------------------------------------------
# DATE PAGE
# ---------------------------------------------------------
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
            data_cached.games.filter(pl.col("game_date") == date)
            .with_columns(
                pl.when(pl.col("first_poss") == 1)
                .then(pl.lit("A"))
                .when(pl.col("first_poss") == -1)
                .then(pl.lit("B"))
                .otherwise(pl.lit("Idk"))
                .alias("first_poss")
            )
            .drop(
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
        ),
        main_tooltip=tooltips.main_tooltip,
    )


# ---------------------------------------------------------
# UPLOAD DATA
# ---------------------------------------------------------
def rebuild_data_from_file(file_bytes: BytesIO):
    """Rebuild all data from uploaded Excel file."""
    import argparse
    from collective_bball.basketball_data import BasketballData
    from collective_bball.rapm_model import RAPMModel
    from collective_bball.moneyline_model import BettingGames
    from collective_bball import create_db_tables

    args = argparse.Namespace(
        use_tier_data=True,
        min_games_to_not_tier=20,
        default_lambda=True,
        lambda_params=[0.1, 0.5, 1, 5, 10, 25, 50, 100],
        decay_half_life=270,
        save_csv=False,
        loop_through_ratings_dates=False,
    )

    conn = duckdb.connect("bball_database.duckdb")
    create_db_tables.create_tables(conn)

    new_data = BasketballData(data_source=file_bytes, args=args)
    new_data.clean_data()
    new_data.compute_clock_and_starting_poss()
    new_data.compute_player_stats()
    new_data.compute_fatigue()

    rapm_model = RAPMModel()
    new_data.compute_rapm(rapm_model)
    new_data.write_to_db(conn=conn)

    new_data.merge_player_data()

    betting_games = BettingGames()
    new_data.compute_spreads(betting_games)
    new_data.compute_moneylines(betting_games)

    new_data.assemble_player_data()
    new_data.assemble_days_data()

    plots = Plots(conn)
    new_data.plot_things(plots)

    conn.close()

    return new_data


@app.route("/upload", methods=["GET", "POST"])
def upload_data():
    upload_password = os.environ.get("UPLOAD_PASSWORD")

    if request.method == "POST":
        # Check password
        submitted_password = request.form.get("password", "")
        if not upload_password or submitted_password != upload_password:
            return render_template(
                "upload.html",
                error="Invalid password. Please try again.",
                success=False,
            )

        # Check if file was uploaded
        if "excel_file" not in request.files:
            return render_template(
                "upload.html",
                error="No file uploaded. Please select a file.",
                success=False,
            )

        file = request.files["excel_file"]
        if file.filename == "":
            return render_template(
                "upload.html",
                error="No file selected. Please choose a file.",
                success=False,
            )

        # Check file extension
        if not file.filename.endswith((".xlsx", ".xlsm")):
            return render_template(
                "upload.html",
                error="Invalid file type. Please upload an Excel file (.xlsx or .xlsm).",
                success=False,
            )

        try:
            # Read file into BytesIO
            file_bytes = BytesIO(file.read())

            # Rebuild all data
            new_data = rebuild_data_from_file(file_bytes)

            # Update the cached data
            app.config["DATA_CACHED"] = new_data
            app.config["HOME_PAGE_DATA"] = _prepare_home_page_data(new_data)

            return render_template(
                "upload.html",
                success=True,
                message=f"Data updated successfully! Processed {len(new_data.games)} games.",
            )

        except Exception as e:
            return render_template(
                "upload.html",
                error=f"Error processing file: {str(e)}",
                success=False,
            )

    # GET request - show upload form
    return render_template("upload.html", success=False, error=None)


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
