"""Supervised autopilot: prepare applications overnight, queue them for the morning.

Nothing here submits an application. Overnight, JobPilot scans boards,
drafts the best matches (see ``discovery``), and prepares each form's answers
where the questions are public (Greenhouse). In the morning the user opens
each application with the Chrome extension, which fills the form, and clicks
Submit themselves.

Scheduling: ``tick`` runs one pass over every user — the board scan two
hours before their digest hour, then the digest — in their own time zone.
It runs in-process every few minutes when a service key is set, and via
``POST /api/v1/autopilot/tick`` from an external cron, so hosts that sleep
when idle (Render's free tier) still wake up for it.
"""

import asyncio
import hashlib
import re
import secrets
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx

from app.config import settings
from app.models.user import WorkPreferences
from app.services import form_answers
from app.services.job_boards import HEADERS, TIMEOUT
from app.services.materials import is_missing_column_error
from app.services.supabase import select_all

TICK_SECONDS = 600
TOKEN_PREFIX = "jpx_"
_tick_lock = asyncio.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _missing_table(error: Exception, *tables: str) -> bool:
    text = str(error)
    return "PGRST205" in text or any(t in text and "does not exist" in text for t in tables)


# --- Apply links ------------------------------------------------------------------------

def apply_url(ats: str | None, url: str, board_slug: str | None = None, external_id: str | None = None) -> str:
    """The page with the application form itself, where the extension can fill it."""
    url = (url or "").strip()
    if ats == "greenhouse" and board_slug and external_id:
        return f"https://job-boards.greenhouse.io/{board_slug}/jobs/{external_id}"
    if ats == "lever" and url and not url.rstrip("/").endswith("/apply"):
        return url.rstrip("/") + "/apply"
    if ats == "ashby" and url and not url.rstrip("/").endswith("/application"):
        return url.rstrip("/") + "/application"
    return url


def _posting_for(supabase, application_id: str, user_id: str) -> tuple[dict | None, str | None]:
    """The discovered posting an application came from, and its board's slug."""
    try:
        rows = supabase.table("job_postings").select("ats, external_id, url, source_id").eq("application_id", application_id).eq("user_id", user_id).execute().data
    except Exception:
        return None, None
    if not rows:
        return None, None
    posting = rows[0]
    slug = None
    if posting.get("source_id"):
        src = supabase.table("job_sources").select("slug").eq("id", posting["source_id"]).execute().data
        slug = src[0]["slug"] if src else None
    return posting, slug


def application_apply_url(supabase, application: dict, user_id: str) -> tuple[str, str | None]:
    posting, slug = _posting_for(supabase, application["id"], user_id)
    if posting:
        return apply_url(posting["ats"], posting.get("url") or application.get("jd_url") or "", slug, posting.get("external_id")), posting["ats"]
    url = application.get("jd_url") or ""
    m = re.search(r"greenhouse\.io/([\w-]+)/jobs/(\d+)", url)
    if m:
        return apply_url("greenhouse", url, m.group(1), m.group(2)), "greenhouse"
    for ats, host in (("lever", "lever.co"), ("ashby", "ashbyhq.com"), ("smartrecruiters", "smartrecruiters.com")):
        if host in url:
            return apply_url(ats, url), ats
    return url, None


# --- Preparing a form ---------------------------------------------------------------------

def load_answers(supabase, user_id: str) -> list[dict]:
    try:
        return supabase.table("qa_answers").select("question, answer, sensitive").eq("user_id", user_id).execute().data
    except Exception:
        return []


def applicant_context(supabase, user_id: str, email: str, application: dict | None) -> form_answers.ApplicantContext:
    profile = (supabase.table("user_profiles").select("*").eq("id", user_id).execute().data or [{}])[0]
    resume = (supabase.table("resumes").select("*").eq("user_id", user_id).eq("version", "base").execute().data or [{}])[0]
    return form_answers.build_context(
        email=email, profile=profile, resume=resume, answers=load_answers(supabase, user_id),
        application=application, prefs=profile.get("work_preferences") or {},
    )


