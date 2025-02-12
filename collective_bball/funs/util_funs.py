import polars as pl
import pandas as pd
from datetime import date


def pull_in_data() -> tuple[pl.DataFrame, pl.DataFrame]:
    data = "collective_bball/GameResults.xlsm"
    df = pl.from_pandas(
        pd.read_excel(data, sheet_name="GameResults", engine="openpyxl")
    )
    tiers = pl.from_pandas(
        pd.read_excel(data, sheet_name="PlayerTiers", engine="openpyxl")
    )

    return df, tiers


def clean_data(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.with_columns(
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
            (pl.col("GameDate") + "-" + (pl.col("GameNum")).cast(pl.Utf8)).alias(
                "GameId"
            )
        )
        .drop("GameDate")
        .filter(pl.col("A_SCORE").is_not_nan())
    )


def played_games(df: pl.DataFrame) -> pl.DataFrame:

    player_columns = [f"A{i}" for i in range(1, 6)] + [f"B{i}" for i in range(1, 6)]
    return (
        df.select(player_columns)  # Select all player columns
        .unpivot(on=player_columns, value_name="player")  # Use unpivot instead of melt
        .filter(pl.col("player").is_not_null())  # Remove any null player values
        .group_by("player")  # Group by player
        .agg(pl.len().alias("games_played"))  # Count how many times each player appears
        .sort(pl.col("games_played"))
    )


def player_data(df: pl.DataFrame) -> pl.DataFrame:
    # Reshape the dataframe with unpivot
    team_cols = [f"A{i}" for i in range(1, 6)] + [f"B{i}" for i in range(1, 6)]
    id_cols = ["GameId", "A_SCORE", "B_SCORE", "Winner"]

    return (
        df.select(id_cols + team_cols)
        .unpivot(index=id_cols)
        .with_columns(
            pl.col("variable").str.extract(r"([AB])", 1).alias("team"),
            pl.col("value").alias("player"),
        )
        .drop(["value", "variable"])
        .with_columns(
            pl.when(pl.col("team") == "A")
            .then(pl.col("A_SCORE"))
            .otherwise(pl.col("B_SCORE"))
            .alias("team_score"),
            pl.when(pl.col("team") == "A")
            .then(pl.col("B_SCORE"))
            .otherwise(pl.col("A_SCORE"))
            .alias("opponent_score"),
            (pl.col("team") == pl.col("Winner")).cast(pl.Int8).alias("GameWon"),
        )
        .with_columns(
            (pl.col("team_score") - pl.col("opponent_score")).alias("point_diff"),
            pl.when(pl.col("team") == "A").then(1).otherwise(-1).alias("effect"),
        )
    )


def sub_tier_data(
    df: pl.DataFrame, tiers: pl.DataFrame, min_games: int
) -> pl.DataFrame:
    tiers = tiers.filter(pl.col("games_played") < min_games)
    tiers_dict = dict(zip(tiers["player"].to_list(), tiers["tier"].to_list()))
    # Columns to replace
    player_columns = [f"A{i}" for i in range(1, 6)] + [f"B{i}" for i in range(1, 6)]

    # Replace values in the specified columns
    df = df.with_columns(
        [
            pl.col(col).replace(tiers_dict, default=pl.col(col)).alias(col)
            for col in player_columns
        ]
    )

    return df


def process_output_file(args, best_alpha: int) -> str:
    used_tiers = "-all_tiers" if args.use_tier_data else ""
    min_games = (
        f"-min-tier-games={args.min_games_to_not_tier}" if args.use_tier_data else ""
    )

    return f"collective_bball/ratings/{date.today()}-ratings-alpha={best_alpha}{used_tiers}{min_games}.csv"
