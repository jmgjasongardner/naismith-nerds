"""
Prototype: time-centered ratings, and what they would change.

Not wired into the pipeline. Run it, read the numbers, decide.

    python -m scripts.prototype_time_centered

The idea
--------
Today every historical game is scored against each player's *current* rating.
So a March 2025 game keeps being re-interpreted as ratings move, and a player
who stops showing up decays toward zero — retroactively rewriting how good his
old teammates and opponents looked.

A time-centered rating instead asks, for a game on day D, "how good was this
player *around* D", weighting games by distance from D in **both** directions:

    w_i = exp(-ln2 / HL * |t_i - D|)

Two-sided is the important part. A one-sided "as-of" rating only knows what had
happened by D, so early in a career it is starved and heavily shrunk — Jalen's
as-of rating in early 2025 was +0.60 climbing through +1.28, never the ~2.0 his
play deserved. The two-sided kernel uses the surrounding season, which is what
you actually want for attribution.

Cost
----
The design matrix never changes: same games, same players, same covariates.
Only the weight vector moves. So this is one matrix build plus N cheap refits,
not N full pipelines.
"""

import argparse
import time
from datetime import date

import numpy as np
import polars as pl
import scipy.sparse as sp
from sklearn.linear_model import Ridge

from collective_bball.paths import artifacts_dir

PLAYER_COLS = [f"A{i}" for i in range(1, 6)] + [f"B{i}" for i in range(1, 6)]
EXTRA_COLS = [
    "first_poss",
    "total_games_played_diff",
    "consecutive_games_waited_diff",
    "consecutive_games_played_diff",
    "total_games_played_diff_sq",
    "consecutive_games_waited_diff_sq",
    "consecutive_games_played_diff_sq",
]
ALPHA = 25
HALF_LIFE = 365


def load():
    d = artifacts_dir()
    return (
        pl.read_parquet(d / "games.parquet"),
        pl.read_parquet(d / "player_games.parquet"),
        pl.read_parquet(d / "player_data.parquet"),
        pl.read_parquet(d / "ratings.parquet"),
    )


def tier_map(player_data, ratings):
    """Recover each tiered player's tier by matching their rating to a tier's.

    The pipeline substitutes sub-20-game players with their tier label before
    fitting. Kept global here rather than recomputed per target date: a player
    who is thin overall carries little weight in any window anyway, and a
    time-varying tier assignment would change the matrix and give up the one
    build / many refits trick that makes this cheap.
    """
    tiers = {
        r["player"]: r["rating"]
        for r in ratings.filter(pl.col("player").str.contains("Tier")).to_dicts()
    }
    out = {}
    for row in player_data.filter(pl.col("tiered_rating") == 1).to_dicts():
        for name, value in tiers.items():
            if row["rating"] is not None and abs(row["rating"] - value) < 1e-9:
                out[row["player"]] = name
    return out


def build_design(games, tmap):
    """One sparse design matrix for every fit. Rows are games in date order."""
    g = games.with_columns(
        [pl.col(c).replace(tmap, default=pl.col(c)).alias(c) for c in PLAYER_COLS]
    ).sort(["game_date", "game_num"])

    names = sorted({v for c in PLAYER_COLS for v in g[c].to_list() if v is not None})
    index = {n: i for i, n in enumerate(names)}

    rows, cols, vals = [], [], []
    for c in PLAYER_COLS:
        effect = 1 if c.startswith("A") else -1
        for r, v in enumerate(g[c].to_list()):
            if v is not None:
                rows.append(r)
                cols.append(index[v])
                vals.append(effect)

    # coo sums duplicates, which is what we want when two players on a side
    # collapse to the same tier.
    X = sp.coo_matrix(
        (vals, (rows, cols)), shape=(g.height, len(names))
    ).tocsr()
    X = sp.hstack([X, sp.csr_matrix(g.select(EXTRA_COLS).to_numpy())]).tocsr()

    y = -g["score_diff"].to_numpy()
    days = (
        g.with_columns(pl.col("game_date").str.strptime(pl.Date, "%Y-%m-%d").alias("d"))
        .with_columns((pl.col("d") - pl.lit(date(2025, 1, 1))).dt.total_days().alias("n"))["n"]
        .to_numpy()
        .astype(float)
    )
    return g, X, y, days, names, index


def fit(X, y, w, names, index):
    m = Ridge(alpha=ALPHA, fit_intercept=False)
    m.fit(X, y, sample_weight=w)
    return {n: m.coef_[i] for n, i in index.items()}


