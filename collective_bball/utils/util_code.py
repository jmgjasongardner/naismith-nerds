import logging
import os
from io import BytesIO
from typing import Union
from pathlib import Path

from dotenv import load_dotenv

from collective_bball.paths import REPO_ROOT, excel_cache_path

load_dotenv()

logger = logging.getLogger(__name__)

# The workbook committed to the repo. Last-resort fallback only: it is whatever
# was true at the most recent push, which is exactly the staleness the OneDrive
# integration exists to eliminate.
LOCAL_DATA_PATH = REPO_ROOT / "collective_bball" / "GameResults.xlsm"

player_columns = [f"A{i}" for i in range(1, 6)] + [f"B{i}" for i in range(1, 6)]


def get_data_source(allow_stale: bool = True) -> Union[str, BytesIO]:
    """Resolve the workbook to build from, freshest source first.

    1. OneDrive, the live copy Jason edits courtside.
    2. The last workbook successfully fetched from OneDrive, cached on the
       volume, so a Graph outage doesn't roll the site back months.
    3. The copy committed to the repo.

    Set allow_stale=False in the scheduled refresh: a fallback there would
    silently rebuild identical data and hide the fact that OneDrive is broken.
    """
    try:
        from collective_bball.utils.onedrive_client import fetch_excel_from_onedrive

        logger.info("Fetching workbook from OneDrive...")
        return fetch_excel_from_onedrive()
    except Exception as exc:
        if not allow_stale:
            raise
        logger.warning("OneDrive fetch failed (%s); falling back", exc)

    cached = excel_cache_path()
    if cached.exists():
        logger.warning("Using cached workbook from %s", cached)
        return str(cached)

    if Path(LOCAL_DATA_PATH).exists():
        logger.warning("Using workbook committed to the repo: %s", LOCAL_DATA_PATH)
        return str(LOCAL_DATA_PATH)

    raise FileNotFoundError(
        "No workbook available. Either authenticate OneDrive:\n"
        "  python -m collective_bball.utils.onedrive_client\n"
        f"or place the file at {LOCAL_DATA_PATH}"
    )
