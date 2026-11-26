"""Courier runs (queue kind 'courier'): one approved action, through the policy gate, sent once.

    approved --gate--> executing --Gmail--> provider_accepted | send_unknown | failed

* The gate (app.core.actions.start_execution) re-checks the kill switch, caps, quiet hours
  and cooldowns. Quiet hours and daily caps reschedule the run; other refusals leave the
  action approved and tell Dhrumil why.
* A run that finds its action already `executing` (a crash mid-send) looks in Sent for the
  Message-ID; found -> provider_accepted, not found -> send_unknown (never a blind resend).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
from psycopg.types.json import Jsonb

from app.config import settings
from app.core import actions, cases
from app.core.policy import load_policy
from app.courier import connections, gmail
from app.db import get_db
from app.services.runs import PermanentRunError, RunStore

SENDERS = {"send_email"}


def dispatch(user_id: str, action_id: str, *, available_at: datetime | None = None, store: RunStore | None = None) -> dict:
    """Queue Courier for an approved action (idempotent per action and time)."""
    store = store or RunStore()
    key = f"courier:{action_id}" + (f":{available_at.isoformat()}" if available_at else "")
    return store.enqueue(user_id, "courier", {"action_id": action_id}, key, available_at=available_at)


def _event(user_id: str, action: dict, kind: str, summary: str, data: dict | None = None) -> None:
    if action.get("case_id"):
        cases.add_event(user_id, action["case_id"], kind, actor="courier", actor_name="gmail", summary=summary,
                        data={"action_id": action["id"], **(data or {})})


def _record_touch(user_id: str, action: dict) -> None:
    contact = action["payload"].get("contact_id")
    if contact:
        get_db(user_id).fetch("""insert into public.contact_touch (contact_id, user_id, case_id, channel, action_id, sent_at, outcome)
                                 values (%s::uuid, %s::uuid, %s::uuid, 'email', %s::uuid, now(), 'sent')""",
                              [contact, user_id, action.get("case_id"), action["id"]])


def _next_local_morning(now: datetime) -> datetime:
    policy = load_policy()
    return policy.day_start(now) + timedelta(days=1, hours=9)


def _prepare(user_id: str, payload: dict, client: httpx.Client) -> tuple[str, str, tuple[str, bytes] | None]:
    """Everything a send needs, checked before the gate so a broken connection leaves the action approved."""
    token, sender = connections.google_access_token(user_id, need=gmail.SEND_SCOPE, client=client)
    return token, sender, gmail.attachment_for(payload, settings.FILE_STORAGE_DIR)


def execute(user_id: str, action_id: str, *, now: datetime | None = None, client: httpx.Client | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    current = get_db(user_id).fetch("select status, kind from public.action where id = %s::uuid and user_id = %s::uuid",
                                    [action_id, user_id])
    if not current:
        raise PermanentRunError("The action no longer exists.")
    status, kind = current[0]
    if kind not in SENDERS:
        raise PermanentRunError(f"Courier has no executor for {kind}.")
    if status in ("provider_accepted", "delivered", "failed", "send_unknown", "cancelled"):
        return {"status": status, "skipped": "already settled"}
    if status == "executing":
        return _recover(user_id, action_id, client=client)
    own = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(60.0, connect=15.0))
    try:
        return _execute(user_id, action_id, now, client)
    finally:
        if own:
            client.close()


def _execute(user_id: str, action_id: str, now: datetime, client: httpx.Client) -> dict:
    pending = get_db(user_id).fetch("select to_jsonb(a) from public.action a where id = %s::uuid", [action_id])[0][0]
    try:
        token, sender, attachment = _prepare(user_id, pending["payload"], client)
    except (connections.ConnectionError_, FileNotFoundError, ValueError) as exc:
        # Nothing was attempted: the action stays approved and can go out once this is fixed.
        _event(user_id, pending, "held", f"Not sent yet: {exc}", {"reasons": [str(exc)]})
        return {"status": "approved", "held": [str(exc)]}
    try:
        gate = actions.start_execution(user_id, action_id, now=now)
    except actions.ActionError as exc:
        raise PermanentRunError(str(exc)) from None
    action = gate.action
    if not gate.run:
        reasons = gate.verdict.reasons
        later = gate.verdict.retry_at or (_next_local_morning(now) if any("Daily cap" in r for r in reasons) else None)
        if later:
            dispatch(user_id, action_id, available_at=later)
        _event(user_id, action, "held", "Not sent yet: " + "; ".join(reasons),
               {"reasons": reasons, "retry_at": later.isoformat() if later else None})
        return {"status": "approved", "held": reasons, "retry_at": later.isoformat() if later else None}
    msg = gmail.build(action["payload"], sender, action["payload"].get("from_name", ""), action["id"], attachment)
    result = gmail.send(client, token, msg)
    actions.record_outcome(user_id, action_id, result.status, provider_ref=result.provider_ref, error=result.error)
    if result.status == "provider_accepted":
        _record_touch(user_id, action)
        _event(user_id, action, "email_sent", f"Email sent to {action['payload'].get('to')}", {"gmail_id": result.provider_ref})
        _mark_resume_used(user_id, action)
    else:
        _event(user_id, action, "email_" + result.status, result.error or result.status)
    return {"status": result.status, "provider_ref": result.provider_ref, "error": result.error}


def _recover(user_id: str, action_id: str, *, client: httpx.Client | None = None) -> dict:
    action = get_db(user_id).fetch("select to_jsonb(a) from public.action a where id = %s::uuid", [action_id])[0][0]
    own = client is None
    client = client or httpx.Client(timeout=30)
    try:
        token, sender = connections.google_access_token(user_id, need=gmail.READ_SCOPE, client=client)
        found = gmail.already_sent(client, token, gmail.message_id(action_id, sender))
    except connections.ConnectionError_:
        found = None
    finally:
        if own:
            client.close()
    if found:
        actions.record_outcome(user_id, action_id, "provider_accepted", provider_ref=found)
        _record_touch(user_id, action)
        _event(user_id, action, "email_sent", f"Email sent to {action['payload'].get('to')} (confirmed after a restart)")
        return {"status": "provider_accepted", "provider_ref": found}
    actions.record_outcome(user_id, action_id, "send_unknown",
                           error="The worker stopped mid-send and Gmail's Sent folder doesn't show it yet. Check Sent before sending again.")
    _event(user_id, action, "email_send_unknown", "Send result unknown after a restart; check your Sent folder.")
    return {"status": "send_unknown"}


def _mark_resume_used(user_id: str, action: dict) -> None:
    artifact = (action["payload"].get("attachment") or {}).get("artifact_id")
    if artifact:
        get_db(user_id).fetch("""update public.artifact set content = content || %s where id = %s::uuid
                                 and kind = 'resume_version' and content->>'status' = 'awaiting_review'""",
                              [Jsonb({"status": "approved"}), artifact])


async def run(ctx) -> dict:
    """Worker entry point for run kind 'courier'."""
    return await asyncio.to_thread(execute, ctx.run["user_id"], ctx.run["inputs"]["action_id"])

