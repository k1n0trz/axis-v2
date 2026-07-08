import argparse
import json
import os
import threading
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests


AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/adwords"


def parse_env_file(path):
    values = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def upsert_env_values(path, updates):
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    handled = set()
    new_lines = []
    for line in lines:
        if "=" not in line or line.lstrip().startswith("#"):
            new_lines.append(line)
            continue
        key, _ = line.split("=", 1)
        clean_key = key.strip()
        if clean_key in updates:
            new_lines.append(f"{clean_key}={updates[clean_key]}")
            handled.add(clean_key)
        else:
            new_lines.append(line)

    for key, value in updates.items():
        if key not in handled:
            new_lines.append(f"{key}={value}")

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    server_version = "AxisGoogleAdsOAuth/1.0"

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path != self.server.callback_path:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Ruta no encontrada.")
            return

        if "error" in query:
            self.server.oauth_error = query["error"][0]
            message = f"Autorizacion rechazada o fallida: {self.server.oauth_error}"
            self.send_response(400)
            self.end_headers()
            self.wfile.write(message.encode("utf-8"))
            return

        code = query.get("code", [None])[0]
        if not code:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"No se recibio codigo de autorizacion.")
            return

        self.server.authorization_code = code
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"""
            <html>
              <body style="font-family: Arial, sans-serif; padding: 24px;">
                <h2>Autorizacion completada</h2>
                <p>Puedes volver a Codex o cerrar esta ventana.</p>
              </body>
            </html>
            """
        )

    def log_message(self, format, *args):
        return


def build_auth_url(client_id, redirect_uri, state):
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code_for_tokens(client_id, client_secret, redirect_uri, code):
    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code": code,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def refresh_access_token(client_id, client_secret, refresh_token):
    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def expires_at_from_seconds(expires_in):
    return (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))).isoformat()


def save_token_store(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_token_store(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def run_local_callback_server(host, port, callback_path):
    server = HTTPServer((host, port), OAuthCallbackHandler)
    server.callback_path = callback_path
    server.authorization_code = None
    server.oauth_error = None
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def wait_for_code(server, timeout_seconds):
    started_at = time.time()
    while time.time() - started_at < timeout_seconds:
        if server.oauth_error:
            raise RuntimeError(server.oauth_error)
        if server.authorization_code:
            return server.authorization_code
        time.sleep(0.25)
    raise TimeoutError("No se recibio el codigo OAuth dentro del tiempo esperado.")


def main():
    parser = argparse.ArgumentParser(description="Autorizacion OAuth2 para Google Ads con guardado de refresh token.")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--token-store", default="data/google_ads_tokens.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--callback-path", default="/google-ads/oauth/callback")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    env_path = Path(args.env_file).resolve()
    token_store_path = Path(args.token_store).resolve()
    env_values = parse_env_file(env_path)

    client_id = env_values.get("GOOGLE_ADS_CLIENT_ID") or os.getenv("GOOGLE_ADS_CLIENT_ID")
    client_secret = env_values.get("GOOGLE_ADS_CLIENT_SECRET") or os.getenv("GOOGLE_ADS_CLIENT_SECRET")
    developer_token = env_values.get("GOOGLE_ADS_DEVELOPER_TOKEN") or os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN")
    if not client_id or not client_secret:
        raise SystemExit("Faltan GOOGLE_ADS_CLIENT_ID y/o GOOGLE_ADS_CLIENT_SECRET en .env o variables de entorno.")
    if not developer_token:
        print("Aviso: GOOGLE_ADS_DEVELOPER_TOKEN no es necesario para OAuth, pero si para llamar la API luego.")

    redirect_uri = f"http://{args.host}:{args.port}{args.callback_path}"
    print("Antes de continuar, agrega este Redirect URI en Google Cloud:")
    print(redirect_uri)
    print()

    server, thread = run_local_callback_server(args.host, args.port, args.callback_path)
    state = f"axis-{int(time.time())}"
    auth_url = build_auth_url(client_id, redirect_uri, state)

    print("Abriendo ventana de autorizacion de Google...")
    print(auth_url)
    if not args.no_browser:
        webbrowser.open(auth_url, new=1, autoraise=True)

    try:
        code = wait_for_code(server, args.timeout)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)

    token_payload = exchange_code_for_tokens(client_id, client_secret, redirect_uri, code)
    access_token = token_payload["access_token"]
    refresh_token = token_payload.get("refresh_token")
    expires_at = expires_at_from_seconds(token_payload.get("expires_in", 3600))

    if not refresh_token:
        print("Google no devolvio refresh_token. Repite el flujo con prompt=consent y revisa si ya habia consentimiento previo.")
        raise SystemExit(1)

    print()
    print("Refresh token obtenido correctamente:")
    print(refresh_token)
    print()

    env_updates = {
        "GOOGLE_ADS_ACCESS_TOKEN": access_token,
        "GOOGLE_ADS_REFRESH_TOKEN": refresh_token,
        "GOOGLE_ADS_TOKEN_EXPIRES_AT": expires_at,
    }
    upsert_env_values(env_path, env_updates)
    save_token_store(
        token_store_path,
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": token_payload.get("token_type", "Bearer"),
            "scope": token_payload.get("scope", SCOPE),
            "expires_at": expires_at,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    refreshed_payload = refresh_access_token(client_id, client_secret, refresh_token)
    refreshed_access_token = refreshed_payload["access_token"]
    refreshed_expires_at = expires_at_from_seconds(refreshed_payload.get("expires_in", 3600))
    upsert_env_values(
        env_path,
        {
            "GOOGLE_ADS_ACCESS_TOKEN": refreshed_access_token,
            "GOOGLE_ADS_TOKEN_EXPIRES_AT": refreshed_expires_at,
        },
    )
    save_token_store(
        token_store_path,
        {
            **load_token_store(token_store_path),
            "access_token": refreshed_access_token,
            "expires_at": refreshed_expires_at,
            "refreshed_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    print("Tokens guardados en:")
    print(f"- .env: {env_path}")
    print(f"- token store: {token_store_path}")
    print()
    print("Siguientes variables disponibles:")
    print("- GOOGLE_ADS_ACCESS_TOKEN")
    print("- GOOGLE_ADS_REFRESH_TOKEN")
    print("- GOOGLE_ADS_TOKEN_EXPIRES_AT")
    print()
    print("Ya puedes usar GOOGLE_ADS_REFRESH_TOKEN para renovar access tokens sin intervencion manual.")


if __name__ == "__main__":
    main()
