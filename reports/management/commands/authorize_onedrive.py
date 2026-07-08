import json
import threading
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from reports.utils import onedrive


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


def expires_at_from_seconds(expires_in):
    return (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))).isoformat()


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    server_version = "AxisOneDriveOAuth/1.0"

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
            self.send_response(400)
            self.end_headers()
            self.wfile.write(self.server.oauth_error.encode("utf-8"))
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
                <p>Puedes volver a la terminal.</p>
              </body>
            </html>
            """
        )

    def log_message(self, format, *args):
        return


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


class Command(BaseCommand):
    help = "Autoriza OneDrive con navegador y guarda refresh token delegado en .env."

    def add_arguments(self, parser):
        parser.add_argument("--env-file", default=".env")
        parser.add_argument("--timeout", type=int, default=180)
        parser.add_argument("--no-browser", action="store_true")

    def handle(self, *args, **options):
        if not onedrive.is_configured():
            raise CommandError("Faltan ONEDRIVE_CLIENT_ID, ONEDRIVE_CLIENT_SECRET, ONEDRIVE_TENANT_ID u ONEDRIVE_REDIRECT_URI.")

        redirect_uri = settings.ONEDRIVE_REDIRECT_URI
        parsed = urlparse(redirect_uri)
        if not parsed.scheme or not parsed.hostname:
            raise CommandError("ONEDRIVE_REDIRECT_URI debe ser una URL valida, por ejemplo http://127.0.0.1:8766/onedrive/callback")

        server, thread = run_local_callback_server(
            parsed.hostname,
            parsed.port or 80,
            parsed.path or "/",
        )
        auth_url = onedrive.get_auth_url(state=f"axis-onedrive-{int(time.time())}")
        self.stdout.write("Abriendo navegador para autorizar OneDrive...")
        self.stdout.write(auth_url)
        if not options["no_browser"]:
            webbrowser.open(auth_url, new=1, autoraise=True)

        try:
            code = wait_for_code(server, options["timeout"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=1)

        token_payload = onedrive.exchange_code_for_token(code)
        refresh_token = token_payload.get("refresh_token")
        access_token = token_payload.get("access_token")
        if not refresh_token or not access_token:
            raise CommandError("Microsoft no devolvio refresh_token/access_token. Repite el flujo y revisa permisos/redirect URI.")

        env_path = Path(options["env_file"]).resolve()
        updates = {
            "ONEDRIVE_ACCESS_TOKEN": access_token,
            "ONEDRIVE_REFRESH_TOKEN": refresh_token,
            "ONEDRIVE_TOKEN_EXPIRES_AT": expires_at_from_seconds(token_payload.get("expires_in", 3600)),
            "ONEDRIVE_AUTH_MODE": "delegated",
        }
        upsert_env_values(env_path, updates)

        self.stdout.write(
            json.dumps(
                {
                    "message": "Autorizacion de OneDrive completada.",
                    "env_file": str(env_path),
                    "saved_keys": list(updates.keys()),
                    "refresh_token_preview": refresh_token[:12] + "...",
                },
                indent=2,
            )
        )
