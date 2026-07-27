"""
Fetches the GameResults workbook from OneDrive via Microsoft Graph.

The important detail, and the reason the previous version stopped working:
Microsoft rotates the refresh token on every redemption. The old token is
invalidated and a new one comes back in the same response. If you keep
re-sending the original token from a fixed environment variable, it works until
the grant ages out and then fails permanently with AADSTS70000.

So the token lives in a JSON file on the Fly volume, not in an env var, and is
rewritten on every refresh. REFRESH_TOKEN is read only to seed that file the
first time. As long as a refresh happens within the inactivity window (90 days
for personal accounts, and the scheduler runs daily) the chain never breaks.

One-time setup:
    python -m collective_bball.utils.onedrive_client
"""

import json
import logging
import os
import time
from io import BytesIO
from typing import Optional

import msal
import requests
from dotenv import load_dotenv

from collective_bball.paths import excel_cache_path, token_path

load_dotenv()
logger = logging.getLogger(__name__)

CLIENT_ID = os.environ.get("CLIENT_ID")
TENANT_ID = os.environ.get("TENANT_ID", "consumers")

ONEDRIVE_FILE_PATH = os.environ.get(
    "ONEDRIVE_FILE_PATH",
    "/Documents/17th Grade/CodingProjects/naismith-nerds/collective_bball/GameResults.xlsm",
)

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
# offline_access is what makes Entra return a refresh token at all.
SCOPES = ["Files.Read", "User.Read"]
GRAPH_API_ENDPOINT = "https://graph.microsoft.com/v1.0"

REQUEST_TIMEOUT = 60


class OneDriveError(RuntimeError):
    """Raised when OneDrive cannot serve the workbook."""


def _get_msal_app() -> msal.PublicClientApplication:
    if not CLIENT_ID:
        raise OneDriveError("CLIENT_ID is not set")
    return msal.PublicClientApplication(client_id=CLIENT_ID, authority=AUTHORITY)


def read_stored_token() -> Optional[str]:
    """Current refresh token, preferring the rotating file over the env seed."""
    path = token_path()
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            token = stored.get("refresh_token")
            if token:
                return token
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read stored token at %s: %s", path, exc)

    # First run on a fresh volume: seed from the environment.
    return os.environ.get("REFRESH_TOKEN") or None


def store_token(refresh_token: str) -> None:
    """Persist a rotated refresh token, replacing the file atomically."""
    path = token_path()
    payload = {
        "refresh_token": refresh_token,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    logger.info("Stored rotated OneDrive refresh token at %s", path)


def get_access_token() -> str:
    """Exchange the stored refresh token for an access token, persisting the
    new refresh token that comes back."""
    refresh_token = read_stored_token()
    if not refresh_token:
        raise OneDriveError(
            "No OneDrive refresh token available. Run:\n"
            "  python -m collective_bball.utils.onedrive_client"
        )

    result = _get_msal_app().acquire_token_by_refresh_token(
        refresh_token=refresh_token, scopes=SCOPES
    )

    if "access_token" not in result:
        raise OneDriveError(
            f"Token refresh failed: {result.get('error_description', result)}"
        )

    # This is the line whose absence broke the previous implementation.
    rotated = result.get("refresh_token")
    if rotated and rotated != refresh_token:
        store_token(rotated)

    return result["access_token"]


def fetch_excel_from_onedrive(file_path: Optional[str] = None) -> BytesIO:
    """Download the workbook and cache it locally.

    The cached copy is what makes a transient Graph outage a non-event: the
    caller can fall back to the last known-good workbook rather than to a stale
    file committed months ago.
    """
    file_path = file_path or ONEDRIVE_FILE_PATH
    access_token = get_access_token()

    encoded_path = requests.utils.quote(file_path, safe="/")
    url = f"{GRAPH_API_ENDPOINT}/me/drive/root:{encoded_path}:/content"

    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code == 200:
        content = response.content
        logger.info("Fetched %s (%d bytes) from OneDrive", file_path, len(content))
        try:
            excel_cache_path().write_bytes(content)
        except OSError as exc:
            logger.warning("Could not cache workbook: %s", exc)
        return BytesIO(content)

    if response.status_code == 401:
        raise OneDriveError("OneDrive rejected the access token; re-authenticate.")
    if response.status_code == 404:
        raise OneDriveError(f"File not found in OneDrive: {file_path}")
    raise OneDriveError(
        f"OneDrive returned {response.status_code}: {response.text[:200]}"
    )


def authenticate_interactive() -> dict:
    """Device-code sign-in. Run once; the token then rotates on its own."""
    app = _get_msal_app()
    flow = app.initiate_device_flow(scopes=SCOPES)

    if "user_code" not in flow:
        raise OneDriveError(f"Failed to start device flow: {flow}")

    print("\n" + "=" * 64)
    print("ONEDRIVE AUTHENTICATION")
    print("=" * 64)
    print(f"\n{flow['message']}\n")
    print("=" * 64 + "\n")

    result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        raise OneDriveError(
            f"Authentication failed: {result.get('error_description', result)}"
        )

    refresh_token = result.get("refresh_token")
    if not refresh_token:
        raise OneDriveError(
            "Sign-in succeeded but no refresh token was returned. Confirm the "
            "app registration is a public client with offline_access granted."
        )

    store_token(refresh_token)
    print(f"Success. Refresh token stored at {token_path()}")
    print("\nIt now rotates automatically on every refresh; no env var needed.")
    print("To seed the Fly volume once, run:")
    print(f"  fly secrets set REFRESH_TOKEN='{refresh_token}' --app naismith-nerds")
    return result


def test_connection() -> bool:
    """Verify the stored token can reach Graph."""
    try:
        access_token = get_access_token()
    except OneDriveError as exc:
        print(f"No usable token: {exc}")
        return False

    response = requests.get(
        f"{GRAPH_API_ENDPOINT}/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code == 200:
        user = response.json()
        print(
            f"Connected as {user.get('displayName', 'Unknown')} "
            f"({user.get('userPrincipalName', '')})"
        )
        return True

    print(f"Connection test failed: {response.status_code}")
    return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print("\nOneDrive setup")
    print("-" * 40)
    print(f"Token file: {token_path()}")

    if read_stored_token() and test_connection():
        print("\nConnection working. Testing file fetch...")
        workbook = fetch_excel_from_onedrive()
        print(f"Fetched {len(workbook.getvalue())} bytes")
    else:
        print("\nNo working token. Starting sign-in...\n")
        authenticate_interactive()
        test_connection()
