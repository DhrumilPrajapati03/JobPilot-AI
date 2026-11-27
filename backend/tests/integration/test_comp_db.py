"""Day 12 against the throwaway Postgres (search and model faked): Comp Analyst writes a cited
pay report, keeps only quoted figures, respects its search caps, and the Answerer shows the
research next to pay questions without ever answering pay from it. Fictional data only."""
import asyncio
import os
import re
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("JOBDOTS_TEST_DATABASE_URL"),
                                reason="needs the throwaway database from scripts/check_database.py")

from app.config import settings  # noqa: E402
from app.core import cases  # noqa: E402
from app.core import policy as policy_mod  # noqa: E402
from app.db import get_db  # noqa: E402
from app.experts import answerer, artifacts, comp_analyst, runtime, spec  # noqa: E402
from app.services import brave  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "resume"
JOB = "Acme is hiring an ML Engineer in Bengaluru, India to build RAG on pgvector."


class FakeModel:
    def __init__(self):
        self.prompts = []

    async def ainvoke(self, prompt):
        self.prompts.append(prompt)
        if prompt[0].content.startswith("You get candidate sentences about pay"):
            ids = re.findall(r"^\[(c\d+)\]", prompt[1].content, re.M)
            # Every real candidate, plus an id that doesn't exist (dropped: the model can't add text).
            return comp_analyst.Picks(picks=[comp_analyst.Pick(id=i, basis="ML Engineer") for i in ids] +
                                      [comp_analyst.Pick(id="c99", basis="made up")])
        return answerer.Drafts(answers=[])


@pytest.fixture()
def owner(monkeypatch):
    for name, value in {"RESUME_MASTER_PATH": str(FIXTURES / "master.tex"), "FACT_VAULT_PATH": str(FIXTURES / "fact_vault.yaml")}.items():
        monkeypatch.setattr(settings, name, value)
    model = FakeModel()
    monkeypatch.setattr(comp_analyst.llm, "with_structured", lambda llm_, schema: model)
    import app.experts.email_outreach as eo
    monkeypatch.setattr(eo, "chat_model", lambda spec_: object())
    calls = []

    async def search(query, **kw):
        calls.append(query)
        return [brave.Result("https://pay.example/acme", "Acme ML Engineer salary", "ML Engineer salary at Acme ranges from 18 LPA to 28 LPA."),
                brave.Result("https://pay.example/india", "ML Engineer salary India", "ML Engineers in India earn 14-24 LPA.")]
    monkeypatch.setattr(brave, "web_search", search)
    uid = str(uuid.uuid4())
    db = get_db()
    db.fetch("insert into auth.users(id, email) values (%s::uuid, %s)", [uid, f"{uid}@example.invalid"])
    spec.sync_builtins(db)
    yield uid, calls, monkeypatch
    db.fetch("delete from auth.users where id = %s::uuid", [uid])


def run(uid, agent, case_id, inputs=None):
    ctx = runtime.ExpertContext(uid, spec.load_spec(get_db(), agent), case_id, inputs or {})
    return asyncio.run(runtime.run_expert(ctx))


def test_comp_report_then_pay_questions(owner):
    uid, calls, _ = owner
    case = cases.create_case(uid, company="Acme", role="ML Engineer", jd_text=JOB)
    out = run(uid, "comp_analyst", case["id"])
    assert len(calls) == 3 and calls[1] == "ML Engineer salary India"           # comp_searches_per_run = 3; no personal data
    assert out["ranges"] == 2                                                    # the made-up 40-60 isn't in any source
    report = artifacts.latest(uid, case["id"], "comp_report")["content"]
    assert report["market"]["low"] == 17 * 100_000 and report["market"]["high"] == 25 * 100_000
    assert report["suggested"]["low"] == 21 * 100_000                           # the fixture vault has no expected floor
    assert {s["url"] for s in report["sources"]} == {"https://pay.example/acme", "https://pay.example/india"}
    timeline = [e["summary"] for e in cases.get_case(uid, case["id"])["events"]]
    assert any(t.startswith("Comp Analyst: market 17–25 LPA (2 sources); suggested ask 21–25 LPA") for t in timeline)

    result = run(uid, "answerer", case["id"], {"url": "https://x", "questions": [
        {"key": "ctc", "label": "Expected CTC (in LPA)", "type": "text", "options": [], "required": True},
        {"key": "cur", "label": "Current CTC", "type": "text", "options": [], "required": True}]})
    card = {a["key"]: a for a in get_db().fetch("select content from public.artifact where id = %s::uuid",
                                                [result["artifact_id"]])[0][0]["answers"]}
    # The fixture vault has no confirmed pay figures: never a number from research, it's yours to decide.
    assert card["ctc"]["value"] is None and card["ctc"]["badge"] == "needs_you" and card["ctc"]["flagged"]
    assert card["ctc"]["note"].startswith("No confirmed pay figure in your vault. Comp Analyst:")
    assert "suggested ask 21–25 LPA" in card["ctc"]["note"] and card["cur"]["value"] is None


def test_pay_searches_stop_at_the_daily_cap(owner):
    uid, calls, monkeypatch = owner
    capped = policy_mod.load_policy("""
version: 1
action_modes: {save_artifact: act}
caps: {emails_per_day: 1, linkedin_invites_per_day: 1, linkedin_invites_per_week: 1, linkedin_dms_per_day: 1,
       max_people_per_company: 3, min_hours_accept_to_dm: 24, no_contact_if_touched_within_days: 14,
       comp_searches_per_run: 3, comp_searches_per_day: 4, quiet_hours: "", timezone: UTC}
""")
    monkeypatch.setattr(comp_analyst, "load_policy", lambda: capped)
    first = cases.create_case(uid, company="Acme", role="ML Engineer", jd_text=JOB)
    second = cases.create_case(uid, company="Globex", role="ML Engineer", jd_text="Globex pays 20-30 LPA for an ML Engineer.")
    run(uid, "comp_analyst", first["id"])
    run(uid, "comp_analyst", second["id"])
    assert len(calls) == 4                                                       # 3, then only 1 left today
    report = artifacts.latest(uid, second["id"], "comp_report")["content"]
    assert report["jd_range"]["low"] == 20 * 100_000 and report["suggested"]["high"] == 30 * 100_000
