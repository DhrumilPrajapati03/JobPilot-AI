"""Owner authentication (plan section 4.1).

JobDots has exactly one user, the owner. A request is signed in by either:

* a **session cookie** (`jobdots_session`), created by Google/GitHub login or by trading
  the bearer token at POST /auth/session. Server-side rows store only a sha256 of the
  cookie value; expiry slides (SESSION_DAYS). Cookie-authenticated requests that change
  state must send `X-JobDots-Request: 1` and an allowed Origin (CSRF defence).
* the **bearer token** (`Authorization: Bearer <OWNER_API_TOKEN>`): break-glass for
  scripts, tests and recovery. Constant-time compare; BEARER_AUTH_ENABLED=false turns it off.

The owner row lives in auth.users; it is created on first use from OWNER_EMAIL (and
OWNER_ID, when set, so imported JobPilot rows keep their user id). The browser
extension (jpx_ tokens) and the cron endpoint keep their own separate credentials.
"""

import asyncio
import hashlib
import hmac
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

# Expect "Authorization: Bearer <token>"; a missing header gives 401, not 403.
security = HTTPBearer(auto_error=False)

MIN_TOKEN_LENGTH = 32
SESSION_COOKIE = "jobdots_session"
SESSION_PREFIX = "jds_"
CSRF_HEADER = "x-jobdots-request"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Refresh last_seen/expiry at most this often, so reads don't write on every request.
_TOUCH_EVERY = timedelta(minutes=10)

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
    return settings.BEARER_AUTH_ENABLED and len(settings.OWNER_API_TOKEN) >= MIN_TOKEN_LENGTH


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


# --- sessions -----------------------------------------------------------------------------------

def create_session(user_id: str, method: str, user_agent: str = "") -> str:
    """Start a server-side session; returns the cookie value (only its hash is stored)."""
    from app.db import get_db
    token = SESSION_PREFIX + secrets.token_urlsafe(32)
    get_db().fetch("""insert into public.session (user_id, token_hash, method, expires_at, user_agent)
                      values (%s::uuid, %s, %s, now() + make_interval(days => %s), %s)""",
                   [user_id, hash_secret(token), method, settings.SESSION_DAYS, user_agent[:300]])
    return token


def revoke_session(token: str) -> None:
    from app.db import get_db
    if token.startswith(SESSION_PREFIX):
        get_db().fetch("update public.session set revoked_at = now() where token_hash = %s and revoked_at is null",
                       [hash_secret(token)])


def _session_user(token: str) -> str | None:
    """The owner id for a live session, sliding its expiry; None when unknown/expired/revoked."""
    from app.db import get_db
    db = get_db()
    rows = db.fetch("""select user_id::text, last_seen_at from public.session
                       where token_hash = %s and revoked_at is null and expires_at > now()""", [hash_secret(token)])
    if not rows:
        return None
    user_id, last_seen = rows[0]
    if datetime.now(timezone.utc) - last_seen > _TOUCH_EVERY:
        db.fetch("""update public.session set last_seen_at = now(), expires_at = now() + make_interval(days => %s)
                    where token_hash = %s""", [settings.SESSION_DAYS, hash_secret(token)])
    return user_id


def _owner_email(user_id: str) -> str:
    from app.db import get_db
    rows = get_db().fetch("select email from auth.users where id = %s::uuid", [user_id])
    return rows[0][0] if rows else ""


async def _verify_token(token: str) -> dict:
    """Check a credential (bearer token or session cookie value) -> {"sub": owner_id, "email": ...}.

    Raises 401 for a wrong/expired credential and 503 when auth is not configured or the
    owner row cannot be loaded. Bearer comparison is constant-time.
    """
    if isinstance(token, str) and token.startswith(SESSION_PREFIX):
        try:
            user_id = await asyncio.to_thread(_session_user, token)
            email = await asyncio.to_thread(_owner_email, user_id) if user_id else ""
        except Exception:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Sign-in is temporarily unavailable.") from None
        if not user_id:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has ended. Sign in again.")
        return {"sub": user_id, "email": email}
    if not _token_configured():
        if not settings.BEARER_AUTH_ENABLED:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token sign-in is turned off. Use Google or GitHub.")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Owner sign-in is not configured on the server.")
    if not isinstance(token, str) or not hmac.compare_digest(token.encode(), settings.OWNER_API_TOKEN.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired credentials.")
    try:
        owner_id, email = await asyncio.to_thread(owner_identity)
    except Exception:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Sign-in is temporarily unavailable.") from None
    return {"sub": owner_id, "email": email}


# --- request checks -------------------------------------------------------------------------------

def allowed_origins() -> set[str]:
    return {o.strip().rstrip("/") for o in settings.FRONTEND_URL.split(",") if o.strip()}


def origin_allowed(origin: str | None) -> bool:
    return bool(origin) and origin.rstrip("/") in allowed_origins()


def check_csrf(request: Request) -> None:
    """Cookie sessions only: state changes need our custom header and an allowed Origin.

    A cross-site form can't add the header, and a cross-site fetch that adds it triggers a
    CORS preflight that only FRONTEND_URL origins pass.
    """
    if request.method in UNSAFE_METHODS:
        if request.headers.get(CSRF_HEADER) != "1" or not origin_allowed(request.headers.get("origin")):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This request was blocked (cross-site check failed).")


@dataclass
class CurrentUser:
    """The verified owner, for endpoint handlers. `token` is the credential used (bearer
    token or session cookie value); long streams re-check it with _verify_token."""
    id: str
    token: str
    email: str = ""
    method: str = "bearer"


def _credential(request: Request, credentials: HTTPAuthorizationCredentials | None) -> tuple[str, str]:
    if credentials is not None and credentials.scheme.lower() == "bearer" and credentials.credentials:
        if credentials.credentials.startswith(SESSION_PREFIX):
            # Session values only travel in the HttpOnly cookie.
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired credentials.")
        return credentials.credentials, "bearer"
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie and cookie.startswith(SESSION_PREFIX):
        check_csrf(request)
        return cookie, "session"
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.", headers={"WWW-Authenticate": "Bearer"})


async def get_current_user(request: Request,
                           credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> CurrentUser:
    """FastAPI dependency: the verified owner (id, credential, email)."""
    token, method = _credential(request, credentials)
    claims = await _verify_token(token)
    return CurrentUser(id=claims["sub"], token=token, email=claims["email"], method=method)


async def get_current_user_id(request: Request,
                              credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> str:
    """FastAPI dependency: the verified owner's id."""
    return (await get_current_user(request, credentials)).id
