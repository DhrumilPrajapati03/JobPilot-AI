"""Autopilot endpoints: the apply queue, the morning digest, the cron tick and extension tokens."""

import asyncio

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.api.v1.applications import _get_owned_application
from app.config import settings
from app.models.user import WorkPreferences
from app.services import autopilot, digest
from app.services.auth import CurrentUser, get_current_user
from app.services.supabase import get_supabase_admin_client, get_supabase_client

router = APIRouter()
MIGRATION_FILE = "supabase/migrations/20261014_autopilot.sql"
_background: set[asyncio.Task] = set()


def _client(user: CurrentUser):
    return get_supabase_client(user_jwt=user.token)


def _prefs(supabase, user_id: str) -> WorkPreferences:
    rows = supabase.table("user_profiles").select("work_preferences").eq("id", user_id).execute().data
    try:
        return WorkPreferences.model_validate((rows[0].get("work_preferences") if rows else None) or {})
    except Exception:
        return WorkPreferences()


def _setup_error(e: Exception):
    if autopilot._missing_table(e, "extension_tokens", "autopilot_state"):
        raise HTTPException(status_code=503, detail=f"Autopilot tables don't exist yet. Run {MIGRATION_FILE} in Supabase.")
    raise e


@router.get("/status")
async def autopilot_status(current_user: CurrentUser = Depends(get_current_user)):
    """What runs automatically on this server, and when it last ran for you."""
    supabase = _client(current_user)
    prefs = _prefs(supabase, current_user.id)
    try:
        state = (supabase.table("autopilot_state").select("*").eq("user_id", current_user.id).execute().data or [None])[0]
        tables_ready = True
    except Exception:
        state, tables_ready = None, False
    return {
        "tables_ready": tables_ready,
        "server_scheduler": autopilot.server_ready(),
        "cron_configured": bool(settings.CRON_SECRET),
        "email_configured": digest.email_configured(),
        "digest_to": prefs.digest_email or current_user.email,
        "scan_hour": autopilot.scan_hour(prefs),
        "state": state,
    }


@router.get("/queue")
async def apply_queue(current_user: CurrentUser = Depends(get_current_user)):
    """Drafted applications waiting to be sent, with their prepared answers."""
    return {"queue": autopilot.build_queue(_client(current_user), current_user.id)}


@router.post("/prepare/{application_id}")
async def prepare(application_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """(Re)prepare an application's form answers, e.g. after updating the answer bank."""
    supabase = _client(current_user)
    _get_owned_application(supabase, application_id, current_user.id)
    prepared = await autopilot.prepare_application_form(supabase, current_user.id, application_id, current_user.email)
    return prepared or {}


@router.get("/digest/preview")
async def digest_preview(current_user: CurrentUser = Depends(get_current_user)):
    supabase = _client(current_user)
    prefs = _prefs(supabase, current_user.id)
    subject, body_html, _ = digest.render_digest(digest.build_digest_data(supabase, current_user.id, prefs))
    return {"subject": subject, "html": body_html, "to": prefs.digest_email or current_user.email}


@router.post("/digest/send")
async def digest_send(current_user: CurrentUser = Depends(get_current_user)):
    """Send today's digest now (a test; it doesn't replace tomorrow morning's)."""
    supabase = _client(current_user)
    prefs = _prefs(supabase, current_user.id)
    try:
        return await digest.send_digest(supabase, current_user.id, prefs, prefs.digest_email or current_user.email)
    except digest.DigestError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tick")
async def cron_tick(x_cron_secret: str = Header(default="")):
    """Run the daily schedule for everyone. Call it every 10-15 minutes from a cron service.

    Returns at once and works in the background, so a slow scan never times out the caller.
    """
    if not settings.CRON_SECRET or x_cron_secret != settings.CRON_SECRET:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad or missing X-Cron-Secret.")
    if not autopilot.server_ready():
        raise HTTPException(status_code=503, detail="Set SUPABASE_SERVICE_KEY on the server to run the schedule.")
    task = asyncio.create_task(autopilot.tick(get_supabase_admin_client()))
    _background.add(task)
    task.add_done_callback(_background.discard)
    return {"status": "started"}


# --- Extension tokens ------------------------------------------------------------------------

@router.post("/extension-tokens", status_code=status.HTTP_201_CREATED)
async def create_extension_token(current_user: CurrentUser = Depends(get_current_user)):
    """A personal token for the Chrome extension. Shown once; only its hash is stored."""
    token = autopilot.new_token()
    try:
        row = _client(current_user).table("extension_tokens").insert({
            "user_id": current_user.id, "token_hash": autopilot.hash_token(token),
        }).execute().data[0]
    except Exception as e:
        _setup_error(e)
    return {"id": row["id"], "token": token, "created_at": row.get("created_at")}


@router.get("/extension-tokens")
async def list_extension_tokens(current_user: CurrentUser = Depends(get_current_user)):
    try:
        rows = _client(current_user).table("extension_tokens").select("id, label, created_at, last_used_at").eq("user_id", current_user.id).order("created_at", desc=True).execute().data
    except Exception as e:
        _setup_error(e)
    return {"tokens": rows, "server_ready": autopilot.server_ready()}


@router.delete("/extension-tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_extension_token(token_id: str, current_user: CurrentUser = Depends(get_current_user)):
    try:
        _client(current_user).table("extension_tokens").delete().eq("id", token_id).eq("user_id", current_user.id).execute()
    except Exception as e:
        _setup_error(e)
