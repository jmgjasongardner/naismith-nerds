import polars as pl
from typing import Tuple
import pandas as pd


def load_data(filepath: str) -> Tuple[pl.DataFrame, pl.DataFrame]:
    """Loads game data from Excel and returns Polars DataFrames."""
    raw_games_df = (pl.DataFrame(pd.read_excel(
        filepath, sheet_name="GameResults", engine="openpyxl"
    ))).rename({"Date": "date", "A_SCORE": "a_score", "B_SCORE": "b_score"})
    raw_games_df = raw_games_df.drop([col for col in raw_games_df.columns if "Unnamed" in col])
    tiers = pl.DataFrame(pd.read_excel(filepath, sheet_name="Players", engine="openpyxl"))

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
