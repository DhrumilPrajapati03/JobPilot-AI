"""GitHub and X handles from public GitHub profiles (no login, no scraping).

A GitHub account is accepted only when its public profile names the company (the
`company` field, or the bio) and its display name is the person's name. The X handle
comes from that same profile's `twitter_username`, so it is never a lookalike account.
Unauthenticated GitHub API limits are small (search 10/min, 60 requests/hour), so Recon
looks up at most a few people per run and stops quietly when GitHub says to wait.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from app.recon.people import core_company, same_company

API = "https://api.github.com"
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "JobDots-Recon", "X-GitHub-Api-Version": "2022-11-28"}


class RateLimited(RuntimeError):
    pass


@dataclass
class Handles:
    github: str = ""
    x_handle: str = ""
    evidence: str = ""


def _norm(name: str) -> str:
    return " ".join(re.sub(r"[^a-z ]", " ", (name or "").lower()).split())


def profile_matches(profile: dict, name: str, company: str) -> str | None:
    """Plain-words evidence when the profile is this person at this company, else None."""
    if _norm(profile.get("name") or "") != _norm(name):
        return None
    field = (profile.get("company") or "").lstrip("@")
    if field and any(same_company(part, company) for part in re.split(r"[,/|&]| and ", field)):
        return f"GitHub profile lists {field.strip()}"
    bio = profile.get("bio") or ""
    core = core_company(company)
    if core and re.search(rf"(?:@|\bat\s+){re.escape(core)}\b", bio.lower()):
        return "GitHub bio names the company"
    return None


async def lookup(name: str, company: str, client: httpx.AsyncClient | None = None, max_profiles: int = 3) -> Handles | None:
    own = client is None
    client = client or httpx.AsyncClient(timeout=15, trust_env=False, follow_redirects=False, headers=HEADERS)
    try:
        response = await client.get(f"{API}/search/users", params={"q": f'"{name}" in:name type:user', "per_page": max_profiles})
        if response.status_code in (403, 429):
            raise RateLimited("GitHub asked to wait")
        if response.status_code != 200:
            return None
        for item in (response.json().get("items") or [])[:max_profiles]:
            login = item.get("login") or ""
            if not re.fullmatch(r"[A-Za-z0-9-]{1,39}", login):
                continue
            detail = await client.get(f"{API}/users/{login}")
            if detail.status_code in (403, 429):
                raise RateLimited("GitHub asked to wait")
            if detail.status_code != 200:
                continue
            profile = detail.json()
            evidence = profile_matches(profile, name, company)
            if evidence:
                x = (profile.get("twitter_username") or "").strip().lstrip("@")
                return Handles(github=login, x_handle=x if re.fullmatch(r"[A-Za-z0-9_]{1,15}", x) else "", evidence=evidence)
        return None
    except httpx.HTTPError:
        return None
    finally:
        if own:
            await client.aclose()
