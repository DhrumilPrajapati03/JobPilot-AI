"""Job discovery: scan followed job boards, score postings, auto-draft the best.

A scan fetches every followed board, drops postings whose title doesn't fit
the user's target roles, scores the rest locally (see ``job_matching``) and
stores them. Postings that break a skip rule are stored as ``skipped`` so the
user can see why. If auto-draft is on, the top new matches above the user's
threshold go through the normal application pipeline, up to a daily cap.

Scans run when the user asks, when the app opens and the last scan is stale,
and nightly on the server when a service key is set (see ``autopilot``).
"""

import asyncio
import re
import uuid
from datetime import datetime, timedelta, timezone

import httpx

from app.agents.orchestrator import run_agent_pipeline
from app.config import settings
from app.models.user import WorkPreferences
from app.services.job_boards import HEADERS, REMOTE_BOARDS, TIMEOUT, BoardError, FetchOptions, fetch_board
from app.services.job_filters import evaluate_skip_rules, india_eligibility_flag
from app.services.job_matching import (
    MIN_TITLE_MATCH,
    build_profile,
    location_flag,
    region_flag,
    score_posting,
    title_match,
    user_country,
)
from app.services.referrals import contact_counts
from app.services.websocket import manager

MIGRATION_FILE = "supabase/migrations/20261011_job_discovery.sql"
STALE_AFTER = timedelta(hours=20)
BRIEFING_WINDOW = timedelta(hours=24)
FETCH_CONCURRENCY = 4
CHUNK = 100

# Descriptions are needed to enforce eligibility on previously stored postings.
POSTING_FIELDS = (
    "id, source_id, ats, external_id, company, title, location, remote, url, posted_at, fit_score, title_match, "
    "matched_skills, missing_skills, skip_flags, status, application_id, auto_drafted, drafted_at, closed_at, discovered_at, description"
)

_scanning: set[str] = set()
# Keep references so fire-and-forget draft tasks aren't garbage collected.
_background_tasks: set[asyncio.Task] = set()


