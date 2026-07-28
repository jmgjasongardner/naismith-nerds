"""
Naismith Nerds web application.

Boots by loading prebuilt parquet artifacts, so nothing here imports pandas,
openpyxl, scikit-learn or plotly at module scope. Those belong to the build
path, which runs on a background thread or from the CLI.

Routes:
    /            new site
    /classic     the original site, built solo by Jason (see legacy_views.py)
    /api/*       JSON for the tables
    /admin/*     password-protected refresh and upload
"""

import logging
import os
from datetime import datetime, timedelta
from io import BytesIO

import zoneinfo
from flask import Flask, current_app, jsonify, render_template, request

import polars as pl

from collective_bball import artifacts
from collective_bball.paths import player_photo_path, player_thumb_path
from flask_app.api import api
from flask_app.data_store import DataStore
from flask_app.legacy_views import legacy
from flask_app.player_page_data_loader import load_player_bio_data
from flask_app.refresh import DEFAULT_INTERVAL_SECONDS, RefreshService

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

EASTERN = zoneinfo.ZoneInfo("America/New_York")

MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}


def _initial_data():
    """Load prebuilt artifacts, building them first if none exist.

    A build here is the cold-start path only: a fresh volume, or a deploy that
    changed the artifact schema. The steady state is a sub-second load.
    """
    if artifacts.is_current():
        return artifacts.load()

    logger.warning("No usable artifacts found; building from source (this is slow)")
    from collective_bball.utils.util_code import get_data_source

    return artifacts.build_and_save(get_data_source())


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static")

    store = DataStore(_initial_data())
    app.config["DATA_STORE"] = store

    interval = int(
        os.environ.get("REFRESH_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS)
    )
    refresh_service = RefreshService(store, interval_seconds=interval)
    app.config["REFRESH_SERVICE"] = refresh_service
    if os.environ.get("DISABLE_AUTO_REFRESH", "").lower() not in ("1", "true", "yes"):
        refresh_service.start()

    app.register_blueprint(legacy)
    app.register_blueprint(api)
    _register_routes(app)

    @app.context_processor
    def inject_globals():
        """Every page embeds the set of players who have a thumbnail, so tables
        can render avatars without probing for images that would 404."""
        return {"thumb_players": _players_with_thumbs(app.config["DATA_STORE"])}

    return app


def _players_with_thumbs(store) -> list:
    """Cached per data version; a directory scan per request would be wasteful."""
    cached = _players_with_thumbs.cache
    if cached.get("version") == store.version:
        return cached["names"]

    names = sorted(
        name
        for name in store.data.player_data["player"].to_list()
        if player_thumb_path(name).exists()
    )
    _players_with_thumbs.cache = {"version": store.version, "names": names}
    return names


_players_with_thumbs.cache = {}


def _require_password() -> bool:
    """Admin endpoints share the existing upload password."""
    expected = os.environ.get("UPLOAD_PASSWORD")
    if not expected:
        return False
    supplied = request.form.get("password") or request.headers.get("X-Admin-Password")
    return supplied == expected


def _register_routes(app: Flask) -> None:

    @app.route("/")
    def home():
        data = current_app.config["DATA_STORE"].data
        latest = data.meta.get("latest_game_date")
        top = data.player_data.sort("rating", descending=True, nulls_last=True).row(
            0, named=True
        )

        # Wins leader over the trailing three months, from the daily splits.
        cutoff = (
            datetime.strptime(latest, "%Y-%m-%d").date() - timedelta(days=90)
        ).isoformat()
        recent = (
            data.player_days.filter(pl.col("game_date") >= cutoff)
            .group_by("player")
            .agg(pl.col("wins").sum().alias("wins"))
            .sort(["wins", "player"], descending=[True, False])
        )
        recent_leader = recent.row(0, named=True) if recent.height else None

        summary = {
            "num_days": data.days.height,
            "num_games": data.games.height,
            "num_players": data.player_data.height,
            "active_players": int(data.player_data["active_player"].sum() or 0),
            "latest_date": latest,
            "latest_games": data.games.filter(pl.col("game_date") == latest).height,
            "top_player": top["player"],
            "top_rating": top["rating"],
            "recent_leader": recent_leader["player"] if recent_leader else None,
            "recent_wins": recent_leader["wins"] if recent_leader else 0,
        }
        # Only the near window on the home page; the full year lives at
        # /birthdays.
        near = [b for b in _birthday_rows(data) if -7 <= b["days_away"] <= 14]

        return render_template("index.html", summary=summary, birthdays=near)

    @app.route("/player/<player_name>")
    def player_page(player_name):
        data = current_app.config["DATA_STORE"].data
        rows = data.player_data.filter(pl.col("player") == player_name)
        if rows.is_empty():
            return render_template("not_found.html", thing=player_name), 404

        row = rows.row(0, named=True)
        full_name, height_str, position, birthday = load_player_bio_data(
            player_name=player_name, player_data=data.player_data
        )

        # Where this rating sits among players who earned their own rating.
        # Tiered players share a group estimate, so ranking them against
        # individually-fitted ratings would be misleading.
        rating_rank = None
        if row.get("rating") is not None and not row.get("tiered_rating"):
            rated = data.player_data.filter(pl.col("tiered_rating") == 0)[
                "rating"
            ].to_list()
            rating_rank = {
                "rank": ordinal(_rank_of(rated, row["rating"])),
                "total": len(rated),
            }

        return render_template(
            "player.html",
            player_name=player_name,
            full_name=full_name,
            height_str=height_str,
            position=position,
            birthday=birthday,
            is_active=bool(row.get("active_player")),
            rating_rank=rating_rank,
            profile=_player_profile(
                data.player_data, row, _player_awards(data.days, player_name)
            ),
            image_exists=player_photo_path(player_name).exists(),
            stats={
                # Withheld for tiered players: the number is their tier's.
                "rating": None if row.get("tiered_rating") else row.get("rating"),
                "tiered": bool(row.get("tiered_rating")),
                "wins": row.get("wins"),
                "losses": row.get("losses"),
                "win_pct": row.get("win_pct"),
                "games_played": row.get("games_played"),
                "days_played": row.get("days_played"),
                "avg_score_diff": row.get("avg_score_diff"),
                "gospel": row.get("result_vs_expectation"),
                "most_recent_game": row.get("most_recent_game"),
                "pct_total_days_played": row.get("pct_total_days_played"),
            },
        )

    @app.route("/date/<date>")
    def date_page(date):
        data = current_app.config["DATA_STORE"].data
        day_rows = data.days.filter(pl.col("game_date") == date)
        if day_rows.is_empty():
            return render_template("not_found.html", thing=date), 404

        # Neighboring runs, for the prev/next links.
        all_dates = data.days["game_date"].sort().to_list()
        index = all_dates.index(date)

        day = day_rows.row(0, named=True)

        # How strong this run was relative to every other, both per player and
        # weighted by games played.
        def rank_badge(column):
            values = data.days[column].to_list()
            total = len([v for v in values if v is not None])
            if day[column] is None or total < 2:
                return None
            rank = _rank_of(values, day[column])
            return {
                "rank": ordinal(rank),
                "total": total,
                # 0 = worst run, 1 = best. Drives the red-to-green scale.
                "pct": (total - rank) / (total - 1),
            }

        return render_template(
            "date.html",
            date=date,
            day=day,
            day_of_week=day["day"],
            weighted_rank=rank_badge("mean_rating_player_games"),
            avg_rank=rank_badge("mean_rating_players"),
            prev_date=all_dates[index - 1] if index > 0 else None,
            next_date=all_dates[index + 1] if index < len(all_dates) - 1 else None,
        )

    @app.route("/team-builder")
    def team_builder():
        data = current_app.config["DATA_STORE"].data
        roster = (
            data.player_data.select(["player", "rating", "games_played"])
            .drop_nulls("rating")
            .sort("rating", descending=True)
            .rename({"games_played": "games"})
            .to_dicts()
        )
        return render_template("team_builder.html", roster=roster)

    @app.route("/glossary")
    def glossary():
        return render_template("glossary.html")

    @app.route("/birthdays")
    def birthdays_page():
        data = current_app.config["DATA_STORE"].data
        rows = _birthday_rows(data)
        today = datetime.now(EASTERN).date()

        # Twelve month buckets, each sorted by day of month.
        months = [{"name": MONTH_NAMES[m], "num": m, "entries": []} for m in range(1, 13)]
        for row in rows:
            month, day = row["month"], row["day"]
            months[month - 1]["entries"].append(row)
        for bucket in months:
            bucket["entries"].sort(key=lambda r: r["day"])
            bucket["is_current"] = bucket["num"] == today.month

        return render_template(
            "birthdays.html",
            months=months,
            upcoming=[r for r in rows if -7 <= r["days_away"] <= 14],
            total=len(rows),
        )

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("not_found.html", thing=None), 404

    @app.route("/health")
    def health():
        store = current_app.config["DATA_STORE"]
        return jsonify(
            {
                "status": "ok",
                "data_version": store.version,
                "built_at": getattr(store.data, "built_at", None),
                "games": store.data.games.height,
                "latest_game_date": store.data.meta.get("latest_game_date"),
            }
        )

    @app.route("/admin/status")
    def admin_status():
        store = current_app.config["DATA_STORE"]
        service = current_app.config["REFRESH_SERVICE"]
        return jsonify(
            {
                "data_version": store.version,
                "meta": store.data.meta,
                "refresh": service.status,
            }
        )

    @app.route("/admin/reload", methods=["GET", "POST"])
    def admin_reload():
        """Swap in artifacts rebuilt by another process.

        Unauthenticated on purpose: it only re-reads files this app already
        owns and exposes nothing new. Handy after a CLI rebuild during local
        development, where restarting the server is the only alternative.
        """
        service = current_app.config["REFRESH_SERVICE"]
        return jsonify(service.reload_if_artifacts_changed())

    @app.route("/admin/refresh", methods=["POST"])
    def admin_refresh():
        if not _require_password():
            return jsonify({"error": "unauthorized"}), 401
        service = current_app.config["REFRESH_SERVICE"]
        force = request.form.get("force", "").lower() in ("1", "true", "yes")
        return jsonify(service.run_once(force=force, allow_stale=False))

    @app.route("/api/birthdays")
    def birthday_api():
        return jsonify(_birthday_rows(current_app.config["DATA_STORE"].data))

    @app.route("/upload", methods=["GET", "POST"])
    def upload_data():
        """Manual workbook upload. Kept as a fallback for when OneDrive is
        unavailable and Jason needs the site updated right now."""
        if request.method != "POST":
            return render_template("upload.html", success=False, error=None)

        if not _require_password():
            return render_template(
                "upload.html", error="Invalid password. Please try again.", success=False
            )

        uploaded = request.files.get("excel_file")
        if uploaded is None or uploaded.filename == "":
            return render_template(
                "upload.html", error="No file selected.", success=False
            )
        if not uploaded.filename.endswith((".xlsx", ".xlsm")):
            return render_template(
                "upload.html",
                error="Invalid file type. Upload an .xlsx or .xlsm file.",
                success=False,
            )

        try:
            file_bytes = BytesIO(uploaded.read())
            fingerprint = artifacts.source_fingerprint(file_bytes)
            data = artifacts.build(file_bytes)
            artifacts.save(data, fingerprint=fingerprint)
            store = current_app.config["DATA_STORE"]
            store.swap(artifacts.load())

            report = data.ingest_report
            message = f"Data updated. Processed {report.get('rows_kept', 0)} games."
            if report.get("rows_skipped"):
                message += f" Skipped {report['rows_skipped']} incomplete row(s)."
            return render_template("upload.html", success=True, message=message)
        except Exception as exc:
            logger.exception("Upload rebuild failed")
            return render_template(
                "upload.html", error=f"Error processing file: {exc}", success=False
            )


def _birthday_rows(data) -> list:
    """Upcoming and just-passed birthdays, nearest first."""
    import polars as pl

    rows = (
        data.player_data.select(["player", "birthday"])
        .drop_nulls()
        .filter(pl.col("birthday").str.len_chars() > 0)
        .to_dicts()
    )
    today = datetime.now(EASTERN).date()
    processed = []

    for row in rows:
        player, raw = row["player"], row["birthday"]
        if not raw:
            continue

        try:
            bday = datetime.strptime(raw, "%Y-%m-%d").date()
            has_year = True
        except ValueError:
            try:
                bday = datetime.strptime(raw, "%m-%d").date().replace(year=today.year)
            except ValueError:
                continue
            has_year = False

        this_year = bday.replace(year=today.year)
        days_since = (this_year - today).days
        next_birthday = (
            bday.replace(year=today.year + 1) if days_since < 0 else this_year
        )
        days_until = (next_birthday - today).days
        days_diff = days_since if -7 <= days_since <= 0 else days_until

        if has_year:
            age = today.year - bday.year + 1
            if days_since >= -7:
                age -= 1
            label = f"{player}'s {age}{_ordinal_suffix(age)} birthday!"
        else:
            label = f"{player}'s birthday!"

        if -7 <= days_since <= -2:
            day_text = f"{-days_diff} days ago"
        elif days_since == -1:
            day_text = "Yesterday!"
        elif days_since == 0:
            day_text = "🎉Today!!🥳"
        elif days_since == 1:
            day_text = "Tomorrow!"
        else:
            day_text = f"{days_diff} days from now"

        processed.append(
            {
                "player": player,
                "raw": raw,
                "display_date": next_birthday.strftime("%b %d"),
                "month": bday.month,
                "day": bday.day,
                "has_year": has_year,
                "age": age if has_year else None,
                "days_away": days_diff,
                "days_from_today": day_text,
                "label": label,
            }
        )

    processed.sort(key=lambda item: item["days_away"])
    return processed


# The full stat sheet on a player page, grouped so it reads as sections rather
# than one undifferentiated wall of numbers. Every column the Players table
# shows appears here; the hero tiles above stay deliberately short.
PROFILE_GROUPS = [
    ("Impact", [
        "rating", "result_vs_expectation", "avg_score_diff", "proj_score_diff",
    ]),
    ("Record", [
        "wins", "losses", "win_pct", "expected_wins", "expected_win_pct",
    ]),
    ("Volume", [
        "games_played", "days_played", "games_played_per_day",
        "pct_total_games_played", "pct_total_days_played",
    ]),
    ("Company kept", [
        "team_quality", "teammate_quality", "opp_quality",
        "other_9_players_quality_diff",
        "pct_positive_teammates", "pct_positive_opponents",
        "pct_games_favorite", "pct_games_better_teammates",
    ]),
    ("Honors", ["mvps", "lvps", "mvp_pct", "lvp_pct"]),
    ("Attendance", [
        "mon_rate", "wed_rate", "sat_rate",
        "first_game_of_day_rate", "last_game_of_day_rate", "most_recent_game",
    ]),
]


def _format_stat(key: str, value, dtype) -> dict:
    """One stat, formatted for display, with the sign class it should wear."""
    from flask_app.columns import TIPS, label_for, type_for

    kind = type_for(key, dtype)
    entry = {"key": key, "label": label_for(key), "tip": TIPS.get(key), "tone": ""}

    if value is None:
        entry["value"] = "—"
        return entry

    if kind == "pct":
        entry["value"] = f"{value * 100:.1f}%"
    elif kind == "signed":
        entry["value"] = f"{value:+.2f}"
        entry["tone"] = "pos" if value > 0 else "neg" if value < 0 else ""
    elif kind == "int":
        entry["value"] = f"{value:,}"
    elif kind == "num":
        entry["value"] = f"{value:.2f}"
    else:
        entry["value"] = str(value)

    return entry


def _player_profile(player_data, row: dict, awards: dict) -> list:
    """Group the player's columns into labelled sections for the stat sheet."""
    dtypes = dict(zip(player_data.columns, player_data.dtypes))

    # A tiered player's rating belongs to their tier, not to them, so it is
    # withheld here for the same reason it is absent from the Players table.
    tiered = bool(row.get("tiered_rating"))
    groups = []

    for title, keys in PROFILE_GROUPS:
        items = []
        for key in keys:
            if key not in row:
                continue
            if key == "rating" and tiered:
                continue
            item = _format_stat(key, row.get(key), dtypes.get(key))
            # MVP/LVP counts expand to the dates they were earned.
            if key in ("mvps", "lvps") and awards.get(key):
                item["dates"] = awards[key]
            items.append(item)
        if items:
            groups.append({"title": title, "items": items})

    return groups


def _player_awards(days, player_name: str) -> dict:
    """Dates this player took the day's MVP or LVP, most recent first."""
    import polars as pl

    def dates_for(column):
        return (
            days.filter(pl.col(column) == player_name)
            .sort("game_date", descending=True)
            .select(["game_date", f"{column}_gospel"])
            .rename({f"{column}_gospel": "gospel"})
            .to_dicts()
        )

    return {"mvps": dates_for("mvp"), "lvps": dates_for("lvp")}


def ordinal(n: int) -> str:
    """1 -> 1st, 2 -> 2nd, 11 -> 11th."""
    return f"{n}{_ordinal_suffix(n)}"


def _rank_of(values: list, target, descending: bool = True) -> int:
    """1-based rank of `target` within `values`, highest first by default."""
    ordered = sorted((v for v in values if v is not None), reverse=descending)
    return ordered.index(target) + 1


def _ordinal_suffix(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "st"
    if n % 10 == 2 and n % 100 != 12:
        return "nd"
    if n % 10 == 3 and n % 100 != 13:
        return "rd"
    return "th"


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
