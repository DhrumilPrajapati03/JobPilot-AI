"""Morning digest email: what's ready to send, what's new, what's due.

Sent with Resend's HTTP API. On Resend's free plan, mail comes from
``onboarding@resend.dev`` and can only go to the address you signed up with,
which is exactly what a personal digest needs.
"""

import html
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings
from app.models.user import WorkPreferences
from app.services import autopilot


class DigestError(Exception):
    """The digest couldn't be sent; the message is safe to show the user."""


def app_url() -> str:
    return (settings.FRONTEND_URL.split(",")[0].strip() or "http://localhost:5173").rstrip("/")


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


def build_digest_data(supabase, user_id: str, prefs: WorkPreferences) -> dict:
    from app.services import discovery

    now = datetime.now(timezone.utc)
    week_ago = (now - timedelta(days=7)).isoformat()
    queue = autopilot.build_queue(supabase, user_id)
    briefing = _safe(lambda: discovery.build_briefing(supabase, user_id, prefs), None)
    referrals = _safe(lambda: supabase.table("referral_requests").select("id, application_id, status").eq("user_id", user_id).eq("status", "drafted").execute().data, [])
    apps = supabase.table("job_applications").select("id, role, company, status, applied_at, follow_up_at").eq("user_id", user_id).execute().data
    profile = (supabase.table("user_profiles").select("name").eq("id", user_id).execute().data or [{}])[0]
    due = [
        a for a in apps
        if a["status"] == "applied" and a.get("follow_up_at") and a["follow_up_at"] <= now.isoformat()
    ]
    return {
        "name": (profile.get("name") or "").split(" ")[0],
        "queue": queue,
        "new_matches": (briefing or {}).get("new_matches", 0),
        "top_matches": (briefing or {}).get("top_matches", []),
        "auto_draft": (briefing or {}).get("auto_draft"),
        "sources": (briefing or {}).get("sources", 0),
        "follow_ups": due[:5],
        "referrals_to_send": len(referrals),
        "applied_this_week": sum(1 for a in apps if (a.get("applied_at") or "") >= week_ago),
        "interviewing": sum(1 for a in apps if a["status"] == "interviewing"),
    }


def subject_for(data: dict) -> str:
    parts = []
    if data["queue"]:
        n = len(data["queue"])
        parts.append(f"{n} application{'s' if n != 1 else ''} ready to send")
    if data["new_matches"]:
        parts.append(f"{data['new_matches']} new match{'es' if data['new_matches'] != 1 else ''}")
    if data["follow_ups"]:
        parts.append(f"{len(data['follow_ups'])} follow-up{'s' if len(data['follow_ups']) != 1 else ''} due")
    return "JobPilot: " + (", ".join(parts) if parts else "your morning briefing")


# --- Rendering ----------------------------------------------------------------------------

_INK, _MUTED, _ACCENT, _WARN, _LINE = "#1f1e1d", "#6b6966", "#0f7b6c", "#b45309", "#e7e4de"


def _e(text) -> str:
    return html.escape(str(text or ""))


def _section(title: str, body: str) -> str:
    return (
        f'<tr><td style="padding:20px 24px 4px;font:600 13px/1.4 -apple-system,Segoe UI,sans-serif;color:{_MUTED};'
        f'text-transform:uppercase;letter-spacing:.04em">{_e(title)}</td></tr>'
        f'<tr><td style="padding:4px 24px 8px">{body}</td></tr>'
    )


def _row(title: str, meta: str, href: str, trailing: str = "") -> str:
    return (
        f'<table role="presentation" width="100%" style="border-bottom:1px solid {_LINE}"><tr>'
        f'<td style="padding:10px 0;font:14px/1.4 -apple-system,Segoe UI,sans-serif">'
        f'<a href="{_e(href)}" style="color:{_INK};font-weight:600;text-decoration:none">{_e(title)}</a>'
        f'<div style="color:{_MUTED};font-size:12px">{meta}</div></td>'
        f'<td style="padding:10px 0;text-align:right;white-space:nowrap;font:600 13px -apple-system,Segoe UI,sans-serif">{trailing}</td>'
        "</tr></table>"
    )


