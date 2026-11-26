"""Brave Search API client (Web Search), used by Recon. API reference: the brave-web-search skill.

* The key is BRAVE_API_KEY, read by the backend only; it never appears in traces or errors.
* Queries hold company names, roles and people's public names only, never the owner's own
  email address or other personal data.
* 429 and 5xx are retried a couple of times with a short backoff; anything else is a
  SearchError with a plain-words message.
"""
from __future__ import annotations

import asyncio
import html
import re
from dataclasses import dataclass, field

import httpx

from app.config import settings

URL = "https://api.search.brave.com/res/v1/web/search"
LINKEDIN_ONLY = "$discard\n$site=linkedin.com"
_TAG = re.compile(r"<[^>]+>")


class SearchError(RuntimeError):
    pass


class SearchNotConfigured(SearchError):
    pass


@dataclass
class Result:
    url: str
    title: str
    description: str = ""
    extra_snippets: list[str] = field(default_factory=list)


def clean(text: str) -> str:
    """Plain text from a result field: no highlight tags, entities decoded, spaces collapsed."""
    return " ".join(html.unescape(_TAG.sub("", text or "")).split())


def configured() -> bool:
    return bool(settings.BRAVE_API_KEY.strip())


async def web_search(query: str, *, goggles: str | None = None, count: int = 10, country: str = "ALL",
                     extra_snippets: bool = True, client: httpx.AsyncClient | None = None) -> list[Result]:
    if not configured():
        raise SearchNotConfigured("Search isn't configured: add BRAVE_API_KEY to the root .env.")
    params = {"q": query[:400], "count": max(1, min(count, 20)), "country": country, "safesearch": "moderate",
              "text_decorations": "false", "extra_snippets": "true" if extra_snippets else "false"}
    if goggles:
        params["goggles"] = goggles
    headers = {"Accept": "application/json", "X-Subscription-Token": settings.BRAVE_API_KEY.strip()}
    own = client is None
    client = client or httpx.AsyncClient(timeout=20, trust_env=False, follow_redirects=False)
    try:
        for attempt in range(3):
            try:
                response = await client.get(URL, params=params, headers=headers)
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise SearchError(f"Brave Search could not be reached ({type(exc).__name__}).") from None
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            if response.status_code == 200:
                break
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            if response.status_code in (401, 403):
                raise SearchError("Brave Search refused the key (check BRAVE_API_KEY and your plan).")
            if response.status_code == 429:
                raise SearchError("Brave Search rate limit reached; try again later.")
            raise SearchError(f"Brave Search returned HTTP {response.status_code}.")
        data = response.json()
    finally:
        if own:
            await client.aclose()
    results = []
    for item in (data.get("web") or {}).get("results") or []:
        url = item.get("url") or ""
        if not url.startswith("https://"):
            continue
        results.append(Result(url=url, title=clean(item.get("title", "")), description=clean(item.get("description", "")),
                              extra_snippets=[clean(s) for s in (item.get("extra_snippets") or [])[:5]]))
    return results
