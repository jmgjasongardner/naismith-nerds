import util_funs
import model_funs_rapm
import polars as pl
from datetime import date
import argparse

pl.Config.set_tbl_rows(n=50)
pl.Config.set_tbl_cols(n=8)

parser = argparse.ArgumentParser()
parser.add_argument(
    "--use_tier_data",
    help="Replace data with tiered players for small sample",
    action="store_true",
)
parser.add_argument(
    "--include_common_player_tiers",
    help="Replace data with tiered players for common players with small samples",
    action="store_true",
)
parser.add_argument(
    "--run_in_sample",
    help="Run the model without hyperparameter tuning and cross-validating",
    action="store_true",
)
parser.add_argument(
    "--alpha_params",
    help="Replace data with tiered players for common players with small samples",
    default=[0.1, 0.5, 1, 10, 100],
)
args = parser.parse_args()


# Pull in data
df, tiers = util_funs.pull_in_data()
df = util_funs.clean_data(df=df)
if (
    args.use_tier_data
):  # TODO: Improve this logic for setting case of min number of games played to not be replaced
    # TODO: And perhaps more urgent, make sure if we have Tier guys on opposite sides that's not an issue
    df = util_funs.sub_tier_data(
        df=df, tiers=tiers, include_commons=args.include_common_player_tiers
    )
players = util_funs.player_data(df=df)

# Model training
if args.run_in_sample:  # With default value scikit-learn 1 for alpha value
    print("in-sample")
    ratings_df = model_funs_rapm.train_final_model(df=df, players=players)
else:
    print("out-of-sample")
    alphas, best_alpha = model_funs_rapm.tune_alpha(
        df=df, players=players, alpha_values=args.alpha_params
    )
    ratings_df = model_funs_rapm.train_final_model(
        df=df, players=players, best_alpha=best_alpha
    )

ratings_pd = ratings_df.to_pandas()

used_tiers = (
    "-all_tiers"
    if args.use_tier_data and args.include_common_player_tiers
    else "-uncommon_tiers" if args.use_tier_data else ""
)
sampling = "-in_sample" if args.run_in_sample else ""
ratings_pd.to_csv(
    f"ratings/{date.today()}-ratings{used_tiers}{sampling}.csv", index=False
)

print(ratings_df)
