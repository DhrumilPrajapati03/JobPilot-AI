"""Day 9 against the throwaway Postgres: the dashboard read, and editing a draft from the web
(it goes back through the Reviewer and can be approved again). Fictional data; no network."""
import os
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("JOBDOTS_TEST_DATABASE_URL"),
                                reason="needs the throwaway database from scripts/check_database.py")

from app.api.v1 import dashboard  # noqa: E402
from app.config import settings  # noqa: E402
from app.core import actions, cases  # noqa: E402
from app.db import get_db  # noqa: E402
from app.experts import rereview, spec  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "resume"
JOB = "Acme is hiring an ML Engineer to build RAG on pgvector with FastAPI."


@pytest.fixture()
def owner(monkeypatch):
    for name, value in {"RESUME_MASTER_PATH": str(FIXTURES / "master.tex"), "FACT_VAULT_PATH": str(FIXTURES / "fact_vault.yaml")}.items():
        monkeypatch.setattr(settings, name, value)
    uid = str(uuid.uuid4())
    db = get_db()
    db.fetch("insert into auth.users(id, email) values (%s::uuid, %s)", [uid, f"{uid}@example.invalid"])
    spec.sync_builtins(db)
    yield uid
    db.fetch("delete from auth.users where id = %s::uuid", [uid])


def test_dashboard_counts_the_pipeline_and_scrubs_errors(owner):
    uid = owner
    a = cases.create_case(uid, company="Acme", role="ML Engineer", jd_text=JOB)
    b = cases.create_case(uid, company="Globex", role="AI Engineer", jd_text=JOB)
    cases.set_stage(uid, a["id"], "applied", actor="user")
    cases.set_stage(uid, b["id"], "interview", actor="user")
    get_db().fetch("""insert into public.agent_runs (user_id, kind, idempotency_key, inputs, status, last_error, case_id)
                      values (%s::uuid, 'agent', %s, '{"agent": "connector"}'::jsonb, 'failed', %s, %s::uuid)""",
                   [uid, f"t:{uuid.uuid4()}", "Groq said api_key=sk-secret-123 was rejected\nTraceback ...", a["id"]])
    d = dashboard.summary(uid)
    assert d["pipeline"]["week"]["found"] == 2 and d["pipeline"]["week"]["applied"] == 2
    assert d["pipeline"]["week"]["replied"] == 1 and d["pipeline"]["week"]["interviews"] == 1
    failed = d["ops"]["failed"][0]
    assert failed["agent"] == "connector" and failed["company"] == "Acme"
    assert "sk-secret" not in failed["error"] and "Traceback" not in failed["error"] and "[hidden]" in failed["error"]
    assert d["ops"]["sent_today"]["emails"][1] is not None


def test_editing_an_email_from_the_web_reviews_it_again(owner):
    uid = owner
    case = cases.create_case(uid, company="Acme", role="ML Engineer", jd_text=JOB)
    body = ("Hi Jane,\n\nAcme is building RAG on pgvector. At Example Labs I built a RAG service on PostgreSQL and pgvector "
            "that answers support questions for 40 teams.\n\nWould you consider my application for the ML Engineer role?\n\nAda Example")
    payload = {"to": "jane@acme.example", "to_name": "Jane", "subject": "ML Engineer at Acme", "body": body, "company": "Acme",
               "contact_id": None, "attachment": None}
    action = actions.propose(uid, "send_email", payload, agent="email_outreach", idempotency_key=f"t:{uuid.uuid4()}", case_id=case["id"])
    actions.review(uid, action["id"], ok=True)
    good = rereview.edit_and_review(uid, action["id"], {**payload, "subject": "ML Engineer role at Acme"})
    assert good["status"] == "reviewed" and good["revision"] == 2                 # approvable again
    bad = rereview.edit_and_review(uid, action["id"], {**payload, "body": body.replace("40 teams", "400 teams")})
    assert bad["status"] == "blocked" and "400" in bad["block_reason"]
