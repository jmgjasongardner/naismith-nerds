from collective_bball.eda import z  # Importing z directly from eda.py
from collective_bball.rapm_model_main import compute_ratings

def get_stats():
    """Return the dataframe z as a dictionary for JSON serving."""
    return z  # Flask can easily return JSON from a list of dicts

def get_ratings():
    """Fetch ratings as a pandas dataframe."""
    ratings_df = compute_ratings()[0]
    return ratings_df.to_pandas()
