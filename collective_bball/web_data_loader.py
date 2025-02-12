from collective_bball.eda import stats  # Importing z directly from eda.py
from collective_bball.rapm_model_main import compute_ratings

def format_stats(stats_df):
    """Rename columns and round numeric values before passing to Jinja."""
    column_map = {
        "player": "Player",
        "games_played": "Games Played",
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

def get_stats():
    """Return formatted stats with renamed columns and rounded values."""
    return format_stats(stats)  # Apply formatting before sending


def get_ratings():
    """Fetch ratings as a pandas dataframe."""
    ratings_df = compute_ratings()[0].to_pandas()
    ratings_df["rating"] = ratings_df["rating"].round(5)
    column_map = {
        "player": "Player",
        "rating": "Rating",
    }
    ratings_df = ratings_df.rename(columns=column_map)  # Rename columns
    return ratings_df.to_dict(orient="records")
