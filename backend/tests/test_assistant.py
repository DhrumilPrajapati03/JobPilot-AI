"""Chat assistant: tool loop, proposals and SSE streaming with a scripted LLM."""

import asyncio
import json

from langchain_core.messages import AIMessageChunk, ToolMessage

from app.agents import assistant
from app.services.websocket import manager
from test_application_flow import USER_ID, client, db  # noqa: F401  (pytest fixtures)

APP_ID = "0b0c9b3e-5d55-4b0a-9a39-9a7a2c1e0001"


class ScriptedLLM:
    """Stands in for a chat model: each astream() call replays the next scripted turn."""

    def __init__(self, turns):
        self.turns = turns
        self.calls: list[list] = []

    def bind_tools(self, _tools):
        return self

    async def astream(self, messages):
        self.calls.append(list(messages))
        turn = self.turns[len(self.calls) - 1]
        for chunk in turn(messages) if callable(turn) else turn:
            yield chunk


def tool_call(name, args, call_id):
    payload = json.dumps(args)
    # Split the JSON across chunks like a real stream does.
    return [
        AIMessageChunk(content="", tool_call_chunks=[{"name": name, "args": payload[:5], "id": call_id, "index": 0}]),
        AIMessageChunk(content="", tool_call_chunks=[{"name": None, "args": payload[5:], "id": None, "index": 0}]),
    ]


def text(*parts):
    return [AIMessageChunk(content=p) for p in parts]


def seed_application(db):
    db.tables["job_applications"] = [{
        "id": APP_ID, "user_id": USER_ID, "company": "Globex", "role": "ML Engineer", "status": "saved",
        "created_at": "2026-10-01T00:00:00+00:00", "jd_analysis": {"company_type": "mnc", "required_skills": ["Python"]},
        "notes": "", "cover_letter": "Dear Globex", "linkedin_dm": {},
    }]
    db.tables["tailored_resumes"] = [{
        "id": "t-1", "application_id": APP_ID, "user_id": USER_ID, "version": 1, "content": {},
        "keyword_match_score": 72.0, "missing_keywords": ["kubernetes"],
    }]
    db.tables["cold_emails"] = [{"id": "e-1", "application_id": APP_ID, "sequence_number": 1, "subject": "Hi", "body": "Hello"}]


def parse_sse(body: str) -> list[dict]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


def test_assistant_reads_proposes_creates_and_opens_views(db, client, monkeypatch):
    seed_application(db)

    def final_turn(messages):
        # The model must have seen every tool result before answering.
        tool_results = [m for m in messages if isinstance(m, ToolMessage)]
        assert len(tool_results) == 4
        return text("Proposed the move ", "and started your application.")

    llm = ScriptedLLM([
        tool_call("list_applications", {"status": "saved"}, "c1"),
        tool_call("propose_status_change", {"application_id": APP_ID, "status": "applied", "reason": "You applied"}, "c2"),
        tool_call("create_application", {"jd_text": "Senior ML Engineer at Initech"}, "c3"),
        tool_call("open_view", {"view": "detail", "application_id": APP_ID, "tab": "email"}, "c4"),
        final_turn,
    ])
    monkeypatch.setattr(assistant, "get_agent_llm", lambda: llm)

    res = client.post("/api/v1/agent/chat", json={"messages": [{"role": "user", "content": "What should I do?"}]})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(res.text)

    results = {e["name"]: e["result"] for e in events if e["type"] == "tool_result"}
    assert results["list_applications"]["applications"][0]["id"] == APP_ID
    assert results["list_applications"]["applications"][0]["match_score"] == 72.0

    proposal = results["propose_status_change"]
    assert proposal["action"] == "update_status" and proposal["awaiting_approval"]
    assert proposal["args"] == {"application_id": APP_ID, "status": "applied"}
    # Proposals never write: the application is still saved.
    assert db.tables["job_applications"][0]["status"] == "saved"

    run_id = results["create_application"]["run_id"]
    assert run_id in manager.history
    # The UI gets the run id; the model never sees it (so it can't repeat it).
    assert run_id not in llm.calls[-1][-2].content and run_id not in "".join(m.content for m in llm.calls[-1] if isinstance(m, ToolMessage))
    assert results["open_view"] == {"opened": "detail", "application_id": APP_ID, "tab": "email"}

    assert "".join(e["delta"] for e in events if e["type"] == "text") == "Proposed the move and started your application."
    assert events[-1]["type"] == "done"

    # Untrusted-data guidance reached the system prompt.
    assert "untrusted data" in llm.calls[0][0].content


