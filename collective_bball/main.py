"""
Command line entry point for building the dataset.

    python -m collective_bball.main            # build from the freshest source
    python -m collective_bball.main --local    # build from the committed workbook

This module used to run the entire pipeline at import time, which meant every
web worker boot re-read Excel and refit the ridge model before serving a single
request. It no longer does anything on import; the web app loads prebuilt
artifacts instead. Keep it that way.
"""

import argparse
import logging

import polars as pl

from collective_bball import artifacts
from collective_bball.utils import util_code

pl.Config.set_tbl_rows(n=100)
pl.Config.set_tbl_cols(n=8)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Build Naismith Nerds artifacts")
    parser.add_argument("--use_tier_data", action="store_false")
    parser.add_argument("--min_games_to_not_tier", default=20, type=int)
    parser.add_argument("--default_lambda", action="store_false")
    parser.add_argument(
        "--lambda_params",
        type=float,
        nargs="*",
        default=[0.1, 0.5, 1, 5, 10, 25, 50, 100],
    )
    parser.add_argument("--decay_half_life", default=365, type=int)
    # Bandwidth of the two-sided kernel used for per-game historical ratings.
    # Chosen to match decay_half_life so that at the most recent game day --
    # where the kernel has nothing to its right -- it collapses to the same
    # one-sided decay the leaderboard rating uses. Leave-one-day-out CV shows
    # narrower is worse out of sample (60d costs 2.1% RMSE, 365d costs 0.19%)
    # while 365d still removes 43% of the drift in a historical spread.
    parser.add_argument("--time_centered_half_life", default=365, type=int)
    parser.add_argument("--save_csv", action="store_true")
    parser.add_argument("--loop_through_ratings_dates", action="store_true")
    parser.add_argument(
        "--local",
        action="store_true",
        help="Build from the committed workbook instead of OneDrive",
    )
    args, _unknown = parser.parse_known_args(argv)
    return args


def create_data(args=None):
    """Build the dataset and persist it as artifacts. Returns the loaded set."""
    args = args or parse_args([])
    source = (
        str(util_code.LOCAL_DATA_PATH)
        if getattr(args, "local", False)
        else util_code.get_data_source()
    )
    return artifacts.build_and_save(source, args=args)


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args(argv)
    data = create_data(args)

    report = data.ingest_report
    print(f"\nBuilt {report.get('rows_kept', 0)} games from {report.get('rows_read', 0)} rows")
    if report.get("rows_skipped"):
        print(
            f"Skipped {report['rows_skipped']} incomplete row(s): "
            f"{report.get('missing_date', 0)} missing a date, "
            f"{report.get('incomplete_lineup', 0)} missing players, "
            f"{report.get('missing_score', 0)} missing a score"
        )
    print(f"Players: {data.player_data.height}   Best lambda: {data.best_lambda}")
    print(f"Latest game: {data.meta.get('latest_game_date')}")
    return data


if __name__ == "__main__":
    main()
