"""Routines with catch-up-on-wake (plan sections 4 and 9.2).

A routine belongs to an expert and runs once per local day after its hour (policy.yaml time
zone). The worker records the day each routine last ran for; on startup it runs every
routine that came due while the laptop was off, once each (not once per missed day), and
posts one line: "JobDots woke up and ran N missed routines".

Defaults: Scout's daily scan (two hours before the digest hour, as before) and the nightly
backup (BACKUP_HOUR).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from psycopg.types.json import Jsonb

from app.config import settings
from app.core.policy import load_policy
from app.db import get_db


def ensure_defaults(user_id: str) -> None:
    from app.services.autopilot import scan_hour
    from app.services.discovery import load_preferences
    db = get_db(user_id)
    try:
        hour = scan_hour(load_preferences(db, user_id))
    except Exception:
        hour = 5
    defaults = [("scout_daily_scan", "scout", "Daily job scan", "scout_scan", hour, settings.DISCOVERY_AUTO_SCAN),
                ("nightly_backup", "supervisor", "Nightly backup", "backup", settings.BACKUP_HOUR, settings.BACKUP_ENABLED)]
    for key, agent, name, kind, at_hour, enabled in defaults:
        db.fetch("""insert into public.routine (user_id, key, agent, name, kind, schedule, enabled)
                    values (%s::uuid, %s, %s, %s, %s, %s, %s) on conflict (user_id, key) do nothing""",
                 [user_id, key, agent, name, kind, Jsonb({"kind": "daily", "hour": at_hour}), enabled])
    # Inbox (Day 10): Gmail every 30 minutes, follow-up drafts each morning.
    for key, name, task, schedule in [("inbox_poll", "Check Gmail for replies", "poll", {"kind": "every", "minutes": 30}),
                                      ("follow_ups", "Draft follow-ups", "follow_up", {"kind": "daily", "hour": 10})]:
        db.fetch("""insert into public.routine (user_id, key, agent, name, kind, task, schedule, enabled)
                    values (%s::uuid, %s, 'inbox', %s, 'expert', %s, %s, true) on conflict (user_id, key) do nothing""",
                 [user_id, key, name, task, Jsonb(schedule)])
    # DM Outreach (Day 11): messages to people who accepted your invitation, each morning.
    db.fetch("""insert into public.routine (user_id, key, agent, name, kind, task, schedule, enabled)
                values (%s::uuid, 'accepted_dms', 'dm_outreach', 'Message people who accepted', 'expert', 'after_accept', %s, true)
                on conflict (user_id, key) do nothing""", [user_id, Jsonb({"kind": "daily", "hour": 11})])


def _local(now: datetime):
    try:
        policy = load_policy()
        return policy.local(now)
    except Exception:
        return now


def due_routines(user_id: str, now: datetime) -> list[dict]:
    local = _local(now)
    today = local.date()
    rows = get_db(user_id).fetch("""select to_jsonb(r) from public.routine r where user_id = %s::uuid and enabled
                                    order by key""", [user_id])
    due = []
    for (routine,) in rows:
        schedule = routine.get("schedule") or {}
        if schedule.get("kind") == "every":          # interval routines: due when the interval has passed
            last_run = routine.get("last_run_at")
            minutes = max(int(schedule.get("minutes", 30)), 5)
            if not last_run or now - datetime.fromisoformat(last_run) >= timedelta(minutes=minutes):
                due.append(routine)
            continue
        last = routine.get("last_due_on")
        last_day = datetime.fromisoformat(last).date() if last else None
        hour = int((routine.get("schedule") or {}).get("hour", 0))
        if last_day == today:
            continue
        # Due after its hour; a routine that never ran, or skipped a whole day (laptop off),
        # catches up now, whatever the hour.
        if local.hour >= hour or last_day is None or last_day < today - timedelta(days=1):
            due.append(routine)
    return due


def _enqueue(store, user_id: str, routine: dict, day: str, now: datetime | None = None) -> dict:
    if routine["kind"] == "backup":
        return store.enqueue(user_id, "backup", {"scheduled_on": day}, f"backup:{day}")
    from app.experts.runtime import enqueue_expert
    if routine["kind"] == "expert":
        every = (routine.get("schedule") or {}).get("kind") == "every"
        slot = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M") if every else day
        return enqueue_expert(user_id, routine["agent"], store=store, key=f"routine:{routine['key']}:{slot}",
                              trigger="routine", scheduled_on=day, task=routine.get("task") or "")
    return enqueue_expert(user_id, routine["agent"], store=store, key=f"routine:{routine['key']}:{day}",
                          trigger="routine", scheduled_on=day)


async def tick(store, user_id: str, *, now: datetime | None = None, waking: bool = False) -> dict:
    """Queue every due routine once. On the worker's first tick (waking) report missed runs."""
    import asyncio
    from app.experts.runtime import note
    now = now or datetime.now(timezone.utc)
    day = _local(now).date().isoformat()
    due = await asyncio.to_thread(due_routines, user_id, now)
    queued, missed = [], 0
    for routine in due:
        try:
            run = await asyncio.to_thread(_enqueue, store, user_id, routine, day, now)
            status = "queued"
        except Exception as exc:
            run, status = None, f"failed to queue ({type(exc).__name__})"
        await asyncio.to_thread(get_db(user_id).fetch, """
            update public.routine set last_due_on = %s, last_run_at = now(), last_run_id = %s::uuid, last_status = %s
            where id = %s::uuid""", [day, run and run.get("id"), status, routine["id"]])
        queued.append(routine["key"])
    # On the first tick after start, everything due was missed while the worker was down
    # (interval routines like Gmail checks aren't "missed": they simply run again).
    missed = len([k for k in queued if k not in ("inbox_poll",)]) if waking else 0
    if missed:
        await note(user_id, "supervisor", f"JobDots woke up and ran {missed} missed routine{'s' if missed > 1 else ''}",
                   detail={"routines": queued})
    return {"queued": queued, "missed": missed}