def test_tool_errors_are_reported_not_raised(db):
    user = assistant.CurrentUser(id=USER_ID, token="t")
    missing = asyncio.run(assistant.execute_tool("get_application", {"application_id": "nope"}, user))
    assert "not found" in missing["error"].lower()
    assert "Unknown tool" in asyncio.run(assistant.execute_tool("drop_tables", {}, user))["error"]
    assert "needs an application_id" in asyncio.run(assistant.execute_tool("open_view", {"view": "detail"}, user))["error"]


def test_email_proposal_resolves_email_id(db):
    seed_application(db)
    user = assistant.CurrentUser(id=USER_ID, token="t")
    result = asyncio.run(assistant.execute_tool(
        "propose_email_draft",
        {"application_id": APP_ID, "sequence_number": 1, "subject": "New", "body": "Better"},
        user,
    ))
    assert result["action"] == "update_email"
    assert result["args"]["email_id"] == "e-1"
    assert result["current"]["subject"] == "Hi"


def test_removed_views_are_rejected(db):
    user = assistant.CurrentUser(id=USER_ID, token="t")
    assert "Unknown view" in asyncio.run(assistant.execute_tool("open_view", {"view": "arena"}, user))["error"]


def test_open_view_rejects_made_up_application_ids(db):
    user = assistant.CurrentUser(id=USER_ID, token="t")
    result = asyncio.run(assistant.execute_tool("open_view", {"view": "detail", "application_id": "app_12345"}, user))
    assert "not found" in result["error"].lower()


def test_resume_edit_proposal_flags_invented_numbers_and_skills(db):
    seed_application(db)
    db.tables["tailored_resumes"][0]["content"] = {
        "name": "Ada", "headline": "ML Engineer", "summary": "Builds retrieval systems.",
        "experience": [{"company": "Acme", "role": "Engineer", "duration": "2021-2024", "bullets": ["Built RAG"]}],
        "skills": {"primary": ["Python"], "secondary": []}, "projects": [], "education": [], "certifications": [],
    }
    user = assistant.CurrentUser(id=USER_ID, token="t")

    bad_company = asyncio.run(assistant.execute_tool(
        "propose_resume_edit", {"application_id": APP_ID, "experience": [{"company": "Google", "bullets": ["x"]}]}, user))
    assert "Companies can't be added" in bad_company["error"]

    result = asyncio.run(assistant.execute_tool("propose_resume_edit", {
        "application_id": APP_ID,
        "summary": "RAG engineer who cut latency by 30%.",
        "experience": [{"company": "acme", "bullets": ["Built a RAG platform with LangChain"]}],
        "skills_primary": ["Python", "Terraform"],
    }, user))
    assert result["action"] == "update_resume" and result["awaiting_approval"]
    content = result["args"]["content"]
    assert content["summary"].startswith("RAG engineer") and content["experience"][0]["bullets"] == ["Built a RAG platform with LangChain"]
    assert content["experience"][0]["duration"] == "2021-2024"  # facts untouched
    warnings = " ".join(result["warnings"])
    assert "30%" in warnings and "Terraform" in warnings
    # Proposals don't write anything.
    assert db.tables["tailored_resumes"][0]["content"]["summary"] == "Builds retrieval systems."
    assert "content" not in assistant._model_view(result)["args"]


def test_invalid_application_id_is_404_not_500(client):
    assert client.get("/api/v1/applications/app_12345").status_code == 404


def test_rejected_tool_call_is_retried_not_fatal(db):
    """Groq validates tool arguments server-side and rejects the whole reply on a bad value."""
    def rejected(_messages):
        raise RuntimeError(
            "Error code: 400 - {'error': {'message': 'tool call validation failed: parameters for tool open_view did not match schema', "
            "'code': 'tool_use_failed'}}"
        )
        yield  # pragma: no cover  (makes this a generator)

    def corrected(messages):
        note = messages[-1].content
        assert "rejected" in note and "open_view" in note
        return tool_call("open_view", {"view": "feed"}, "c1")

    llm = ScriptedLLM([rejected, corrected, text("Opened your job feed.")])
    events = asyncio.run(_collect(assistant.run_assistant([{"role": "user", "content": "show my remote jobs"}], _user(), llm=llm)))
    assert not [e for e in events if e["type"] == "error"]
    assert any(e["type"] == "tool_result" and e["result"].get("opened") == "feed" for e in events)
    assert events[-1]["type"] == "done"


def test_tool_schemas_have_no_enums():
    # Enums make strict providers reject replies; executors validate values instead.
    assert '"enum"' not in json.dumps(assistant.TOOL_SCHEMAS)
    opened = asyncio.run(assistant.execute_tool("open_view", {"view": "feed", "tab": "jobs"}, _user()))
    assert opened == {"opened": "feed", "application_id": None, "tab": None}


def _user():
    return assistant.CurrentUser(id=USER_ID, token="t")


async def _collect(stream):
    return [event async for event in stream]
