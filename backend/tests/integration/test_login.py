"""Google/GitHub login, sessions and the bearer break-glass against the throwaway Postgres.
Provider HTTP is mocked; state, PKCE, ID-token verification and the allowlist are real.
Covers the plan's section 10 login tests."""
import os
import time
import uuid
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("JOBDOTS_TEST_DATABASE_URL"),
                                reason="needs the throwaway database from scripts/check_database.py")

import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import auth, login  # noqa: E402

TOKEN = "t" * 40
ORIGIN = "http://localhost:5173"
REAL_FINISH = login.finish
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class Keys:
    def get_signing_key_from_jwt(self, _token):
        return type("K", (), {"key": KEY.public_key()})()


@pytest.fixture()
def owner(monkeypatch):
    uid = str(uuid.uuid4())
    for name, value in {"OWNER_EMAIL": "owner@example.invalid", "OWNER_API_TOKEN": TOKEN, "OWNER_ID": uid,
                        "GOOGLE_LOGIN_CLIENT_ID": "google-client", "GOOGLE_LOGIN_CLIENT_SECRET": "google-secret",
                        "GITHUB_OAUTH_CLIENT_ID": "github-client", "GITHUB_OAUTH_CLIENT_SECRET": "github-secret",
                        "FRONTEND_URL": ORIGIN, "PUBLIC_API_URL": "http://localhost:8000",
                        "BEARER_AUTH_ENABLED": True}.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(login, "_google_keys", lambda: Keys())
    auth.reset_owner_cache()
    yield uid
    auth.reset_owner_cache()
    get_db().fetch("delete from auth.users where id = %s::uuid", [uid])


@pytest.fixture()
def client():
    # https: the session cookie is Secure (browsers also accept it on http://localhost).
    return TestClient(app, base_url="https://localhost:8000", follow_redirects=False)


def provider(monkeypatch, *, google_sub="g-1", github_id=101, email="owner@example.invalid"):
    """Mock both providers' token and user endpoints; the ID token is really signed and checked."""
    seen = {}

    def respond(request: httpx.Request):
        if request.url.host == "oauth2.googleapis.com":
            form = parse_qs(request.content.decode())
            seen["google_verifier"] = form["code_verifier"][0]
            claims = {"iss": "https://accounts.google.com", "aud": "google-client", "sub": google_sub, "email": email,
                      "email_verified": True, "iat": int(time.time()), "exp": int(time.time()) + 300,
                      "nonce": seen.get("nonce", "")}
            return httpx.Response(200, json={"id_token": jwt.encode(claims, KEY, algorithm="RS256")})
        if request.url.host == "github.com":
            return httpx.Response(200, json={"access_token": "gho_x"})
        if request.url.host == "api.github.com":
            return httpx.Response(200, json={"id": github_id, "login": "owner", "email": email})
        return httpx.Response(404)

    real_finish = REAL_FINISH

    def finish(provider_name, code, state, cookie_state, **kw):
        rows = get_db().fetch("select nonce from public.oauth_state where state_hash = %s", [auth.hash_secret(state or "x")])
        if rows:
            seen["nonce"] = rows[0][0]
        return real_finish(provider_name, code, state, cookie_state, client=httpx.Client(transport=httpx.MockTransport(respond)))

    monkeypatch.setattr(login, "finish", finish)
    return seen


def token_sign_in(client) -> None:
    r = client.post("/auth/session", headers={"Authorization": f"Bearer {TOKEN}", "Origin": ORIGIN})
    assert r.status_code == 200, r.text


def round_trip(client, provider_name, intent="login"):
    start = client.get(f"/auth/{provider_name}/start", params={"intent": intent})
    assert start.status_code == 303, start.text
    state = parse_qs(urlparse(start.headers["location"]).query).get("state", [""])[0]
    return client.get(f"/auth/{provider_name}/callback", params={"code": "c", "state": state}), start


