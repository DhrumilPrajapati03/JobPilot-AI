"""Phase 1: skip rules in the pipeline, skill-gap insights and the answer bank."""

import asyncio

from app.agents import assistant, orchestrator
from app.services.websocket import manager
from test_application_flow import USER_ID, client, db  # noqa: F401  (pytest fixtures)


def test_pipeline_flags_skip_rules_but_still_creates_application(db):
    db.tables["user_profiles"][0]["work_preferences"] = {
        "skip_keywords": ["security clearance"],
        "blocked_companies": ["Globex"],
        "remote_only": False,
    }
    asyncio.run(orchestrator.run_agent_pipeline("run-skip", USER_ID, "t", jd_text="Requires an active Security Clearance."))
    events = manager.history["run-skip"]
    warning = next(e for e in events if e["step"] == "jd_parsing" and e["status"] == "warning")
    assert "blocked companies" in warning["message"] and "security clearance" in warning["message"]
    assert events[-1]["step"] == "complete"
    app = db.tables["job_applications"][0]
    assert len(app["jd_analysis"]["skip_flags"]) == 2
    assert app["jd_text"] == "Requires an active Security Clearance."


def test_skill_gaps_separate_learnable_from_unsurfaced(db, client):
    db.tables["resumes"][0]["experience"][0]["bullets"] = ["Ran services on Kubernetes"]
    for i, missing in enumerate([["kubernetes", "go"], ["go"], ["rust"]]):
        db.tables.setdefault("job_applications", []).append({
            "id": f"a{i}", "user_id": USER_ID, "role": f"Role {i}", "company": f"Co {i}", "status": "saved",
            "jd_analysis": {"required_skills": ["Python", "Go"], "tech_stack": ["Kubernetes"]},
        })
        db.tables.setdefault("tailored_resumes", []).append(
            {"id": f"t{i}", "application_id": f"a{i}", "user_id": USER_ID, "version": 1, "missing_keywords": missing}
        )
    data = client.get("/api/v1/analytics/skill-gaps").json()
    assert data["applications_analyzed"] == 3
    gaps = {g["keyword"].lower(): g for g in data["gaps"]}  # shown with the JD's casing
    assert gaps["go"]["count"] == 2 and gaps["go"]["in_base_resume"] is False
    assert gaps["kubernetes"]["in_base_resume"] is True  # already in a bullet: a tailoring fix
    requested = {r["skill"]: r for r in data["most_requested"]}
    assert requested["Python"]["count"] == 3 and requested["Python"]["you_have"] is True
    assert requested["Go"]["you_have"] is False


def test_answer_bank_upserts_by_question_and_hides_sensitive_from_llm(db, client):
    res = client.put("/api/v1/answers/", json={"answers": [
        {"question": "Notice period", "answer": "15 days", "category": "availability"},
        {"question": "Gender", "answer": "Decline to self-identify", "category": "eeo", "sensitive": True},
    ]})
    assert res.status_code == 200, res.text
    client.put("/api/v1/answers/", json={"answers": [{"question": "Notice period", "answer": "30 days", "category": "availability"}]})
    saved = client.get("/api/v1/answers/").json()["answers"]
    assert {a["question"]: a["answer"] for a in saved} == {"Gender": "Decline to self-identify", "Notice period": "30 days"}

    user = assistant.CurrentUser(id=USER_ID, token="t")
    llm_view = asyncio.run(assistant.execute_tool("get_saved_answers", {}, user))["answers"]
    assert llm_view == [{"question": "Notice period", "answer": "30 days"}]

    answer_id = next(a["id"] for a in saved if a["question"] == "Gender")
    assert client.delete(f"/api/v1/answers/{answer_id}").status_code == 204
    assert len(client.get("/api/v1/answers/").json()["answers"]) == 1


def test_missing_answer_table_gives_actionable_error(client, monkeypatch):
    from app.api.v1 import answers

    class Broken:
        def table(self, _name):
            raise Exception("{'code': 'PGRST205', 'message': \"Could not find the table 'public.qa_answers'\"}")

    monkeypatch.setattr(answers, "get_supabase_client", lambda user_jwt=None: Broken())
    res = client.get("/api/v1/answers/")
    assert res.status_code == 503 and "20261010_answer_bank.sql" in res.json()["detail"]
