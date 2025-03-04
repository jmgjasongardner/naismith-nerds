import polars as pl
from sklearn.linear_model import LogisticRegression


# Prepare Data
def calculate_team_A_win_prob(games_with_spreads: pl.DataFrame) -> pl.DataFrame:

    # Convert to numpy arrays for sklearn
    X = games_with_spreads.select(["A_Quality", "B_Quality"]).to_numpy()
    y = (games_with_spreads["Winner"] == "A").to_numpy()

    # Train Logistic Regression Model on entire dataset
    model = LogisticRegression()
    model.fit(X, y)
    games_with_spreads = games_with_spreads.with_columns(
        pl.Series(name="A_Win_Prob", values=(model.predict_proba(X)[:, 1]))
    )
    games_with_spreads = games_with_spreads.with_columns(
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

    return games_with_spreads
