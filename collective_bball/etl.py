import os
import polars as pl
import pandas as pd
import requests
from urllib.parse import quote
from typing import Tuple
import msal
from dotenv import load_dotenv

# Load .env for local runs (Fly injects env vars automatically)
load_dotenv()

# === ENVIRONMENT VARIABLES ===
CLIENT_ID = os.getenv("CLIENT_ID")
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
USER_ID = os.getenv("USER_ID")  # from Graph Explorer (the "id" field)
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["https://graph.microsoft.com/.default"]

# === AUTHENTICATION ===
def get_app_only_token() -> str:
    """Gets an app-only Microsoft Graph access token (for both local + production)."""
    if not all([CLIENT_ID, CLIENT_SECRET, TENANT_ID]):
        raise EnvironmentError("Missing CLIENT_ID, CLIENT_SECRET, or TENANT_ID")

    app = msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
    )

    # Check for cached token
    result = app.acquire_token_silent(SCOPES, account=None)

    # If not cached, get a new one
    if not result:
        result = app.acquire_token_for_client(scopes=SCOPES)

    if "access_token" not in result:
        raise Exception(f"Failed to acquire token: {result.get('error_description')}")

    return result["access_token"]

# === FILE DOWNLOAD ===
def download_excel_from_onedrive(filename: str, local_path: str) -> None:
    """Downloads an Excel file from OneDrive using Graph API (no device flow)."""
    access_token = get_app_only_token()
    headers = {"Authorization": f"Bearer {access_token}"}

    # Build the path
    onedrive_path = f"Documents/17th Grade/CodingProjects/naismith-nerds/{filename}"
    encoded_path = quote(onedrive_path)

    # Use the /users/{USER_ID} endpoint since app-only tokens can’t use /me
    url = f"https://graph.microsoft.com/v1.0/users/{USER_ID}/drive/root:/{encoded_path}:/content"

    resp = requests.get(url, headers=headers)
    resp.raise_for_status()

    with open(local_path, "wb") as f:
        f.write(resp.content)

    print(f"✅ Downloaded {filename} → {local_path}")

# === LOAD DATA ===
def load_data(filename: str) -> Tuple[pl.DataFrame, pl.DataFrame]:
    """Downloads Excel from OneDrive, loads it into Polars DataFrames."""
    temp_path = "GameResults.xlsm"
    download_excel_from_onedrive(filename, temp_path)

    raw_games_df = (
        pl.DataFrame(
            pd.read_excel(temp_path, sheet_name="GameResults", engine="openpyxl")
        )
        .rename({"Date": "date", "A_SCORE": "a_score", "B_SCORE": "b_score"})
        .drop([c for c in pl.read_excel(temp_path).columns if "Unnamed" in c])
    )

    tiers = pl.DataFrame(
        pd.read_excel(temp_path, sheet_name="Players", engine="openpyxl")
    )

    return raw_games_df, tiers


def clean_games_data(raw_games_df: pl.DataFrame) -> pl.DataFrame:
    games = (
        raw_games_df.with_columns(
            pl.col("a_score").cast(pl.Int64), pl.col("b_score").cast(pl.Int64)
        )
        .with_columns(
            pl.when(pl.col("b_score") > pl.col("a_score"))
            .then(pl.lit("B"))
            .when(pl.col("b_score") < pl.col("a_score"))
            .then(pl.lit("A"))
            .otherwise(pl.lit("Error"))
            .alias("winner")
        )
        .with_columns(
            pl.col("date")
            .dt.strftime("%Y-%m-%d")
            .alias("game_date")  # Format the date to YYYY-MM-DD
        )
        .with_columns(
            pl.col("date")
            .cum_count()
            .over("game_date")
            .cast(pl.Int32)
            .alias("game_num")  # Sequential count per Date
        )
        .with_columns(
            pl.col("game_date")
            .cast(pl.Date)
            .dt.strftime("%A")
            .str.slice(0, 3)
            .alias("day")
        )
        .filter(pl.col("a_score").is_not_nan())
    ).drop("date")

    return games
