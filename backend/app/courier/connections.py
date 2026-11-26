"""Token broker (plan section 4): OAuth connections for Courier executors.

Refresh tokens are stored Fernet-encrypted (ENCRYPTION_KEY) in `connection`; only Courier
code decrypts them, to mint short-lived access tokens. Agents never hold tokens.

In Google's Testing mode a refresh token with Gmail scopes ends after 7 days, so each
connection carries `expires_hint`; Telegram warns a day before, and a refused refresh marks
the connection expired (reconnect with scripts/connect_google.py).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings
from app.db import get_db

GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
TESTING_LIFETIME = timedelta(days=7)


class ConnectionError_(RuntimeError):
    """The connection is missing, expired or refused; the message says how to fix it."""


@dataclass
class Connection:
    id: str
    account_email: str
    scopes: list[str]
    status: str
    connected_at: datetime
    expires_hint: datetime | None


def _box() -> Fernet:
    key = settings.ENCRYPTION_KEY.strip()
    if not key:
        raise ConnectionError_("ENCRYPTION_KEY is not set; run: python scripts/connect_google.py new-key")
    return Fernet(key.encode())


def save_google(user_id: str, account_email: str, scopes: list[str], refresh_token: str, *, testing: bool = True) -> None:
    secret = _box().encrypt(refresh_token.encode()).decode()
    expires = datetime.now(timezone.utc) + TESTING_LIFETIME if testing else None
    get_db(user_id).fetch("""
        insert into public.connection (user_id, provider, account_email, scopes, secret_enc, status, connected_at, expires_hint)
        values (%s::uuid, 'google', %s, %s, %s, 'active', now(), %s)
        on conflict (user_id, provider) do update set account_email = excluded.account_email, scopes = excluded.scopes,
          secret_enc = excluded.secret_enc, status = 'active', connected_at = now(), expires_hint = excluded.expires_hint,
          warned_at = null, last_error = null""", [user_id, account_email, scopes, secret, expires])


def get_google(user_id: str) -> Connection | None:
    rows = get_db(user_id).fetch("""select id::text, account_email, scopes, status, connected_at, expires_hint
                                    from public.connection where user_id = %s::uuid and provider = 'google'""", [user_id])
    return Connection(*rows[0]) if rows else None


def _mark(user_id: str, status: str, error: str) -> None:
    get_db(user_id).fetch("""update public.connection set status = %s, last_error = %s
                             where user_id = %s::uuid and provider = 'google'""", [status, error[:300], user_id])


def google_access_token(user_id: str, *, need: str, client: httpx.Client | None = None) -> tuple[str, str]:
    """A fresh access token and the connected address. `need` is a scope the caller requires."""
    rows = get_db(user_id).fetch("""select account_email, scopes, status, secret_enc from public.connection
                                    where user_id = %s::uuid and provider = 'google'""", [user_id])
    if not rows:
        raise ConnectionError_("Gmail is not connected. Run: python scripts/connect_google.py connect")
    email, scopes, status, secret = rows[0]
    if status != "active":
        raise ConnectionError_("The Gmail connection has expired. Reconnect: python scripts/connect_google.py connect")
    if need not in scopes:
        raise ConnectionError_(f"The Gmail connection lacks {need.rsplit('/', 1)[-1]}; reconnect to grant it.")
    try:
        refresh = _box().decrypt(secret.encode()).decode()
    except InvalidToken:
        raise ConnectionError_("The stored Gmail connection can't be decrypted with ENCRYPTION_KEY; reconnect.") from None
    own = client is None
    client = client or httpx.Client(timeout=30)
    try:
        response = client.post(GOOGLE_TOKEN, data={"client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                                                   "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                                                   "refresh_token": refresh, "grant_type": "refresh_token"})
    finally:
        if own:
            client.close()
    if response.status_code != 200:
        error = (response.json() if response.headers.get("content-type", "").startswith("application/json") else {}).get("error", "")
        if error == "invalid_grant":
            _mark(user_id, "expired", "Google refused the refresh token (expired or revoked)")
            raise ConnectionError_("The Gmail connection has expired (Testing mode lasts 7 days). "
                                   "Reconnect: python scripts/connect_google.py connect")
        raise ConnectionError_(f"Google token refresh failed (HTTP {response.status_code}); try again shortly.")
    return response.json()["access_token"], email


def needs_warning(conn: Connection | None, now: datetime | None = None) -> bool:
    """True a day before a Testing-mode connection runs out (warn once)."""
    now = now or datetime.now(timezone.utc)
    return bool(conn and conn.status == "active" and conn.expires_hint and conn.expires_hint - now <= timedelta(days=1))
