"""
Regenerate the whole ratings history in DuckDB.

    python -m scripts.rebuild_ratings_history --local          # dry run
    python -m scripts.rebuild_ratings_history --local --write  # commit it

Why this is needed
------------------
Every snapshot in the `ratings` table was written under the reversed decay
weights (see rapm_model.preprocess_data), so the accumulated history is wrong
in the same way the live ratings were. Fixing the model forward only produces
a sawtooth: one corrected date sitting between uncorrected neighbours.

What it writes
--------------
For each game day D, the rating fit on games up to and including D, decayed
one-sidedly from D. That is a genuine as-of number -- what the leaderboard
would have said that night -- which is what a ratings-over-time chart should
show. It is deliberately *not* the two-sided `ratings_by_date` used to price
individual games; those answer different questions and both are kept.

Anchoring the decay at D rather than at the wall clock is what makes this
reproducible: re-running it next month produces identical rows.
"""

import argparse
import time

import duckdb
import polars as pl

from collective_bball import create_db_tables
from collective_bball.basketball_data import BasketballData
from collective_bball.main import parse_args as pipeline_args
from collective_bball.paths import db_path
from collective_bball.rapm_model import RAPMModel
from collective_bball.utils import util_code


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true", help="use the committed workbook")
    ap.add_argument("--write", action="store_true", help="actually write to DuckDB")
    ap.add_argument("--limit", type=int, default=0, help="only the last N days")
    opts = ap.parse_args()

    args = pipeline_args([])
    source = (
        str(util_code.LOCAL_DATA_PATH) if opts.local else util_code.get_data_source()
    )

    data = BasketballData(data_source=source, args=args)
    data.clean_data()
    data.compute_clock_and_starting_poss()
    data.compute_player_stats()
    data.compute_fatigue()

    days = sorted(data.games["game_date"].unique().to_list())
    if opts.limit:
        days = days[-opts.limit :]
    print(f"{len(days)} game days, {data.games.height} games\n")

    model = RAPMModel()
    rows = []
    started = time.time()
    for i, day in enumerate(days, 1):
        data.compute_rapm(model, date_to_filter=day)
        rows.append(data.ratings.with_columns(pl.lit(day).alias("date")))
        if i % 40 == 0 or i == len(days):
            print(f"  {i}/{len(days)} days  ({time.time() - started:.0f}s)")

    history = pl.concat(rows).select(["player", "date", "rating"])
    print(f"\nbuilt {history.height} rows in {time.time() - started:.0f}s")

    conn = duckdb.connect(str(db_path()))
    try:
        create_db_tables.create_tables(conn)
        old = pl.from_pandas(
            conn.execute("SELECT player, date, rating FROM ratings").fetch_df()
        )
        merged = old.join(history, on=["player", "date"], suffix="_new").drop_nulls()
        if merged.height:
            delta = (merged["rating_new"] - merged["rating"]).abs()
            print(
                f"overlap {merged.height} rows: mean |change| {delta.mean():.3f}, "
                f"max {delta.max():.3f}"
            )
        print(f"existing rows {old.height} -> new rows {history.height}")

        if not opts.write:
            print("\nDRY RUN. Re-run with --write to replace the table.")
            return

        # Replace wholesale: every row is being recomputed, and leaving stale
        # rows for players who no longer resolve would mix two decay regimes in
        # one table.
        history_df = history.to_pandas()  # noqa: F841 - referenced by DuckDB
        conn.execute("DELETE FROM ratings")
        conn.execute("INSERT INTO ratings BY NAME SELECT * FROM history_df")
        n = conn.execute("SELECT count(*) FROM ratings").fetchone()[0]
        print(f"\nwrote {n} rows to {db_path()}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
