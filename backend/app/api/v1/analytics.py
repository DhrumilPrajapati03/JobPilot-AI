"""Analytics and reporting endpoints.

Provides application funnel metrics, response rates,
and weekly activity summaries.
"""

from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from app.models.application import ApplicationStatus
from app.services.auth import CurrentUser, get_current_user
from app.services.supabase import get_supabase_client

router = APIRouter()

WEEKS_OF_HISTORY = 8
# Statuses that mean the employer has answered (positively or not).
RESPONDED = {"interviewing", "offer", "rejected"}
SUBMITTED = RESPONDED | {"applied"}


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _pct(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 1) if denominator else 0.0


@router.get("/summary")
async def get_analytics_summary(current_user: CurrentUser = Depends(get_current_user)):
    """Get application statistics and funnel metrics.

    Returns aggregated data: total applications, status breakdown,
    response/interview/offer rates, outreach counts, follow-ups due,
    average ATS score, weekly trend and recent activity.
    """
    supabase = get_supabase_client(user_jwt=current_user.token)
    apps = (
        supabase.table("job_applications")
        .select("*")
        .eq("user_id", current_user.id)
        .order("created_at", desc=True)
        .execute()
    ).data

    ids = [a["id"] for a in apps]
    scores: list[float] = []
    emails: list[dict] = []
    if ids:
        scores = [
            r["keyword_match_score"]
            for r in supabase.table("tailored_resumes")
            .select("keyword_match_score")
            .in_("application_id", ids)
            .execute()
            .data
            if r.get("keyword_match_score") is not None
        ]
        emails = (
            supabase.table("cold_emails")
            .select("*")
            .in_("application_id", ids)
            .execute()
        ).data

    now = datetime.now(timezone.utc)
    breakdown = Counter(a["status"] for a in apps)
    status_breakdown = {s.value: breakdown.get(s.value, 0) for s in ApplicationStatus}
    submitted = sum(status_breakdown[s] for s in SUBMITTED)
    responded = sum(status_breakdown[s] for s in RESPONDED)
    interviews = status_breakdown["interviewing"] + status_breakdown["offer"]

    follow_ups_due = []
    for a in apps:
        due = _parse_ts(a.get("follow_up_at"))
        if a["status"] == "applied" and due and due <= now:
            follow_ups_due.append({k: a[k] for k in ("id", "company", "role", "follow_up_at")})

    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    weeks = [week_start - timedelta(weeks=i) for i in range(WEEKS_OF_HISTORY - 1, -1, -1)]
    weekly = Counter()
    for a in apps:
        created = _parse_ts(a.get("created_at"))
        if created:
            weekly[(created - timedelta(days=created.weekday())).date()] += 1

    sent = [e for e in emails if e.get("sent_at")]
    return {
        "total_applications": len(apps),
        "status_breakdown": status_breakdown,
        "submitted": submitted,
        "response_rate": _pct(responded, submitted),
        "interview_rate": _pct(interviews, submitted),
        "offer_rate": _pct(status_breakdown["offer"], submitted),
        "emails_sent": len(sent),
        "email_reply_rate": _pct(sum(1 for e in sent if e.get("replied")), len(sent)),
        "avg_keyword_score": round(sum(scores) / len(scores), 1) if scores else None,
        "pending_follow_ups": len(follow_ups_due),
        "follow_ups_due": follow_ups_due[:10],
        "weekly_applications": [
            {"week": w.date().isoformat(), "count": weekly.get(w.date(), 0)} for w in weeks
        ],
        "recent_activity": [
            {k: a.get(k) for k in ("id", "company", "role", "status", "created_at", "updated_at")}
            for a in sorted(apps, key=lambda a: a.get("updated_at") or a.get("created_at") or "", reverse=True)[:8]
        ],
    }


def _norm(term: str) -> str:
    return " ".join(term.lower().split())


@router.get("/skill-gaps")
async def get_skill_gaps(current_user: CurrentUser = Depends(get_current_user)):
    """Which skills the user's target jobs ask for, and which their resumes miss.

    Missing keywords come from each application's latest tailored resume. A gap
    is "in_base_resume" when the user's base resume already mentions it — the
    tailoring didn't surface it, so it's a quick fix rather than a skill to learn.
    """
    supabase = get_supabase_client(user_jwt=current_user.token)
    apps = supabase.table("job_applications").select("*").eq("user_id", current_user.id).execute().data
    ids = [a["id"] for a in apps]

    latest: dict[str, dict] = {}
    if ids:
        for row in supabase.table("tailored_resumes").select("*").in_("application_id", ids).execute().data:
            current = latest.get(row["application_id"])
            if current is None or (row.get("version") or 0) >= (current.get("version") or 0):
                latest[row["application_id"]] = row

    base_res = supabase.table("resumes").select("*").eq("user_id", current_user.id).eq("version", "base").execute().data
    base = base_res[0] if base_res else {}
    skills = base.get("skills") or {}
    base_text = _norm(" ".join([
        base.get("summary") or "",
        base.get("headline") or "",
        " ".join(skills.get("primary") or []),
        " ".join(skills.get("secondary") or []),
        " ".join(b for e in base.get("experience") or [] for b in (e.get("bullets") or [])),
        " ".join(f"{p.get('name', '')} {p.get('description', '')} {' '.join(p.get('tech') or [])}" for p in base.get("projects") or []),
    ]))

    display: dict[str, str] = {}
    demand: Counter = Counter()
    gaps: Counter = Counter()
    gap_roles: dict[str, list[str]] = {}
    analyzed = 0
    for app in apps:
        analysis = app.get("jd_analysis") or {}
        requested = {_norm(s): s for s in [*(analysis.get("required_skills") or []), *(analysis.get("tech_stack") or [])] if s}
        for key, label in requested.items():
            display.setdefault(key, label)
            demand[key] += 1
        tailored = latest.get(app["id"])
        if not tailored:
            continue
        analyzed += 1
        for kw in {_norm(k) for k in tailored.get("missing_keywords") or [] if k}:
            display.setdefault(kw, kw)
            gaps[kw] += 1
            gap_roles.setdefault(kw, []).append(f"{app.get('role')} · {app.get('company')}")

    def in_base(term: str) -> bool:
        return bool(base_text) and f" {term} " in f" {base_text} "

    total_jobs = len(apps)
    return {
        "applications_analyzed": analyzed,
        "jobs_considered": total_jobs,
        "has_base_resume": bool(base),
        "gaps": [
            {
                "keyword": display[k],
                "count": n,
                "share": round(n / analyzed * 100, 1) if analyzed else 0.0,
                "in_base_resume": in_base(k),
                "examples": gap_roles[k][:3],
            }
            for k, n in gaps.most_common(15)
        ],
        "most_requested": [
            {"skill": display[k], "count": n, "share": round(n / total_jobs * 100, 1) if total_jobs else 0.0, "you_have": in_base(k)}
            for k, n in demand.most_common(12)
        ],
    }