class DiscoveryError(Exception):
    """A scan can't run; the message is safe to show the user."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value) -> datetime | None:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def is_table_missing(error: Exception) -> bool:
    message = str(error)
    return "PGRST205" in message or (("job_postings" in message or "job_sources" in message) and "does not exist" in message)


def _job_key(company: str, title: str) -> tuple[str, str]:
    """Same company + same title: the same job, wherever it was found."""
    def norm(s: str) -> str:
        return " ".join(re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split())
    return norm(company), norm(title)


def _chunks(items: list, size: int = CHUNK):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _spawn(coro):
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def load_preferences(supabase, user_id: str) -> WorkPreferences:
    res = supabase.table("user_profiles").select("work_preferences").eq("id", user_id).execute()
    raw = (res.data[0].get("work_preferences") if res.data else None) or {}
    try:
        return WorkPreferences.model_validate(raw)
    except Exception:
        return WorkPreferences()


def _load_location(supabase, user_id: str) -> str:
    res = supabase.table("user_profiles").select("location").eq("id", user_id).execute()
    return (res.data[0].get("location") if res.data else "") or ""


def _evaluate(prefs, profile, country, *, ats, company, title, description, location, remote):
    """Fit and skip flags for one posting (new or already stored)."""
    fit = score_posting(title, description, profile)
    flags = evaluate_skip_rules(prefs, company, description, {"remote": remote})
    if loc := location_flag(prefs, location, remote):
        flags.append(loc)
    if ats in REMOTE_BOARDS and (region := region_flag(location, "India")):
        flags.append(region)
    if eligibility := india_eligibility_flag({"location": location, "remote": remote, "description": description}):
        flags.append(eligibility)
    return fit, flags


def _rescore_stored(supabase, user_id: str, prefs, profile, country, skip_ids: set) -> dict:
    """Re-apply current preferences and scoring to stored open postings."""
    rows = supabase.table("job_postings").select(
        "id, ats, external_id, company, title, location, remote, description, status, fit_score, skip_flags"
    ).eq("user_id", user_id).in_("status", ["new", "skipped"]).execute().data
    changed, dropped = [], []
    for r in rows:
        if r["id"] in skip_ids:
            continue
        if profile.role_terms and title_match(r["title"], profile) < MIN_TITLE_MATCH:
            dropped.append(r["id"])  # no longer a target role; found again if roles change back
            continue
        fit, flags = _evaluate(
            prefs, profile, country, ats=r["ats"], company=r["company"], title=r["title"],
            description=r.get("description") or "", location=r.get("location") or "", remote=r.get("remote"),
        )
        status = "skipped" if flags else "new"
        if abs(float(r.get("fit_score") or 0) - fit.score) > 0.05 or flags != (r.get("skip_flags") or []) or status != r["status"]:
            changed.append({
                "user_id": user_id, "ats": r["ats"], "external_id": r["external_id"], "fit_score": fit.score,
                "title_match": fit.title_match, "matched_skills": fit.matched[:12], "missing_skills": fit.missing[:12],
                "skip_flags": flags, "status": status,
            })
    for chunk in _chunks(changed):
        supabase.table("job_postings").upsert(chunk, on_conflict="user_id,ats,external_id").execute()
    for chunk in _chunks(dropped):
        supabase.table("job_postings").delete().in_("id", chunk).eq("user_id", user_id).execute()
    return {"rescored": len(changed), "dropped": len(dropped)}


def _load_base_resume(supabase, user_id: str) -> dict | None:
    res = supabase.table("resumes").select("*").eq("user_id", user_id).eq("version", "base").execute()
    return res.data[0] if res.data else None


def _posting_row(user_id: str, source: dict, posting, fit, flags: list[str]) -> dict:
    return {
        "user_id": user_id,
        "source_id": source["id"],
        "ats": posting.ats,
        "external_id": posting.external_id,
        # Remote boards list many companies; company boards list one.
        "company": posting.company if posting.ats in REMOTE_BOARDS else source.get("company") or posting.company,
        "title": posting.title,
        "location": posting.location,
        "remote": posting.remote,
        "url": posting.url,
        "description": posting.description,
        "posted_at": posting.posted_at,
        "fit_score": fit.score,
        "title_match": fit.title_match,
        "matched_skills": fit.matched[:12],
        "missing_skills": fit.missing[:12],
        "skip_flags": flags,
        "status": "skipped" if flags else "new",
        "discovered_at": _now().isoformat(),
    }


async def scan_user(
    supabase,
    user_id: str,
    *,
    user_token: str = "",
    user_email: str = "",
    auto_draft: bool = True,
    source_ids: list[str] | None = None,
) -> dict:
    """Scan the user's followed boards. Returns a summary of what changed."""
    if user_id in _scanning:
        return {"status": "already_running"}
    _scanning.add(user_id)
    try:
        return await _scan(supabase, user_id, user_token, user_email, auto_draft, source_ids)
    finally:
        _scanning.discard(user_id)


