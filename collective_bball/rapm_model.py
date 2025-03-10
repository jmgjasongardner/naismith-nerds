from sklearn.model_selection import KFold
from sklearn.metrics import mean_squared_error
import numpy as np
import polars as pl
import scipy.sparse as sp
from sklearn.linear_model import Ridge
from typing import Tuple, List
from collective_bball.utils import util_code


class RAPMModel:
    def __init__(self):
        self.ratings = None
        self.best_lambda = None

    def run_rapm(self, games, tiers, args) -> Tuple[pl.DataFrame, int]:
        if args.default_lambda:
            self.best_lambda = 25 if args.use_tier_data else 100
        else:
            lambdas, self.best_lambda = self.tune_lambda(games=games, tiers=tiers, args=args)
        self.ratings, self.best_lambda = self.train_final_model(games=games, tiers=tiers, args=args, best_lambda=self.best_lambda)

        return self.ratings, self.best_lambda

    def train_final_model(
            self, games: pl.DataFrame, tiers: pl.DataFrame, args=None, best_lambda=None
    ) -> Tuple[pl.DataFrame, int]:
        y, players, sparse_matrix, dense_matrix = self.preprocess_data(games=games, tiers=tiers, args=args)
        player_to_idx = {
            player: idx for idx, player in enumerate(players["player"].unique().sort())
        }

        # Train final model on all data with the best lambda
        model = Ridge(alpha=best_lambda, fit_intercept=False)
        model.fit(sparse_matrix, y)

        # Get player ratings
        ratings = {player: model.coef_[i] for player, i in player_to_idx.items()}

        # Convert ratings to a DataFrame
        ratings_list = [(player, rating) for player, rating in ratings.items()]
        self.ratings = pl.DataFrame(
            ratings_list, schema=["player", "rating"], orient="row"
        ).sort("rating", descending=True)

        return self.ratings, self.best_lambda

    def tune_lambda(
            self, games: pl.DataFrame, tiers: pl.DataFrame, args=None, n_splits=10
    ) -> Tuple[List, float]:

        # Store results for each lambda
        results = []

        y, players, sparse_matrix, dense_matrix = self.preprocess_data(games=games, tiers=tiers, args=args)

        lambda_values = args.lambda_params
        # Iterate over different lambda values
        for lambda_val in lambda_values:
            fold_rmse = []  # To store RMSE for each fold
            for random_state_val in [0, 11, 21, 42]:
                # Initialize k-fold cross-validation
                kf = KFold(n_splits=n_splits, shuffle=True, random_state=random_state_val)

                # Cross-validation loop
                for train_idx, val_idx in kf.split(sparse_matrix):
                    X_train, X_val = dense_matrix[train_idx], dense_matrix[val_idx]
                    y_train, y_val = y[train_idx], y[val_idx]

                    # Train Ridge model with current lambda
                    model = Ridge(alpha=lambda_val, fit_intercept=False)
                    model.fit(X_train, y_train)

                    # Predict on validation set
                    y_pred = model.predict(X_val)

                    # Calculate RMSE for the fold
                    fold_rmse.append(np.sqrt(mean_squared_error(y_val, y_pred)))

            # Calculate the average RMSE for this lambda
            avg_rmse = np.mean(fold_rmse)
            results.append((lambda_val, avg_rmse))

        # Find the lambda with the lowest average RMSE
        best_lambda = min(results, key=lambda x: x[1])
        print(f"Best lambda: {best_lambda[0]} with RMSE: {best_lambda[1]}")

        return results, best_lambda[0]

    def preprocess_data(self, games: pl.DataFrame, tiers=None, args=None) -> Tuple[np.ndarray, pl.DataFrame, sp.coo_matrix, np.ndarray]:
        if args.use_tier_data:
            games = self.sub_tier_data(
                games=games,
                tiers=tiers,
                min_games=args.min_games_to_not_tier,
            )

        id_cols = ["game_date", "game_num", "a_score", "b_score", "winner"]
        team_cols = util_code.player_columns

        players = games.select(id_cols + team_cols).unpivot(index=id_cols).with_columns(
            pl.col("variable").str.extract(r"([AB])", 1).alias("team"),
            pl.col("value").alias("player"),
        ).drop(["value", "variable"]).with_columns(
            pl.when(pl.col("team") == "A")
            .then(pl.col("a_score"))
            .otherwise(pl.col("b_score"))
            .alias("team_score"),
            pl.when(pl.col("team") == "A")
            .then(pl.col("b_score"))
            .otherwise(pl.col("a_score"))
            .alias("opponent_score"),
            (pl.col("team") == pl.col("winner")).cast(pl.Int8).alias("game_won"),
        ).with_columns(
            (pl.col("team_score") - pl.col("opponent_score")).alias("score_diff"),
            pl.when(pl.col("team") == "A").then(1).otherwise(-1).alias("effect"),
        )


        game_to_idx = {
            (date, num): idx
            for idx, (date, num) in enumerate(
                games.select(["game_date", "game_num"])
                .unique()
                .sort(["game_date", "game_num"])
                .iter_rows()
            )
        }

        player_to_idx = {
            player: idx for idx, player in enumerate(players["player"].unique().sort())
        }

        row_indices = np.array(
            [
                game_to_idx[(date, num)]
                for date, num in zip(players["game_date"], players["game_num"])
            ]
        )
        col_indices = np.array([player_to_idx[player] for player in players["player"]])
        data = players["effect"].to_numpy()

        sparse_matrix = sp.coo_matrix(
            (data, (row_indices, col_indices)),
            shape=(
                len(games.select(["game_date", "game_num"]).unique()),
                len(players["player"].unique()),
            ),
        )

        y = (
            games.sort(["game_date", "game_num"], descending=[False, False])
            .with_columns((pl.col("a_score") - pl.col("b_score")).alias("score_diff"))
            .select("score_diff")
            .to_numpy()
        )

        dense_matrix = sparse_matrix.toarray()

        return y, players, sparse_matrix, dense_matrix

    @staticmethod
    def sub_tier_data(
            games: pl.DataFrame, tiers: pl.DataFrame, min_games: int
    ) -> pl.DataFrame:
        player_columns = util_code.player_columns
        games_played = games.select(player_columns).unpivot(
                on=player_columns, value_name="player").filter(
                pl.col("player").is_not_null()).group_by(
                "player").agg(
                pl.len().alias("games_played")).sort(  # Count how many times each player appears
                pl.col("games_played")
        )
        tiers = tiers.join(games_played, on="player")
        tiers = tiers.filter(pl.col("games_played") < min_games)
        tiers_dict = dict(zip(tiers["player"].to_list(), tiers["tier"].to_list()))
        # Columns to replace
        player_columns = util_code.player_columns

        # Replace values in the specified columns
        games_with_tier_players = games.with_columns(
            [
                pl.col(col).replace(tiers_dict, default=pl.col(col)).alias(col)
                for col in player_columns
            ]
        )

        return games_with_tier_players