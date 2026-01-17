import os
from typing import Union
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()

# Local fallback path
LOCAL_DATA_PATH = "collective_bball/GameResults.xlsm"

player_columns = [f"A{i}" for i in range(1, 6)] + [f"B{i}" for i in range(1, 6)]


def get_data_source() -> Union[str, BytesIO]:
    """
    Get the data source for Excel file.

    Returns OneDrive BytesIO if REFRESH_TOKEN is set and valid,
    otherwise falls back to local file path.
    """
    # Check if OneDrive is configured
    refresh_token = os.environ.get("REFRESH_TOKEN")

    if refresh_token:
        try:
            from collective_bball.utils.onedrive_client import fetch_excel_from_onedrive
            print("Fetching data from OneDrive...")
            return fetch_excel_from_onedrive()
        except Exception as e:
            print(f"OneDrive fetch failed: {e}")
            print("Falling back to local file...")

    # Fall back to local file
    if os.path.exists(LOCAL_DATA_PATH):
        print(f"Using local file: {LOCAL_DATA_PATH}")
        return LOCAL_DATA_PATH
    else:
        raise FileNotFoundError(
            f"No data source available. Either:\n"
            f"  1. Set REFRESH_TOKEN for OneDrive access, or\n"
            f"  2. Place Excel file at: {LOCAL_DATA_PATH}"
        )


# For backward compatibility - this will be evaluated when imported
# Use get_data_source() for dynamic fetching
public_data_url = LOCAL_DATA_PATH  # Deprecated: use get_data_source() instead
