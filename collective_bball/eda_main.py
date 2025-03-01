import polars as pl
import pandas as pd
from datetime import date
import argparse

pl.Config.set_tbl_rows(n=50)
pl.Config.set_tbl_cols(n=8)

def generate_stats(run_locally=False):
    data = "collective_bball/GameResults.xlsm"
    df = pl.from_pandas(pd.read_excel(data, sheet_name="GameResults", engine="openpyxl"))
    tiers = pl.from_pandas(pd.read_excel(data, sheet_name="PlayerTiers", engine="openpyxl"))

    games = (
        df.with_columns(
            pl.col("A_SCORE").cast(pl.Int64),
            pl.col("B_SCORE").cast(pl.Int64)
        ).with_columns(
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
        ).with_columns(
            pl.col("GameDate").cast(pl.Date).dt.strftime("%A").str.slice(0, 3).alias("Day")
        )
        .filter(pl.col("A_SCORE").is_not_nan())
    )

    team_cols = [f"A{i}" for i in range(1, 6)] + [f"B{i}" for i in range(1, 6)]
    id_cols = ["GameDate", "GameNum", "A_SCORE", "B_SCORE", "Winner"]

    players = (
        games.select(id_cols + team_cols)
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
        .with_columns((pl.col("team_score") - pl.col("opponent_score")).alias("point_diff"))
    )

    player_stats = (
        players.group_by("player")
        .agg(
            [
                pl.count("player").alias("games_played"),
                pl.n_unique("GameDate").alias("days_played"),
                pl.sum("GameWon").alias("wins"),
                (pl.count("player") - pl.sum("GameWon")).alias("losses"),
                (pl.sum("GameWon") / pl.count("player")).round(3).alias("win_pct"),
                pl.mean("point_diff").round(3).alias("avg_point_diff"),
            ]
        )
        .sort("wins", "losses", "avg_point_diff", descending=[True, False, True])
    )

    if run_locally:
        player_stats.to_pandas().to_csv(f"collective_bball/raw-stats/PlayerStats-{date.today()}.csv", index=False)
        print(player_stats.to_pandas())

    return player_stats, games

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--run_locally", action="store_true")
    args, unknown = parser.parse_known_args()

    stats, games = generate_stats(run_locally=args.run_locally)