async def _greenhouse_form(apply: str) -> list[form_answers.FormField] | None:
    m = re.search(r"greenhouse\.io/([\w-]+)/jobs/(\d+)", apply)
    if not m:
        return None
    url = f"https://boards-api.greenhouse.io/v1/boards/{m.group(1)}/jobs/{m.group(2)}?questions=true"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS) as client:
            res = await client.get(url)
        if res.status_code != 200:
            return None
        return form_answers.greenhouse_fields(res.json())
    except httpx.HTTPError:
        return None


def save_prepared(supabase, application_id: str, user_id: str, prepared: dict) -> bool:
    try:
        supabase.table("job_applications").update({"prepared_form": prepared}).eq("id", application_id).eq("user_id", user_id).execute()
        return True
    except Exception as e:
        if is_missing_column_error(e):
            return False
        raise


async def prepare_application_form(supabase, user_id: str, application_id: str, email: str = "") -> dict | None:
    """Work out the apply link and, when the questions are public, every answer. Best-effort."""
    rows = supabase.table("job_applications").select("*").eq("id", application_id).eq("user_id", user_id).execute().data
    if not rows:
        return None
    application = rows[0]
    link, ats = application_apply_url(supabase, application, user_id)
    prepared = {"apply_url": link, "ats": ats, "prepared_at": _now().isoformat(), "fields": [], "summary": None}
    fields = await _greenhouse_form(link) if ats == "greenhouse" else None
    if fields:
        ctx = applicant_context(supabase, user_id, email, application)
        answers = await form_answers.answer_fields(fields, ctx)
        prepared["fields"] = [a.to_dict() for a in answers]
        prepared["summary"] = form_answers.summarise(answers)
    else:
        prepared["note"] = "The questions are read from the page when you open it with the JobPilot extension."
    save_prepared(supabase, application_id, user_id, prepared)
    return prepared


# --- The morning queue ------------------------------------------------------------------------

def build_queue(supabase, user_id: str) -> list[dict]:
    """Applications drafted and waiting to be sent, best first."""
    from app.services.referrals import contact_counts

    apps = supabase.table("job_applications").select("*").eq("user_id", user_id).eq("status", "saved").execute().data
    if not apps:
        return []
    ids = [a["id"] for a in apps]
    scores = {
        r["application_id"]: r["keyword_match_score"]
        for r in supabase.table("tailored_resumes").select("application_id, keyword_match_score, version").in_("application_id", ids).order("version").execute().data
    }
    contacts = contact_counts(supabase, user_id, [a["company"] for a in apps])
    queue = []
    for a in apps:
        prepared = a.get("prepared_form") or {}
        queue.append({
            "id": a["id"],
            "role": a["role"],
            "company": a["company"],
            "created_at": a.get("created_at"),
            "source": a.get("source"),
            "match_score": scores.get(a["id"]),
            "apply_url": prepared.get("apply_url") or a.get("jd_url") or "",
            "ats": prepared.get("ats"),
            "summary": prepared.get("summary"),
            "flagged": [f for f in prepared.get("fields") or [] if f.get("flagged")][:12],
            "prepared": bool(prepared),
            "referral_count": contacts.get(a["company"], 0),
            "skip_flags": (a.get("jd_analysis") or {}).get("skip_flags") or [],
        })
    queue.sort(key=lambda q: (q["skip_flags"] != [], -(q["match_score"] or 0), q["created_at"] or ""))
    return queue


# --- Extension tokens ------------------------------------------------------------------------

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


# --- Daily schedule -----------------------------------------------------------------------------

def server_ready() -> bool:
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY)


def account_email(admin, user_id: str) -> str:
    try:
        res = admin.auth.admin.get_user_by_id(user_id)
        return getattr(getattr(res, "user", None), "email", "") or ""
    except Exception:
        return ""


