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
                index=["game_date", "game_num"],
                on=["A1", "A2", "A3", "A4", "A5", "B1", "B2", "B3", "B4", "B5"],
                variable_name="team_role",
                value_name="player",
            )
            .join(ratings, on="player", how="left")
            .with_columns(
                (pl.col("team_role").str.starts_with("A") * pl.col("rating")).alias(
                    "a_rating"
                ),
                (pl.col("team_role").str.starts_with("B") * pl.col("rating")).alias(
                    "b_rating"
                ),
            )
            .group_by(["game_date", "game_num"])
            .agg(
                pl.sum("a_rating").round(3).alias("a_quality"),
                pl.sum("b_rating").round(3).alias("b_quality"),
            )
            .with_columns(
                (pl.col("b_quality") - pl.col("a_quality")).round(3).alias("spread")
            )
        )

        games_with_spreads = (
            games.join(games_long, on=["game_date", "game_num"], how="inner")
            .with_columns((pl.col("b_score") - pl.col("a_score")).alias("score_diff"))
            .with_columns(
                (pl.col("score_diff") - pl.col("spread"))
                .round(3)
                .alias("diff_from_spread")
            )
            .with_columns(
                (pl.col("spread").abs()).alias("absolute_spread"),
                (pl.col("score_diff").abs()).alias("absolute_score_diff"),
                (pl.col("diff_from_spread").abs()).alias("absolute_spread_diff"),
            )
        ).sort("game_date", "game_num", descending=[True, True])
        return games_with_spreads

    def calculate_moneylines_log_reg(
        self, games_with_spreads: pl.DataFrame
    ) -> pl.DataFrame:
        """Trains logistic regression and computes win probabilities."""

        x = games_with_spreads.select(["a_quality", "b_quality"]).to_numpy()
        y = (games_with_spreads["winner"] == "A").to_numpy()
        self.model.fit(x, y)
        games_with_spreads_moneylines = games_with_spreads.with_columns(
            pl.Series(name="a_win_prob", values=(self.model.predict_proba(x)[:, 1]))
        )
        games_with_spreads_moneylines = games_with_spreads_moneylines.with_columns(
            pl.when(pl.col("a_win_prob") >= 0.5)
            .then(
                (-100 * pl.col("a_win_prob") / (1 - pl.col("a_win_prob")))
                .round(0)
                .cast(pl.Int64)
            )
            .otherwise(
                (100 * (1 - pl.col("a_win_prob")) / pl.col("a_win_prob"))
                .round(0)
                .cast(pl.Int64)
            )
            .alias("moneyline")
        ).with_columns(pl.col("a_win_prob").round(3).alias("a_win_prob"))
        return games_with_spreads_moneylines
