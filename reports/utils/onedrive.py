from io import BytesIO

import msal
import requests
from django.conf import settings

SCOPES = ["Files.Read", "User.Read"]
GRAPH_ROOT = "https://graph.microsoft.com/v1.0"


def is_configured():
    return all(
        [
            settings.ONEDRIVE_CLIENT_ID,
            settings.ONEDRIVE_CLIENT_SECRET,
            settings.ONEDRIVE_TENANT_ID,
            settings.ONEDRIVE_REDIRECT_URI,
        ]
    )


def _client():
    authority = f"https://login.microsoftonline.com/{settings.ONEDRIVE_TENANT_ID}"
    return msal.ConfidentialClientApplication(
        settings.ONEDRIVE_CLIENT_ID,
        authority=authority,
        client_credential=settings.ONEDRIVE_CLIENT_SECRET,
    )


def get_auth_url(state=None):
    if not is_configured():
        return None
    return _client().get_authorization_request_url(
        scopes=SCOPES,
        redirect_uri=settings.ONEDRIVE_REDIRECT_URI,
        state=state,
        prompt="select_account",
    )


def exchange_code_for_token(code):
    result = _client().acquire_token_by_authorization_code(
        code,
        scopes=SCOPES,
        redirect_uri=settings.ONEDRIVE_REDIRECT_URI,
    )
    if "access_token" not in result:
        raise RuntimeError(result.get("error_description", "No se pudo autenticar con OneDrive."))
    return result


def refresh_access_token(refresh_token=None):
    token = refresh_token or settings.ONEDRIVE_REFRESH_TOKEN
    if not token:
        raise RuntimeError("No hay refresh token de OneDrive configurado.")
    result = _client().acquire_token_by_refresh_token(
        token,
        scopes=SCOPES,
    )
    if "access_token" not in result:
        raise RuntimeError(result.get("error_description", "No se pudo refrescar el token de OneDrive."))
    return result


def list_excel_files(access_token):
    response = requests.get(
        f"{GRAPH_ROOT}/me/drive/root/search(q='.xlsx')",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    response.raise_for_status()
    files = response.json().get("value", [])
    return [
        {"id": item["id"], "name": item["name"], "modified": item.get("lastModifiedDateTime")}
        for item in files
        if item.get("name", "").lower().endswith(".xlsx")
    ]


def download_file_content(access_token, file_id):
    response = requests.get(
        f"{GRAPH_ROOT}/me/drive/items/{file_id}/content",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    response.raise_for_status()
    return BytesIO(response.content)


def download_file_content_by_path(access_token, drive_path, user_id=None):
    safe_path = drive_path.strip("/")
    if user_id:
        url = f"{GRAPH_ROOT}/users/{user_id}/drive/root:/{safe_path}:/content"
    else:
        url = f"{GRAPH_ROOT}/me/drive/root:/{safe_path}:/content"
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    response.raise_for_status()
    return BytesIO(response.content)
