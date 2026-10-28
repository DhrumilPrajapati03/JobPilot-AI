"""Recovery invariants; SQL transaction/RLS assertions live in supabase/tests."""
import asyncio
import copy
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi import BackgroundTasks

from app.agents import orchestrator
from app.api.v1 import runs as runs_api
from app.api.v1 import applications as application_api
from app.config import settings
from app.models.user import WorkPreferences
from app.services import autopilot, digest, runs, run_stream
from app.services.auth import CurrentUser
from app.workers.runner import Worker
from app.workflows.context import ExecutionContext
from test_application_flow import USER_ID, db  # noqa: F401


class MemoryStore:
    """Persistent test boundary shared by separate worker objects, not SQL emulation."""
    def __init__(self, client=None, kind="application"):
        self.client = client
        self.row = dict(id=str(uuid.uuid4()), user_id=USER_ID, kind=kind, inputs={"jd_text": "Engineer at Globex"} if kind == "application" else {},
                        checkpoints={}, attempts=0, max_attempts=3, status="queued", lease_token=None)
        self.events_log = []
        self.material_commits = 0
        self.lose_save_reply = False
        self.fail_checkpoint = None

    def claim(self, worker):
        if self.row["status"] not in {"queued", "retry_wait"}:
            return None
        self.row.update(status="running", lease_token=str(uuid.uuid4()), attempts=self.row["attempts"] + 1)
        return copy.deepcopy(self.row)

    def renew(self, run_id, token):
        return token == self.row["lease_token"]

    def checkpoint(self, run_id, token, stage, value):
        if stage == self.fail_checkpoint:
            self.fail_checkpoint = None
            raise RuntimeError("connection dropped before checkpoint")
        self.row["checkpoints"][stage] = copy.deepcopy(value)

    def emit(self, run_id, token, event):
        self.events_log.append(copy.deepcopy(event))

    def finish(self, run_id, token, status, **kwargs):
        self.row.update(status=status, **kwargs)

    def rpc(self, name, **kwargs):
        if name == "save_run_application":
            self.material_commits += 1
            application = self.client.table("job_applications").insert({"user_id": self.row["user_id"], **kwargs["p_application"]}).execute().data[0]
            result = {"application_id": application["id"], "company": "Globex", "role": "Engineer", "score": 66.7}
            self.row["checkpoints"]["database_saving"] = result
            if self.lose_save_reply:
                self.lose_save_reply = False
                raise RuntimeError("DB committed, response lost")
            return result
        raise AssertionError(name)


def test_graph_recovers_after_commit_without_rewriting_or_duplicate_application(db, monkeypatch):
    store = MemoryStore(db)
    db.missing_columns = {}  # Durable mode requires the feature migrations.
    store.lose_save_reply = True
    calls = []
    old_parse = orchestrator.JDParserAgent.parse

    async def parse(*args, **kwargs):
        calls.append("parse")
        return await old_parse(*args, **kwargs)

    async def prepare(*args, **kwargs):
        return {}

    monkeypatch.setattr(orchestrator.JDParserAgent, "parse", parse)
    monkeypatch.setattr(autopilot, "prepare_application_form", prepare)
    first = Worker(store, heartbeat_factory=lambda: store)
    assert asyncio.run(first.run_once())
    assert store.row["status"] == "retry_wait"
    assert "database_saving" in store.row["checkpoints"]
    replacement = Worker(store, heartbeat_factory=lambda: store)
    assert replacement.id != first.id
    assert asyncio.run(replacement.run_once())
    assert store.row["status"] == "succeeded"
    assert calls == ["parse"]
    assert store.material_commits == 1
    assert len(db.tables["job_applications"]) == 1
    assert store.row["result"]["application_id"] == store.row["checkpoints"]["database_saving"]["application_id"]
    assert any(e["step"] == "pdf_rendering" and e["status"] == "warning" for e in store.events_log)


def test_digest_retry_keeps_recipient_body_and_provider_key(monkeypatch):
    store = MemoryStore(kind="digest")
    store.fail_checkpoint = "digest_delivery"  # provider sent, process died before acknowledging
    monkeypatch.setattr(autopilot, "account_email", lambda *a: "owner@example.invalid")
    monkeypatch.setattr('app.workers.runner.discovery.load_preferences', lambda *a: WorkPreferences())
    renders = []
    monkeypatch.setattr(digest, "build_digest_data", lambda *a: {})
    monkeypatch.setattr(digest, "render_digest", lambda *a: (renders.append(1) or "Subject", "<p>Snapshot</p>", "Snapshot"))
    calls, delivered = [], set()

    async def send(to, subject, html, text, *, idempotency_key, sender):
        calls.append((to, subject, html, text, idempotency_key, sender))
        delivered.add(idempotency_key)  # provider-side idempotency boundary

    monkeypatch.setattr(digest, "send_email", send)
    asyncio.run(Worker(store, heartbeat_factory=lambda: store).run_once())
    assert store.row["status"] == "retry_wait"
    # Even if preferences/data change, recovery sends the frozen package.
    monkeypatch.setattr(autopilot, "account_email", lambda *a: "changed@example.invalid")
    monkeypatch.setattr(settings, "DIGEST_FROM", "Changed sender <changed@example.invalid>")
    asyncio.run(Worker(store, heartbeat_factory=lambda: store).run_once())
    assert store.row["status"] == "succeeded"
    assert len(calls) == 2 and calls[0] == calls[1]
    assert len(delivered) == 1 and len(renders) == 1


