"""JobDots backups (plan section 9.2). The worker runs them nightly; this is the manual door.

    python scripts/backup.py new-key                  write BACKUP_ENCRYPTION_KEY into the root .env (if missing)
    python scripts/backup.py connect-drive            connect Google Drive (drive.file) and save the refresh token
    python scripts/backup.py run                      back up now (Drive when connected, else local disk)
    python scripts/backup.py status                   recent backups
    python scripts/backup.py restore FILE --into URL  decrypt FILE and restore it into a scratch database

Secrets are written to the root .env and never printed.
"""
import argparse
import base64
import hashlib
import http.server
import secrets
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ here, /app in the image

# On the host, read the root .env (Compose settings) too; inside the containers the
# environment already has everything.
import os  # noqa: E402

from dotenv import dotenv_values  # noqa: E402

for _key, _value in dotenv_values(ROOT / ".env").items():
    os.environ.setdefault(_key, _value or "")
if not os.environ.get("DATABASE_URL") and os.environ.get("POSTGRES_PASSWORD"):
    os.environ["DATABASE_URL"] = (f"postgresql+psycopg://jobdots:{os.environ['POSTGRES_PASSWORD']}"
                                  f"@127.0.0.1:{os.environ.get('POSTGRES_PORT') or '55432'}/jobdots")

from app.config import settings  # noqa: E402

ENV_FILE = ROOT / ".env"
REDIRECT = "http://localhost:8080/"


def set_env(name: str, value: str) -> None:
    """Add or replace NAME=value in the root .env without echoing it."""
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    lines = [line for line in lines if not line.startswith(f"{name}=")] + [f"{name}={value}"]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def new_key(_args) -> int:
    from cryptography.fernet import Fernet
    existing = [line for line in (ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else [])
                if line.startswith("BACKUP_ENCRYPTION_KEY=") and line.split("=", 1)[1].strip()]
    if existing:
        print("BACKUP_ENCRYPTION_KEY is already set in .env; not replacing it (old backups need it).")
        return 0
    set_env("BACKUP_ENCRYPTION_KEY", Fernet.generate_key().decode())
    print(f"Wrote BACKUP_ENCRYPTION_KEY to {ENV_FILE}. Copy it into your password manager now:\n"
          "without it, no backup can ever be restored. Then: docker compose up -d")
    return 0


def connect_drive(_args) -> int:
    if not (settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET):
        print("Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET (your Google API client with redirect URI "
              f"{REDIRECT}) in the root .env first.")
        return 2
    import httpx
    from app.services.backup import DRIVE_SCOPE, GOOGLE_TOKEN
    state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID, "redirect_uri": REDIRECT, "response_type": "code",
        "scope": DRIVE_SCOPE, "access_type": "offline", "prompt": "consent", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256"})
    received: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
            if query.get("state") == state:
                received.update(query)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("JobDots: Drive connected. You can close this tab.".encode() if "code" in received
                             else "JobDots: Drive was not connected. Return to the terminal.".encode())

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 8080), Handler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    print("Opening Google to allow JobDots to create its own backup files in your Drive (drive.file only).")
    print("If no browser opens, visit:\n" + url)
    webbrowser.open(url)
    thread.join(timeout=300)
    server.server_close()
    if "code" not in received:
        print("Drive was not connected (no approval within 5 minutes, or it was denied).")
        return 1
    response = httpx.post(GOOGLE_TOKEN, data={
        "code": received["code"], "client_id": settings.GOOGLE_OAUTH_CLIENT_ID, "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
        "redirect_uri": REDIRECT, "grant_type": "authorization_code", "code_verifier": verifier}, timeout=30)
    token = response.json().get("refresh_token") if response.status_code == 200 else None
    if not token:
        print(f"Google did not return a refresh token (HTTP {response.status_code}). Try again.")
        return 1
    set_env("GOOGLE_DRIVE_REFRESH_TOKEN", token)
    print("Drive connected; the token is saved in .env. In Google's Testing mode it expires after 7 days, so run this "
          "again when a backup reports the connection expired. Then: docker compose up -d")
    return 0


def run(_args) -> int:
    from app.services import backup
    result = backup.run_backup()
    print(f"{result.status}: {result.file_name} ({result.size_bytes} bytes, {result.destination})"
          + (f" - {result.error}" if result.error else ""))
    return 0 if result.status == "verified" else 1


def status(_args) -> int:
    from app.db import get_db
    rows = get_db().fetch("""select started_at, tier, destination, status, size_bytes, coalesce(error, '')
                             from public.backup_log order by started_at desc limit 15""")
    for started, tier, dest, state, size, error in rows:
        print(f"{started:%Y-%m-%d %H:%M}  {tier:<6} {dest:<5} {state:<8} {size or 0:>10}  {error}")
    return 0


def restore(args) -> int:
    from app.services import backup
    backup.restore(Path(args.file), args.into)
    print("Restored into the target database.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, fn in (("new-key", new_key), ("connect-drive", connect_drive), ("run", run), ("status", status)):
        sub.add_parser(name).set_defaults(fn=fn)
    r = sub.add_parser("restore")
    r.add_argument("file")
    r.add_argument("--into", required=True, help="scratch database URL (never your live one)")
    r.set_defaults(fn=restore)
    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
