import os
from pathlib import Path
from dotenv import load_dotenv
import msal
import requests
import pandas as pd
import polars as pl
# import pickle

# Load env
env_path = Path(__file__).resolve().parents[2] / ".env" # This is the interactive environment part
env_path = Path.cwd() / ".env" # This is the part for testing locally
load_dotenv(dotenv_path=env_path)

CLIENT_ID = os.getenv("CLIENT_ID")
TOKEN_CACHE_PATH = os.getenv("TOKEN_CACHE_PATH", "msal_token_cache.bin")
AUTHORITY = "https://login.microsoftonline.com/consumers"
SCOPES = ["Files.ReadWrite"]

# --- Initialize token cache ---
cache = msal.SerializableTokenCache()
if os.path.exists(TOKEN_CACHE_PATH):
    cache.deserialize(open(TOKEN_CACHE_PATH, "r").read())

app = msal.PublicClientApplication(
    client_id=CLIENT_ID,
    authority=AUTHORITY,
    token_cache=cache
)

# --- Try to get a cached token first ---
accounts = app.get_accounts()
result = None
if accounts:
    result = app.acquire_token_silent(SCOPES, account=accounts[0])

# --- If no token, run device flow (first time only) ---
if not result:
    flow = app.initiate_device_flow(scopes=SCOPES)
    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)

# --- Save token cache ---
with open(TOKEN_CACHE_PATH, "w") as f:
    f.write(cache.serialize())

# --- Download Excel from OneDrive ---
if "access_token" in result:
    headers = {"Authorization": f"Bearer {result['access_token']}"}

    # Path-based access
    url = "https://graph.microsoft.com/v1.0/me/drive/root:/Documents/17th Grade/CodingProjects/naismith-nerds/collective_bball/GameResults.xlsm:/content"
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()

    with open("GameResults.xlsm", "wb") as f:
        f.write(resp.content)

    # Load into pandas + polars
    df = pd.read_excel("GameResults.xlsm", sheet_name="GameResults", engine="openpyxl")
    pl_df = pl.DataFrame(df)
    print(pl_df.head())
else:
    print("Failed to acquire token:", result.get("error_description"))
