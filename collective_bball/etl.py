import polars as pl
from typing import Tuple, Union, IO
import pandas as pd


def load_data(filepath: Union[str, IO]) -> Tuple[pl.DataFrame, pl.DataFrame]:
    """Loads game data from Excel file path or file-like object and returns Polars DataFrames."""
    raw_games_df = (
        pl.DataFrame(
            pd.read_excel(filepath, sheet_name="GameResults", engine="openpyxl")
        )
    ).rename({"Date": "date", "A_SCORE": "a_score", "B_SCORE": "b_score"})
    raw_games_df = raw_games_df.drop(
        [col for col in raw_games_df.columns if "Unnamed" in col]
    )
    tiers = pl.DataFrame(
        pd.read_excel(filepath, sheet_name="Players", engine="openpyxl", dtype=str)
    ).with_columns(pl.col("birthday").cast(pl.Utf8), pl.col("resident").cast(pl.Int8))

    return raw_games_df, tiers


def clean_games_data(raw_games_df: pl.DataFrame) -> pl.DataFrame:
    games = (
        raw_games_df.with_columns(
            pl.col("a_score").cast(pl.Int64), pl.col("b_score").cast(pl.Int64)
        )
        .with_columns(
            pl.when(pl.col("b_score") > pl.col("a_score"))
            .then(pl.lit("B"))
            .when(pl.col("b_score") < pl.col("a_score"))
            .then(pl.lit("A"))
            .otherwise(pl.lit("Error"))
            .alias("winner"),
            (pl.col("b_score") - pl.col("a_score")).alias("score_diff"),
        )
        .with_columns(
            pl.col("date")
            .dt.strftime("%Y-%m-%d")
            .alias("game_date")  # Format the date to YYYY-MM-DD
        )
        .with_columns(
            pl.col("date")
            .cum_count()
            .over("game_date")
            .cast(pl.Int32)
            .alias("game_num")  # Sequential count per Date
        )
        .with_columns(
            pl.col("game_date")
            .cast(pl.Date)
            .dt.strftime("%A")
            .str.slice(0, 3)
            .alias("day")
        )
        .filter(pl.col("a_score").is_not_nan())
    ).drop("date")

    return games


def compute_clock(games: pl.DataFrame) -> pl.DataFrame:
    """
    Logic:
    - If winning_score is < 21 then clock = 1 always
    In cases where winning_score >= 21:
    - Start with default logic clock = 0
    - If a winning_score for game_num = [1,2] for that game_date is < 21, then clock = 1 for all of the games that day
    - If a winning_score for a lesser value for game_num for that game_date (so, an earlier game that day) is < 21, then clock = 1 for all of the following games
    - If it is the last game of the day (max game_num for game_date) and winning_score >= 21 then override prior logic and set clock = 0
    """
    games = games.with_columns(
        pl.when(pl.col("b_score") > pl.col("a_score"))
        .then(pl.col("b_score"))
        .when(pl.col("b_score") < pl.col("a_score"))
        .then(pl.col("a_score"))
        .alias("winning_score")
    )

    games = games.with_columns(
        [
            # mark whether each game individually had a short winning score
            (pl.col("winning_score") < 21).alias("short_game"),
        ]
    )

    # per-day max game_num (to know the last game)
    games = games.join(
        games.group_by("game_date").agg(pl.col("game_num").max().alias("max_game_num")),
        on="game_date",
    )

    # flag days where an early game (1 or 2) was short
    games = games.join(
        games.filter(pl.col("game_num").is_in([1, 2]) & pl.col("short_game"))
        .select("game_date")
        .unique()
        .with_columns(pl.lit(True).alias("early_short_day")),
        on="game_date",
        how="left",
    ).with_columns(pl.col("early_short_day").fill_null(False))

    # cumulative logic: once a short_game happens that day, all later ones become clock=1
    games = games.sort(["game_date", "game_num"]).with_columns(
        [
            pl.col("short_game")
            .cum_sum()
            .over("game_date")
            .gt(0)
            .alias("has_prior_short"),
        ]
    )

    # main logic: build base clock column step by step
    games = games.with_columns(
        [
            pl.when(pl.col("winning_score") < 21)
            .then(1)
            .when(pl.col("early_short_day"))
            .then(1)
            .when(pl.col("has_prior_short"))
            .then(1)
            .otherwise(0)
            .alias("clock")
        ]
    )

    # final override: last game of day with 21+ resets to 0
    games = games.with_columns(
        pl.when(
            (pl.col("game_num") == pl.col("max_game_num"))
            & (pl.col("winning_score") >= 21)
        )
        .then(0)
        .otherwise(pl.col("clock"))
        .alias("clock")
    )

    games = games.drop(
        ["short_game", "max_game_num", "early_short_day", "has_prior_short"]
    )

    return games


