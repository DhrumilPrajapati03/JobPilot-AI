"""Browser login routes (plan section 4.1), mounted at /auth (not /api/v1) so the provider
callbacks are <PUBLIC_API_URL>/auth/google/callback and /auth/github/callback."""
import asyncio
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from app.config import settings
from app.services import auth, login
from app.services.auth import CurrentUser, get_current_user

router = APIRouter()


def _frontend(path: str, **query) -> str:
    base = (settings.FRONTEND_URL.split(",")[0].strip() or "http://localhost:5173").rstrip("/")
    return f"{base}{path}" + (f"?{urlencode(query)}" if query else "")


def _secure(request: Request) -> bool:
    # Browsers accept Secure cookies on http://localhost; elsewhere only over HTTPS.
    return request.url.scheme == "https" or request.url.hostname in ("localhost", "127.0.0.1")


def _set_session(response: Response, request: Request, token: str) -> None:
    response.set_cookie(auth.SESSION_COOKIE, token, max_age=settings.SESSION_DAYS * 86400, httponly=True,
                        secure=_secure(request), samesite="lax", path="/")


@router.get("/providers")
async def providers():
    """Which sign-in buttons to show. Public; reveals nothing but on/off."""
    return {"google": login.configured("google"), "github": login.configured("github"),
            "token": auth._token_configured()}


@router.get("/{provider}/start")
async def start(provider: str, request: Request, intent: str = Query(default="login", pattern="^(login|link)$")):
    user_id = None
    if intent == "link":
        # Linking needs the signed-in owner (session cookie from a token sign-in or a provider).
        cookie = request.cookies.get(auth.SESSION_COOKIE)
        if not cookie:
            return RedirectResponse(_frontend("/login", auth_error="sign_in_first"), status.HTTP_303_SEE_OTHER)
        try:
            user_id = (await auth._verify_token(cookie))["sub"]
        except HTTPException:
            return RedirectResponse(_frontend("/login", auth_error="sign_in_first"), status.HTTP_303_SEE_OTHER)
    try:
        url, state = await asyncio.to_thread(login.start, provider, intent, user_id)
    except login.LoginError as exc:
        return RedirectResponse(_frontend("/login", auth_error=exc.code), status.HTTP_303_SEE_OTHER)
    response = RedirectResponse(url, status.HTTP_303_SEE_OTHER)
    response.set_cookie(login.STATE_COOKIE, state, max_age=login.STATE_MINUTES * 60, httponly=True,
                        secure=_secure(request), samesite="lax", path="/auth")
    return response


@router.get("/{provider}/callback")
async def callback(provider: str, request: Request, code: str = "", state: str = "", error: str = ""):
    cookie_state = request.cookies.get(login.STATE_COOKIE)
    try:
        if error and state:
            # The user cancelled at the provider; still consume the state.
            await asyncio.to_thread(login.finish, provider, "", state, cookie_state)
        intent, user_id = await asyncio.to_thread(login.finish, provider, code, state, cookie_state)
    except login.LoginError as exc:
        target = _frontend("/settings", link_error=exc.code) if exc.code in ("linked_elsewhere", "already_linked") \
            else _frontend("/login", auth_error=exc.code)
        response = RedirectResponse(target, status.HTTP_303_SEE_OTHER)
        response.delete_cookie(login.STATE_COOKIE, path="/auth")
        return response
    if intent == "link":
        response = RedirectResponse(_frontend("/settings", linked=provider), status.HTTP_303_SEE_OTHER)
    else:
        token = await asyncio.to_thread(auth.create_session, user_id, provider, request.headers.get("user-agent", ""))
        response = RedirectResponse(_frontend("/"), status.HTTP_303_SEE_OTHER)
        _set_session(response, request, token)
    response.delete_cookie(login.STATE_COOKIE, path="/auth")
    return response


@router.post("/session")
async def token_session(request: Request, response: Response, current_user: CurrentUser = Depends(get_current_user)):
    """Break-glass sign-in: trade the bearer token for a browser session (first run, recovery)."""
    if current_user.method != "bearer":
        return {"user_id": current_user.id}
    if not auth.origin_allowed(request.headers.get("origin")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This request was blocked (cross-site check failed).")
    token = await asyncio.to_thread(auth.create_session, current_user.id, "bearer", request.headers.get("user-agent", ""))
    _set_session(response, request, token)
    return {"user_id": current_user.id}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response):
    cookie = request.cookies.get(auth.SESSION_COOKIE)
    if cookie:
        auth.check_csrf(request)
        await asyncio.to_thread(auth.revoke_session, cookie)
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/identities")
async def identities(current_user: CurrentUser = Depends(get_current_user)):
    return {"identities": await asyncio.to_thread(login.identities, current_user.id),
            "available": {p: login.configured(p) for p in login.PROVIDERS}}


@router.delete("/identities/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink(provider: str, current_user: CurrentUser = Depends(get_current_user)):
    if provider not in login.PROVIDERS:
        raise HTTPException(404, "Unknown provider")
    if not await asyncio.to_thread(login.unlink, current_user.id, provider):
        raise HTTPException(404, "That account is not linked")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
