"""
Separates building the dataset from serving it.

Building runs the whole pipeline: read the workbook, clean it, fit the ridge
model, render the charts. It needs pandas, openpyxl, scikit-learn and plotly,
and takes the better part of a minute.

Serving needs none of that. The web app reads prebuilt parquet files and starts
in about a second. That split is what took boot from 37s to ~2s, and it is why
`load()` must never import the modeling stack, directly or transitively.
"""

import hashlib
import json
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Optional, Union

import polars as pl

from collective_bball.paths import artifacts_dir

logger = logging.getLogger(__name__)

# Bump when the set of persisted frames or their columns changes, so a deploy
# carrying new code rebuilds instead of loading artifacts it can't understand.
SCHEMA_VERSION = 1

# Frames persisted as parquet and restored onto the loaded dataset.
FRAMES = (
    "games",
    "player_data",
    "player_games",
    "player_days",
    "days",
    "days_of_week",
    "ratings",
    "teammates",
    "opponents",
)

# Chart HTML is written beside the frames and read lazily. Each blob is several
# megabytes, so it stays out of the boot path and out of memory until the
# classic site actually asks for it.
PLOTS = ("plot_ratings", "plot_rapm_apm")

META_FILENAME = "meta.json"


def default_args():
    """Pipeline arguments. Mirrors the CLI defaults in main.py."""
    import argparse

    return argparse.Namespace(
        use_tier_data=True,
        min_games_to_not_tier=20,
        default_lambda=True,
        lambda_params=[0.1, 0.5, 1, 5, 10, 25, 50, 100],
        decay_half_life=270,
        save_csv=False,
        loop_through_ratings_dates=False,
    )


def source_fingerprint(source: Union[str, Path, IO, bytes]) -> str:
    """Stable hash of the workbook, used to skip rebuilds when nothing changed."""
    digest = hashlib.sha256()
    if isinstance(source, (str, Path)):
        digest.update(Path(source).read_bytes())
    elif isinstance(source, bytes):
        digest.update(source)
    else:
        position = source.tell()
        source.seek(0)
        digest.update(source.read())
        source.seek(position)
    return digest.hexdigest()


def build(source: Union[str, Path, IO], args=None):
    """Run the full pipeline and return the populated BasketballData object."""
    # Imported lazily: these are the expensive dependencies the web app avoids.
    import duckdb

    from collective_bball import create_db_tables
    from collective_bball.basketball_data import BasketballData
    from collective_bball.moneyline_model import BettingGames
    from collective_bball.paths import db_path
    from collective_bball.plots import Plots
    from collective_bball.rapm_model import RAPMModel

    args = args or default_args()
    started = time.time()

    conn = duckdb.connect(str(db_path()))
    try:
        create_db_tables.create_tables(conn)

        data = BasketballData(data_source=source, args=args)
        data.clean_data()
        data.compute_clock_and_starting_poss()
        data.compute_player_stats()
        data.compute_fatigue()

        data.compute_rapm(RAPMModel())
        data.write_to_db(conn=conn)

        data.merge_player_data()

        betting_games = BettingGames()
        data.compute_spreads(betting_games)
        data.compute_moneylines(betting_games)

        data.assemble_player_data()
        data.assemble_days_data()

        data.plot_things(Plots(conn))
    finally:
        conn.close()

    logger.info(
        "Built dataset in %.1fs: %d games, %d players",
        time.time() - started,
        data.games.height,
        data.player_data.height,
    )
    return data


def save(data, out_dir: Optional[Path] = None, fingerprint: str = "") -> Path:
    """Write the dataset to parquet + JSON.

    Written to a sibling staging directory and swapped into place, so a crash
    mid-write can never leave the app booting from a half-written set.
    """
    out_dir = Path(out_dir or artifacts_dir())
    staging = out_dir.parent / f"{out_dir.name}.staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    for name in FRAMES:
        frame = getattr(data, name, None)
        if frame is None:
            raise ValueError(f"Cannot save artifacts: frame '{name}' is missing")
        frame.write_parquet(staging / f"{name}.parquet")

    for name in PLOTS:
        (staging / f"{name}.html").write_text(
            getattr(data, name, "") or "", encoding="utf-8"
        )

    meta = {
        "schema_version": SCHEMA_VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_fingerprint": fingerprint,
        "best_lambda": data.best_lambda,
        "ingest_report": getattr(data, "ingest_report", {}),
        "num_games": data.games.height,
        "num_players": data.player_data.height,
        "num_days": data.days.height,
        "latest_game_date": data.games["game_date"].max(),
    }
    (staging / META_FILENAME).write_text(json.dumps(meta, indent=2), encoding="utf-8")

    previous = out_dir.parent / f"{out_dir.name}.previous"
    if previous.exists():
        shutil.rmtree(previous)
    if out_dir.exists():
        out_dir.rename(previous)
    staging.rename(out_dir)
    if previous.exists():
        shutil.rmtree(previous)

    logger.info("Saved artifacts to %s", out_dir)
    return out_dir


class LoadedData:
    """The dataset as the web app sees it.

    Exposes the same attribute names as BasketballData so the views, the
    formatters and the classic site all work against either one.
    """

    def __init__(self, directory: Path, meta: dict, frames: dict):
        self._dir = directory
        self.meta = meta
        self.best_lambda = meta.get("best_lambda")
        self.ingest_report = meta.get("ingest_report", {})
        self.built_at = meta.get("built_at")
        self.source_fingerprint = meta.get("source_fingerprint", "")
        for name, frame in frames.items():
            setattr(self, name, frame)

    def _read_plot(self, name: str) -> str:
        path = self._dir / f"{name}.html"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    @property
    def plot_ratings(self) -> str:
        return self._read_plot("plot_ratings")

    @property
    def plot_rapm_apm(self) -> str:
        return self._read_plot("plot_rapm_apm")


def read_meta(directory: Optional[Path] = None) -> dict:
    """Just the metadata, without reading any parquet.

    Cheap enough to poll, which is how a running server notices that another
    process rebuilt the dataset underneath it.
    """
    directory = Path(directory or artifacts_dir())
    return json.loads((directory / META_FILENAME).read_text(encoding="utf-8"))


def is_current(directory: Optional[Path] = None) -> bool:
    """True when a complete artifact set matching this code version exists."""
    directory = Path(directory or artifacts_dir())
    meta_file = directory / META_FILENAME
    if not meta_file.exists():
        return False
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if meta.get("schema_version") != SCHEMA_VERSION:
        return False
    return all((directory / f"{name}.parquet").exists() for name in FRAMES)


def load(directory: Optional[Path] = None) -> LoadedData:
    """Read a prebuilt dataset. Cheap: parquet only, no modeling imports."""
    directory = Path(directory or artifacts_dir())
    started = time.time()

    meta = json.loads((directory / META_FILENAME).read_text(encoding="utf-8"))
    frames = {
        name: pl.read_parquet(directory / f"{name}.parquet") for name in FRAMES
    }

    logger.info(
        "Loaded artifacts in %.2fs (built %s)", time.time() - started, meta.get("built_at")
    )
    return LoadedData(directory, meta, frames)


def build_and_save(source: Union[str, Path, IO], args=None):
    """Build from a workbook and persist the result. Returns the loaded dataset."""
    fingerprint = source_fingerprint(source)
    data = build(source, args=args)
    save(data, fingerprint=fingerprint)
    return load()