async def _scan(supabase, user_id, user_token, user_email, auto_draft, source_ids) -> dict:
    query = supabase.table("job_sources").select("*").eq("user_id", user_id).eq("enabled", True)
    sources = query.execute().data
    if source_ids is not None:
        sources = [s for s in sources if s["id"] in source_ids]
    summary = {
        "status": "done", "sources": len(sources), "fetched": 0, "new": 0, "new_matches": 0,
        "skipped": 0, "filtered": 0, "closed": 0, "duplicates": 0, "errors": [], "auto_drafting": [],
        "scanned_at": _now().isoformat(),
    }
    if not sources:
        return summary

    prefs = load_preferences(supabase, user_id)
    base_resume = _load_base_resume(supabase, user_id)
    if not base_resume:
        raise DiscoveryError("Add your base resume on the Profile page first. Matches are scored against it.")
    profile = build_profile(base_resume, prefs)
    country = user_country(_load_location(supabase, user_id))

    known_rows = supabase.table("job_postings").select(
        "id, ats, external_id, source_id, status, closed_at, company, title"
    ).eq("user_id", user_id).execute().data
    known = {(r["ats"], r["external_id"]): r for r in known_rows}
    # The source each job was first stored from, so a job listed on two boards
    # (say Himalayas and the company's own board) appears once.
    job_sources = {_job_key(r.get("company") or "", r.get("title") or ""): r.get("source_id") for r in known_rows}

    def worth_details(ats: str):
        def keep(title: str, external_id: str) -> bool:
            if (ats, external_id) in known:
                return False
            return not profile.role_terms or title_match(title, profile) >= MIN_TITLE_MATCH
        return keep

    semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
        async def fetch(source):
            opts = FetchOptions(keep=worth_details(source["ats"]), queries=profile.roles, country="India")
            async with semaphore:
                try:
                    return source, await fetch_board(source["ats"], source["slug"], client, opts), None
                except BoardError as e:
                    return source, None, str(e)
                except Exception as e:  # malformed board data shouldn't fail the whole scan
                    return source, None, f"Couldn't read this board ({type(e).__name__})."

        results = await asyncio.gather(*(fetch(s) for s in sources))

    now = _now().isoformat()
    new_rows, reopen, closing = [], [], []

    for source, fetched, error in results:
        source_update = {"last_scanned_at": now, "last_error": error}
        if fetched is None:
            summary["errors"].append({"source_id": source["id"], "company": source.get("company") or source["slug"], "error": error})
            supabase.table("job_sources").update(source_update).eq("id", source["id"]).eq("user_id", user_id).execute()
            continue

        company, postings = fetched
        summary["fetched"] += len(postings)
        source_update["job_count"] = len(postings)
        if not source.get("company"):
            source_update["company"] = source["company"] = company
        seen = set()
        for posting in postings:
            if not posting.external_id or not posting.title:
                continue
            seen.add(posting.external_id)
            row = known.get((posting.ats, posting.external_id))
            if row:
                if row.get("closed_at"):
                    reopen.append(row["id"])
                continue
            if profile.role_terms and title_match(posting.title, profile) < MIN_TITLE_MATCH:
                summary["filtered"] += 1
                continue
            row_company = posting.company if posting.ats in REMOTE_BOARDS else source.get("company") or posting.company
            job_key = _job_key(row_company, posting.title)
            if job_sources.get(job_key, source["id"]) != source["id"]:
                summary["duplicates"] += 1
                continue
            job_sources[job_key] = source["id"]
            fit, flags = _evaluate(
                prefs, profile, country, ats=posting.ats, company=posting.company, title=posting.title,
                description=posting.description, location=posting.location, remote=posting.remote,
            )
            new_rows.append(_posting_row(user_id, source, posting, fit, flags))
            known[(posting.ats, posting.external_id)] = {"id": None, "source_id": source["id"], "status": "new"}

        # Remote boards are searched, not listed in full, so absence doesn't mean closed.
        for row in [] if source["ats"] in REMOTE_BOARDS else known_rows:
            if (
                row.get("source_id") == source["id"] and row["external_id"] not in seen
                and not row.get("closed_at") and row["status"] in ("new", "skipped")
            ):
                closing.append(row["id"])
        supabase.table("job_sources").update(source_update).eq("id", source["id"]).eq("user_id", user_id).execute()

    # Preferences or scoring may have changed since stored postings were scored.
    summary.update(_rescore_stored(supabase, user_id, prefs, profile, country, skip_ids=set()))
    for chunk in _chunks(new_rows):
        supabase.table("job_postings").insert(chunk).execute()
    for chunk in _chunks(reopen):
        supabase.table("job_postings").update({"closed_at": None}).in_("id", chunk).eq("user_id", user_id).execute()
    for chunk in _chunks(closing):
        supabase.table("job_postings").update({"closed_at": now}).in_("id", chunk).eq("user_id", user_id).execute()

    summary["new"] = sum(1 for r in new_rows if r["status"] == "new")
    summary["new_matches"] = sum(1 for r in new_rows if r["status"] == "new" and r["fit_score"] >= prefs.min_match_score)
    summary["skipped"] = sum(1 for r in new_rows if r["status"] == "skipped")
    summary["closed"] = len(closing)

    if auto_draft and prefs.auto_draft_enabled:
        summary["auto_drafting"] = start_auto_drafts(supabase, user_id, prefs, user_token=user_token, user_email=user_email)
    return summary


