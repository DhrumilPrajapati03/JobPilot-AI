"""Google and GitHub login for the single owner (plan section 4.1).

* Identity only: Google asks for `openid email profile`, GitHub for `read:user`. Gmail,
  Calendar and Drive are separate connections and never requested here.
* Allowlist on immutable provider ids (Google `sub`, GitHub numeric id). Email or
  username alone never signs anyone in; a matching email under another id is rejected.
* First run: sign in with the bearer token, then link Google/GitHub from Settings
  (intent=link). After that either provider signs in.
* `state` is random, stored hashed in oauth_state for 10 minutes, single use, and bound to
  the browser by a short-lived HttpOnly cookie. Google uses PKCE (S256) and a nonce
  checked inside the verified ID token.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
import jwt

from app.config import settings
from app.db import get_db
from app.services.auth import hash_secret

PROVIDERS = ("google", "github")
STATE_COOKIE = "jobdots_oauth"
STATE_MINUTES = 10
GOOGLE_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
GITHUB_AUTHORIZE = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN = "https://github.com/login/oauth/access_token"
GITHUB_USER = "https://api.github.com/user"
TIMEOUT = httpx.Timeout(15.0)

_jwks: jwt.PyJWKClient | None = None


class LoginError(Exception):
    """A login that must fail. `code` goes to the login page as ?auth_error=<code>."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class ProviderIdentity:
    provider: str
    subject: str        # immutable provider id
    email: str
    name: str


def configured(provider: str) -> bool:
    if provider == "google":
        return bool(settings.GOOGLE_LOGIN_CLIENT_ID and settings.GOOGLE_LOGIN_CLIENT_SECRET)
    if provider == "github":
        return bool(settings.GITHUB_OAUTH_CLIENT_ID and settings.GITHUB_OAUTH_CLIENT_SECRET)
    return False


def callback_url(provider: str) -> str:
    return f"{settings.PUBLIC_API_URL.rstrip('/')}/auth/{provider}/callback"


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def start(provider: str, intent: str, user_id: str | None) -> tuple[str, str]:
    """Begin a login or link. Returns (provider authorize URL, state for the browser cookie)."""
    if provider not in PROVIDERS or not configured(provider):
        raise LoginError("provider_unavailable")
    if intent not in ("login", "link") or (intent == "link") != bool(user_id):
        raise LoginError("invalid_request")
    state, verifier, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(48), secrets.token_urlsafe(16)
    db = get_db()
    db.fetch("delete from public.oauth_state where expires_at < now()")
    db.fetch("""insert into public.oauth_state (state_hash, provider, intent, code_verifier, nonce, user_id, expires_at)
                values (%s, %s, %s, %s, %s, %s::uuid, now() + make_interval(mins => %s))""",
             [hash_secret(state), provider, intent, verifier, nonce, user_id, STATE_MINUTES])
    if provider == "google":
        query = {"client_id": settings.GOOGLE_LOGIN_CLIENT_ID, "redirect_uri": callback_url("google"),
                 "response_type": "code", "scope": "openid email profile", "state": state, "nonce": nonce,
                 "code_challenge": _challenge(verifier), "code_challenge_method": "S256", "prompt": "select_account"}
        return f"{GOOGLE_AUTHORIZE}?{urlencode(query)}", state
    query = {"client_id": settings.GITHUB_OAUTH_CLIENT_ID, "redirect_uri": callback_url("github"),
             "scope": "read:user", "state": state, "allow_signup": "false",
             "code_challenge": _challenge(verifier), "code_challenge_method": "S256"}
    return f"{GITHUB_AUTHORIZE}?{urlencode(query)}", state


def _consume_state(provider: str, state: str, cookie_state: str | None) -> dict:
    if not state or not cookie_state or not secrets.compare_digest(state, cookie_state):
        raise LoginError("invalid_state")
    rows = get_db().fetch("""delete from public.oauth_state where state_hash = %s and provider = %s
                             returning intent, code_verifier, nonce, user_id::text, expires_at > now()""",
                          [hash_secret(state), provider])
    if not rows or not rows[0][4]:
        raise LoginError("invalid_state")
    intent, verifier, nonce, user_id, _ = rows[0]
    return {"intent": intent, "verifier": verifier, "nonce": nonce, "user_id": user_id}


def _google_keys() -> jwt.PyJWKClient:
    global _jwks
    if _jwks is None:
        _jwks = jwt.PyJWKClient(GOOGLE_JWKS, cache_keys=True, lifespan=3600)
    return _jwks


