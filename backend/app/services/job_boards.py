"""Clients for public job boards.

Company boards: Greenhouse, Lever, Ashby and SmartRecruiters publish a
company's open roles through unauthenticated JSON APIs. Remote job boards:
Himalayas and Remotive publish remote roles from many companies, searched by
the user's target roles. No API keys are needed and nobody's site is scraped.

Remote boards ask for attribution (a link back and a "via" credit, which the
feed shows) and for infrequent polling, so their results are cached for hours.
"""

import asyncio
import html
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

ATS_NAMES = {
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
    "smartrecruiters": "SmartRecruiters",
    "himalayas": "Himalayas",
    "remotive": "Remotive",
}
# Boards that list many companies' remote jobs, searched by the user's roles rather than read in full.
REMOTE_BOARDS = {"himalayas", "remotive"}
REMOTE_BOARD_SLUG = "remote"
REMOTE_BOARD_HOME = {"himalayas": "https://himalayas.app", "remotive": "https://remotive.com"}
REMOTE_CACHE_SECONDS = 6 * 3600
MAX_QUERIES = 3
MAX_DESCRIPTION_CHARS = 20_000
TIMEOUT = httpx.Timeout(25.0, connect=10.0)
HEADERS = {"User-Agent": "JobPilotAI/1.0 (job discovery)"}

# (ats, pattern) — the first group is the board's slug.
_BOARD_PATTERNS = [
    ("greenhouse", r"boards-api\.greenhouse\.io/v1/boards/([\w-]+)"),
    ("greenhouse", r"greenhouse\.io/embed/job_board(?:/js)?\?for=([\w-]+)"),
    ("greenhouse", r"(?:job-)?boards(?:\.eu)?\.greenhouse\.io/([\w-]+)"),
    ("lever", r"api\.lever\.co/v0/postings/([\w.-]+)"),
    ("lever", r"jobs\.lever\.co/([\w.-]+)"),
    ("ashby", r"api\.ashbyhq\.com/posting-api/job-board/([\w.-]+)"),
    ("ashby", r"jobs\.ashbyhq\.com/([\w.%-]+)"),
    ("smartrecruiters", r"api\.smartrecruiters\.com/v1/companies/([\w.-]+)"),
    ("smartrecruiters", r"(?:careers|jobs)\.smartrecruiters\.com/([\w.-]+)"),
]
_REMOTE_PATTERNS = [("himalayas", r"himalayas\.app"), ("remotive", r"remotive\.(?:com|io)")]


class BoardError(Exception):
    """A board couldn't be read; the message is safe to show the user."""


@dataclass
class Posting:
    ats: str
    external_id: str
    company: str
    title: str
    location: str
    remote: bool | None
    url: str
    description: str
    posted_at: str | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FetchOptions:
    """What the caller wants from a board beyond its raw listing.

    ``keep(title, external_id)`` says whether a posting is worth its full
    description; boards that list postings without descriptions (SmartRecruiters)
    only fetch details for kept ones. ``queries`` and ``country`` drive remote board searches.
    """
    keep: Callable[[str, str], bool] | None = None
    queries: list[str] = field(default_factory=list)
    country: str | None = None


def parse_board(value: str, ats: str | None = None) -> tuple[str, str]:
    """Turn a careers-page URL (or a bare slug plus ``ats``) into ``(ats, slug)``."""
    value = (value or "").strip()
    if ats in REMOTE_BOARDS:
        return ats, REMOTE_BOARD_SLUG
    for name, pattern in _REMOTE_PATTERNS:
        if ats is None and re.search(pattern, value, re.IGNORECASE):
            return name, REMOTE_BOARD_SLUG
    for name, pattern in _BOARD_PATTERNS:
        if (ats is None or ats == name) and (m := re.search(pattern, value, re.IGNORECASE)):
            return name, m.group(1).lower()
    if ats in ATS_NAMES and re.fullmatch(r"[\w.-]+", value):
        return ats, value.lower()
    raise BoardError(
        "That isn't a job board JobPilot can read. Paste a link like boards.greenhouse.io/stripe, "
        "jobs.lever.co/paytm, jobs.ashbyhq.com/sarvam or careers.smartrecruiters.com/swiggy. "
        "Companies with their own careers site (for example Zomato and Blinkit) don't publish a public feed."
    )


