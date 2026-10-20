"""Job discovery: board clients, scanning, scoring, auto-draft caps, feed and briefing."""

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.agents import assistant
from app.api.v1 import discovery as discovery_api
from app.services import discovery, job_boards
from app.services.job_boards import BoardError, Posting, parse_board
from app.services.auth import CurrentUser
from test_application_flow import USER_ID, client, db  # noqa: F401  (pytest fixtures)

USER = CurrentUser(id=USER_ID, token="t", email="ada@example.com")

BOARD = {
    "1": ("Senior Machine Learning Engineer", "Remote - India", "Python, LangChain, RAG and Docker. Kubernetes a plus."),
    "2": ("ML Engineer, Search", "Remote, worldwide", "Python and RAG pipelines. Requires an active security clearance."),
    "3": ("Account Executive", "Remote", "Quota-carrying sales role."),
    "4": ("Machine Learning Engineer, Ads", "Remote, worldwide", "Python, Spark, Scala, Java, Go, Rust, C++ and Kubernetes."),
}


def _postings(ids=None):
    return [
        Posting(
            ats="greenhouse", external_id=pid, company="Globex", title=title, location=loc, remote=True,
            url=f"https://boards.greenhouse.io/globex/jobs/{pid}", description=desc, posted_at=None,
        )
        for pid, (title, loc, desc) in BOARD.items() if ids is None or pid in ids
    ]


@pytest.fixture
def board(db, monkeypatch):
    """Stub the network; ``board.ids`` controls which postings are open."""
    state = type("Board", (), {"ids": None})()

    async def fake_fetch(ats, slug, client=None, opts=None):
        if slug == "missing":
            raise BoardError("There's no Greenhouse job board called 'missing'.")
        return "Globex", _postings(state.ids)

    monkeypatch.setattr(discovery, "fetch_board", fake_fetch)
    monkeypatch.setattr(discovery_api, "fetch_board", fake_fetch)
    monkeypatch.setattr(discovery_api, "get_supabase_client", lambda user_jwt=None: db)
    monkeypatch.setattr(assistant, "get_supabase_client", lambda user_jwt=None: db)
    db.tables["user_profiles"][0]["work_preferences"] = {"preferred_roles": ["Machine Learning Engineer"]}
    return state


def _prefs(db, **values):
    db.tables["user_profiles"][0]["work_preferences"].update(values)


async def _scan_and_finish(db, **kwargs):
    summary = await discovery.scan_user(db, USER_ID, user_token="t", **kwargs)
    await asyncio.gather(*list(discovery._background_tasks))
    return summary


def _postings_by_external_id(db):
    return {p["external_id"]: p for p in db.tables.get("job_postings", [])}


# --- Board clients ------------------------------------------------------------------

@pytest.mark.parametrize("value, expected", [
    ("https://boards.greenhouse.io/stripe", ("greenhouse", "stripe")),
    ("https://job-boards.greenhouse.io/Anthropic/jobs/123", ("greenhouse", "anthropic")),
    ("https://boards.greenhouse.io/embed/job_board?for=figma", ("greenhouse", "figma")),
    ("https://jobs.lever.co/spotify/abc-123", ("lever", "spotify")),
    ("jobs.ashbyhq.com/linear", ("ashby", "linear")),
])
def test_parse_board_urls(value, expected):
    assert parse_board(value) == expected


def test_parse_board_slug_needs_ats():
    assert parse_board("ramp", "ashby") == ("ashby", "ramp")
    with pytest.raises(BoardError):
        parse_board("ramp")


def test_board_clients_normalise_each_ats():
    payloads = {
        "boards-api.greenhouse.io/v1/boards/acme/jobs": {"jobs": [{
            "id": 7, "title": "ML Engineer", "location": {"name": "Remote, US"}, "absolute_url": "https://acme/7",
            "content": "&lt;p&gt;Build &lt;b&gt;RAG&lt;/b&gt;&lt;/p&gt;", "first_published": "2026-10-01T00:00:00Z",
        }]},
        "boards-api.greenhouse.io/v1/boards/acme": {"name": "Acme Corp"},
        "api.lever.co/v0/postings/acme": [{
            "id": "l1", "text": "Data Engineer", "categories": {"allLocations": ["London"]}, "workplaceType": "hybrid",
            "hostedUrl": "https://jobs.lever.co/acme/l1", "createdAt": 1790000000000, "descriptionPlain": "Intro",
            "lists": [{"text": "Requirements", "content": "<li>Spark</li><li>Airflow</li>"}], "additionalPlain": "EEO",
        }],
        "api.ashbyhq.com/posting-api/job-board/acme": {"jobs": [
            {"id": "a1", "title": "AI Engineer", "location": "NYC", "isRemote": True, "workplaceType": "Hybrid",
             "jobUrl": "https://jobs.ashbyhq.com/acme/a1", "descriptionPlain": "LLMs",
             "compensation": {"scrapeableCompensationSalarySummary": "$150K – $200K"}},
            {"id": "a2", "title": "Hidden", "isListed": False},
        ]},
    }

    def handler(request: httpx.Request):
        key = f"{request.url.host}{request.url.path}"
        return httpx.Response(200, json=payloads[key]) if key in payloads else httpx.Response(404)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gh = await job_boards.fetch_board("greenhouse", "acme", client)
            lv = await job_boards.fetch_board("lever", "acme", client)
            ab = await job_boards.fetch_board("ashby", "acme", client)
            with pytest.raises(BoardError, match="no Lever job board"):
                await job_boards.fetch_board("lever", "nope", client)
        return gh, lv, ab

    (gh_company, gh), (_, lv), (_, ab) = asyncio.run(run())
    assert gh_company == "Acme Corp" and gh[0].remote is True and gh[0].description == "Build RAG"
    assert lv[0].remote is False and "Spark" in lv[0].description and lv[0].posted_at.startswith("2026")
    assert len(ab) == 1 and ab[0].remote is True and "$150K" in ab[0].description