def drafts_today(supabase, user_id: str) -> int:
    """Auto-drafts started since midnight UTC (in progress or finished)."""
    midnight = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = supabase.table("job_postings").select("drafted_at, auto_drafted").eq("user_id", user_id).eq("auto_drafted", True).execute().data
    return sum(1 for r in rows if (ts := _parse_ts(r.get("drafted_at"))) and ts >= midnight)


def start_auto_drafts(supabase, user_id: str, prefs: WorkPreferences, *, user_token: str = "", user_email: str = "") -> list[dict]:
    """Queue drafts for the best new matches, within today's remaining cap."""
    remaining = prefs.auto_draft_daily_cap - drafts_today(supabase, user_id)
    if remaining <= 0:
        return []
    rows = supabase.table("job_postings").select(POSTING_FIELDS).eq("user_id", user_id).eq("status", "new").execute().data
    candidates = sorted(
        (r for r in rows if not r.get("closed_at") and not india_eligibility_flag(r) and float(r.get("fit_score") or 0) >= prefs.auto_draft_min_score),
        key=lambda r: float(r.get("fit_score") or 0),
        reverse=True,
    )[:remaining]
    queued = [begin_draft(supabase, user_id, r, auto=True) for r in candidates]
    if queued:
        _spawn(_run_drafts(supabase, user_id, queued, user_token, user_email))
    return [{k: q[k] for k in ("posting_id", "run_id", "title", "company")} for q in queued]


def begin_draft(supabase, user_id: str, posting: dict, *, auto: bool) -> dict:
    """Mark a posting as drafting and reserve a pipeline run id for it."""
    if reason := india_eligibility_flag(posting):
        raise DiscoveryError(reason)
    run_id = str(uuid.uuid4())
    manager.register(run_id, user_id)
    supabase.table("job_postings").update({
        "status": "drafting", "drafted_at": _now().isoformat(), "auto_drafted": auto,
    }).eq("id", posting["id"]).eq("user_id", user_id).execute()
    return {"posting_id": posting["id"], "run_id": run_id, "title": posting.get("title"), "company": posting.get("company")}


async def _run_drafts(supabase, user_id: str, queued: list[dict], user_token: str, user_email: str):
    # One at a time: each run makes several LLM calls and free tiers rate-limit bursts.
    for item in queued:
        await draft_posting(supabase, user_id, item["posting_id"], item["run_id"], user_token=user_token, user_email=user_email)


def start_manual_draft(supabase, user_id: str, posting: dict, *, user_token: str, user_email: str) -> dict:
    queued = begin_draft(supabase, user_id, posting, auto=False)
    _spawn(draft_posting(supabase, user_id, posting["id"], queued["run_id"], user_token=user_token, user_email=user_email))
    return queued


async def draft_posting(supabase, user_id: str, posting_id: str, run_id: str, *, user_token: str = "", user_email: str = "") -> str | None:
    """Run the application pipeline for a stored posting and link the result."""
    res = supabase.table("job_postings").select("*").eq("id", posting_id).eq("user_id", user_id).execute()
    if not res.data:
        return None
    p = res.data[0]
    if reason := india_eligibility_flag(p):
        supabase.table("job_postings").update({"status": "skipped", "skip_flags": [reason]}).eq("id", posting_id).eq("user_id", user_id).execute()
        await manager.send_update(run_id, {"type": "status", "step": "complete", "status": "error", "message": reason})
        return None
    where = p.get("location") or ""
    if p.get("remote"):
        where = f"{where} (remote)" if where else "Remote"
    jd_text = f"{p['title']} at {p['company']}\nLocation: {where or 'Not stated'}\n\n{p.get('description') or ''}"
    application_id = None
    try:
        application_id = await run_agent_pipeline(
            run_id, user_id, user_token, p.get("url") or None, jd_text, user_email,
            source=p.get("ats") or "discovery", supabase=supabase,
        )
    except Exception as e:
        print(f"Draft for posting {posting_id} failed: {e}")
    update = (
        {"status": "drafted", "application_id": application_id}
        if application_id
        else {"status": "new", "drafted_at": None, "auto_drafted": False}
    )
    supabase.table("job_postings").update(update).eq("id", posting_id).eq("user_id", user_id).execute()
    return application_id


