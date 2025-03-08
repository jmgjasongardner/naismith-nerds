from collective_bball_OO.basketball_data import BasketballData
from collective_bball_OO.rapm_model import RAPMModel
from collective_bball_OO.moneyline_model import BettingGames
import argparse
import polars as pl

pl.Config.set_tbl_rows(n=100)
pl.Config.set_tbl_cols(n=8)

if __name__ == "__main__":

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

    # Initialize data processing
    data = BasketballData(data_source="./collective_bball/GameResults.xlsm", args=args)
    data.clean_data()

    # Step 1: Compute player stats (without RAPM)
    data.compute_player_stats()

    # Step 2: Compute RAPM ratings
    rapm_model = RAPMModel()
    data.compute_rapm(rapm_model)

    # Step 3: Merge stats + RAPM into final player data
    data.merge_player_data()
    # TODO: perhaps here or elsewhere, make player_games

    # Step 4: Compute win probabilities
    betting_games = BettingGames()
    data.compute_spreads(betting_games)
    data.compute_moneylines(betting_games)

    # Step 5: Compute player games
    data.assemble_final_data()

    # Print results
    print(data.games.head())  # Games with win probabilities
    print(data.player_data.head())  # Players with stats + RAPM ratings
