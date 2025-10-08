import os
from dotenv import load_dotenv
import msal
import requests
import pandas as pd
import polars as pl

load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
TENANT_ID = os.getenv("TENANT_ID")
AUTHORITY = "https://login.microsoftonline.com/consumers"
SCOPES = ["Files.ReadWrite.All"]  # Delegated permission

# MSAL device code flow
app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY)

# Acquire token interactively
flow = app.initiate_device_flow(scopes=SCOPES)
if "user_code" not in flow:
    raise Exception("Failed to create device flow. Check your CLIENT_ID and permissions.")

print(flow["message"])  # Gives URL and code to log in

result = app.acquire_token_by_device_flow(flow)  # Will block until you complete login

if "access_token" in result:
    url = "https://graph.microsoft.com/v1.0/me/drive/root:/Documents/17th Grade/CodingProjects/naismith-nerds/collective_bball/GameResults.xlsm:/content"

    resp = requests.get(url, headers={"Authorization": f"Bearer {result['access_token']}"})
    resp.raise_for_status()

    # Save and read
    with open("GameResults.xlsm", "wb") as f:
        f.write(resp.content)

    df = pd.read_excel("GameResults.xlsm", sheet_name="GameResults", engine="openpyxl")
    pl_df = pl.DataFrame(df)
    print(pl_df.head())
else:
    print("Error getting token:", result.get("error_description"))
