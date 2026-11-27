"""Dashboards (plan section 6, Day 9): the Pipeline funnel and Live Ops in one read.

Pipeline: cases found, tailored, applied, replied and at interview, this week and all time
(imported JobPilot applications count in all time and are shown separately).
Live Ops: what the worker is doing, what failed in the last day (plain words, no secrets),
LLM spend this month against the budget, today's outward sends against the caps, and the
kill switch.
"""
import asyncio
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from app.core import budgets
from app.core.policy import PolicyError, load_policy
from app.db import get_db
from app.services.auth import CurrentUser, get_current_user

router = APIRouter()
_SECRET = re.compile(r"\b(api[_-]?key|token|secret|password)\s*[:=]\s*\S+|\b(bearer)\s+\S+|\b(?:sk|gsk|jpx)_[A-Za-z0-9_-]{8,}", re.I)


def clean_error(text: str | None) -> str:
    """The first line of an error, with anything that looks like a credential replaced."""
    first = (text or "").strip().splitlines()[0] if text and text.strip() else ""
    return _SECRET.sub(lambda m: f"{m.group(1) or m.group(2) or 'key'} [hidden]", first)[:240]


def _funnel(db, user_id: str, since: datetime | None) -> dict:
    row = db.fetch("""select count(*),
                             count(*) filter (where exists (select 1 from public.artifact a where a.case_id = c.id
                                                            and a.kind = 'resume_version')),
                             count(*) filter (where c.applied_at is not null or c.stage in ('applied','replied','interview','offer')),
                             count(*) filter (where c.stage in ('replied','interview','offer')),
                             count(*) filter (where c.stage in ('interview','offer')),
                             count(*) filter (where c.legacy)
                      from public.job_case c where c.user_id = %s::uuid
                      and (%s::timestamptz is null or (c.created_at >= %s and not c.legacy))""",
                   [user_id, since, since])[0]
    return dict(zip(("found", "tailored", "applied", "replied", "interviews", "imported"), row))


def summary(user_id: str) -> dict:
    db = get_db(user_id)
    try:
        policy = load_policy()
    except PolicyError:
        policy = None
    now = datetime.now(timezone.utc)
    week = policy.week_start(now) if policy else now - timedelta(days=7)
    today = policy.day_start(now) if policy else now - timedelta(days=1)
    pending = dict(db.fetch("""select kind, count(*) from public.action where user_id = %s::uuid
                               and status = 'reviewed' group by kind""", [user_id]))
    runs = dict(db.fetch("""select status, count(*) from public.agent_runs where user_id = %s::uuid
                            and (status in ('queued','running','retry_wait') or updated_at >= %s) group by status""",
                         [user_id, now - timedelta(days=1)]))
    active = db.fetch("""select id::text, kind, coalesce(inputs->>'agent', kind), case_id::text, status, attempts, updated_at
                         from public.agent_runs where user_id = %s::uuid and status in ('queued','running','retry_wait')
                         order by created_at limit 10""", [user_id])
    failed = db.fetch("""select r.id::text, r.kind, coalesce(r.inputs->>'agent', r.kind), r.case_id::text, c.company, r.last_error, r.updated_at
                         from public.agent_runs r left join public.job_case c on c.id = r.case_id
                         where r.user_id = %s::uuid and r.status = 'failed' and r.updated_at >= %s
                         order by r.updated_at desc limit 10""", [user_id, now - timedelta(days=1)])
    sent = dict(db.fetch("""select kind, count(*) from public.action where user_id = %s::uuid and executing_at >= %s
                            group by kind""", [user_id, today]))
    month = budgets.month_status(user_id, policy=policy) if policy else None
    caps = policy.caps if policy else {}
    return {
        "pipeline": {"week": _funnel(db, user_id, week), "all_time": _funnel(db, user_id, None)},
        "approvals": {"total": sum(pending.values()), "by_kind": pending},
        "ops": {
            "kill_switch": bool(policy and policy.kill_switch),
            "quiet_hours": bool(policy and policy.in_quiet_hours(now)),
            "runs_last_day": runs,
            "active": [dict(zip(("id", "kind", "agent", "case_id", "status", "attempts", "updated_at"), r)) for r in active],
            "failed": [{**dict(zip(("id", "kind", "agent", "case_id", "company", "error", "updated_at"), r)),
                        "error": clean_error(r[5])} for r in failed],
            "budget": {"usd_used": round(month.used["usd"], 4), "usd_limit": month.limits["usd"]} if month else None,
            "sent_today": {
                "emails": [sent.get("send_email", 0), caps.get("emails_per_day")],
                "invites": [sent.get("send_linkedin_invite", 0), caps.get("linkedin_invites_per_day")],
                "dms": [sent.get("send_linkedin_dm", 0), caps.get("linkedin_dms_per_day")],
            },
        },
    }


@router.get("")
async def dashboard(user: CurrentUser = Depends(get_current_user)):
    return await asyncio.to_thread(summary, user.id)
