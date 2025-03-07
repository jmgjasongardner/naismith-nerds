import polars as pl
from utils import util_code

class PlayerData:
    def __init__(self, games: pl.DataFrame):
        self.games = games
        self.player_stats = None

    def compute_stats(self) -> pl.DataFrame:
        """Extracts player stats from games."""
        team_cols = util_code.player_columns
        id_cols = ["GameDate", "GameNum", "A_SCORE", "B_SCORE", "Winner"]

        players = (
            self.games.select(id_cols + team_cols)
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
                (pl.col("team_score") - pl.col("opponent_score")).alias("point_diff")
            )
        )

        self.player_stats = (
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

        return self.player_stats
