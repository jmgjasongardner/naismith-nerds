from collective_bball.funs import util_funs, model_funs_rapm
import polars as pl
import argparse
from typing import Tuple

pl.Config.set_tbl_rows(n=100)
pl.Config.set_tbl_cols(n=8)


def parse_args(args=None):
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--use_tier_data", action="store_false")
    parser.add_argument("--min_games_to_not_tier", default=20, type=int)
    parser.add_argument("--default_alpha", action="store_true")
    parser.add_argument(
        "--alpha_params",
        type=float,
        nargs="*",
        default=[0.1, 0.5, 1, 5, 10, 25, 50, 100],
    )
    parser.add_argument("--save_csv", action="store_true")

    return parser.parse_args(args)  # If args is None, it uses sys.argv


def compute_ratings(args=None) -> Tuple[pl.DataFrame, int]:
    """Compute player ratings and return the dataframe."""
    if args is None:
        args = parse_args([])  # Provide empty args for function calls

    # Pull in data
    df, tiers = util_funs.pull_in_data()
    df = util_funs.clean_data(df=df)
    games_played = util_funs.played_games(df=df)
    tiers = tiers.join(games_played, on="player")

    if args.use_tier_data:
        df = util_funs.sub_tier_data(
            df=df,
            tiers=tiers,
            min_games=args.min_games_to_not_tier,
        )

    players = util_funs.player_data(df=df)

    if args.default_alpha:
        best_alpha = 10 if args.use_tier_data else 100
        ratings_df, best_alpha = model_funs_rapm.train_final_model(
            df=df, players=players, best_alpha=best_alpha
        )
    else:
        alphas, best_alpha = model_funs_rapm.tune_alpha(
            df=df, players=players, alpha_values=args.alpha_params
        )
        ratings_df, best_alpha = model_funs_rapm.train_final_model(
            df=df, players=players, best_alpha=best_alpha
        )

    return ratings_df, best_alpha


# ✅ Keeps script functionality when run directly
if __name__ == "__main__":
    args = parse_args()
    ratings_df, best_alpha = compute_ratings(args)
    ratings_pd = ratings_df.to_pandas()

    if args.save_csv:
        ratings_pd.to_csv(
            util_funs.process_output_file(args=args, best_alpha=best_alpha), index=False
        )

    print(ratings_pd)