def _company_from_slug(slug: str) -> str:
    return " ".join(part.capitalize() for part in re.split(r"[-_.]+", slug) if part)


_BLOCK_TAGS = ["p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "blockquote"]


def _html_to_text(markup: str) -> str:
    soup = BeautifulSoup(markup or "", "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for tag in soup.find_all(_BLOCK_TAGS):
        if tag.name == "li":
            tag.insert_before("• ")
        tag.insert_after("\n")
    text = soup.get_text()
    text = re.sub(r"[ \t\xa0]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _iso_from_ms(ms) -> str | None:
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _remote_from_text(*parts: str) -> bool | None:
    text = " ".join(p for p in parts if p).lower()
    return True if re.search(r"\bremote\b|\banywhere\b", text) else None


async def _get_json(client: httpx.AsyncClient, url: str, ats: str, slug: str):
    try:
        res = await client.get(url)
    except httpx.HTTPError as e:
        raise BoardError(f"Couldn't reach {ATS_NAMES[ats]} ({type(e).__name__}). Try again later.") from e
    if res.status_code == 404:
        raise BoardError(f"There's no {ATS_NAMES[ats]} job board called '{slug}'.")
    if res.status_code >= 400:
        raise BoardError(f"{ATS_NAMES[ats]} returned an error ({res.status_code}).")
    return res.json()


async def _greenhouse(client: httpx.AsyncClient, slug: str, _opts: FetchOptions) -> tuple[str, list[Posting]]:
    base = f"https://boards-api.greenhouse.io/v1/boards/{slug}"
    data = await _get_json(client, f"{base}/jobs?content=true", "greenhouse", slug)
    try:
        company = (await _get_json(client, base, "greenhouse", slug)).get("name") or ""
    except BoardError:
        company = ""
    postings = []
    for job in data.get("jobs") or []:
        location = (job.get("location") or {}).get("name") or ""
        name = job.get("company_name") or company or _company_from_slug(slug)
        postings.append(Posting(
            ats="greenhouse",
            external_id=str(job.get("id")),
            company=name,
            title=(job.get("title") or "").strip(),
            location=location,
            remote=_remote_from_text(location),
            url=job.get("absolute_url") or "",
            description=_html_to_text(html.unescape(job.get("content") or ""))[:MAX_DESCRIPTION_CHARS],
            posted_at=job.get("first_published") or job.get("updated_at"),
        ))
    return company or (postings[0].company if postings else _company_from_slug(slug)), postings


async def _lever(client: httpx.AsyncClient, slug: str, _opts: FetchOptions) -> tuple[str, list[Posting]]:
    data = await _get_json(client, f"https://api.lever.co/v0/postings/{slug}?mode=json", "lever", slug)
    company = _company_from_slug(slug)
    postings = []
    for job in data if isinstance(data, list) else []:
        cats = job.get("categories") or {}
        locations = cats.get("allLocations") or ([cats["location"]] if cats.get("location") else [])
        workplace = (job.get("workplaceType") or "").lower()
        remote = True if workplace == "remote" else False if workplace in ("onsite", "on-site", "hybrid") else _remote_from_text(*locations)
        sections = [job.get("descriptionPlain") or ""]
        for block in job.get("lists") or []:
            sections.append(f"{block.get('text', '')}\n{_html_to_text(block.get('content') or '')}")
        sections.append(job.get("additionalPlain") or "")
        postings.append(Posting(
            ats="lever",
            external_id=str(job.get("id")),
            company=company,
            title=(job.get("text") or "").strip(),
            location=", ".join(locations),
            remote=remote,
            url=job.get("hostedUrl") or "",
            description="\n\n".join(s.strip() for s in sections if s and s.strip())[:MAX_DESCRIPTION_CHARS],
            posted_at=_iso_from_ms(job.get("createdAt")),
        ))
    return company, postings


async def _ashby(client: httpx.AsyncClient, slug: str, _opts: FetchOptions) -> tuple[str, list[Posting]]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
    data = await _get_json(client, url, "ashby", slug)
    company = _company_from_slug(slug)
    postings = []
    for job in data.get("jobs") or []:
        if job.get("isListed") is False:
            continue
        locations = [job.get("location") or ""] + [s.get("location", "") for s in job.get("secondaryLocations") or []]
        workplace = (job.get("workplaceType") or "").lower()
        remote = True if job.get("isRemote") or workplace == "remote" else False if workplace in ("onsite", "hybrid") else None
        description = job.get("descriptionPlain") or _html_to_text(job.get("descriptionHtml") or "")
        pay = (job.get("compensation") or {}).get("scrapeableCompensationSalarySummary")
        if pay:
            description += f"\n\nCompensation: {pay}"
        postings.append(Posting(
            ats="ashby",
            external_id=str(job.get("id")),
            company=company,
            title=(job.get("title") or "").strip(),
            location=", ".join(l for l in locations if l),
            remote=remote,
            url=job.get("jobUrl") or "",
            description=description[:MAX_DESCRIPTION_CHARS],
            posted_at=job.get("publishedAt"),
        ))
    return company, postings


SMARTRECRUITERS_PAGE = 100
SMARTRECRUITERS_MAX = 1000
DETAIL_CONCURRENCY = 6


def _smartrecruiters_text(ad: dict) -> str:
    sections = (ad or {}).get("sections") or {}
    parts = []
    for key in ("jobDescription", "qualifications", "additionalInformation"):
        section = sections.get(key) or {}
        if section.get("text"):
            parts.append(f"{section.get('title') or ''}\n{_html_to_text(section['text'])}".strip())
    return "\n\n".join(parts)


async def _smartrecruiters(client: httpx.AsyncClient, slug: str, opts: FetchOptions) -> tuple[str, list[Posting]]:
    base = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    items: list[dict] = []
    while len(items) < SMARTRECRUITERS_MAX:
        page = await _get_json(client, f"{base}?limit={SMARTRECRUITERS_PAGE}&offset={len(items)}", "smartrecruiters", slug)
        batch = page.get("content") or []
        items.extend(batch)
        if len(batch) < SMARTRECRUITERS_PAGE or len(items) >= (page.get("totalFound") or 0):
            break
    if not items:
        # Unknown companies return an empty list rather than a 404.
        raise BoardError(f"There's no SmartRecruiters job board called '{slug}', or it has no open roles.")

    company = ((items[0].get("company") or {}).get("name") or _company_from_slug(slug)).strip()
    if company.isupper() and len(company) > 4:
        company = company.title()
    postings = []
    for job in items:
        loc = job.get("location") or {}
        identifier = (job.get("company") or {}).get("identifier") or slug
        postings.append(Posting(
            ats="smartrecruiters",
            external_id=str(job.get("id")),
            company=company,
            title=(job.get("name") or "").strip(),
            location=loc.get("fullLocation") or ", ".join(p for p in (loc.get("city"), loc.get("country", "").upper()) if p),
            remote=True if loc.get("remote") else False if loc.get("hybrid") is not None and loc.get("city") else None,
            url=f"https://jobs.smartrecruiters.com/{identifier}/{job.get('id')}",
            description="",
            posted_at=job.get("releasedDate"),
        ))

    # Descriptions need one request per posting, so only fetch the ones the caller keeps.
    semaphore = asyncio.Semaphore(DETAIL_CONCURRENCY)

    async def detail(posting: Posting):
        async with semaphore:
            try:
                data = await _get_json(client, f"{base}/{posting.external_id}", "smartrecruiters", slug)
            except BoardError:
                return
            posting.description = _smartrecruiters_text(data.get("jobAd"))[:MAX_DESCRIPTION_CHARS]
            posting.url = data.get("postingUrl") or posting.url

    wanted = [p for p in postings if opts.keep is None or opts.keep(p.title, p.external_id)]
    await asyncio.gather(*(detail(p) for p in wanted))
    return company, postings


# --- Remote job boards -------------------------------------------------------------

_cache: dict[tuple, tuple[float, list[Posting]]] = {}


async def _cached(key: tuple, load):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < REMOTE_CACHE_SECONDS:
        return [Posting(**p.to_dict()) for p in hit[1]]
    result = await load()
    _cache[key] = (time.time(), result)
    return [Posting(**p.to_dict()) for p in result]


def _ts_to_iso(value) -> str | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value) if value else None
    return datetime.fromtimestamp(number / 1000 if number > 1e11 else number, tz=timezone.utc).isoformat()


async def _himalayas(client: httpx.AsyncClient, _slug: str, opts: FetchOptions) -> tuple[str, list[Posting]]:
    if not opts.queries:
        raise BoardError("Add your target roles in Profile → Preferences so JobPilot knows what to search Himalayas for.")

    async def search(query: str) -> list[Posting]:
        postings = []
        for page in (1, 2, 3):
            params = {"q": query, "page": page, "sort": "recent"}
            if opts.country:
                params["country"] = opts.country
            try:
                res = await client.get("https://himalayas.app/jobs/api/search", params=params)
            except httpx.HTTPError as e:
                raise BoardError(f"Couldn't reach Himalayas ({type(e).__name__}). Try again later.") from e
            if res.status_code == 429:
                break  # rate limited: keep what we have
            if res.status_code >= 400:
                raise BoardError(f"Himalayas returned an error ({res.status_code}).")
            jobs = res.json().get("jobs") or []
            for job in jobs:
                regions = job.get("locationRestrictions") or []
                postings.append(Posting(
                    ats="himalayas",
                    external_id=str(job.get("guid") or job.get("applicationLink")),
                    company=(job.get("companyName") or "").strip(),
                    title=(job.get("title") or "").strip(),
                    location="Remote, " + (", ".join(regions) if regions else "eligibility unknown"),
                    remote=True,
                    url=job.get("applicationLink") or job.get("guid") or "",
                    description=_html_to_text(job.get("description") or job.get("excerpt") or "")[:MAX_DESCRIPTION_CHARS],
                    posted_at=_ts_to_iso(job.get("pubDate")),
                ))
            if len(jobs) < 20:
                break
        return postings

    results: dict[str, Posting] = {}
    for query in opts.queries[:MAX_QUERIES]:
        for p in await _cached(("himalayas", query.lower(), opts.country), lambda q=query: search(q)):
            results.setdefault(p.external_id, p)
    return "Himalayas", list(results.values())


async def _remotive(client: httpx.AsyncClient, _slug: str, opts: FetchOptions) -> tuple[str, list[Posting]]:
    if not opts.queries:
        raise BoardError("Add your target roles in Profile → Preferences so JobPilot knows what to search Remotive for.")

    async def search(query: str) -> list[Posting]:
        try:
            res = await client.get("https://remotive.com/api/remote-jobs", params={"search": query, "limit": 100})
        except httpx.HTTPError as e:
            raise BoardError(f"Couldn't reach Remotive ({type(e).__name__}). Try again later.") from e
        if res.status_code >= 400:
            raise BoardError(f"Remotive returned an error ({res.status_code}).")
        return [
            Posting(
                ats="remotive",
                external_id=str(job.get("id")),
                company=(job.get("company_name") or "").strip(),
                title=(job.get("title") or "").strip(),
                location="Remote, " + (job.get("candidate_required_location") or "worldwide"),
                remote=True,
                url=job.get("url") or "",
                description=(_html_to_text(job.get("description") or "") + (f"\n\nSalary: {job['salary']}" if job.get("salary") else ""))[:MAX_DESCRIPTION_CHARS],
                posted_at=job.get("publication_date"),
            )
            for job in res.json().get("jobs") or []
        ]

    results: dict[str, Posting] = {}
    for query in opts.queries[:MAX_QUERIES]:
        for p in await _cached(("remotive", query.lower()), lambda q=query: search(q)):
            results.setdefault(p.external_id, p)
    return "Remotive", list(results.values())


_FETCHERS = {
    "greenhouse": _greenhouse,
    "lever": _lever,
    "ashby": _ashby,
    "smartrecruiters": _smartrecruiters,
    "himalayas": _himalayas,
    "remotive": _remotive,
}


async def fetch_board(
    ats: str, slug: str, client: httpx.AsyncClient | None = None, opts: FetchOptions | None = None,
) -> tuple[str, list[Posting]]:
    """Fetch a board's open postings. Returns ``(company_name, postings)``."""
    if ats not in _FETCHERS:
        raise BoardError(f"Unsupported job board '{ats}'.")
    opts = opts or FetchOptions()
    if client is not None:
        return await _FETCHERS[ats](client, slug, opts)
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as own:
        return await _FETCHERS[ats](own, slug, opts)
