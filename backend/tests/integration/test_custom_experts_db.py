"""Day 14 against the throwaway Postgres (model and search faked): write a custom expert from a
template, see its policy preview, run it dry (nothing saved), activate it, run it on a case.
Fictional data only."""
import asyncio
import os
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("JOBDOTS_TEST_DATABASE_URL"),
                                reason="needs the throwaway database from scripts/check_database.py")

from app.config import settings  # noqa: E402
from app.core import cases  # noqa: E402
from app.db import get_db  # noqa: E402
from app.experts import artifacts, custom, runtime, spec  # noqa: E402
from app.services import brave  # noqa: E402
from app.services.auth import CurrentUser, get_current_user  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "resume"


class FakeModel:
    async def ainvoke(self, prompt):
        if "search queries" in prompt[0].content:
            return custom.Queries(queries=["Acme engineering teams", "Ada Example Acme"])      # the second names you: skipped
        return custom.Note(title="Who could refer you at Acme", body="The retrieval team [1] works on pgvector. It has 77 people.",
                           sources=[1])


@pytest.fixture()
def client(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app
    for name, value in {"RESUME_MASTER_PATH": str(FIXTURES / "master.tex"), "FACT_VAULT_PATH": str(FIXTURES / "fact_vault.yaml")}.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(custom.llm, "with_structured", lambda llm_, schema: FakeModel())
    import app.experts.email_outreach as eo
    monkeypatch.setattr(eo, "chat_model", lambda spec_: object())
    searches = []

    async def search(query, **kw):
        searches.append(query)
        return [brave.Result("https://acme.example/teams", "Acme teams", "Acme's retrieval team builds search on pgvector.")]
    monkeypatch.setattr(brave, "web_search", search)
    import app.api.v1.experts as experts_api
    monkeypatch.setattr(experts_api, "_require_worker", lambda: None)
    uid = str(uuid.uuid4())
    db = get_db()
    db.fetch("insert into auth.users(id, email) values (%s::uuid, %s)", [uid, f"{uid}@example.invalid"])
    spec.sync_builtins(db)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=uid, email="ada@example.invalid", token="t")
    try:
        yield TestClient(app), uid, searches
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        db.fetch("delete from public.agent_spec where owner = 'user' and user_id = %s::uuid", [uid])
        db.fetch("delete from auth.users where id = %s::uuid", [uid])


def test_write_preview_dry_run_activate_and_run(client):
    http, uid, searches = client
    case = cases.create_case(uid, company="Acme", role="ML Engineer", jd_text="Acme is hiring an ML Engineer for RAG on pgvector.")
    made = http.post("/api/v1/experts/custom", json={"template": "referral_hunter"}).json()
    agent = made["spec"]["id"]
    assert agent == "my_referral_hunter" and made["spec"]["status"] == "draft" and made["problems"] == []
    assert any("send email" in n for n in made["preview"]["never"])
    assert http.post(f"/api/v1/experts/custom/{agent}/activate").status_code == 409          # not before a dry run

    dry = http.post(f"/api/v1/experts/custom/{agent}/dry-run", json={"case_id": case["id"]}).json()
    assert dry["dry_run"] and dry["note"]["title"] == "Who could refer you at Acme"
    assert dry["note"]["checks"] == ["Check 77: not in your facts, the case or the sources."]
    assert searches == ["Acme engineering teams"]                                            # your own name never searched
    assert artifacts.latest(uid, case["id"], "note") is None                                 # a dry run saves nothing
    assert http.post(f"/api/v1/experts/custom/{agent}/activate").json()["spec"]["status"] == "active"

    # Run it for real on the case (as the worker would).
    ctx = runtime.ExpertContext(uid, spec.load_spec(get_db(), agent), case["id"], {})
    out = asyncio.run(runtime.run_expert(ctx))
    note = artifacts.latest(uid, case["id"], "note")["content"]
    assert out["checks"] and note["sources"][0]["url"] == "https://acme.example/teams"
    assert cases.get_case(uid, case["id"])["events"][-1]["summary"] == "Referral Hunter wrote a note: Who could refer you at Acme"
    roster = {e["id"]: e for e in http.get("/api/v1/experts").json()["experts"]}
    assert roster[agent]["owner"] == "user" and roster[agent]["status"] == "active"

    # Editing puts it back to draft; it must be run dry again.
    edited = http.put(f"/api/v1/experts/custom/{agent}", json={"name": "Referral Hunter", "role": "x",
                      "instructions": "List teams at the company that match the candidate, and why.", "tools": ["read_case", "save_artifact"]}).json()
    assert edited["spec"]["status"] == "draft" and edited["dry_run_ok_at"] is None
    bad = http.put(f"/api/v1/experts/custom/{agent}", json={"name": "Referral Hunter", "instructions": "List teams at the company, and why.",
                   "tools": ["read_case", "save_artifact", "propose_action"]}).json()
    assert any("can't use propose_action" in p for p in bad["problems"])
    assert http.post(f"/api/v1/experts/cases/{case['id']}/run/{agent}").status_code == 409
    assert http.delete(f"/api/v1/experts/custom/{agent}").status_code == 204
    assert http.get(f"/api/v1/experts/custom/{agent}").status_code == 404
