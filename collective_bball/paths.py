"""
Where persistent state lives.

In production this is a Fly volume mounted at /data, so the DuckDB history, the
rotating OneDrive refresh token, and the prebuilt artifacts all survive
deploys. Locally it falls back to ./data inside the repo.

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
    """Path to the DuckDB database, seeded from the repo copy on first use.

    Seeding preserves the historical `ratings` rows that the ratings-over-time
    charts read; without it a fresh volume would start with no history.
    """
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
