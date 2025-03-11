from collective_bball.basketball_data import BasketballData
from collective_bball.rapm_model import RAPMModel
from collective_bball.moneyline_model import BettingGames
import argparse
import polars as pl

pl.Config.set_tbl_rows(n=100)
pl.Config.set_tbl_cols(n=8)


def create_data(args=None):
    """Creates and processes the BasketballData object."""
    if args is None:
        args = argparse.Namespace(
            use_tier_data=True,
            min_games_to_not_tier=20,
            default_lambda=True,
            lambda_params=[0.1, 0.5, 1, 5, 10, 25, 50, 100],
            save_csv=False,
        )

    data = BasketballData(data_source="./collective_bball/GameResults.xlsm", args=args)
    data.clean_data()
    data.compute_player_stats()

    rapm_model = RAPMModel()
    data.compute_rapm(rapm_model)
    data.merge_player_data()

    betting_games = BettingGames()
    data.compute_spreads(betting_games)
    data.compute_moneylines(betting_games)

    data.assemble_player_data()
    data.assemble_days_data()

    return data


# Create `data` when imported (for Flask)
data = create_data()

if __name__ == "__main__":
    # Allow CLI arguments
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

    # Run with CLI args
    data = create_data(args)
