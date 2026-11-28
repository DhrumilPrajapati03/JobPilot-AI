"""Deep health (plan section 9, Day 16): is every moving part working? Signed-in only.

Checks, each a plain line with ok / warn / down:
database, migrations, worker (a recent heartbeat from the queue), queue depth, routines
(scheduler running, last backup), Google (connected, scopes, expiry), Telegram, model and
search keys present (never their values), disk space for files and backups.
"""
import asyncio
import shutil
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from app.config import settings
from app.db import get_db
from app.services.auth import CurrentUser, get_current_user

router = APIRouter()
HEAD = "0011"


def checks(user_id: str, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    db = get_db(user_id)
    out = []

    def add(name, status, detail):
        out.append({"name": name, "status": status, "detail": detail})
    try:
        version = db.fetch("select version_num from alembic_version")[0][0]
        add("Database", "ok", "Postgres answers.")
        add("Migrations", "ok" if version == HEAD else "warn", f"At {version}" + ("" if version == HEAD else f"; the code expects {HEAD}. Run migrate."))
    except Exception as exc:
        add("Database", "down", f"Postgres doesn't answer ({type(exc).__name__}).")
        return out
    queue = db.fetch("""select count(*) filter (where status in ('queued','retry_wait')), count(*) filter (where status = 'running'),
                               max(updated_at) filter (where status in ('running','succeeded','failed')),
                               min(available_at) filter (where status = 'queued')
                        from public.agent_runs where user_id = %s::uuid""", [user_id])[0]
    waiting, running, last, oldest = queue
    stuck = waiting and oldest and now - oldest > timedelta(minutes=15)
    add("Worker", "down" if stuck else "ok",
        "Jobs have waited over 15 minutes: is the worker running? (docker compose up -d worker)" if stuck
        else f"Last activity {last:%d %b %H:%M} UTC." if last else "No runs yet.")
    add("Queue", "warn" if waiting > 20 else "ok", f"{waiting} waiting, {running} running.")
    routines = dict(db.fetch("select key, last_run_at from public.routine where user_id = %s::uuid and enabled", [user_id]))
    poll = routines.get("inbox_poll")
    add("Routines", "warn" if poll is None or now - poll > timedelta(hours=2) else "ok",
        f"Gmail last checked {poll:%d %b %H:%M} UTC." if poll else "The Gmail check hasn't run yet.")
    backup = routines.get("nightly_backup")
    add("Backups", "warn" if not settings.BACKUP_ENABLED or backup is None or now - backup > timedelta(hours=36) else "ok",
        "Backups are off (BACKUP_ENABLED)." if not settings.BACKUP_ENABLED else
        f"Last backup {backup:%d %b %H:%M} UTC." if backup else "No backup has run yet.")
    google = db.fetch("select status, scopes, expires_hint from public.connection where user_id = %s::uuid and provider = 'google'", [user_id])
    if not google:
        add("Google", "warn", "Not connected: run python scripts/connect_google.py connect.")
    else:
        status, scopes, expires = google[0]
        missing = [s for s, name in (("gmail.send", "send"), ("gmail.readonly", "read"), ("calendar.events", "calendar")) if not any(x.endswith(s) for x in scopes)]
        soon = expires and expires - now < timedelta(days=1)
        add("Google", "down" if status != "active" else "warn" if missing or soon else "ok",
            "The connection expired: reconnect." if status != "active" else
            f"Missing {', '.join(missing)}: reconnect to grant it." if missing else
            f"Ends {expires:%d %b} (Testing mode): reconnect soon." if soon else "Gmail and Calendar connected.")
    add("Telegram", "ok" if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID else "warn",
        "Approvals and alerts on." if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID else "Not linked: no phone approvals or alerts.")
    add("Models", "ok" if settings.GROQ_API_KEY else "warn", "Groq key present." if settings.GROQ_API_KEY else "No GROQ_API_KEY: experts can't write.")
    add("Search", "ok" if settings.BRAVE_API_KEY else "warn", "Brave key present." if settings.BRAVE_API_KEY else "No BRAVE_API_KEY: Recon and Comp Analyst can't search.")
    try:
        free = shutil.disk_usage(settings.FILE_STORAGE_DIR).free / 1e9
        add("Disk", "warn" if free < 2 else "ok", f"{free:.1f} GB free for files and backups.")
    except OSError:
        add("Disk", "warn", "The files folder isn't there.")
    return out


@router.get("/deep")
async def deep(user: CurrentUser = Depends(get_current_user)):
    items = await asyncio.to_thread(checks, user.id)
    worst = "down" if any(i["status"] == "down" for i in items) else "warn" if any(i["status"] == "warn" for i in items) else "ok"
    return {"status": worst, "checks": items}
