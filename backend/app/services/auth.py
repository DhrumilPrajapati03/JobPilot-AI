"""Owner authentication (plan section 4.1, Day 1 form).

JobDots has exactly one user, the owner. Until Google/GitHub login lands (Day 2),
every request authenticates with the owner's bearer token:

    Authorization: Bearer <OWNER_API_TOKEN>

The token stays afterwards as break-glass access. The owner row lives in the local
auth.users table; it is created on first use from OWNER_EMAIL (and OWNER_ID, when
set, so imported JobPilot rows keep their user id). The browser extension and
the cron endpoint keep their own separate credentials.
"""

import asyncio
import hmac
import threading
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

# Expect "Authorization: Bearer <token>"; a missing header gives 401, not 403.
security = HTTPBearer(auto_error=False)

MIN_TOKEN_LENGTH = 32

_owner: tuple[str, str] | None = None
_owner_lock = threading.Lock()


def _resolve_owner(db, email: str, pinned_id: str) -> str:
    """Find or create the single owner row; the database holds one owner.

    * OWNER_ID set: that row is the owner (created if missing; its email follows OWNER_EMAIL).
    * no users yet: create the owner.
    * exactly one user: it is the owner; its email follows OWNER_EMAIL, so changing the
      address never orphans the data under a second "owner".
    * several users (should not happen): only an exact email match is accepted.
    """
    if pinned_id:
        return db.fetch("""insert into auth.users(id, email) values (%s::uuid, %s)
                           on conflict (id) do update set email = excluded.email returning id::text""",
                        [pinned_id, email])[0][0]
    users = db.fetch("select id::text, email from auth.users order by created_at limit 2")
    if not users:
        return db.fetch("insert into auth.users(email) values (%s) returning id::text", [email])[0][0]
    if len(users) == 1:
        if users[0][1] != email:
            db.fetch("update auth.users set email = %s where id = %s::uuid", [email, users[0][0]])
        return users[0][0]
    match = db.fetch("select id::text from auth.users where email = %s", [email])
    if not match:
        raise RuntimeError("Several users exist and none matches OWNER_EMAIL; set OWNER_ID")
    return match[0][0]


def owner_identity() -> tuple[str, str]:
    """Return (owner_id, owner_email), creating the owner row on first use."""
    global _owner
    with _owner_lock:
        if _owner is not None:
            return _owner
        email = settings.OWNER_EMAIL.strip().lower()
        if not email:
            raise RuntimeError("OWNER_EMAIL is not set")
        from app.db import get_db
        owner_id = _resolve_owner(get_db(), email, settings.OWNER_ID.strip().lower())
        _owner = (owner_id, email)
        return _owner


def reset_owner_cache() -> None:
    global _owner
    with _owner_lock:
        _owner = None


def _token_configured() -> bool:
    return len(settings.OWNER_API_TOKEN) >= MIN_TOKEN_LENGTH


async def _verify_token(token: str) -> dict:
    """Check a bearer token and return the owner's claims: {"sub": owner_id, "email": ...}.

    Raises 401 for a wrong token and 503 when owner auth is not configured or the
    owner row cannot be loaded. Comparison is constant-time.
    """
    if not _token_configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Owner sign-in is not configured on the server.")
    if not isinstance(token, str) or not hmac.compare_digest(token.encode(), settings.OWNER_API_TOKEN.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired credentials.")
    try:
        owner_id, email = await asyncio.to_thread(owner_identity)
    except Exception:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Sign-in is temporarily unavailable.") from None
    return {"sub": owner_id, "email": email}


@dataclass
class CurrentUser:
    """The verified owner, for endpoint handlers."""
    id: str
    token: str
    email: str = ""


def _bearer(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.",
                            headers={"WWW-Authenticate": "Bearer"})
    return credentials.credentials


async def get_current_user_id(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> str:
    """FastAPI dependency: the verified owner's id."""
    return (await _verify_token(_bearer(credentials)))["sub"]


async def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> CurrentUser:
    """FastAPI dependency: the verified owner (id, token, email)."""
    token = _bearer(credentials)
    claims = await _verify_token(token)
    return CurrentUser(id=claims["sub"], token=token, email=claims["email"])