# --- Scanning -----------------------------------------------------------------------

def test_add_source_scans_filters_and_flags(board, client, db):
    res = client.post("/api/v1/discovery/sources", json={"url": "https://boards.greenhouse.io/globex"})
    assert res.status_code == 201, res.text
    scan = res.json()["scan"]
    # "Account Executive" doesn't fit the target role, so it's never stored.
    assert scan["filtered"] == 1 and scan["new"] == 2 and scan["skipped"] == 1

    stored = _postings_by_external_id(db)
    assert set(stored) == {"1", "2", "4"}
    assert stored["2"]["status"] == "skipped" and "security clearance" in stored["2"]["skip_flags"][0]
    assert stored["1"]["fit_score"] > stored["4"]["fit_score"]
    assert "kubernetes" in stored["1"]["missing_skills"] and "python" in stored["1"]["matched_skills"]

    feed = client.get("/api/v1/discovery/postings").json()
    assert [p["external_id"] for p in feed["postings"]] == ["1", "4"]
    assert feed["counts"] == {"new": 2, "skipped": 1, "dismissed": 0, "drafted": 0}
    assert "description" not in feed["postings"][0]

    assert client.post("/api/v1/discovery/sources", json={"url": "boards.greenhouse.io/globex"}).status_code == 409
    missing = client.post("/api/v1/discovery/sources", json={"url": "missing", "ats": "greenhouse"})
    assert missing.status_code == 400 and "no Greenhouse job board" in missing.json()["detail"]


def test_rescans_dedupe_close_and_reopen(board, client, db):
    client.post("/api/v1/discovery/sources", json={"url": "boards.greenhouse.io/globex"})
    board.ids = {"1"}
    summary = client.post("/api/v1/discovery/scan").json()
    assert summary["new"] == 0 and summary["closed"] == 2  # #4 (new) and #2 (skipped) are gone
    assert len(db.tables["job_postings"]) == 3
    assert _postings_by_external_id(db)["4"]["closed_at"]
    assert [p["external_id"] for p in client.get("/api/v1/discovery/postings").json()["postings"]] == ["1"]

    board.ids = None
    client.post("/api/v1/discovery/scan")
    assert _postings_by_external_id(db)["4"]["closed_at"] is None


def test_unfollow_removes_postings(board, client, db):
    source = client.post("/api/v1/discovery/sources", json={"url": "boards.greenhouse.io/globex"}).json()["source"]
    assert client.delete(f"/api/v1/discovery/sources/{source['id']}").status_code == 204
    assert db.tables["job_postings"] == [] and db.tables["job_sources"] == []


def test_scan_needs_a_base_resume(board, client, db):
    client.post("/api/v1/discovery/sources", json={"url": "boards.greenhouse.io/globex"})
    db.tables["resumes"] = []
    res = client.post("/api/v1/discovery/scan")
    assert res.status_code == 400 and "base resume" in res.json()["detail"]


def test_missing_tables_explain_the_migration(board, client, db, monkeypatch):
    real_table = db.table

    def table(name):
        if name in ("job_sources", "job_postings"):
            raise Exception("{'code': 'PGRST205', 'message': \"Could not find the table 'public.job_sources'\"}")
        return real_table(name)

    monkeypatch.setattr(db, "table", table)
    res = client.get("/api/v1/discovery/sources")
    assert res.status_code == 503 and "20261011_job_discovery.sql" in res.json()["detail"]


# --- Drafting -----------------------------------------------------------------------

