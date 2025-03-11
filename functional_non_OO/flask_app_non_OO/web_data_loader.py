import polars as pl
from collective_bball.rapm_model_main import run_rapm_model


def format_stats_for_site(stats_df):
    """Rename columns and round numeric values before passing to Jinja."""
    column_map = {
        "player": "Player",
        "games_played": "Games Played",
        "days_played": "Days Played",
        "wins": "Wins",
        "losses": "Losses",
        "win_pct": "Win Pct",
        "avg_point_diff": "Point Differential",
    }
    stats_df = stats_df.rename(columns=column_map)  # Rename columns

    # Round only numeric columns
    for col in stats_df.select_dtypes(include="number").columns:
        stats_df[col] = stats_df[col].round(3)

    return stats_df.to_dict(orient="records")  # Convert to list of dicts for Jinja


def get_model_outputs():
    """Fetch ratings as a pandas dataframe."""
    ratings_df, best_lambda, tiers, bios = run_rapm_model()
    ratings_df = ratings_df.with_columns(pl.col("rating").round(5)).rename(
        {"player": "Player", "rating": "Rating"}
    )
    return ratings_df, best_lambda, tiers, bios


def combine_tier_ratings(stats, ratings, tiers) -> pl.DataFrame:
    combined_ratings = (
        stats.join(ratings, left_on="player", right_on="Player", how="left")
        .join(tiers, left_on="player", right_on="player", how="left")
        .join(ratings, left_on="tier", right_on="Player", how="left")
        .with_columns(pl.col("Rating").fill_null(pl.col("Rating_right")))
        .rename({"player": "Player"})
        .select(["Player", "Rating"])
        .sort("Rating", "Player", descending=[True, False])
    )

    return combined_ratings


def calculate_game_spreads(games, ratings) -> pl.DataFrame:

    games_long = (
        games.unpivot(
            index=["GameDate", "GameNum"],
            on=["A1", "A2", "A3", "A4", "A5", "B1", "B2", "B3", "B4", "B5"],
            variable_name="team_role",
            value_name="Player",
        )
        .join(ratings, on="Player", how="left")
        .with_columns(
            (pl.col("team_role").str.starts_with("A") * pl.col("Rating")).alias(
                "A_Rating"
            ),
            (pl.col("team_role").str.starts_with("B") * pl.col("Rating")).alias(
                "B_Rating"
            ),
        )
        .group_by(["GameDate", "GameNum"])
        .agg(
            pl.sum("A_Rating").round(3).alias("A_Quality"),
            pl.sum("B_Rating").round(3).alias("B_Quality"),
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
    )

    return games_with_spreads
