"""Durable execution repository. PostgreSQL owns claims, fencing and checkpoints.

Only the API/worker uses this service-role repository. Callers must pass a
verified user id; tokens and provider credentials never enter queued payloads.
"""
import uuid
from contextvars import ContextVar

from fastapi import HTTPException

from app.config import settings
from app.services.supabase import get_supabase_admin_client

TERMINAL = {"succeeded", "failed"}
INPUT_FIELDS = {
    "application": {"jd_url", "jd_text", "source", "posting_id", "auto"},
    "scan": {"auto_draft", "source_ids", "scheduled_on"},
    "digest": {"scheduled_on"},
    "mail_send": {"message_id"},
    "mail_sync": {"connection_id", "cycle", "after_id"},
}
current_execution: ContextVar = ContextVar("current_execution", default=None)


class LeaseLost(RuntimeError):
    """This process may no longer commit work for the claimed run."""


class PermanentRunError(ValueError):
    """User input/configuration needs changing before another attempt."""


def durable_enabled() -> bool:
    return settings.EXECUTION_MODE == "durable"


class RunStore:
    def __init__(self, client=None):
        self.client = client or get_supabase_admin_client()

    def rpc(self, name: str, **params):
        return self.client.rpc(name, params).execute().data

    def enqueue(self, user_id: str, kind: str, inputs: dict, key: str | None = None, available_at=None):
        if kind not in INPUT_FIELDS or set(inputs) - INPUT_FIELDS[kind]:
            raise ValueError("Unsupported durable job payload")
        key = str(uuid.uuid4()) if key is None else key
        if not key or len(key) > 200:
            raise ValueError("Idempotency key must contain 1 to 200 characters")
        parent = current_execution.get()
        params = dict(p_user_id=user_id, p_kind=kind, p_inputs=inputs, p_key=key)
        if available_at:
            params["p_available_at"] = available_at
        if parent:
            params.update(p_parent_id=parent.run["id"], p_parent_token=parent.token)
        return self.rpc("enqueue_agent_run", **params)

    def claim(self, worker_id: str):
        return self.rpc("claim_agent_run", p_worker=worker_id, p_lease_seconds=settings.RUN_LEASE_SECONDS)

    def renew(self, run_id: str, token: str):
        return self.rpc("renew_agent_run", p_run_id=run_id, p_token=token, p_lease_seconds=settings.RUN_LEASE_SECONDS)

    def checkpoint(self, run_id, token, stage, value):
        return self.rpc("checkpoint_agent_run", p_run_id=run_id, p_token=token, p_stage=stage, p_value=value)

    def emit(self, run_id, token, event):
        return self.rpc("append_agent_run_event", p_run_id=run_id, p_token=token, p_event=event)

    def finish(self, run_id, token, status, *, result=None, error=None, delay=0):
        return self.rpc("finish_agent_run", p_run_id=run_id, p_token=token, p_status=status,
                        p_result=result or {}, p_error=error, p_delay=delay)

    def get(self, run_id: str, user_id: str):
        rows = self.client.table("agent_runs").select("*").eq("id", run_id).eq("user_id", user_id).execute().data
        return rows[0] if rows else None

    def events(self, run_id: str, user_id: str, after: int = 0, limit: int = 200):
        # Ownership checked here as well as at the HTTP/WebSocket entry point.
        if not self.get(run_id, user_id):
            return None
        return self.client.table("agent_run_events").select("id, event").eq("run_id", run_id).eq(
            "user_id", user_id).gt("id", after).order("id").limit(limit).execute().data

    def replay_cursor(self, run_id: str, user_id: str) -> int:
        rows = self.client.table("agent_run_events").select("id").eq("run_id", run_id).eq(
            "user_id", user_id).eq("event->>step", "queued").order("id", desc=True).limit(1).execute().data
        return rows[0]["id"] - 1 if rows else 0


def enqueue_for_user(user_id, kind, inputs, key=None):
    try:
        return RunStore().enqueue(user_id, kind, inputs, key)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        if "idempotency_key_conflict" in str(exc):
            raise HTTPException(409, "This request key was already used for different input.") from exc
        raise HTTPException(503, "Durable execution is unavailable. Configure the service key, apply the Sprint 2 migration, and start a worker.") from exc


def public_run(run: dict) -> dict:
    return {key: run.get(key) for key in (
        "id", "kind", "status", "stage", "attempts", "max_attempts", "created_at",
        "updated_at", "available_at", "lease_expires_at", "result", "last_error",
    )}
