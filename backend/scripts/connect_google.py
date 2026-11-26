"""Connect Gmail for Courier (and later Inbox).

    cd backend
    python scripts/connect_google.py new-key     # once: ENCRYPTION_KEY in the root .env
    python scripts/connect_google.py connect     # opens Google; approve send + read-only Gmail
    python scripts/connect_google.py status

Uses your Google API client (GOOGLE_OAUTH_CLIENT_ID/SECRET, redirect http://localhost:8080/),
never the login client. The refresh token is stored encrypted in the database; nothing
secret is printed. In Google's Testing mode the connection lasts 7 days: run `connect`
again when JobDots (or Telegram) says it is about to expire.
"""
import base64
import hashlib
import http.server
import json
import secrets
import sys
import threading
import urllib.parse
import webbrowser

import _hostenv

_hostenv.load()
from app.config import settings  # noqa: E402

REDIRECT = "http://localhost:8080/"


def new_key(_args) -> int:
    from cryptography.fernet import Fernet
    if settings.ENCRYPTION_KEY:
        print("ENCRYPTION_KEY is already set; not replacing it (stored connections need it).")
        return 0
    _hostenv.set_env("ENCRYPTION_KEY", Fernet.generate_key().decode())
    print("Wrote ENCRYPTION_KEY to .env. Keep a copy in your password manager. Then run: connect")
    return 0


def connect(_args) -> int:
    import httpx
    from app.courier import connections
    from app.services.auth import owner_identity
    if not (settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET):
        print("Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in the root .env first.")
        return 2
    if not settings.ENCRYPTION_KEY:
        print("Run `python scripts/connect_google.py new-key` first.")
        return 2
    scopes = settings.GMAIL_SCOPES.split()
    state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID, "redirect_uri": REDIRECT, "response_type": "code",
        "scope": " ".join(scopes), "access_type": "offline", "prompt": "consent", "state": state,
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
            self.wfile.write(("JobDots: Gmail connected. You can close this tab." if "code" in received
                              else "JobDots: Gmail was not connected. Return to the terminal.").encode())

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 8080), Handler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    print("Opening Google. Pick the Gmail account you send applications from and allow both Gmail permissions.")
    print("If no browser opens, visit:\n" + url)
    webbrowser.open(url)
    thread.join(timeout=300)
    server.server_close()
    if "code" not in received:
        print("Not connected: " + (received.get("error") or "no approval within 5 minutes") + ".")
        return 1
    response = httpx.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "code": received["code"], "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET, "redirect_uri": REDIRECT,
        "grant_type": "authorization_code", "code_verifier": verifier})
    body = response.json() if response.status_code == 200 else {}
    if not body.get("refresh_token"):
        print(f"Google did not return a refresh token (HTTP {response.status_code}). Try again.")
        return 1
    granted = body.get("scope", "").split()
    missing = [s.rsplit("/", 1)[-1] for s in scopes if s.startswith("https://www.googleapis.com/auth/gmail") and s not in granted]
    if missing:
        print("Google did not grant: " + ", ".join(missing) + ". Tick every Gmail permission on the consent screen and try again.")
        return 1
    info = httpx.get("https://openidconnect.googleapis.com/v1/userinfo", timeout=30,
                     headers={"Authorization": f"Bearer {body['access_token']}"}).json()
    connections.save_google(owner_identity()[0], info.get("email", ""), granted, body["refresh_token"])
    print(f"Gmail connected as {info.get('email')}. Emails you approve will be sent from this address.")
    print("Testing mode: it lasts 7 days; Telegram warns you a day before.")
    return 0


def status(_args) -> int:
    from datetime import datetime, timezone
    from app.courier import connections
    from app.services.auth import owner_identity
    conn = connections.get_google(owner_identity()[0])
    if conn is None:
        print("Gmail: not connected.")
        return 1
    left = (conn.expires_hint - datetime.now(timezone.utc)) if conn.expires_hint else None
    print(f"Gmail: {conn.status}, {conn.account_email}" + (f", about {left.days}d {left.seconds // 3600}h left" if left else ""))
    print("Can send: " + str(any(s.endswith("gmail.send") for s in conn.scopes)) +
          "; can read: " + str(any(s.endswith("gmail.readonly") for s in conn.scopes)))
    return 0


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, fn in (("new-key", new_key), ("connect", connect), ("status", status)):
        sub.add_parser(name).set_defaults(fn=fn)
    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
