"""
OneDrive client for fetching Excel file via Microsoft Graph API.

Setup (one-time):
1. Run `python -m collective_bball.utils.onedrive_client` locally
2. Follow the device code instructions to authenticate
3. Copy the REFRESH_TOKEN to your .env and Fly.io secrets

Usage:
    from collective_bball.utils.onedrive_client import fetch_excel_from_onedrive
    file_bytes = fetch_excel_from_onedrive()
"""

import os
import json
import msal
import requests
from io import BytesIO
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Microsoft Graph API configuration
CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")  # Optional for public client
TENANT_ID = os.environ.get("TENANT_ID", "consumers")  # "consumers" for personal accounts
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")

# The file path in OneDrive - update this to match your file location
ONEDRIVE_FILE_PATH = os.environ.get(
    "ONEDRIVE_FILE_PATH",
    "/Documents/17th Grade/CodingProjects/naismith-nerds/collective_bball/GameResults.xlsm"
)

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["Files.Read", "User.Read"]
GRAPH_API_ENDPOINT = "https://graph.microsoft.com/v1.0"


def get_msal_app() -> msal.PublicClientApplication:
    """Create MSAL public client application."""
    return msal.PublicClientApplication(
        client_id=CLIENT_ID,
        authority=AUTHORITY,
    )


def get_token_from_refresh_token() -> Optional[str]:
    """Get access token using stored refresh token."""
    if not REFRESH_TOKEN:
        return None

    app = get_msal_app()

    # Use the refresh token to get a new access token
    result = app.acquire_token_by_refresh_token(
        refresh_token=REFRESH_TOKEN,
        scopes=SCOPES,
    )

    if "access_token" in result:
        # If we got a new refresh token, log it (you'd want to update your secrets)
        if "refresh_token" in result and result["refresh_token"] != REFRESH_TOKEN:
            print("NOTE: New refresh token issued. Update your REFRESH_TOKEN env var:")
            print(f"REFRESH_TOKEN={result['refresh_token']}")
        return result["access_token"]
    else:
        print(f"Error getting token: {result.get('error_description', result)}")
        return None


def authenticate_interactive() -> dict:
    """
    Interactive authentication using device code flow.
    Run this once locally to get initial tokens.
    """
    app = get_msal_app()

    # Initiate device code flow
    flow = app.initiate_device_flow(scopes=SCOPES)

    if "user_code" not in flow:
        raise Exception(f"Failed to create device flow: {flow}")

    print("\n" + "=" * 60)
    print("AUTHENTICATION REQUIRED")
    print("=" * 60)
    print(f"\n{flow['message']}\n")
    print("=" * 60 + "\n")

    # Wait for user to authenticate
    result = app.acquire_token_by_device_flow(flow)

    if "access_token" in result:
        print("Authentication successful!")
        print("\n" + "=" * 60)
        print("SAVE THIS REFRESH TOKEN TO YOUR SECRETS")
        print("=" * 60)
        print(f"\nREFRESH_TOKEN={result.get('refresh_token', 'N/A')}\n")
        print("Add this to:")
        print("  1. Your local .env file")
        print("  2. Fly.io secrets: fly secrets set REFRESH_TOKEN=...")
        print("=" * 60 + "\n")
        return result
    else:
        raise Exception(f"Authentication failed: {result.get('error_description', result)}")


def fetch_excel_from_onedrive(file_path: Optional[str] = None) -> BytesIO:
    """
    Fetch Excel file from OneDrive using Graph API.

    Args:
        file_path: Path to file in OneDrive (e.g., "/Documents/folder/file.xlsx")
                   If not provided, uses ONEDRIVE_FILE_PATH env var.

    Returns:
        BytesIO object containing the file contents.

    Raises:
        Exception if authentication fails or file not found.
    """
    file_path = file_path or ONEDRIVE_FILE_PATH

    # Get access token
    access_token = get_token_from_refresh_token()
    if not access_token:
        raise Exception(
            "No valid access token. Run authentication first:\n"
            "  python -m collective_bball.utils.onedrive_client"
        )

    # Build the Graph API URL for the file content
    # URL-encode the path (but keep forward slashes)
    encoded_path = requests.utils.quote(file_path, safe="/")
    url = f"{GRAPH_API_ENDPOINT}/me/drive/root:{encoded_path}:/content"

    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    print(f"Fetching file from OneDrive: {file_path}")
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        print(f"Successfully fetched {len(response.content)} bytes")
        return BytesIO(response.content)
    elif response.status_code == 401:
        raise Exception("Authentication expired. Re-run authentication.")
    elif response.status_code == 404:
        raise Exception(f"File not found: {file_path}")
    else:
        raise Exception(f"Error fetching file: {response.status_code} - {response.text}")


def test_connection() -> bool:
    """Test the OneDrive connection by fetching user info."""
    access_token = get_token_from_refresh_token()
    if not access_token:
        print("No access token available")
        return False

    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(f"{GRAPH_API_ENDPOINT}/me", headers=headers)

    if response.status_code == 200:
        user = response.json()
        print(f"Connected as: {user.get('displayName', 'Unknown')} ({user.get('userPrincipalName', '')})")
        return True
    else:
        print(f"Connection test failed: {response.status_code}")
        return False


# CLI for initial authentication
if __name__ == "__main__":
    import sys

    print("\nOneDrive Authentication Setup")
    print("-" * 40)

    if not CLIENT_ID:
        print("ERROR: CLIENT_ID not set in .env file")
        sys.exit(1)

    # Check if we already have a refresh token
    if REFRESH_TOKEN:
        print("Existing REFRESH_TOKEN found. Testing connection...")
        if test_connection():
            print("\nConnection working! You're all set.")
            print("\nTesting file fetch...")
            try:
                file_bytes = fetch_excel_from_onedrive()
                print(f"Successfully fetched file: {len(file_bytes.getvalue())} bytes")
            except Exception as e:
                print(f"File fetch failed: {e}")
            sys.exit(0)
        else:
            print("Token expired. Re-authenticating...")

    # Run interactive authentication
    try:
        authenticate_interactive()
    except Exception as e:
        print(f"Authentication failed: {e}")
        sys.exit(1)
