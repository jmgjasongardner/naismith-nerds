import polars as pl
from typing import Tuple

def load_data(filepath: str) -> Tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Loads game data from Excel and returns Polars DataFrames."""
    raw_games_df = pl.read_excel(filepath, sheet_name="GameResults", engine="openpyxl")
    tiers = pl.read_excel(filepath, sheet_name="PlayerTiers", engine="openpyxl")
    bios = pl.read_excel(filepath, sheet_name="Bios", engine="openpyxl")

    return raw_games_df, tiers, bios

def clean_games_data(raw_games_df: pl.DataFrame) -> pl.DataFrame:
    games = (
        raw_games_df.with_columns(
            pl.col("A_SCORE").cast(pl.Int64), pl.col("B_SCORE").cast(pl.Int64)
        )
        .with_columns(
            pl.when(pl.col("B_SCORE") > pl.col("A_SCORE"))
            .then(pl.lit("B"))
            .when(pl.col("B_SCORE") < pl.col("A_SCORE"))
            .then(pl.lit("A"))
            .otherwise(pl.lit("Error"))
            .alias("Winner")
        )
        .with_columns(
            pl.col("Date")
            .dt.strftime("%Y-%m-%d")
            .alias("GameDate")  # Format the date to YYYY-MM-DD
        )
        .with_columns(
            pl.col("Date")
            .cum_count()
            .over("GameDate")
            .cast(pl.Int32)
            .alias("GameNum")  # Sequential count per Date
        )
        .with_columns(
            pl.col("GameDate")
            .cast(pl.Date)
            .dt.strftime("%A")
            .str.slice(0, 3)
            .alias("Day")
        )
        .filter(pl.col("A_SCORE").is_not_nan())
    )

    return games