def compute_starting_poss(games: pl.DataFrame) -> pl.DataFrame:

    # Make team lists for convenience (optional, but keeps things tidy)
    games = games.with_columns(
        [
            pl.concat_list([f"A{i}" for i in range(1, 6)]).alias("teamA"),
            pl.concat_list([f"B{i}" for i in range(1, 6)]).alias("teamB"),
        ]
    )

    # Create a prev_games frame (shifted by +1 game_num so it joins to the next game)
    prev_games = games.select(
        [
            pl.col("game_date"),
            (pl.col("game_num") + 1).alias(
                "game_num"
            ),  # so prev row lines up with next game
            pl.col("winner").alias("prev_winner"),
            pl.concat_list([f"A{i}" for i in range(1, 6)]).alias("prev_teamA"),
            pl.concat_list([f"B{i}" for i in range(1, 6)]).alias("prev_teamB"),
        ]
    )

    # Join to get previous-game info on the current game row
    games = games.join(prev_games, on=["game_date", "game_num"], how="left")

    # Build a prev_winners list column (players from the winning team in previous game)
    games = games.with_columns(
        pl.when(pl.col("prev_winner") == "A")
        .then(pl.col("prev_teamA"))
        .when(pl.col("prev_winner") == "B")
        .then(pl.col("prev_teamB"))
        .otherwise(pl.lit([]))
        .alias("prev_winners")
    )

    # Count returning winners by explicitly checking each of the five player columns
    # (this avoids the list.eval/col("") ambiguity)
    games = games.with_columns(
        [
            (
                pl.col("A1").is_in(pl.col("prev_winners")).cast(pl.Int8)
                + pl.col("A2").is_in(pl.col("prev_winners")).cast(pl.Int8)
                + pl.col("A3").is_in(pl.col("prev_winners")).cast(pl.Int8)
                + pl.col("A4").is_in(pl.col("prev_winners")).cast(pl.Int8)
                + pl.col("A5").is_in(pl.col("prev_winners")).cast(pl.Int8)
            ).alias("ret_A"),
            (
                pl.col("B1").is_in(pl.col("prev_winners")).cast(pl.Int8)
                + pl.col("B2").is_in(pl.col("prev_winners")).cast(pl.Int8)
                + pl.col("B3").is_in(pl.col("prev_winners")).cast(pl.Int8)
                + pl.col("B4").is_in(pl.col("prev_winners")).cast(pl.Int8)
                + pl.col("B5").is_in(pl.col("prev_winners")).cast(pl.Int8)
            ).alias("ret_B"),
        ]
    )

    # Derive first_poss: game 1 = 0, else compare ret_A vs ret_B
    games = games.with_columns(
        pl.when(pl.col("game_num") == 1)
        .then(0)
        .when(pl.col("ret_A") > pl.col("ret_B"))
        .then(1)
        .when(pl.col("ret_B") > pl.col("ret_A"))
        .then(-1)
        .otherwise(0)
        .alias("first_poss")
    )

    # Drop the helper columns if you want a clean output
    games = games.drop(
        [
            "teamA",
            "teamB",
            "prev_teamA",
            "prev_teamB",
            "prev_winner",
            "prev_winners",
            "ret_A",
            "ret_B",
        ]
    )

    return games