def _google_identity(code: str, verifier: str, nonce: str, client: httpx.Client) -> ProviderIdentity:
    response = client.post(GOOGLE_TOKEN, data={
        "code": code, "client_id": settings.GOOGLE_LOGIN_CLIENT_ID, "client_secret": settings.GOOGLE_LOGIN_CLIENT_SECRET,
        "redirect_uri": callback_url("google"), "grant_type": "authorization_code", "code_verifier": verifier})
    if response.status_code != 200 or "id_token" not in response.json():
        raise LoginError("provider_error")
    id_token = response.json()["id_token"]
    try:
        key = _google_keys().get_signing_key_from_jwt(id_token)
        claims = jwt.decode(id_token, key.key, algorithms=["RS256"], audience=settings.GOOGLE_LOGIN_CLIENT_ID,
                            options={"require": ["sub", "iss", "aud", "exp", "iat"]})
    except jwt.PyJWTError:
        raise LoginError("provider_error") from None
    if claims.get("iss") not in GOOGLE_ISSUERS or not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise LoginError("provider_error")
    email = claims.get("email", "") if claims.get("email_verified") else ""
    return ProviderIdentity("google", str(claims["sub"]), email, claims.get("name", ""))


def _github_identity(code: str, verifier: str, client: httpx.Client) -> ProviderIdentity:
    response = client.post(GITHUB_TOKEN, headers={"Accept": "application/json"}, data={
        "code": code, "client_id": settings.GITHUB_OAUTH_CLIENT_ID, "client_secret": settings.GITHUB_OAUTH_CLIENT_SECRET,
        "redirect_uri": callback_url("github"), "code_verifier": verifier})
    token = response.json().get("access_token") if response.status_code == 200 else None
    if not token:
        raise LoginError("provider_error")
    user = client.get(GITHUB_USER, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    body = user.json() if user.status_code == 200 else {}
    if not isinstance(body.get("id"), int):
        raise LoginError("provider_error")
    return ProviderIdentity("github", str(body["id"]), body.get("email") or "", body.get("login") or "")


def finish(provider: str, code: str, state: str, cookie_state: str | None, *,
           client: httpx.Client | None = None) -> tuple[str, str]:
    """Complete the provider round trip. Returns (intent, owner user id).

    login: the provider id must already be linked. link: attach it to the signed-in owner.
    """
    if provider not in PROVIDERS:
        raise LoginError("invalid_request")
    saved = _consume_state(provider, state, cookie_state)
    if not code:
        raise LoginError("cancelled")
    own_client = client is None
    client = client or httpx.Client(timeout=TIMEOUT)
    try:
        identity = (_google_identity(code, saved["verifier"], saved["nonce"], client) if provider == "google"
                    else _github_identity(code, saved["verifier"], client))
    except httpx.HTTPError:
        raise LoginError("provider_error") from None
    finally:
        if own_client:
            client.close()
    db = get_db()
    linked = db.fetch("select user_id::text from public.login_identity where provider = %s and provider_user_id = %s",
                      [provider, identity.subject])
    if saved["intent"] == "login":
        if not linked:
            raise LoginError("not_linked")
        db.fetch("update public.login_identity set last_login_at = now(), email = %s where provider = %s and provider_user_id = %s",
                 [identity.email, provider, identity.subject])
        return "login", linked[0][0]
    owner = saved["user_id"]
    if linked:
        if linked[0][0] != owner:
            raise LoginError("linked_elsewhere")
        return "link", owner
    if db.fetch("select 1 from public.login_identity where user_id = %s::uuid and provider = %s", [owner, provider]):
        raise LoginError("already_linked")  # unlink the old account first
    db.fetch("""insert into public.login_identity (user_id, provider, provider_user_id, email, display_name)
                values (%s::uuid, %s, %s, %s, %s)""", [owner, provider, identity.subject, identity.email, identity.name])
    return "link", owner


def identities(user_id: str) -> list[dict]:
    rows = get_db().fetch("""select provider, email, display_name, linked_at, last_login_at from public.login_identity
                             where user_id = %s::uuid order by provider""", [user_id])
    return [{"provider": p, "email": e, "name": n, "linked_at": la, "last_login_at": ll} for p, e, n, la, ll in rows]


def unlink(user_id: str, provider: str) -> bool:
    return bool(get_db().fetch("delete from public.login_identity where user_id = %s::uuid and provider = %s returning 1",
                               [user_id, provider]))
