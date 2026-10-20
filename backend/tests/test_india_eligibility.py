"""India eligibility is enforced on old feed data as well as new scans."""

import asyncio

import pytest

from app.agents import assistant
from app.services import discovery, job_boards
from app.services.auth import CurrentUser
from app.services.job_filters import india_eligibility_flag
from test_application_flow import USER_ID, client, db  # noqa: F401
from test_discovery import board  # noqa: F401


@pytest.mark.parametrize("location,remote,description,eligible", [
    ("Remote, Argentina, Brazil, Colombia", True, "Global team with offices in India", False),
    ("Remote, US", True, "", False),
    ("Remote", True, "", False),
    ("", None, "", False),
    ("Remote, APAC", True, "", False),
    ("Remote, Asia", True, "", False),
    ("Remote, worldwide", True, "Except India", False),
    ("Remote, worldwide", True, "Must be authorized to work in the United States.", False),
    ("Remote, worldwide", True, "Must be based in Brazil", False),
    ("Remote, worldwide", True, "US-only applicants", False),
    ("Remote, India", True, "", True),
    ("Bengaluru", False, "", True),
    ("Remote, USA, India, UK", True, "", True),
    ("Remote, worldwide", True, "", True),
    ("Remote", True, "Work from anywhere in the world", True),
])
def test_eligibility(location, remote, description, eligible):
    assert (india_eligibility_flag(dict(location=location, remote=remote, description=description)) is None) == eligible


def test_existing_ineligible_jobs_hidden_and_cannot_be_drafted(board, client, db):
    client.post("/api/v1/discovery/sources", json={"url": "boards.greenhouse.io/globex"})
    # Simulate stale rows stored under the old permissive filter.
    rows = db.tables["job_postings"]
    blocked = next(r for r in rows if r["external_id"] == "1")
    blocked.update(location="Remote, Argentina, Brazil, Colombia", status="new", description="Python")
    feed = client.get("/api/v1/discovery/postings").json()
    assert blocked["id"] not in [r["id"] for r in feed["postings"]]
    assert feed["counts"]["new"] == 1
    user = CurrentUser(id=USER_ID, token="t", email="ada@example.com")
    chat_feed = asyncio.run(assistant._get_job_feed(user, {}))
    assert blocked["id"] not in [r["id"] for r in chat_feed["postings"]]
    briefing = client.get("/api/v1/discovery/briefing").json()
    assert blocked["id"] not in [r["id"] for r in briefing["top_matches"]]
    response = client.post(f"/api/v1/discovery/postings/{blocked['id']}/draft")
    assert response.status_code == 400
    prefs = discovery.load_preferences(db, USER_ID)
    prefs.auto_draft_daily_cap = 1
    prefs.auto_draft_min_score = 0
    # The highest scoring stale job must never be automatically drafted.
    blocked["fit_score"] = 100
    for r in rows:
        if r["id"] != blocked["id"]:
            r["status"] = "dismissed"
    assert discovery.start_auto_drafts(db, USER_ID, prefs) == []


def test_missing_himalayas_scope_is_not_invented_as_worldwide(monkeypatch):
    import httpx

    monkeypatch.setattr(job_boards, "_cache", {})

    async def fetch():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"jobs": [{
            "guid": "job-1", "title": "ML Engineer", "companyName": "Acme",
        }]}))) as client:
            return await job_boards.fetch_board("himalayas", "remote", client, job_boards.FetchOptions(queries=["ML"]))

    _, postings = asyncio.run(fetch())
    assert india_eligibility_flag(vars(postings[0]))
