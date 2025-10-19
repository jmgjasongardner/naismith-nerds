import duckdb

from collective_bball.basketball_data import BasketballData
from collective_bball.rapm_model import RAPMModel
from collective_bball.moneyline_model import BettingGames
from collective_bball.utils import util_code
from collective_bball.plots import Plots
import argparse
import polars as pl
import logging
from collective_bball import create_db_tables

pl.Config.set_tbl_rows(n=100)
pl.Config.set_tbl_cols(n=8)
logging.basicConfig(level=logging.DEBUG)


def create_data(args=None):
    """Creates and processes the BasketballData object."""
    if args is None:
        args = argparse.Namespace(
            use_tier_data=True,
            min_games_to_not_tier=20,
            default_lambda=True,
            lambda_params=[0.1, 0.5, 1, 5, 10, 25, 50, 100],
            save_csv=False,
            loop_through_ratings_dates=False,
        )
    # logging.debug(f"main.py pre data load")

    conn = duckdb.connect("bball_database.duckdb")
    create_db_tables.create_tables(conn)

    data = BasketballData(data_source=util_code.public_data_url, args=args)
    # logging.debug(f"main.py post data load: {data is not None}")
    data.clean_data()
    data.compute_clock_and_starting_poss()
    # logging.debug(f"main.py post data clean: {data is not None}")
    data.compute_player_stats()
    data.compute_fatigue()
    # logging.debug(f"main.py post data stats: {data is not None}")

    rapm_model = RAPMModel()

    if args.loop_through_ratings_dates:
        for date in data.games["game_date"].unique().sort():
            data.compute_rapm(rapm_model, date_to_filter=date)
            data.write_to_db(conn=conn, date_to_filter=date)
    else:
        data.compute_rapm(rapm_model)
        data.write_to_db(conn=conn)

    # logging.debug(f"main.py post data rapm: {data is not None}")
    data.merge_player_data()
    # logging.debug(f"main.py post data player merge: {data is not None}")

    betting_games = BettingGames()
    data.compute_spreads(betting_games)

    data.compute_moneylines(betting_games)
    # logging.debug(f"main.py post data betting: {data is not None}")

    data.assemble_player_data()
    data.assemble_days_data()
    # logging.debug(f"main.py post data everything: {data is not None}")

    plots = Plots(conn)
    data.plot_things(plots)

    conn.close()

    return data


# Create `data` when imported (for Flask)
# logging.debug(f"main.py pre data obj creation:")
data = create_data()
# logging.debug(f"main.py post data obj creation: {data is not None}")

if __name__ == "__main__":
    # Allow CLI arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--use_tier_data", action="store_false")
    parser.add_argument("--min_games_to_not_tier", default=20, type=int)
    parser.add_argument("--default_lambda", action="store_false")
    parser.add_argument(
        "--lambda_params",
        type=float,
        nargs="*",
        default=[0.1, 0.5, 1, 5, 10, 25, 50, 100],
    )
    parser.add_argument("--save_csv", action="store_true")
    parser.add_argument("--loop_through_ratings_dates", action="store_true")
    args, unknown = parser.parse_known_args()

    # Run with CLI args
    data = create_data(args)
