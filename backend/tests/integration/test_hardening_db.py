"""Day 16 on the throwaway Postgres: Telegram alerts are sent once and in order, failing experts
and the budget alert once per period; deep health names what to fix. Fictional data."""
import os
import uuid
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("JOBDOTS_TEST_DATABASE_URL"),
                                reason="needs the throwaway database from scripts/check_database.py")

from app.api.v1 import health  # noqa: E402
from app.core import cases  # noqa: E402
from app.db import get_db  # noqa: E402
from app.telegram import alerts  # noqa: E402


@pytest.fixture()
def owner():
    uid = str(uuid.uuid4())
    db = get_db()
    db.fetch("insert into auth.users(id, email) values (%s::uuid, %s)", [uid, f"{uid}@example.invalid"])
    db.fetch("insert into public.telegram_state (user_id, chat_id) values (%s::uuid, 42)", [uid])
    yield uid
    db.fetch("delete from auth.users where id = %s::uuid", [uid])


def test_alerts_once_in_order_and_never_history(owner):
    uid = owner
    case = cases.create_case(uid, company="Acme", role="ML Engineer")
    cases.add_event(uid, case["id"], "reply", actor="agent", actor_name="inbox", summary="Old reply before alerts existed")
    assert alerts.pending(uid) == []                                  # first run starts from now: no replay
    cases.add_event(uid, case["id"], "reply", actor="agent", actor_name="inbox", summary="Jane Example replied: thanks <b>")
    cases.add_event(uid, case["id"], "note", actor="agent", actor_name="inbox", summary="A quiet note")
    cases.add_event(uid, case["id"], "interview", actor="agent", actor_name="inbox", summary="Jane wants to talk")
    sent = alerts.pending(uid)
    assert sent == ["💬 <b>Acme</b>: Jane Example replied: thanks &lt;b&gt;", "📅 <b>Acme</b>: Jane wants to talk"]
    assert alerts.pending(uid) == []                                  # once

    for _ in range(2):
        get_db().fetch("""insert into public.agent_runs (user_id, kind, idempotency_key, inputs, status, last_error)
                          values (%s::uuid, 'agent', %s, '{"agent": "connector"}'::jsonb, 'failed', 'token=abc123 broke')""",
                       [uid, f"t:{uuid.uuid4()}"])
    failing = alerts.pending(uid)
    assert len(failing) == 1 and failing[0].startswith("⚠️ <b>Connector</b> failed 2 times") and "abc123" not in failing[0]
    assert alerts.pending(uid) == []                                  # once a day per expert


def test_deep_health_says_what_to_fix(owner):
    uid = owner
    checks = {c["name"]: c for c in health.checks(uid, now=datetime.now(timezone.utc))}
    assert checks["Database"]["status"] == "ok" and checks["Migrations"]["status"] == "ok"
    assert checks["Google"]["status"] == "warn" and "connect_google.py" in checks["Google"]["detail"]
    assert checks["Routines"]["status"] == "warn"                     # the Gmail check hasn't run for this new owner
    assert {"Worker", "Queue", "Backups", "Telegram", "Models", "Search", "Disk"} <= set(checks)
    assert all("key" not in c["detail"].lower() or "present" in c["detail"] or "No " in c["detail"] for c in checks.values())
