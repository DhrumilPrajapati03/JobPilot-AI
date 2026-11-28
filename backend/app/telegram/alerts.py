"""Telegram alerts (plan section 9.2, Day 16): what you'd want to know without opening JobDots.

The Telegram process calls `pending(user_id)` on every loop and sends what it returns:

* case events that need you or are good news: a reply, an interview invite, a likely
  rejection, an accepted LinkedIn invitation, a calendar event added (forwarded once, in
  order, after `telegram_state.alert_event_id`);
* an expert failing again and again (2+ failed runs in the last hour), once a day per expert;
* the monthly model budget past 80%, once a month.

Each alert is a short line with a link-free summary; nothing in it is a secret.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db import get_db
from app.telegram.client import esc

EVENTS = {"reply": "💬", "interview": "📅", "rejection": "📭", "linkedin_accepted": "🤝", "calendar_added": "🗓"}


def _once(db, user_id: str, key: str) -> bool:
    """True the first time this key is seen (then it is recorded)."""
    return bool(db.fetch("""insert into public.telegram_alert (user_id, key) values (%s::uuid, %s)
                            on conflict do nothing returning key""", [user_id, key]))


def pending(user_id: str, *, now: datetime | None = None) -> list[str]:
    now = now or datetime.now(timezone.utc)
    db = get_db(user_id)
    out = []
    cursor = db.fetch("select alert_event_id from public.telegram_state where user_id = %s::uuid", [user_id])
    if cursor:
        start = cursor[0][0]
        if start == 0:                                   # first run: don't replay history, start from now
            latest = db.fetch("select coalesce(max(id), 0) from public.case_event where user_id = %s::uuid", [user_id])[0][0]
            db.fetch("update public.telegram_state set alert_event_id = %s where user_id = %s::uuid", [latest, user_id])
        else:
            rows = db.fetch("""select e.id, e.kind, e.summary, c.company from public.case_event e join public.job_case c on c.id = e.case_id
                               where e.user_id = %s::uuid and e.id > %s and e.kind = any(%s) order by e.id limit 20""",
                            [user_id, start, list(EVENTS)])
            for event_id, kind, summary, company in rows:
                out.append(f"{EVENTS[kind]} <b>{esc(company or 'A case')}</b>: {esc(summary)[:600]}")
            if rows:
                db.fetch("update public.telegram_state set alert_event_id = %s where user_id = %s::uuid", [rows[-1][0], user_id])
    failing = db.fetch("""select inputs->>'agent', count(*), (array_agg(last_error order by updated_at desc))[1]
                          from public.agent_runs where user_id = %s::uuid and kind = 'agent' and status = 'failed' and updated_at >= %s
                          group by 1 having count(*) >= 2""", [user_id, now - timedelta(hours=1)])
    for agent, n, error in failing:
        if _once(db, user_id, f"failing:{agent}:{now:%Y-%m-%d}"):
            from app.api.v1.dashboard import clean_error
            out.append(f"⚠️ <b>{esc(agent.replace('_', ' ').title())}</b> failed {n} times in the last hour: {esc(clean_error(error))}. "
                       "See Dashboard → Live Ops.")
    try:
        from app.core import budgets
        month = budgets.month_status(user_id)
        used, limit = month.used["usd"], month.limits["usd"]
        if limit and used >= 0.8 * limit and _once(db, user_id, f"budget80:{now:%Y-%m}"):
            out.append(f"💸 Model spend this month is ${used:.2f} of ${limit:.2f}. Experts stop at the limit.")
    except Exception:
        pass
    return out