def local_now(prefs: WorkPreferences) -> datetime:
    try:
        tz = ZoneInfo(prefs.timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    return _now().astimezone(tz)


def scan_hour(prefs: WorkPreferences) -> int:
    return max(0, prefs.digest_hour - 2)


def _save_state(admin, user_id: str, **values):
    admin.table("autopilot_state").upsert({"user_id": user_id, **values, "updated_at": _now().isoformat()}, on_conflict="user_id").execute()


async def tick(admin) -> dict:
    """One pass of the daily schedule for every user. Safe to call as often as you like."""
    if _tick_lock.locked():
        return {"status": "already_running"}
    async with _tick_lock:
        return await _tick(admin)


async def _tick(admin) -> dict:
    from app.services import digest, discovery

    report = {"status": "done", "scanned": [], "digests": [], "errors": []}
    try:
        states = {r["user_id"]: r for r in select_all(lambda: admin.table("autopilot_state").select("*").order("user_id"))}
    except Exception as e:
        if _missing_table(e, "autopilot_state"):
            return {"status": "not_set_up", "detail": "Run supabase/migrations/20261014_autopilot.sql in Supabase."}
        raise
    profiles = select_all(lambda: admin.table("user_profiles").select("id, work_preferences").order("id"))
    try:
        followers = {r["user_id"] for r in select_all(lambda: admin.table("job_sources").select("user_id").eq("enabled", True).order("user_id"))}
    except Exception:
        followers = set()

    for p in profiles:
        user_id = p["id"]
        try:
            prefs = WorkPreferences.model_validate(p.get("work_preferences") or {})
        except Exception:
            prefs = WorkPreferences()
        now = local_now(prefs)
        today = now.date().isoformat()
        state = states.get(user_id, {})
        try:
            if user_id in followers and state.get("last_scan_on") != today and now.hour >= scan_hour(prefs):
                email = account_email(admin, user_id)
                summary = await discovery.scan_user(admin, user_id, auto_draft=True, user_email=email)
                _save_state(admin, user_id, last_scan_on=today, last_scan_at=_now().isoformat())
                report["scanned"].append({"user_id": user_id, "new": summary.get("new"), "drafting": len(summary.get("auto_drafting") or [])})
            if prefs.digest_enabled and state.get("last_digest_on") != today and now.hour >= prefs.digest_hour:
                drafting = admin.table("job_postings").select("id").eq("user_id", user_id).eq("status", "drafting").execute().data if user_id in followers else []
                if drafting and now.hour < prefs.digest_hour + 1:
                    continue  # give tonight's drafts up to an hour to finish
                to = prefs.digest_email or account_email(admin, user_id)
                try:
                    await digest.send_digest(admin, user_id, prefs, to)
                    _save_state(admin, user_id, last_digest_on=today, last_digest_at=_now().isoformat(), last_digest_error=None)
                    report["digests"].append(user_id)
                except digest.DigestError as e:
                    _save_state(admin, user_id, last_digest_on=today, last_digest_error=str(e))
                    report["errors"].append({"user_id": user_id, "error": str(e)})
        except Exception as e:  # one user's failure shouldn't stop everyone else's morning
            print(f"Autopilot tick failed for {user_id}: {e}")
            report["errors"].append({"user_id": user_id, "error": f"{type(e).__name__}: {e}"})
    return report


async def scheduler_loop():
    """Runs ``tick`` every few minutes while the server is awake."""
    from app.services.supabase import get_supabase_admin_client

    await asyncio.sleep(30)  # let the app finish starting
    while True:
        try:
            report = await tick(get_supabase_admin_client())
            if report.get("scanned") or report.get("digests") or report.get("errors"):
                print(f"Autopilot: {report}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"Autopilot scheduler error: {e}")
        await asyncio.sleep(TICK_SECONDS)
