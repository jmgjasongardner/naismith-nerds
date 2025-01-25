import util_funs
import scipy.sparse as sp
import polars as pl
import numpy as np
from sklearn.linear_model import Ridge
from datetime import date
import argparse
from util_funs import sub_tier_data

pl.Config.set_tbl_rows(n=50)
pl.Config.set_tbl_cols(n=8)

parser = argparse.ArgumentParser()
parser.add_argument("--use_tier_data", help="Replace data with tiered players for small sample",
                    action="store_true")
parser.add_argument("--include_common_player_tiers", help="Replace data with tiered players for common players with small samples",
                    action="store_true")
args = parser.parse_args()


# Example of how you might pull in and clean your data
df, tiers = util_funs.pull_in_data()
df = util_funs.clean_data(df=df)
if args.use_tier_data:
    df = sub_tier_data(df=df, tiers=tiers, include_commons=args.include_common_player_tiers)
players = util_funs.player_data(df=df)

# Number of unique players and games
n_players = len(players.select("player").unique())
n_games = len(players.select("GameId").unique())

# Step 4: Prepare data for the sparse matrix
# Create team effects (+1 for team A, -1 for team B)
players = players.with_columns(
    pl.when(pl.col("team") == "A").then(1).otherwise(-1).alias("effect")
)

# Step 5: Create mappings from `GameId` and `player` to integer indices
game_to_idx = {game: idx for idx, game in enumerate(df["GameId"])}
player_to_idx = {player: idx for idx, player in enumerate(players["player"].unique().sort())}

# Step 6: Map `GameId` and `player` to indices
row_indices = np.array([game_to_idx[game] for game in players["GameId"]])
col_indices = np.array([player_to_idx[player] for player in players["player"]])

# Step 7: Data for the sparse matrix (team effects)
data = players["effect"].to_numpy()

# Step 8: Build the sparse matrix using the row, col, and data
sparse_matrix = sp.coo_matrix((data, (row_indices, col_indices)), shape=(n_games, n_players))
dense_matrix = sparse_matrix.toarray()
y = (
    df.sort("GameId")
    .with_columns((pl.col('A_SCORE') - pl.col('B_SCORE')).alias("point_diff"))
    .select("point_diff")
    .to_numpy()
)


# Now, sparse_matrix is a scipy sparse matrix that you can use for modeling

ridge = Ridge(alpha=1.0, fit_intercept=False)
ridge.fit(sparse_matrix, y)

# Get player ratings
ratings = {player: ridge.coef_[i] for player, i in player_to_idx.items()}

# Convert the ratings dictionary to a list of tuples
ratings_list = [(player, rating) for player, rating in ratings.items()]

# Create a Polars DataFrame
ratings_df = pl.DataFrame(ratings_list, schema=["player", "rating"], orient='row').sort("rating", descending=True)
ratings_pd = ratings_df.to_pandas()

used_tiers = '-all_tiers' if args.use_tier_data and args.include_common_player_tiers else '-uncommon_tiers' if args.use_tier_data else ''
ratings_pd.to_csv(f'ratings/{date.today()}-ratings{used_tiers}.csv', index=False)

print(ratings_df)
