from sklearn.model_selection import KFold
from sklearn.metrics import mean_squared_error
import numpy as np
import polars as pl
import scipy.sparse as sp
from sklearn.linear_model import Ridge
from typing import Tuple, List
from collective_bball.utils import util_code

# Ridge's default for sparse input is sparse_cg, an iterative solver that stops
# at a tolerance about 0.001 short of the exact answer, and where it stops
# depends on row order. Polars does not promise a stable row order through the
# joins upstream, so two builds of the same games disagreed by up to 0.0013:
# enough to flip a near-tie MVP on a day long finished. Cholesky solves exactly
# and is order-independent. The system is ~100 columns, so it costs nothing.
EXACT_SOLVER = "cholesky"


class RAPMModel:
    def __init__(self):
        self.ratings = None
        self.best_lambda = None

    def run_rapm(self, games, tiers, args) -> Tuple[pl.DataFrame, int]:
        if args.default_lambda:
            self.best_lambda = 25 if args.use_tier_data else 100
        else:
            lambdas, self.best_lambda = self.tune_lambda(
                games=games, tiers=tiers, args=args
            )
        self.ratings, self.best_lambda = self.train_final_model(
            games=games, tiers=tiers, args=args, best_lambda=self.best_lambda
        )

        return self.ratings, self.best_lambda

    def run_as_of(self, games, tiers, args) -> pl.DataFrame:
        """A rating for every player on every game day, as it stood that night.

        Why this exists: the ordinary rating answers "how good is this player
        now", and scoring a 2025 game against it means the game keeps being
        reinterpreted as people improve or stop showing up.

        For day D this is exactly the leaderboard as it read at the end of D:
        fit only on games up to and including D, players tiered by how many
        games they had played by D, decay running one way from D. Nothing
        after D enters, so once a later day is logged, D never moves again.
        The day still being played keeps updating with every game logged.

        This replaced a two-sided kernel (|t_i - D|) that also weighted games
        after D. It priced a newcomer's first weeks with hindsight, but every
        new game day rewrote about 2.6 past MVPs and 2.2 past LVPs, a median
        of 55 game days back, and Jalen's Oct 2025 peak games were priced at
        2.02 instead of the 2.30 he was rated at the time. Past results should
        reflect what we believed then and stay put; a newcomer's thin early
        rating is the honest cost of that.

        Stays immutable only while lambda is fixed (default_lambda). A tuned
        lambda depends on every game and would move all of history.

        Each day needs its own design matrix because tiering changes as
        players cross the games threshold: ~5s for 171 game days.
        """
        alpha = self.best_lambda or (25 if args.use_tier_data else 100)
        days = games["game_date"].unique().sort().to_list()

        frames = []
        for day in days:
            y, players, sparse_matrix, _dense, decay_weights = self.preprocess_data(
                games=games.filter(pl.col("game_date") <= day), tiers=tiers, args=args
            )
            model = Ridge(alpha=alpha, fit_intercept=False, solver=EXACT_SOLVER)
            model.fit(sparse_matrix, y, sample_weight=decay_weights.ravel())

            # Player columns come first, in sorted order; the fatigue and
            # possession covariates follow and are not ratings.
            names = players["player"].unique().sort().to_list()
            frames.append(
                pl.DataFrame(
                    {
                        "game_date": [day] * len(names),
                        "player": names,
                        "rating": model.coef_[: len(names)].astype(float),
                    }
                )
            )

        return pl.concat(frames)

    def train_final_model(
        self, games: pl.DataFrame, tiers: pl.DataFrame, args=None, best_lambda=None
    ) -> Tuple[pl.DataFrame, int]:
        y, players, sparse_matrix, dense_matrix, decay_weights = self.preprocess_data(
            games=games, tiers=tiers, args=args
        )
        player_to_idx = {
            player: idx for idx, player in enumerate(players["player"].unique().sort())
        }

        # Train final model on all data with the best lambda
        model = Ridge(alpha=best_lambda, fit_intercept=False, solver=EXACT_SOLVER)
        model.fit(sparse_matrix, y, sample_weight=decay_weights.ravel())

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

        y, players, sparse_matrix, dense_matrix, decay_weights = self.preprocess_data(
            games=games, tiers=tiers, args=args
        )

        lambda_values = args.lambda_params
        # Iterate over different lambda values
        for lambda_val in lambda_values:
            fold_rmse = []  # To store RMSE for each fold
            for random_state_val in [0, 11, 21, 42]:
                # Initialize k-fold cross-validation
                kf = KFold(
                    n_splits=n_splits, shuffle=True, random_state=random_state_val
                )

                # Cross-validation loop
                for train_idx, val_idx in kf.split(sparse_matrix):
                    X_train, X_val = dense_matrix[train_idx], dense_matrix[val_idx]
                    y_train, y_val = y[train_idx], y[val_idx]

                    # Train Ridge model with current lambda
                    model = Ridge(alpha=lambda_val, fit_intercept=False)
                    model.fit(
                        X_train, y_train, sample_weight=decay_weights.ravel()[train_idx]
                    )

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

    def preprocess_data(
        self, games: pl.DataFrame, tiers=None, args=None
    ) -> Tuple[np.ndarray, pl.DataFrame, sp.coo_matrix, np.ndarray, np.ndarray]:

        if args.use_tier_data:
            games = self.sub_tier_data(
                games=games,
                tiers=tiers,
                min_games=args.min_games_to_not_tier,
            )

        id_cols = ["game_date", "game_num", "a_score", "b_score", "winner"]
        team_cols = util_code.player_columns

        players = (
            games.select(id_cols + team_cols)
            .unpivot(index=id_cols)
            .with_columns(
                pl.col("variable").str.extract(r"([AB])", 1).alias("team"),
                pl.col("value").alias("player"),
            )
            .drop(["value", "variable"])
            .filter(pl.col("player").is_not_null())
            .with_columns(
                pl.when(pl.col("team") == "A")
                .then(pl.col("a_score"))
                .otherwise(pl.col("b_score"))
                .alias("team_score"),
                pl.when(pl.col("team") == "A")
                .then(pl.col("b_score"))
                .otherwise(pl.col("a_score"))
                .alias("opponent_score"),
                (pl.col("team") == pl.col("winner")).cast(pl.Int8).alias("game_won"),
            )
            .with_columns(
                (pl.col("team_score") - pl.col("opponent_score")).alias("score_diff"),
                pl.when(pl.col("team") == "A").then(1).otherwise(-1).alias("effect"),
            )
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

        # --- add clock and first_poss columns as additional features ---
        extra_features = (
            games.sort(["game_date", "game_num"])
            .select(
                [
                    "first_poss",
                    "total_games_played_diff",
                    "consecutive_games_waited_diff",
                    "consecutive_games_played_diff",
                    "total_games_played_diff_sq",
                    "consecutive_games_waited_diff_sq",
                    "consecutive_games_played_diff_sq",
                ]
            )
            .to_numpy()
        )
        extra_sparse = sp.csr_matrix(extra_features)  # (n_games, 2)
        # horizontally stack: [player effects | clock | first_poss]
        sparse_matrix = sp.hstack([sparse_matrix.tocsr(), extra_sparse]).tocsr()
        # ---

        y = (
            games.sort(["game_date", "game_num"], descending=[False, False])
            .with_columns(-(pl.col("score_diff")).alias("score_diff"))
            .select("score_diff")
            .to_numpy()
        )

        dense_matrix = sparse_matrix.toarray()

        # Calculate time-decay weights.
        #
        # This MUST be sorted the same way as y, extra_features and the row
        # indices above. It was not, and `games` arrives in reverse
        # chronological order, so weight[i] was landing on the game at sorted
        # position i — exactly reversing the decay. The oldest game was
        # carrying the weight meant for the newest (0.997 vs 0.234), which
        # made the model lean hardest on ancient history and left players who
        # were good long ago but poor lately looking better than their results.
        # Anchored to the most recent game in this set, not to the wall clock.
        # date.today() made the ratings drift every day even when no basketball
        # had been played, so two builds of identical data disagreed and the
        # history could never be reproduced. It is also what makes run_as_of
        # work: filter to games up to D and the decay runs one way from D.
        anchor = games["game_date"].max()
        days_since_today = (
            games.sort(["game_date", "game_num"], descending=[False, False])
            .with_columns(pl.col("game_date").str.strptime(pl.Date, "%Y-%m-%d"))
            .with_columns(
                (
                    pl.lit(anchor).str.strptime(pl.Date, "%Y-%m-%d")
                    - pl.col("game_date")
                )
                .dt.total_days()
                .alias("days_since_today")
            )
            .select("days_since_today")
            .to_numpy()
        )
        lam = np.log(2) / args.decay_half_life
        decay_weights = np.exp(-lam * days_since_today)

        return y, players, sparse_matrix, dense_matrix, decay_weights

    @staticmethod
    def sub_tier_data(
        games: pl.DataFrame, tiers: pl.DataFrame, min_games: int
    ) -> pl.DataFrame:
        player_columns = util_code.player_columns
        games_played = (
            games.select(player_columns)
            .unpivot(on=player_columns, value_name="player")
            .filter(pl.col("player").is_not_null())
            .group_by("player")
            .agg(pl.len().alias("games_played"))
            .sort(pl.col("games_played"))  # Count how many times each player appears
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