def test_token_session_cookie_flags_csrf_and_logout(owner, client):
    header = next(v for k, v in client.post("/auth/session", headers={"Authorization": f"Bearer {TOKEN}", "Origin": ORIGIN})
                  .headers.multi_items() if k == "set-cookie" and v.startswith(auth.SESSION_COOKIE))
    assert "HttpOnly" in header and "SameSite=lax" in header and "Secure" in header
    cookie = client.cookies.get(auth.SESSION_COOKIE)
    assert cookie and cookie.startswith(auth.SESSION_PREFIX)
    assert client.post("/auth/session", headers={"Authorization": f"Bearer {TOKEN}", "Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/v1/auth/me").json()["user_id"] == owner
    # Cookie-authenticated writes need the custom header and an allowed Origin.
    assert client.post("/api/v1/cases", json={"company": "Co"}).status_code == 403
    assert client.post("/api/v1/cases", json={"company": "Co"}, headers={"X-JobDots-Request": "1",
                                                                          "Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/v1/cases", json={"company": "Co"}, headers={"X-JobDots-Request": "1", "Origin": ORIGIN}).status_code == 201
    assert client.post("/auth/logout", headers={"X-JobDots-Request": "1", "Origin": ORIGIN}).status_code == 204
    client.cookies.set(auth.SESSION_COOKIE, cookie)
    assert client.get("/api/v1/auth/me").status_code == 401  # revoked server-side, not just cleared


def test_expired_session_and_bearer_kill_switch(owner, client, monkeypatch):
    token_sign_in(client)
    get_db().fetch("update public.session set expires_at = now() - interval '1 minute' where user_id = %s::uuid", [owner])
    assert client.get("/api/v1/auth/me").status_code == 401
    client.cookies.clear()
    monkeypatch.setattr(settings, "BEARER_AUTH_ENABLED", False)
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer jds_forged"}).status_code == 401


def test_link_then_login_with_google_and_github(owner, client, monkeypatch):
    seen = provider(monkeypatch)
    # Before linking, provider login is refused even for the owner's own email.
    response, _ = round_trip(client, "google")
    assert "auth_error=not_linked" in response.headers["location"]
    token_sign_in(client)
    for name in ("google", "github"):
        response, start = round_trip(client, name, intent="link")
        assert response.headers["location"].endswith(f"/settings?linked={name}"), response.headers["location"]
    assert "code_challenge" not in start.headers["location"] and seen["google_verifier"]  # start is the GitHub one
    linked = client.get("/auth/identities").json()["identities"]
    assert [i["provider"] for i in linked] == ["github", "google"]
    client.cookies.clear()
    for name in ("google", "github"):
        response, _ = round_trip(client, name)
        assert response.headers["location"] == ORIGIN + "/" and client.cookies.get(auth.SESSION_COOKIE)
        assert client.get("/api/v1/auth/me").json()["user_id"] == owner
        client.cookies.clear()


def test_wrong_account_same_email_and_bad_state_are_rejected(owner, client, monkeypatch):
    provider(monkeypatch, google_sub="g-owner")
    token_sign_in(client)
    round_trip(client, "google", intent="link")
    client.cookies.clear()
    # Same email, different Google account id: rejected.
    provider(monkeypatch, google_sub="g-intruder", email="owner@example.invalid")
    response, _ = round_trip(client, "google")
    assert "auth_error=not_linked" in response.headers["location"] and not client.cookies.get(auth.SESSION_COOKIE)
    # Wrong GitHub account.
    provider(monkeypatch, github_id=999)
    response, _ = round_trip(client, "github")
    assert "auth_error=not_linked" in response.headers["location"]
    # State that doesn't match the browser's cookie, or is replayed, is refused.
    provider(monkeypatch, google_sub="g-owner")
    start = client.get("/auth/google/start")
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    forged = client.get("/auth/google/callback", params={"code": "c", "state": "forged" + state})
    assert "auth_error=invalid_state" in forged.headers["location"]
    client.cookies.set(login.STATE_COOKIE, state, path="/auth")
    ok = client.get("/auth/google/callback", params={"code": "c", "state": state})
    assert ok.headers["location"] == ORIGIN + "/"
    client.cookies.set(login.STATE_COOKIE, state, path="/auth")
    replay = client.get("/auth/google/callback", params={"code": "c", "state": state})
    assert "auth_error=invalid_state" in replay.headers["location"]


def test_a_provider_account_cannot_be_linked_to_two_owners(owner, client, monkeypatch):
    provider(monkeypatch, github_id=4242)
    other = str(uuid.uuid4())
    get_db().fetch("insert into auth.users(id, email) values (%s::uuid, 'other@example.invalid')", [other])
    try:
        get_db().fetch("""insert into public.login_identity (user_id, provider, provider_user_id)
                          values (%s::uuid, 'github', '4242')""", [other])
        token_sign_in(client)
        response, _ = round_trip(client, "github", intent="link")
        assert "link_error=linked_elsewhere" in response.headers["location"]
    finally:
        get_db().fetch("delete from auth.users where id = %s::uuid", [other])


def test_link_requires_a_session_and_providers_endpoint(owner, client):
    start = client.get("/auth/google/start", params={"intent": "link"})
    assert "auth_error=sign_in_first" in start.headers["location"]
    assert client.get("/auth/providers").json() == {"google": True, "github": True, "token": True}
    assert "auth_error=provider_unavailable" in client.get("/auth/nope/start").headers["location"]