def server_scans_enabled() -> bool:
    """Nightly scans run on the server (see services.autopilot)."""
    return bool(settings.DISCOVERY_AUTO_SCAN and settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY)


def compact_posting(r: dict) -> dict:
    return {k: r.get(k) for k in (
        "id", "ats", "title", "company", "location", "remote", "url", "fit_score", "matched_skills",
        "missing_skills", "status", "application_id", "discovered_at", "posted_at",
    )}


def build_briefing(supabase, user_id: str, prefs: WorkPreferences) -> dict:
    """What changed since yesterday: new matches, drafts to review, follow-ups due."""
    now = _now()
    since = now - BRIEFING_WINDOW
    sources = supabase.table("job_sources").select("id, company, enabled, last_scanned_at, last_error").eq("user_id", user_id).execute().data
    postings = supabase.table("job_postings").select(POSTING_FIELDS).eq("user_id", user_id).execute().data

    scans = [ts for s in sources if s.get("enabled") and (ts := _parse_ts(s.get("last_scanned_at")))]
    last_scan = max(scans) if scans else None
    enabled = [s for s in sources if s.get("enabled")]
    stale = bool(enabled) and (len(scans) < len(enabled) or last_scan is None or now - min(scans) > STALE_AFTER)

    def fit(r):
        return float(r.get("fit_score") or 0)

    open_matches = sorted(
        (r for r in postings if r["status"] == "new" and not r.get("closed_at") and not india_eligibility_flag(r) and fit(r) >= prefs.min_match_score),
        key=fit, reverse=True,
    )
    fresh = [r for r in open_matches if (ts := _parse_ts(r.get("discovered_at"))) and ts >= since]
    drafts = [
        r for r in postings
        if r["status"] in ("drafting", "drafted") and not india_eligibility_flag(r) and (ts := _parse_ts(r.get("drafted_at"))) and ts >= since
    ]

    apps = supabase.table("job_applications").select("id, role, company, status, follow_up_at").eq("user_id", user_id).eq("status", "applied").execute().data
    follow_ups = sorted(
        (a for a in apps if (ts := _parse_ts(a.get("follow_up_at"))) and ts <= now),
        key=lambda a: a["follow_up_at"],
    )

    top = (fresh or open_matches)[:3]
    contacts = contact_counts(supabase, user_id, [r["company"] for r in top])
    return {
        "generated_at": now.isoformat(),
        "sources": len(enabled),
        "last_scan_at": last_scan.isoformat() if last_scan else None,
        "stale": stale,
        "server_scans": server_scans_enabled(),
        "min_match_score": prefs.min_match_score,
        "new_matches": len(fresh),
        "open_matches": len(open_matches),
        "top_matches": [{**compact_posting(r), "referral_count": contacts.get(r["company"], 0)} for r in top],
        "drafts": [compact_posting(r) for r in sorted(drafts, key=lambda r: r.get("drafted_at") or "", reverse=True)[:5]],
        "follow_ups_due": [{k: a.get(k) for k in ("id", "role", "company", "follow_up_at")} for a in follow_ups[:5]],
        "auto_draft": {
            "enabled": prefs.auto_draft_enabled,
            "min_score": prefs.auto_draft_min_score,
            "daily_cap": prefs.auto_draft_daily_cap,
            "remaining_today": max(0, prefs.auto_draft_daily_cap - drafts_today(supabase, user_id)),
        },
    }
