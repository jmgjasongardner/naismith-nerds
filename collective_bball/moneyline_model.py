from sklearn.linear_model import LogisticRegression
import polars as pl

class BettingGames:
    def __init__(self):
        self.model = LogisticRegression()

    @staticmethod
    def calculate_spreads(games: pl.DataFrame, ratings: pl.DataFrame) -> pl.DataFrame:
        """Calculate the spreads of games just using algebra"""
        games_long = (
            games.unpivot(
                index=["GameDate", "GameNum"],
                on=["A1", "A2", "A3", "A4", "A5", "B1", "B2", "B3", "B4", "B5"],
                variable_name="team_role",
                value_name="player",
            )
            .join(ratings, on="player", how="left")
            .with_columns(
                (pl.col("team_role").str.starts_with("A") * pl.col("rating")).alias(
                    "A_rating"
                ),
                (pl.col("team_role").str.starts_with("B") * pl.col("rating")).alias(
                    "B_rating"
                ),
            )
            .group_by(["GameDate", "GameNum"])
            .agg(
                pl.sum("A_rating").round(3).alias("A_Quality"),
                pl.sum("B_rating").round(3).alias("B_Quality"),
            )
            .with_columns(
                (pl.col("B_Quality") - pl.col("A_Quality")).round(3).alias("Spread")
            )
        )

        games_with_spreads = (
            games.join(games_long, on=["GameDate", "GameNum"], how="inner")
            .with_columns((pl.col("B_SCORE") - pl.col("A_SCORE")).alias("Score_Difference"))
            .with_columns(
                (pl.col("Score_Difference") - pl.col("Spread"))
                .round(3)
                .alias("Difference_From_Spread")
            )
            .with_columns(
                (pl.col("Spread").abs()).alias("Absolute_Spread"),
                (pl.col("Score_Difference").abs()).alias("Absolute_Score_Difference"),
                (pl.col("Difference_From_Spread").abs()).alias(
                    "Absolute_Spread_Difference"
                ),
            )
        ).sort(
            "GameDate", "GameNum", descending=[True, True]
        )
        return games_with_spreads

    def calculate_moneylines_log_reg(self, games_with_spreads: pl.DataFrame) -> pl.DataFrame:
        """Trains logistic regression and computes win probabilities."""

        x = games_with_spreads.select(["A_Quality", "B_Quality"]).to_numpy()
        y = (games_with_spreads["Winner"] == "A").to_numpy()
        self.model.fit(x, y)
        games_with_spreads_moneylines = games_with_spreads.with_columns(
            pl.Series(name="A_Win_Prob", values=(self.model.predict_proba(x)[:, 1]))
        )
        games_with_spreads_moneylines = games_with_spreads_moneylines.with_columns(
            pl.when(pl.col("A_Win_Prob") >= 0.5)
            .then(
                (-100 * pl.col("A_Win_Prob") / (1 - pl.col("A_Win_Prob")))
                .round(0)
                .cast(pl.Int64)
            )
            .otherwise(
                (100 * (1 - pl.col("A_Win_Prob")) / pl.col("A_Win_Prob"))
                .round(0)
                .cast(pl.Int64)
            )
            .alias("Moneyline")
        ).with_columns(pl.col("A_Win_Prob").round(3).alias("A_Win_Prob"))
        return games_with_spreads_moneylines