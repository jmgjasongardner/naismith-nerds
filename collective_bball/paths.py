"""
Where persistent state lives.

In production this is durable storage mounted at /data, so the DuckDB history,
the rotating OneDrive refresh token, and the prebuilt artifacts survive
deploys. Locally it falls back to ./data inside the repo — except for the
DuckDB file, which stays at the repo root so its accumulated ratings history
keeps being version controlled. See db_path().

Nothing here imports polars, duckdb, or sklearn, so it stays cheap to import.
"""

import os
import shutil
from pathlib import Path

# Repo root, i.e. the directory containing collective_bball/ and flask_app/.
REPO_ROOT = Path(__file__).resolve().parent.parent

# The DuckDB file checked into the repo. It carries the ratings history back to
# January 2025, so it is used to seed a fresh volume exactly once.
SEED_DB_PATH = REPO_ROOT / "bball_database.duckdb"

STATIC_DIR = REPO_ROOT / "flask_app" / "static"


def player_thumb_path(player_name: str) -> Path:
    """Small round avatar used in tables."""
    return STATIC_DIR / "player_pics_thumbs" / f"{player_name}.webp"


def player_photo_path(player_name: str) -> Path:
    """Full-size photo used on player pages."""
    return STATIC_DIR / "player_pics" / f"{player_name}.png"


def data_dir() -> Path:
    """Root of persistent state. Created if missing."""
    configured = os.environ.get("NN_DATA_DIR")
    if configured:
        path = Path(configured)
    elif Path("/data").is_dir():
        path = Path("/data")
    else:
        path = REPO_ROOT / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    """Path to the DuckDB database holding the ratings history.

    Locally this is the file committed to the repo. That matters: the ratings
    snapshots accumulate one date at a time and can never be recomputed from
    the workbook alone, so the history only survives by being version
    controlled and pushed. Writing it to a gitignored directory instead meant
    a local rebuild silently left the committed copy — the one that actually
    deploys — frozen, and the ratings-over-time charts stopped advancing.

    In production NN_DATA_DIR points at durable storage, and the committed
    file seeds it once.
    """
    if not os.environ.get("NN_DATA_DIR") and not Path("/data").is_dir():
        return SEED_DB_PATH

    path = data_dir() / "bball_database.duckdb"
    if not path.exists() and SEED_DB_PATH.exists():
        shutil.copy2(SEED_DB_PATH, path)
    return path


def artifacts_dir() -> Path:
    """Directory holding the prebuilt parquet tables the web app boots from."""
    path = data_dir() / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def token_path() -> Path:
    """Where the rotating OneDrive refresh token is persisted."""
    return data_dir() / "onedrive_token.json"


def excel_cache_path() -> Path:
    """Last Excel workbook successfully fetched from OneDrive.

    Lets the app rebuild from the most recent known-good workbook when
    OneDrive is unreachable, instead of falling back to a stale committed file.
    """
    return data_dir() / "GameResults.xlsm"
