"""Regressions found running the pipeline against real providers."""

import asyncio
import json
from datetime import datetime, timezone

from app.agents import orchestrator, resume_tailor
from app.models.resume import Resume
from app.services.llm import FallbackEmbeddings
from app.services.websocket import manager
from test_application_flow import BASE_RESUME, USER_ID, db  # noqa: F401  (pytest fixture)


class _StructuredLLM:
    def __init__(self, result):
        self.result = result

    def with_structured_output(self, _schema):
        return self

    async def ainvoke(self, _prompt):
        return self.result


def test_tailored_content_is_json_safe_without_row_metadata(monkeypatch):
    # The model echoes the base resume's timestamps back as datetimes.
    echoed = Resume(**{**BASE_RESUME, "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})
    agent = resume_tailor.ResumeTailorAgent()
    monkeypatch.setattr(agent, "_get_best_llm", lambda: _StructuredLLM(echoed))
    monkeypatch.setattr(resume_tailor, "search_relevant", lambda *a, **k: [])

    result = asyncio.run(agent.tailor(BASE_RESUME, {"required_skills": ["Python"], "keywords": []}))
    json.dumps(result["content"])  # raises if anything non-JSON slipped through
    for key in resume_tailor.RESUME_METADATA_KEYS:
        assert key not in result["content"]


def test_template_fallback_is_reported(db, monkeypatch):
    async def failing_emails(self, jd, contact, profile):
        self.used_fallback = True
        return {"initial": {"subject": "Outreach", "body": "Hello"}}

    monkeypatch.setattr(orchestrator.EmailWriterAgent, "generate", failing_emails)
    asyncio.run(orchestrator.run_agent_pipeline("run-fallback", USER_ID, "t", jd_text="Senior ML Engineer"))
    events = manager.history["run-fallback"]
    warning = next(e for e in events if e["step"] == "outreach_generation" and e["status"] == "warning")
    assert "emails" in warning["message"] and "templates" in warning["message"]
    assert events[-1]["step"] == "complete"


def test_failed_save_removes_partial_application(db):
    db.missing_columns["tailored_resumes"] = {"content"}  # make the second insert fail
    asyncio.run(orchestrator.run_agent_pipeline("run-partial", USER_ID, "t", jd_text="Senior ML Engineer"))
    last = manager.history["run-partial"][-1]
    assert last["step"] == "database_saving" and last["status"] == "error"
    assert db.tables["job_applications"] == []


def test_embeddings_stop_calling_a_failing_primary():
    calls = {"primary": 0}

    class Primary:
        def embed_documents(self, texts):
            calls["primary"] += 1
            raise OSError("getaddrinfo failed")

        def embed_query(self, text):
            return self.embed_documents([text])[0]

    class Backup:
        def embed_documents(self, texts):
            return [[0.0] * 3 for _ in texts]

        def embed_query(self, text):
            return [0.0] * 3

    emb = FallbackEmbeddings(Primary(), Backup())
    for _ in range(3):
        assert emb.embed_documents(["a"]) == [[0.0, 0.0, 0.0]]
    assert emb.embed_query("b") == [0.0, 0.0, 0.0]
    assert calls["primary"] == 1


def test_ats_score_normalises_dashes_parentheticals_and_job_terms():
    from app.resume_engine.validator import calculate_ats_score

    tailored = {
        "summary": "Software engineering work: LLM\u2011powered agents and RAG pipelines at a startup",
        "skills": {"primary": ["Python", "LangChain"], "secondary": ["Vector databases"]},
    }
    jd = {
        "keywords": ["LLM-powered agents", "RAG pipelines", "remote"],
        "required_skills": ["Python", "software engineering (2-4 years)", "vector databases", "Kubernetes"],
    }
    score, missing = calculate_ats_score(tailored, jd)
    # "remote" describes the job, not the candidate, so it isn't scored at all.
    assert missing == ["kubernetes"]
    assert score == round(5 / 6 * 100, 1)


def test_tailoring_fallback_is_reported(db, monkeypatch):
    async def failing_tailor(self, base, jd):
        self.used_fallback = True
        return {"content": dict(base), "keyword_match_score": 14.0, "missing_keywords": ["rag"]}

    monkeypatch.setattr(orchestrator.ResumeTailorAgent, "tailor", failing_tailor)
    asyncio.run(orchestrator.run_agent_pipeline("run-tailor-fallback", USER_ID, "t", jd_text="Senior ML Engineer"))
    events = manager.history["run-tailor-fallback"]
    warning = next(e for e in events if e["step"] == "resume_tailoring" and e["status"] == "warning")
    assert "base resume unedited" in warning["message"]
