from sklearn.model_selection import KFold
from sklearn.metrics import mean_squared_error
import numpy as np
import polars as pl
import scipy.sparse as sp
from sklearn.linear_model import Ridge
from typing import Tuple, List


def preprocess(
    df: pl.DataFrame, players: pl.DataFrame
) -> Tuple[np.ndarray, sp.coo_matrix, np.ndarray]:
    # Prepare your data (same preprocessing steps)
    game_to_idx = {game: idx for idx, game in enumerate(df["GameId"])}
    player_to_idx = {
        player: idx for idx, player in enumerate(players["player"].unique().sort())
    }

    row_indices = np.array([game_to_idx[game] for game in players["GameId"]])
    col_indices = np.array([player_to_idx[player] for player in players["player"]])
    data = players["effect"].to_numpy()
    sparse_matrix = sp.coo_matrix(
        (data, (row_indices, col_indices)),
        shape=(len(df["GameId"].unique()), len(players["player"].unique())),
    )
    y = (
        df.sort("GameId")
        .with_columns((pl.col("A_SCORE") - pl.col("B_SCORE")).alias("point_diff"))
        .select("point_diff")
        .to_numpy()
    )

    dense_matrix = sparse_matrix.toarray()

    return y, sparse_matrix, dense_matrix


# Define a function for hyperparameter tuning using cross-validation
def tune_lambda(
    df: pl.DataFrame, players: pl.DataFrame, lambda_values: List[float], n_splits=10
) -> Tuple[List[Tuple[float, float]], float]:

    # Store results for each lambda
    results = []

    y, sparse_matrix, dense_matrix = preprocess(df=df, players=players)

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


def train_final_model(
    df: pl.DataFrame, players: pl.DataFrame, best_lambda=1
) -> Tuple[pl.DataFrame, int]:
    player_to_idx = {
        player: idx for idx, player in enumerate(players["player"].unique().sort())
    }
    y, sparse_matrix = preprocess(df=df, players=players)[0:2]

    # Train final model on all data with the best lambda
    model = Ridge(alpha=best_lambda, fit_intercept=False)
    model.fit(sparse_matrix, y)

    # Get player ratings
    ratings = {player: model.coef_[i] for player, i in player_to_idx.items()}

    # Convert ratings to a DataFrame
    ratings_list = [(player, rating) for player, rating in ratings.items()]
    ratings_df = pl.DataFrame(
        ratings_list, schema=["player", "rating"], orient="row"
    ).sort("rating", descending=True)

    return ratings_df, best_lambda
