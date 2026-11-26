"""Work emails Recon may use. Never guessed from a name pattern.

1. Addresses printed in the job description (source: job_description). A personal address
   is matched to a person Recon found when its local part spells their name; a team
   mailbox (careers@, jobs@, talent@, …) becomes a "hiring mailbox" contact.
2. Hunter's Email Finder, only when HUNTER_API_KEY is set, and only results Hunter itself
   verified as `valid` on the company's own domain (source: hunter).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.recon.people import core_company

_EMAIL = re.compile(r"(?<![\w.+-])([A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,24})(?![\w-])")
NO_REPLY = re.compile(r"^(no-?reply|do-?not-?reply|mailer-daemon|postmaster|bounce|notifications?)\b", re.I)
TEAM = re.compile(r"^(careers?|jobs?|talent|recruit(?:ing|ment|er)?|hr|hiring|people|apply|join|work|team|hello|contact)"
                  r"(?:[._-]?(?:india|in|us|team|ops))?$", re.I)
WEBMAIL = {"gmail.com", "googlemail.com", "yahoo.com", "outlook.com", "hotmail.com", "live.com", "icloud.com",
           "proton.me", "protonmail.com", "aol.com", "rediffmail.com", "yandex.com", "zoho.com"}
JOB_BOARDS = ("greenhouse.io", "lever.co", "ashbyhq.com", "workable.com", "myworkdayjobs.com", "workday.com",
              "smartrecruiters.com", "linkedin.com", "indeed.", "naukri.com", "wellfound.com", "angel.co",
              "instahyre.com", "glassdoor.", "bamboohr.com", "recruitee.com", "breezy.hr", "jobvite.com",
              "icims.com", "teamtailor.com", "keka.com", "darwinbox", "freshteam.com", "ycombinator.com",
              "cutshort.io", "hirist.", "iimjobs.", "foundit.", "monster.", "google.com")


@dataclass
class FoundEmail:
    email: str
    kind: str              # 'person' | 'team'
    source: str            # 'job_description' | 'hunter'


def in_text(text: str) -> list[FoundEmail]:
    out, seen = [], set()
    for raw in _EMAIL.findall(text or ""):
        email = raw.strip(".").lower()
        local, _, domain = email.partition("@")
        if email in seen or NO_REPLY.match(local) or domain.endswith((".png", ".jpg", ".gif", ".svg", ".webp")):
            continue
        seen.add(email)
        out.append(FoundEmail(email, "team" if TEAM.match(local) else "person", "job_description"))
    return out


def name_matches(local: str, name: str) -> bool:
    """first.last, firstlast, first_last, flast, first.l, first: the address spells this name."""
    parts = [p for p in re.split(r"[\s.\-']+", (name or "").lower()) if p.isalpha()]
    if not parts:
        return False
    first, last = parts[0], parts[-1] if len(parts) > 1 else ""
    local = local.lower()
    options = {first}
    if last:
        options |= {f"{first}.{last}", f"{first}{last}", f"{first}_{last}", f"{first}-{last}", f"{first[0]}{last}",
                    f"{first[0]}.{last}", f"{first}.{last[0]}", f"{first}{last[0]}", f"{last}.{first}", f"{last}{first}"}
    return local in options


def company_domain(company: str, *, emails: list[FoundEmail], urls: list[str]) -> str | None:
    """The company's own domain, from evidence only: an address in the JD, or a source URL
    whose host spells the company (never a job board or webmail)."""
    core = core_company(company).replace(" ", "")
    for found in emails:
        domain = found.email.split("@")[1]
        if domain not in WEBMAIL and core and core in domain.replace("-", "").replace(".", ""):
            return domain
    for url in urls:
        hostname = urlparse(url or "").hostname or ""
        hostname = hostname.removeprefix("www.").removeprefix("careers.").removeprefix("jobs.")
        if not hostname or any(b in hostname for b in JOB_BOARDS):
            continue
        if core and hostname.split(".")[0].replace("-", "") == core:
            return hostname
    return None


def hunter_configured() -> bool:
    key = settings.HUNTER_API_KEY.strip()
    return bool(key) and not key.lower().startswith(("your", "xxx", "changeme"))


async def hunter_find(domain: str, name: str, client: httpx.AsyncClient | None = None) -> str | None:
    """Hunter Email Finder for one person; only a Hunter-verified `valid` address on `domain`."""
    if not hunter_configured():
        return None
    parts = name.replace(".", " ").split()
    if len(parts) < 2:
        return None
    own = client is None
    client = client or httpx.AsyncClient(timeout=20, trust_env=False, follow_redirects=False)
    try:
        response = await client.get("https://api.hunter.io/v2/email-finder",
                                    params={"domain": domain, "first_name": parts[0], "last_name": parts[-1]},
                                    headers={"X-API-KEY": settings.HUNTER_API_KEY.strip()})
        if response.status_code != 200:
            return None
        data = response.json().get("data") or {}
    except (httpx.HTTPError, ValueError):
        return None
    finally:
        if own:
            await client.aclose()
    email = (data.get("email") or "").lower()
    status = ((data.get("verification") or {}).get("status") or "").lower()
    if not email or status != "valid" or email.split("@")[-1] != domain.lower():
        return None
    return email
