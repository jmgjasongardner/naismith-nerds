import polars as pl
from typing import Tuple


def load_data(filepath: str) -> Tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Loads game data from Excel and returns Polars DataFrames."""
    raw_games_df = pl.read_excel(
        filepath, sheet_name="GameResults", engine="openpyxl"
    ).rename({"Date": "date", "A_SCORE": "a_score", "B_SCORE": "b_score"})
    tiers = pl.read_excel(filepath, sheet_name="PlayerTiers", engine="openpyxl")
    bios = pl.read_excel(filepath, sheet_name="Bios", engine="openpyxl")

    return raw_games_df, tiers, bios


def clean_games_data(raw_games_df: pl.DataFrame) -> pl.DataFrame:
    raw_games_df = raw_games_df.sample(60)
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
            .alias("winner")
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