def time_centered(X, y, days, names, index, targets, half_life=HALF_LIFE):
    """Rating for every player at every target day, two-sided kernel."""
    lam = np.log(2) / half_life
    out = {}
    for t in targets:
        out[t] = fit(X, y, np.exp(-lam * np.abs(days - t)), names, index)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--half_life", type=int, default=HALF_LIFE)
    args = ap.parse_args()

    games, player_games, player_data, ratings = load()
    tmap = tier_map(player_data, ratings)
    g, X, y, days, names, index = build_design(games, tmap)

    day_of = dict(
        zip(
            g["game_date"].to_list(),
            days.tolist(),
        )
    )
    game_days = sorted(day_of)

    t0 = time.time()
    centered = time_centered(
        X, y, days, names, index, [day_of[d] for d in game_days], args.half_life
    )
    elapsed = time.time() - t0
    print(f"time-centered ratings: {len(game_days)} game days in {elapsed:.1f}s "
          f"({elapsed/len(game_days)*1000:.0f}ms per day)\n")

    rating_at = {d: centered[day_of[d]] for d in game_days}
    current = dict(zip(player_data["player"].to_list(), player_data["rating"].to_list()))

    # At the most recent game day the two-sided kernel has nothing to its right,
    # so it collapses to the ordinary one-sided decay. That makes it exactly the
    # single global rating the pipeline produces once the decay bug is fixed —
    # the right baseline for isolating what time-centering alone changes.
    fixed_global = centered[day_of[game_days[-1]]]

    T = [f"T{i}" for i in range(1, 5)]
    O = [f"O{i}" for i in range(1, 6)]

    def quality_diff(row, table, fallback):
        tq = [table.get(row[k], fallback.get(row[k])) for k in T if row[k]]
        oq = [table.get(row[k], fallback.get(row[k])) for k in O if row[k]]
        tq = [v for v in tq if v is not None]
        oq = [v for v in oq if v is not None]
        if not tq or not oq:
            return None
        return float(np.mean(tq)) - float(np.mean(oq))

    recomputed = []
    for row in player_games.select(
        ["player", "game_date", "score_diff", "result_vs_expectation"] + T + O
    ).to_dicts():
        qd_fixed = quality_diff(row, fixed_global, current)
        qd_tc = quality_diff(row, rating_at[row["game_date"]], current)
        if qd_fixed is None or qd_tc is None:
            continue
        recomputed.append(
            (
                row["player"],
                row["game_date"],
                row["result_vs_expectation"],          # live: backwards decay, 270d
                row["score_diff"] - qd_fixed,           # after the decay fix only
                row["score_diff"] - qd_tc,              # + time-centering
            )
        )

    df = pl.DataFrame(
        recomputed,
        schema=["player", "game_date", "gospel_live", "gospel_fixed", "gospel_tc"],
        orient="row",
    )
    per_player = (
        df.group_by("player")
        .agg(
            pl.len().alias("games"),
            pl.mean("gospel_live").alias("live"),
            pl.mean("gospel_fixed").alias("fixed"),
            pl.mean("gospel_tc").alias("centered"),
        )
        .filter(pl.col("games") >= 40)
        .with_columns(
            (pl.col("fixed") - pl.col("live")).alias("d_decay"),
            (pl.col("centered") - pl.col("fixed")).alias("d_center"),
        )
        .sort(pl.col("d_center").abs(), descending=True)
    )

    print("CAREER GOSPEL, decomposed  (players with 40+ games)")
    print("  live     = what the site shows now (backwards decay, 270d)")
    print("  fixed    = after the decay fix alone (one global rating, 365d)")
    print("  centered = fixed + time-centered ratings\n")
    print(f"{'player':11s} {'live':>7s} {'fixed':>7s} {'centered':>9s} {'d_decay':>8s} {'d_center':>9s}")
    for r in per_player.head(10).to_dicts():
        print(f"{r['player']:11s} {r['live']:+7.2f} {r['fixed']:+7.2f} {r['centered']:+9.2f} "
              f"{r['d_decay']:+8.2f} {r['d_center']:+9.2f}")
    print(f"\nn={per_player.height}")
    for label, col in [("decay fix alone", "d_decay"), ("time-centering on top", "d_center")]:
        s = per_player[col].abs()
        print(f"  {label:22s} median {s.median():.3f}   90th {s.quantile(.9):.3f}   max {s.max():.3f}")

    # --- would MVP/LVP awards move? -----------------------------------------
    def awards(col):
        day = (
            df.group_by(["game_date", "player"])
            .agg(pl.len().alias("g"), pl.mean(col).alias("v"))
            .filter(pl.col("g") >= 3)
            .sort(["game_date", "v", "player"], descending=[False, True, False])
        )
        return {
            r["game_date"]: r["player"]
            for r in day.group_by("game_date").agg(pl.col("player").first()).to_dicts()
        }

    a_fixed, a_tc = awards("gospel_fixed"), awards("gospel_tc")
    shared = set(a_fixed) & set(a_tc)
    flips = sum(1 for d in shared if a_fixed[d] != a_tc[d])
    print(f"\nMVP would change on {flips} of {len(shared)} days from time-centering alone")

    # --- does it actually stop drifting? ------------------------------------
    # Refit using only data through 2026-01-31 and compare early-2025 ratings.
    # A stable scheme gives nearly the same answer for an old game either way.
    cutoff = float(day_of[max(d for d in game_days if d <= "2026-01-31")])
    keep = days <= cutoff
    Xc, yc, dc = X[keep], y[keep], days[keep]
    early = [d for d in game_days if d <= "2025-04-30"]
    partial = time_centered(Xc, yc, dc, names, index, [day_of[d] for d in early], args.half_life)

    drift_tc, drift_now = [], []
    for d in early:
        full_r, part_r = centered[day_of[d]], partial[day_of[d]]
        for p in names:
            if p.startswith("Tier"):
                continue
            drift_tc.append(abs(full_r[p] - part_r[p]))
    # the current scheme's "rating for an old game" is just the latest rating,
    # so its drift is how much the latest rating moved over those same 6 months
    latest_full = centered[day_of[game_days[-1]]]
    latest_part = fit(Xc, yc, np.exp(-np.log(2)/args.half_life*np.abs(dc-cutoff)), names, index)
    for p in names:
        if not p.startswith("Tier"):
            drift_now.append(abs(latest_full[p] - latest_part[p]))

    print("\nSTABILITY: how much does an early-2025 game's rating input move")
    print("when six more months of unrelated basketball arrive?")
    print(f"  time-centered   mean |change| = {np.mean(drift_tc):.3f}")
    print(f"  current method  mean |change| = {np.mean(drift_now):.3f}")


if __name__ == "__main__":
    main()