def test_auto_draft_respects_threshold_and_daily_cap(board, db):
    db.tables["job_sources"] = [{"id": "src-1", "user_id": USER_ID, "ats": "greenhouse", "slug": "globex", "company": "", "enabled": True}]
    _prefs(db, auto_draft_enabled=True, auto_draft_min_score=50, auto_draft_daily_cap=1)

    summary = asyncio.run(_scan_and_finish(db))
    assert len(summary["auto_drafting"]) == 1
    stored = _postings_by_external_id(db)
    best = stored["1"]
    assert best["status"] == "drafted" and best["auto_drafted"] and best["application_id"]
    app = next(a for a in db.tables["job_applications"] if a["id"] == best["application_id"])
    assert app["source"] == "greenhouse" and app["jd_url"].endswith("/jobs/1")
    assert "Senior Machine Learning Engineer at Globex" in app["jd_text"]
    assert stored["2"]["status"] == "skipped"  # skip rules beat auto-draft

    # Cap reached for today: a rescan drafts nothing more.
    assert asyncio.run(_scan_and_finish(db))["auto_drafting"] == []
    # Tomorrow the cap resets.
    best["drafted_at"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert len(asyncio.run(_scan_and_finish(db))["auto_drafting"]) == 1


def test_auto_draft_is_off_by_default(board, db):
    db.tables["job_sources"] = [{"id": "src-1", "user_id": USER_ID, "ats": "greenhouse", "slug": "globex", "company": "", "enabled": True}]
    assert asyncio.run(_scan_and_finish(db))["auto_drafting"] == []


def test_failed_draft_returns_posting_to_feed(board, db, monkeypatch):
    db.tables["job_sources"] = [{"id": "src-1", "user_id": USER_ID, "ats": "greenhouse", "slug": "globex", "company": "", "enabled": True}]
    _prefs(db, auto_draft_enabled=True, auto_draft_min_score=50, auto_draft_daily_cap=1)

    async def failing_pipeline(*args, **kwargs):
        return None

    monkeypatch.setattr(discovery, "run_agent_pipeline", failing_pipeline)
    asyncio.run(_scan_and_finish(db))
    best = _postings_by_external_id(db)["1"]
    assert best["status"] == "new" and best["drafted_at"] is None and not best["auto_drafted"]


def test_manual_draft_and_dismiss(board, client, db, monkeypatch):
    client.post("/api/v1/discovery/sources", json={"url": "boards.greenhouse.io/globex"})
    stored = _postings_by_external_id(db)
    started = []

    async def pending(*args, **kwargs):
        started.append(args)

    monkeypatch.setattr(discovery, "draft_posting", pending)
    res = client.post(f"/api/v1/discovery/postings/{stored['1']['id']}/draft")
    assert res.status_code == 200 and res.json()["run_id"]
    assert stored["1"]["status"] == "drafting" or _postings_by_external_id(db)["1"]["status"] == "drafting"
    assert client.post(f"/api/v1/discovery/postings/{stored['1']['id']}/draft").status_code == 409

    assert client.patch(f"/api/v1/discovery/postings/{stored['4']['id']}", json={"status": "dismissed"}).status_code == 200
    counts = client.get("/api/v1/discovery/postings?status=dismissed").json()["counts"]
    assert counts["dismissed"] == 1 and counts["drafted"] == 1 and counts["new"] == 0


# --- Briefing and assistant -------------------------------------------------------------

def test_briefing(board, client, db):
    empty = client.get("/api/v1/discovery/briefing").json()
    assert empty["sources"] == 0 and empty["stale"] is False

    client.post("/api/v1/discovery/sources", json={"url": "boards.greenhouse.io/globex"})
    _prefs(db, min_match_score=50)
    overdue = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    db.tables.setdefault("job_applications", []).append(
        {"id": "app-9", "user_id": USER_ID, "role": "Engineer", "company": "Initech", "status": "applied", "follow_up_at": overdue}
    )
    b = client.get("/api/v1/discovery/briefing").json()
    assert b["sources"] == 1 and b["stale"] is False and b["last_scan_at"]
    assert b["new_matches"] == 2 and b["top_matches"][0]["title"] == "Senior Machine Learning Engineer"
    assert b["follow_ups_due"][0]["company"] == "Initech"
    assert b["auto_draft"] == {"enabled": False, "min_score": 80, "daily_cap": 3, "remaining_today": 3}

    db.tables["job_sources"][0]["last_scanned_at"] = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    assert client.get("/api/v1/discovery/briefing").json()["stale"] is True


def test_assistant_job_tools(board, client, db):
    client.post("/api/v1/discovery/sources", json={"url": "boards.greenhouse.io/globex"})
    feed = asyncio.run(assistant.execute_tool("get_job_feed", {"min_score": 0}, USER))
    assert feed["total"] == 2 and feed["postings"][0]["title"] == "Senior Machine Learning Engineer"
    assert "error" in asyncio.run(assistant.execute_tool("draft_job", {"posting_id": "job_123"}, USER))
    briefing = asyncio.run(assistant.execute_tool("get_briefing", {}, USER))
    assert briefing["sources"] == 1
    opened = asyncio.run(assistant.execute_tool("open_view", {"view": "feed"}, USER))
    assert opened["opened"] == "feed"
