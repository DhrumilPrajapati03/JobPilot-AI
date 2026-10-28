"""Composio REST integration; private per-user Gmail accounts, no token custody."""
import json
import re
from urllib.parse import urlencode, urlsplit

import httpx

from app.config import settings


class BrokerError(RuntimeError):
    def __init__(self, message="Gmail is temporarily unavailable", *, rejected=False):
        super().__init__(message)
        self.rejected = rejected


def configured():
    return bool(settings.MAILBOX_ENABLED and settings.COMPOSIO_API_KEY and settings.COMPOSIO_GMAIL_AUTH_CONFIG_ID)


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", value):
        raise BrokerError("Invalid provider identifier", rejected=True)
    return value


class GmailBroker:
    async def request(self, method, path, body=None):
        if not configured():
            raise BrokerError("Gmail connection is not configured", rejected=True)
        try:
            async with httpx.AsyncClient(timeout=30, trust_env=False, follow_redirects=False) as client:
                async with client.stream(method, "https://backend.composio.dev" + path,
                                         headers={"x-api-key": settings.COMPOSIO_API_KEY}, json=body) as response:
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > 8 * 1024 * 1024:
                            raise BrokerError("Provider response exceeded the size limit")
                    if response.status_code >= 300:
                        raise BrokerError(f"Composio request failed ({response.status_code})", rejected=400 <= response.status_code < 500)
                    return json.loads(content) if content else {}
        except BrokerError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            # Do not include response bodies, URLs with auth state, or secrets.
            raise BrokerError("Provider response was not confirmed") from exc

    async def link(self, uid):
        result = await self.request("POST", "/api/v3/connected_accounts/link", {
            "auth_config_id": settings.COMPOSIO_GMAIL_AUTH_CONFIG_ID, "user_id": uid,
            "callback_url": settings.FRONTEND_URL.split(',')[0].rstrip('/') + "/settings",
        })
        url = result.get("redirect_url", "")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not (parsed.hostname or "").endswith(".composio.dev") or parsed.username or parsed.password:
            raise BrokerError("Provider returned an invalid connection link")
        return {"redirect_url": url, "expires_at": result.get("expires_at")}

    async def verify(self, uid, account_id):
        account = await self.request("GET", "/api/v3/connected_accounts/" + safe_id(account_id))
        if (account.get("user_id") != uid or account.get("status") != "ACTIVE"
                or account.get("is_disabled") is True or account.get("auth_config", {}).get("is_disabled") is True
                or account.get("toolkit", {}).get("slug") != "gmail"
                or account.get("auth_config", {}).get("id") != settings.COMPOSIO_GMAIL_AUTH_CONFIG_ID
                or account.get("experimental", {}).get("account_type", "PRIVATE") != "PRIVATE"):
            raise BrokerError("This private Gmail connection is not active for your account", rejected=True)
        return account

    async def complete(self, uid, session_uri):
        result = await self.request("POST", "/api/v3.1/connected_accounts/complete_auth", {"user_id": uid, "session_uri": session_uri})
        if result.get("toolkit_slug") != "gmail":
            raise BrokerError("The connection is not Gmail", rejected=True)
        account_id = safe_id(result.get("connected_account_id"))
        await self.verify(uid, account_id)
        profile = await self.gmail(uid, account_id, "GET", "profile")
        return account_id, profile["emailAddress"]

    async def disconnect(self, uid, account_id):
        await self.verify(uid, account_id)
        await self.request("DELETE", "/api/v3/connected_accounts/" + safe_id(account_id))

    async def gmail(self, uid, account_id, method, path, body=None, query=None):
        # The endpoint is constructed by this app, never supplied by the client.
        allowed = ((method == "GET" and re.fullmatch(r"profile|messages(?:/[A-Za-z0-9_-]+)?|threads/[A-Za-z0-9_-]+", path))
                   or (method == "POST" and path == "messages/send"))
        if not allowed:
            raise BrokerError("Unsupported Gmail operation", rejected=True)
        try:
            await self.verify(uid, account_id)
        except BrokerError as exc:
            exc.rejected = True  # Verification failed before the provider operation.
            raise
        endpoint = "https://gmail.googleapis.com/gmail/v1/users/me/" + path
        if query:
            endpoint += "?" + urlencode(query)
        response = await self.request("POST", "/api/v3/tools/execute/proxy", {
            "connected_account_id": account_id, "user_id": uid, "endpoint": endpoint, "method": method, **({"body": body} if body is not None else {}),
        })
        status = response.get("status")
        if not isinstance(status, int) or status < 200 or status >= 300:
            raise BrokerError("Gmail did not confirm the request", rejected=isinstance(status, int) and 400 <= status < 500)
        data = response.get("data")
        if not isinstance(data, dict):
            raise BrokerError("Gmail returned an unexpected response")
        return data
