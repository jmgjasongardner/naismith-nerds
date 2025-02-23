from collective_bball.funs import util_funs, model_funs_rapm
import polars as pl
from typing import Tuple
import argparse

pl.Config.set_tbl_rows(n=100)
pl.Config.set_tbl_cols(n=8)


def parse_args(args=None):
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--use_tier_data", action="store_false")
    parser.add_argument("--min_games_to_not_tier", default=20, type=int)
    parser.add_argument("--default_lambda", action="store_true")
    parser.add_argument(
        "--lambda_params",
        type=float,
        nargs="*",
        default=[0.1, 0.5, 1, 5, 10, 25, 50, 100],
    )
    parser.add_argument("--save_csv", action="store_true")
    args, unknown = parser.parse_known_args()

    return args, unknown  # If args is None, it uses sys.argv


def run_rapm_model(args=None) -> Tuple[pl.DataFrame, int, pl.DataFrame, pl.DataFrame]:
    """Compute player ratings and return the dataframe."""
    args, unknown = parse_args()  # Provide empty args for function calls

    # Pull in data
    df, tiers, bios = util_funs.pull_in_data()
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

    if args.default_lambda:
        best_lambda = 10 if args.use_tier_data else 100
        ratings_df, best_lambda = model_funs_rapm.train_final_model(
            df=df, players=players, best_lambda=best_lambda
        )
    else:
        lambdas, best_lambda = model_funs_rapm.tune_lambda(
            df=df, players=players, lambda_values=args.lambda_params
        )
        ratings_df, best_lambda = model_funs_rapm.train_final_model(
            df=df, players=players, best_lambda=best_lambda
        )

    return ratings_df, best_lambda, tiers, bios


# ✅ Keeps script functionality when run directly
if __name__ == "__main__":

    args, unknown = parse_args()
    ratings_df, best_lambda, tiers = run_rapm_model(args)
    ratings_pd = ratings_df.to_pandas()

    if args.save_csv:
        ratings_pd.to_csv(
            util_funs.process_output_file(args=args, best_lambda=best_lambda), index=False
        )

    print(ratings_pd)
