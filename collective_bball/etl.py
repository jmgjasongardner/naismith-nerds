import os
import polars as pl
import pandas as pd
import requests
from urllib.parse import quote
from typing import Tuple
import msal

# Load environment variables
CLIENT_ID = os.getenv("CLIENT_ID")
TENANT_ID = os.getenv("TENANT_ID")
AUTHORITY = "https://login.microsoftonline.com/consumers"
SCOPES = ["Files.Read", "Files.ReadWrite", "User.Read"]


def get_access_token() -> str:
    """Authenticates via device code flow and caches the token."""
    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY)

    # Check if there's a valid cached token
    result = app.acquire_token_silent(SCOPES, account=None)
    if not result:
        flow = app.initiate_device_flow(scopes=SCOPES)
        print(flow["message"])  # Only needed the first time manually
        result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        raise Exception("Authentication failed")

    return result["access_token"]


def download_excel_from_onedrive(filename: str, local_path: str) -> None:
    """Downloads an Excel file from OneDrive using Graph API."""
    access_token = get_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}

    onedrive_path = "Documents/17th Grade/CodingProjects/naismith-nerds/GameResults.xlsm"
    encoded_path = quote(onedrive_path)

    url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_path}:/content"
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()

    with open(local_path, "wb") as f:
        f.write(resp.content)


def load_data(filepath: str) -> Tuple[pl.DataFrame, pl.DataFrame]:
    """Loads game data from Excel (downloaded from OneDrive) into Polars."""
    temp_path = "GameResults.xlsm"
    download_excel_from_onedrive(filepath, temp_path)

    raw_games_df = (
        pl.DataFrame(
            pd.read_excel(temp_path, sheet_name="GameResults", engine="openpyxl")
        )
    ).rename({"Date": "date", "A_SCORE": "a_score", "B_SCORE": "b_score"})
    raw_games_df = raw_games_df.drop(
        [col for col in raw_games_df.columns if "Unnamed" in col]
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
