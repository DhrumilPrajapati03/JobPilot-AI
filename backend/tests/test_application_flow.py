"""End-to-end test of the application flow against an in-memory Supabase.

JD → agent pipeline (LLM agents stubbed) → tracker → detail → edits →
status changes → analytics → delete. Runs both with and without the
``cover_letter`` / ``linkedin_dm`` columns from the materials migration.
"""

import asyncio
import copy
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.agents import orchestrator
from app.api.v1 import analytics, answers, applications, profile, resume
from app.main import app
from app.models.application import JDAnalysis
from app.services.auth import CurrentUser, get_current_user
from app.services.websocket import manager

USER_ID = "user-1"


class FakeResult:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class FakeQuery:
    def __init__(self, db: "FakeSupabase", table: str):
        self.db, self.table = db, table
        self.op, self.payload = "select", None
        self.filters, self.orders = [], []
        self.window, self.want_count = None, False

    def select(self, _cols="*", count=None):
        self.want_count = count is not None
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def upsert(self, payload, on_conflict="", ignore_duplicates=False):
        self.op, self.payload = "upsert", payload
        self.ignore_duplicates = ignore_duplicates
        self.conflict_cols = [c.strip() for c in on_conflict.split(",") if c.strip()] or ["id"]
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, col, val):
        self.filters.append(lambda r: r.get(col) == val)
        return self

    def in_(self, col, vals):
        self.filters.append(lambda r: r.get(col) in vals)
        return self

    def order(self, col, desc=False):
        self.orders.append((col, desc))
        return self

    def range(self, start, end):
        self.window = (start, end + 1)
        return self

    def limit(self, n):
        self.window = (0, n)
        return self

    def _check_columns(self, row: dict):
        for col in row:
            if col in self.db.missing_columns.get(self.table, set()):
                raise Exception(f"{{'code': 'PGRST204', 'message': \"Could not find the '{col}' column\"}}")

    def execute(self):
        rows = self.db.tables.setdefault(self.table, [])
        if self.op == "insert":
            new_rows = self.payload if isinstance(self.payload, list) else [self.payload]
            created = []
            for row in new_rows:
                self._check_columns(row)
                created.append({"id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc).isoformat(), **row})
            rows.extend(created)
            return FakeResult(copy.deepcopy(created))

        if self.op == "upsert":
            written = []
            for row in self.payload if isinstance(self.payload, list) else [self.payload]:
                self._check_columns(row)
                existing = next((r for r in rows if all(r.get(c) == row.get(c) for c in self.conflict_cols)), None)
                if existing is not None:
                    if not self.ignore_duplicates:
                        existing.update(copy.deepcopy(row))
                    written.append(existing)
                else:
                    created = {"id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc).isoformat(), **row}
                    rows.append(created)
                    written.append(created)
            return FakeResult(copy.deepcopy(written))

        matched = [r for r in rows if all(f(r) for f in self.filters)]
        if self.op == "update":
            self._check_columns(self.payload)
            for r in matched:
                r.update(copy.deepcopy(self.payload))
            return FakeResult(copy.deepcopy(matched))
        if self.op == "delete":
            self.db.tables[self.table] = [r for r in rows if r not in matched]
            return FakeResult(copy.deepcopy(matched))

        for col, desc in reversed(self.orders):
            matched.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
        total = len(matched)
        if self.window:
            matched = matched[self.window[0]:self.window[1]]
        return FakeResult(copy.deepcopy(matched), total if self.want_count else None)


class FakeSupabase:
    def __init__(self, missing_columns=None):
        self.tables: dict[str, list[dict]] = {}
        self.missing_columns = missing_columns or {}

    def table(self, name):
        return FakeQuery(self, name)


BASE_RESUME = {
    "id": "resume-1",
    "user_id": USER_ID,
    "version": "base",
    "name": "Ada Lovelace",
    "headline": "ML Engineer",
    "summary": "Builds retrieval systems.",
    "experience": [{"company": "Acme", "role": "Engineer", "duration": "2021-2024", "bullets": ["Built RAG"]}],
    "skills": {"primary": ["Python", "LangChain"], "secondary": ["Docker"]},
    "projects": [],
    "education": [{"institution": "MIT", "degree": "BSc", "year": "2020"}],
    "certifications": [],
}


@pytest.fixture(params=[False, True], ids=["with-migration", "without-migration"])
def db(request, monkeypatch):
    missing = {"job_applications": {"cover_letter", "linkedin_dm"}} if request.param else {}
    fake = FakeSupabase(missing)
    fake.tables["user_profiles"] = [{"id": USER_ID, "name": "Ada Lovelace", "location": "London"}]
    fake.tables["resumes"] = [copy.deepcopy(BASE_RESUME)]
    for module in (orchestrator, applications, resume, analytics, answers, profile):
        monkeypatch.setattr(module, "get_supabase_client", lambda user_jwt=None: fake)

    async def parse(self, jd_url=None, jd_text=None):
        return JDAnalysis(
            role="ML Engineer", company="Globex", seniority="Senior",
            required_skills=["Python", "Kubernetes"], keywords=["RAG"],
        )

    async def tailor(self, base, jd):
        return {"content": {**base, "summary": "RAG and Python expert."}, "keyword_match_score": 66.7, "missing_keywords": ["kubernetes"]}

    async def no_pdf(content):
        raise RuntimeError("WeasyPrint external GTK libraries are missing")

    async def cover(self, jd, profile, research=None):
        return "Dear Globex team, ..."

    async def emails(self, jd, contact, profile):
        return {k: {"subject": f"{k} subject", "body": f"{k} body"} for k in ("initial", "follow_up_1", "follow_up_2")}

    async def dms(self, jd, contact, profile):
        return {"connection_request": "Hi, let's connect!", "follow_up": "Thanks for connecting."}

    monkeypatch.setattr(orchestrator.JDParserAgent, "parse", parse)
    monkeypatch.setattr(orchestrator.ResumeTailorAgent, "tailor", tailor)
    monkeypatch.setattr(orchestrator, "render_resume_pdf", no_pdf)
    monkeypatch.setattr(orchestrator.CoverLetterAgent, "generate", cover)
    monkeypatch.setattr(orchestrator.EmailWriterAgent, "generate", emails)
    monkeypatch.setattr(orchestrator.DMWriterAgent, "generate", dms)
    monkeypatch.setattr(resume, "render_resume_pdf", no_pdf)
    return fake


@pytest.fixture
def client(monkeypatch):
    from app.services import auth
    async def verify(token):
        if token != "test-session":
            from fastapi import HTTPException
            raise HTTPException(401, "Invalid token")
        return {"sub": USER_ID, "email": "ada@example.com"}
    monkeypatch.setattr(auth, "_verify_token", verify)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=USER_ID, token="t", email="ada@example.com")
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_full_application_flow(db, client):
    run_id = "run-1"
    asyncio.run(orchestrator.run_agent_pipeline(run_id, USER_ID, "t", jd_text="Senior ML Engineer at Globex"))

    events = manager.history[run_id]
    assert events[-1]["step"] == "complete" and events[-1]["status"] == "success", events[-1]
    assert any(e["step"] == "pdf_rendering" and e["status"] == "warning" for e in events)
    app_id = events[-1]["application_id"]

    # Late WebSocket subscribers get the full replay.
    with client.websocket_connect(f"/ws/agent-stream/{run_id}") as ws:
        ws.send_json({"token": "test-session"})
        replayed = [ws.receive_json() for _ in events]
    assert [e["step"] for e in replayed] == [e["step"] for e in events]

    listing = client.get("/api/v1/applications/").json()
    assert listing["total"] == 1
    assert listing["applications"][0]["keyword_match_score"] == 66.7

    detail = client.get(f"/api/v1/applications/{app_id}").json()
    assert detail["application"]["cover_letter"] == "Dear Globex team, ..."
    assert detail["application"]["linkedin_dm"]["connection_request"] == "Hi, let's connect!"
    assert detail["application"]["notes"] == ""
    assert [e["sequence_number"] for e in detail["cold_emails"]] == [1, 2, 3]
    # cold_emails.user_id is NOT NULL and RLS-checked in Supabase.
    assert all(e["user_id"] == USER_ID for e in db.tables["cold_emails"])

    # Edit materials and user notes independently.
    res = client.patch(f"/api/v1/applications/{app_id}", json={"cover_letter": "Edited letter", "notes": "Call Bob"})
    assert res.status_code == 200, res.text
    detail = client.get(f"/api/v1/applications/{app_id}").json()["application"]
    assert detail["cover_letter"] == "Edited letter"
    assert detail["notes"] == "Call Bob"
    assert detail["linkedin_dm"]["follow_up"] == "Thanks for connecting."

    # Applying stamps applied_at and schedules a follow-up.
    res = client.put(f"/api/v1/applications/{app_id}/status", json={"status": "applied"})
    assert res.status_code == 200, res.text
    assert res.json()["application"]["applied_at"] and res.json()["application"]["follow_up_at"]
    assert client.put(f"/api/v1/applications/{app_id}/status", json={"status": "bogus"}).status_code == 422

    email_id = client.get(f"/api/v1/applications/{app_id}").json()["cold_emails"][0]["id"]
    res = client.put(f"/api/v1/applications/{app_id}/emails/{email_id}", json={"subject": "New subject", "sent": True})
    assert res.status_code == 200 and res.json()["sent_at"] and res.json()["subject"] == "New subject"

    # Editing the tailored resume re-scores it.
    tailored = client.get(f"/api/v1/resume/tailored/{app_id}").json()
    content = {**tailored["content"], "summary": "Python, RAG and Kubernetes."}
    res = client.put(f"/api/v1/resume/tailored/{app_id}", json=content)
    assert res.status_code == 200, res.text
    assert res.json()["keyword_match_score"] == 100.0

    assert client.get(f"/api/v1/resume/tailored/{app_id}/pdf").status_code == 503

    summary = client.get("/api/v1/analytics/summary").json()
    assert summary["total_applications"] == 1
    assert summary["status_breakdown"]["applied"] == 1
    assert summary["emails_sent"] == 1
    assert summary["avg_keyword_score"] == 100.0
    assert sum(w["count"] for w in summary["weekly_applications"]) == 1

    assert client.delete(f"/api/v1/applications/{app_id}").status_code == 204
    assert client.get(f"/api/v1/applications/{app_id}").status_code == 404
    assert db.tables["cold_emails"] == [] and db.tables["tailored_resumes"] == []


def test_pipeline_reports_missing_base_resume(db):
    db.tables["resumes"] = []
    asyncio.run(orchestrator.run_agent_pipeline("run-2", USER_ID, "t", jd_text="Some JD"))
    last = manager.history["run-2"][-1]
    assert last["step"] == "profile_loading" and last["status"] == "error"
    assert "base resume" in last["message"]


def test_unknown_run_is_reported(client):
    with client.websocket_connect("/ws/agent-stream/does-not-exist") as ws:
        ws.send_json({"token": "test-session"})
        assert ws.receive_json()["type"] == "unknown_run"


def test_generate_requires_jd(client):
    assert client.post("/api/v1/applications/generate", json={"jd_text": "   "}).status_code == 400