def test_old_digest_stops_before_provider_call(monkeypatch):
    store = MemoryStore(kind="digest")
    store.row["checkpoints"]["digest_package"] = {"to": "owner@example.invalid", "subject": "Old", "html": "old", "text": "old",
        "prepared_at": (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()}
    monkeypatch.setattr(autopilot, "account_email", lambda *a: "owner@example.invalid")
    monkeypatch.setattr('app.workers.runner.discovery.load_preferences', lambda *a: WorkPreferences())
    async def forbidden(*a, **kw):
        raise AssertionError("expired package sent")
    monkeypatch.setattr(digest, "send_email", forbidden)
    asyncio.run(Worker(store, heartbeat_factory=lambda: store).run_once())
    assert store.row["status"] == "failed"
    assert "window expired" in store.row["error"]


def test_lost_lease_does_not_execute_or_write():
    store = MemoryStore()
    claimed = store.claim("worker")
    lost = threading.Event()
    lost.set()
    ctx = ExecutionContext(store, claimed, lost)
    async def forbidden():
        raise AssertionError("stale worker executed operation")
    with pytest.raises(runs.LeaseLost):
        asyncio.run(ctx.stage("jd_parsing", "Parse", forbidden))
    assert not store.row["checkpoints"] and not store.events_log


def test_cancelled_worker_leaves_lease_for_recovery():
    store = MemoryStore()
    class CancelledWorker(Worker):
        async def execute(self, ctx):
            raise asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(CancelledWorker(store, heartbeat_factory=lambda: store).run_once())
    assert store.row["status"] == "running"
    assert runs.current_execution.get() is None


def test_owned_status_sanitizes_inputs_and_rejects_strangers(monkeypatch):
    store = MemoryStore()
    seen = []
    def get(run_id, uid):
        seen.append(uid)
        return {**store.row, "inputs": {"secret": "private"}} if uid == USER_ID else None
    store.get = get
    monkeypatch.setattr(runs_api, "RunStore", lambda: store)
    result = asyncio.run(runs_api.get_run(uuid.UUID(store.row["id"]), CurrentUser(id=USER_ID, token="t", email="")))
    assert "inputs" not in result and "lease_token" not in result and "checkpoints" not in result
    with pytest.raises(HTTPException) as exc:
        asyncio.run(runs_api.get_run(uuid.UUID(store.row["id"]), CurrentUser(id="stranger", token="t", email="")))
    assert exc.value.status_code == 404 and seen == [USER_ID, "stranger"]


def test_websocket_replays_terminal_event_committed_between_reads(monkeypatch):
    events = [{"id": 1, "event": {"type": "status", "step": "queued", "status": "running"}}]
    class ReplayStore:
        def get(self, *a): return {"status": "succeeded"}
        def replay_cursor(self, *a): return 0
        def events(self, run_id, uid, cursor):
            if cursor == 0: return events
            if cursor == 1: return [{"id": 2, "event": {"type": "status", "step": "complete", "status": "success"}}]
            return []
    class Socket:
        def __init__(self): self.frames, self.closed = [], False
        async def send_json(self, value): self.frames.append(value)
        async def close(self, **kw): self.closed = True
    monkeypatch.setattr(run_stream, "get_supabase_client", lambda **kw: object())
    monkeypatch.setattr(run_stream, "RunStore", lambda *a: ReplayStore())
    socket = Socket()
    asyncio.run(run_stream.stream_run(socket, str(uuid.uuid4()), USER_ID, "token"))
    assert [f["event_id"] for f in socket.frames] == [1, 2] and socket.closed


def test_run_payload_rejects_credentials_and_empty_idempotency_key():
    store = runs.RunStore(client=object())
    with pytest.raises(ValueError): store.enqueue(USER_ID, "scan", {"user_token": "secret"})
    with pytest.raises(ValueError): store.enqueue(USER_ID, "scan", {}, "")


def test_deleted_generated_application_is_not_recreated(db, monkeypatch):
    store = MemoryStore(db)
    store.row["checkpoints"]["database_saving"] = {"application_id": str(uuid.uuid4())}
    asyncio.run(Worker(store, heartbeat_factory=lambda: store).run_once())
    assert store.row["status"] == "failed"
    assert "was deleted" in store.row["error"]
    assert store.material_commits == 0


def test_durable_intake_queues_verified_owner_without_in_process_work(monkeypatch):
    seen = []
    class IntakeStore:
        def enqueue(self, uid, kind, inputs, key):
            seen.append((uid, kind, inputs, key))
            return {"id": "persistent-run", "status": "queued"}
    monkeypatch.setattr(settings, "EXECUTION_MODE", "durable")
    monkeypatch.setattr(runs, "RunStore", IntakeStore)
    tasks = BackgroundTasks()
    result = asyncio.run(application_api.generate_application(
        application_api.ApplicationGenerateRequest(jd_text="Engineer at Globex"), tasks,
        CurrentUser(id=USER_ID, email="owner@example.invalid", token="private-jwt"), "request-identity"))
    assert result["run_id"] == "persistent-run" and result["status"] == "queued"
    assert not tasks.tasks
    assert seen == [(USER_ID, "application", {"jd_url": None, "jd_text": "Engineer at Globex", "source": "manual"}, "request-identity")]