def render_digest(data: dict) -> tuple[str, str, str]:
    """``(subject, html, text)`` for the digest."""
    base = app_url()
    subject = subject_for(data)
    hello = f"Good morning{', ' + _e(data['name']) if data['name'] else ''}."
    sections: list[str] = []
    text: list[str] = [hello.replace("&#x27;", "'"), ""]

    if data["queue"]:
        rows = []
        for q in data["queue"][:8]:
            s = q.get("summary") or {}
            bits = []
            if q.get("match_score") is not None:
                bits.append(f"{round(q['match_score'])}% ATS match")
            if s:
                bits.append(f"{s.get('filled', 0)} of {s.get('total', 0)} answers ready" + (f", {s['flagged']} to check" if s.get("flagged") else ""))
            if q.get("referral_count"):
                bits.append(f"you know {q['referral_count']} there")
            link = q.get("apply_url") or f"{base}/applications/{q['id']}"
            rows.append(_row(f"{q['role']} · {q['company']}", _e(" · ".join(bits)), link, f'<a href="{_e(link)}" style="color:{_ACCENT}">Open &amp; fill →</a>'))
            text.append(f"- {q['role']} at {q['company']}: {link}")
        body = "".join(rows) + (
            f'<p style="font:13px/1.5 -apple-system,Segoe UI,sans-serif;color:{_MUTED};margin:10px 0 0">'
            "Open each one with the JobPilot extension: it fills the form, you check it and click Submit. "
            f'<a href="{base}/apply" style="color:{_ACCENT}">See the whole queue</a></p>'
        )
        sections.append(_section("Ready to send", body))
        text.insert(2, f"Ready to send ({len(data['queue'])}):")
        text.append("")

    if data["top_matches"]:
        rows = []
        for m in data["top_matches"][:3]:
            meta = " · ".join(p for p in (_e(m.get("company")), "Remote" if m.get("remote") else _e(m.get("location"))) if p)
            rows.append(_row(m["title"], meta, f"{base}/jobs", f'<span style="color:{_ACCENT}">{round(float(m.get("fit_score") or 0))}% fit</span>'))
        label = f"{data['new_matches']} new matches" if data["new_matches"] else "Best open matches"
        sections.append(_section(label, "".join(rows)))
        text += [f"{label}: {base}/jobs", ""]

    if data["follow_ups"]:
        rows = [_row(f"{a['role']} · {a['company']}", "Follow-up due", f"{base}/applications/{a['id']}?tab=email") for a in data["follow_ups"]]
        sections.append(_section("Follow-ups due", "".join(rows)))
        text += [f"Follow-ups due: {len(data['follow_ups'])}", ""]

    notes = []
    if data["referrals_to_send"]:
        notes.append(f"{data['referrals_to_send']} referral request{'s' if data['referrals_to_send'] != 1 else ''} drafted and waiting for you to send.")
    if data["applied_this_week"] or data["interviewing"]:
        notes.append(f"This week: {data['applied_this_week']} applied, {data['interviewing']} interviewing.")
    if data["auto_draft"] and data["auto_draft"].get("enabled"):
        notes.append(f"Auto-draft is on: up to {data['auto_draft']['daily_cap']} drafts a night at {data['auto_draft']['min_score']}%+ fit.")
    elif data["sources"]:
        notes.append("Auto-draft is off, so nothing was drafted overnight. Turn it on in Profile → Preferences.")
    else:
        notes.append("Follow some companies in your Job feed to get new matches every morning.")
    sections.append(_section("Also", "".join(f'<p style="font:14px/1.5 -apple-system,Segoe UI,sans-serif;color:{_INK};margin:6px 0">{_e(n)}</p>' for n in notes)))
    text += notes

    body_html = (
        f'<!doctype html><html><body style="margin:0;background:#faf9f7">'
        f'<table role="presentation" width="100%" style="background:#faf9f7;padding:24px 12px"><tr><td align="center">'
        f'<table role="presentation" width="100%" style="max-width:600px;background:#fff;border:1px solid {_LINE};border-radius:12px">'
        f'<tr><td style="padding:22px 24px 0;font:600 18px/1.4 -apple-system,Segoe UI,sans-serif;color:{_INK}">{hello}</td></tr>'
        f'<tr><td style="padding:4px 24px 0;font:14px/1.5 -apple-system,Segoe UI,sans-serif;color:{_MUTED}">Here\'s what JobPilot did overnight and what needs you today.</td></tr>'
        + "".join(sections)
        + f'<tr><td style="padding:16px 24px 22px;font:12px/1.5 -apple-system,Segoe UI,sans-serif;color:{_MUTED}">'
        f'JobPilot never submits applications or sends messages for you. '
        f'<a href="{base}/settings" style="color:{_MUTED}">Digest settings</a></td></tr>'
        "</table></td></tr></table></body></html>"
    )
    return subject, body_html, "\n".join(text) + f"\n\nOpen JobPilot: {base}\n"


# --- Sending -----------------------------------------------------------------------------------

def email_configured() -> bool:
    return bool(settings.RESEND_API_KEY)


async def send_email(to: str, subject: str, body_html: str, body_text: str, *, idempotency_key: str | None = None, sender: str | None = None):
    if not settings.RESEND_API_KEY:
        raise DigestError("Email isn't set up on the server: add RESEND_API_KEY (free at resend.com).")
    if not to:
        raise DigestError("No email address for the digest. Set one in Settings.")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            res = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}",
                         **({"Idempotency-Key": idempotency_key} if idempotency_key else {})},
                json={"from": sender or settings.DIGEST_FROM, "to": [to], "subject": subject, "html": body_html, "text": body_text},
            )
    except httpx.HTTPError as e:
        raise DigestError(f"Couldn't reach Resend ({type(e).__name__}).") from e
    if res.status_code >= 400:
        detail = res.json().get("message") if res.headers.get("content-type", "").startswith("application/json") else res.text
        hint = " On Resend's free plan you can only send to the email you signed up with." if res.status_code in (403, 422) else ""
        raise DigestError(f"Resend rejected the email: {detail}.{hint}")


async def send_digest(supabase, user_id: str, prefs: WorkPreferences, to: str) -> dict:
    data = build_digest_data(supabase, user_id, prefs)
    subject, body_html, body_text = render_digest(data)
    await send_email(to, subject, body_html, body_text)
    return {"to": to, "subject": subject}
