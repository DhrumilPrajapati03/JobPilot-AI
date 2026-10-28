"""SmartRecruiters and remote job boards (Himalayas, Remotive), region rules and re-scoring."""

import asyncio

import httpx
import pytest

from app.services import discovery, job_boards
from app.services.job_boards import FetchOptions, Posting, parse_board
from app.services.job_matching import region_flag, user_country
from test_application_flow import USER_ID, client, db  # noqa: F401  (pytest fixtures)
from test_discovery import board  # noqa: F401  (pytest fixture)


@pytest.mark.parametrize("value, ats, expected", [
    ("https://careers.smartrecruiters.com/Swiggy", None, ("smartrecruiters", "swiggy")),
    ("https://jobs.smartrecruiters.com/SWIGGY/6000000001476209-sdm", None, ("smartrecruiters", "swiggy")),
    ("https://himalayas.app/jobs", None, ("himalayas", "remote")),
    ("remotive.com", None, ("remotive", "remote")),
    ("anything", "remotive", ("remotive", "remote")),
])
def test_parse_new_boards(value, ats, expected):
    assert parse_board(value, ats) == expected


def test_zomato_style_careers_pages_get_a_clear_message():
    with pytest.raises(job_boards.BoardError, match="own careers site"):
        parse_board("https://www.eternal.com/careers")


def _run(handler, ats, opts):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await job_boards.fetch_board(ats, "swiggy" if ats == "smartrecruiters" else "remote", client, opts)
    return asyncio.run(go())


def test_smartrecruiters_fetches_details_only_for_kept_postings():
    detail_calls = []
    listing = {"totalFound": 2, "content": [
        {"id": "1", "name": "Software Dev Engineer II", "company": {"identifier": "SWIGGY", "name": "SWIGGY"},
         "location": {"city": "Bengaluru", "country": "in", "remote": False, "hybrid": False, "fullLocation": "Bengaluru, KA, India"},
         "releasedDate": "2026-10-01T00:00:00Z"},
        {"id": "2", "name": "Sales Manager", "company": {"identifier": "SWIGGY", "name": "SWIGGY"},
         "location": {"city": "Mumbai", "country": "in", "remote": False}},
    ]}

    def handler(request: httpx.Request):
        path = request.url.path
        if path.endswith("/postings"):
            return httpx.Response(200, json=listing)
        detail_calls.append(path.rsplit("/", 1)[-1])
        return httpx.Response(200, json={"postingUrl": "https://jobs.smartrecruiters.com/SWIGGY/1-sde", "jobAd": {"sections": {
            "jobDescription": {"title": "Job Description", "text": "<p>Build systems in <b>Go</b> and Python.</p>"},
        }}})

    company, postings = _run(handler, "smartrecruiters", FetchOptions(keep=lambda title, _id: "engineer" in title.lower()))
    assert company == "Swiggy" and len(postings) == 2 and detail_calls == ["1"]
    sde = postings[0]
    assert "Python" in sde.description and sde.url.endswith("1-sde") and sde.remote is False
    assert postings[1].description == ""


def test_remote_boards_search_by_role_and_cache(monkeypatch):
    monkeypatch.setattr(job_boards, "_cache", {})
    calls = []

    def handler(request: httpx.Request):
        calls.append(str(request.url))
        if request.url.host == "himalayas.app":
            return httpx.Response(200, json={"jobs": [{
                "guid": "https://himalayas.app/companies/acme/jobs/ml", "applicationLink": "https://himalayas.app/companies/acme/jobs/ml",
                "title": "ML Engineer", "companyName": "Acme", "locationRestrictions": ["India"], "description": "<p>PyTorch</p>",
                "pubDate": 1791391518,
            }]})
        return httpx.Response(200, json={"jobs": [{
            "id": 9, "url": "https://remotive.com/remote-jobs/software-dev/ml-9", "title": "ML Engineer", "company_name": "Globex",
            "candidate_required_location": "USA", "description": "<p>Python</p>", "publication_date": "2026-10-01T00:00:00",
        }]})

    opts = FetchOptions(queries=["ML Engineer"], country="India")
    name, (h,) = _run(handler, "himalayas", opts)
    assert name == "Himalayas" and h.company == "Acme" and h.location == "Remote, India" and h.remote is True
    assert "country=India" in calls[0] and "q=ML+Engineer" in calls[0]
    _, (r,) = _run(handler, "remotive", opts)
    assert r.company == "Globex" and r.location == "Remote, USA"

    before = len(calls)
    _run(handler, "himalayas", opts)
    assert len(calls) == before  # served from cache: remote boards ask for infrequent polling


def test_remote_boards_need_target_roles():
    with pytest.raises(job_boards.BoardError, match="target roles"):
        _run(lambda r: httpx.Response(200, json={}), "himalayas", FetchOptions())


@pytest.mark.parametrize("location, expected_ok", [
    ("Remote, worldwide", True),
    ("Remote, India", True),
    ("Remote, APAC", True),
    ("Remote, USA, UK, India, Australia", True),
    ("Remote, USA", False),
    ("Remote, Europe", False),
])
def test_region_flag_for_india(location, expected_ok):
    assert (region_flag(location, "India") is None) == expected_ok


def test_user_country():
    assert user_country("Ahmedabad, Gujarat, India") == "India"
    assert user_country("") is None


def test_remote_board_postings_keep_their_company_and_region_rules(board, client, db, monkeypatch):  # noqa: F811
    db.tables["user_profiles"][0]["location"] = "Ahmedabad, India"

    async def remote_fetch(ats, slug, client=None, opts=None):
        assert opts.queries == ["Machine Learning Engineer"] and opts.country == "India"
        return "Remotive", [
            Posting("remotive", "r1", "Initech", "Machine Learning Engineer", "Remote, worldwide", True, "https://remotive.com/1", "Python, RAG", None),
            Posting("remotive", "r2", "Hooli", "Machine Learning Engineer", "Remote, USA", True, "https://remotive.com/2", "Python", None),
        ]

    monkeypatch.setattr(discovery, "fetch_board", remote_fetch)
    res = client.post("/api/v1/discovery/sources", json={"url": "remotive.com"})
    assert res.status_code == 201, res.text
    rows = {p["external_id"]: p for p in db.tables["job_postings"]}
    assert rows["r1"]["company"] == "Initech" and rows["r1"]["status"] == "new"
    assert rows["r2"]["status"] == "skipped" and "only open to candidates in USA" in rows["r2"]["skip_flags"][0]

    # A later search that doesn't return r1 doesn't mark it closed.
    async def fewer(ats, slug, client=None, opts=None):
        return "Remotive", []

    monkeypatch.setattr(discovery, "fetch_board", fewer)
    client.post("/api/v1/discovery/scan")
    assert {p["external_id"]: p for p in db.tables["job_postings"]}["r1"].get("closed_at") is None


def test_stored_postings_are_rescored_when_preferences_change(board, client, db):  # noqa: F811
    client.post("/api/v1/discovery/sources", json={"url": "boards.greenhouse.io/globex"})
    rows = {p["external_id"]: p for p in db.tables["job_postings"]}
    assert rows["1"]["status"] == "new"

    db.tables["user_profiles"][0]["work_preferences"]["blocked_companies"] = ["Globex"]
    summary = client.post("/api/v1/discovery/scan").json()
    rows = {p["external_id"]: p for p in db.tables["job_postings"]}
    assert summary["rescored"] >= 2
    assert rows["1"]["status"] == "skipped" and "blocked companies" in rows["1"]["skip_flags"][0]

    # Different target roles drop postings that no longer fit.
    db.tables["user_profiles"][0]["work_preferences"]["preferred_roles"] = ["Data Analyst"]
    db.tables["user_profiles"][0]["work_preferences"]["blocked_companies"] = []
    summary = client.post("/api/v1/discovery/scan").json()
    assert summary["dropped"] == 3 and summary["new"] == 0
    assert db.tables["job_postings"] == []


def test_bulk_follow_suggested_boards(board, client, db):  # noqa: F811
    res = client.post("/api/v1/discovery/sources/bulk", json={"boards": [
        {"ats": "ashby", "slug": "sarvam"}, {"ats": "smartrecruiters", "slug": "swiggy"},
        {"ats": "himalayas", "slug": "remote"}, {"ats": "lever", "slug": "not-in-catalog"},
    ]})
    assert res.status_code == 201, res.text
    body = res.json()
    assert {s["company"] for s in body["sources"]} == {"Sarvam AI", "Swiggy", "Himalayas"}
    assert body["skipped_unknown"] == ["not-in-catalog"]
    again = client.post("/api/v1/discovery/sources/bulk", json={"boards": [{"ats": "ashby", "slug": "sarvam"}]}).json()
    assert again["sources"] == []
    groups = {s["group"] for s in client.get("/api/v1/discovery/sources").json()["suggestions"]}
    assert groups == {"remote", "india", "global"}


def test_same_job_on_two_boards_is_stored_once(board, client, db, monkeypatch):  # noqa: F811
    async def fetch(ats, slug, client=None, opts=None):
        if ats == "himalayas":
            return "Himalayas", [Posting("himalayas", "h1", "Globex", "Senior Machine Learning Engineer", "Remote, worldwide", True, "https://boards.greenhouse.io/globex/jobs/1?utm_source=himalayas", "Python", None)]
        return "Globex", [Posting("greenhouse", "1", "Globex", "Senior Machine Learning Engineer", "Remote - India", True, "https://boards.greenhouse.io/globex/jobs/1", "Python", None)]

    monkeypatch.setattr(discovery, "fetch_board", fetch)
    monkeypatch.setattr("app.api.v1.discovery.fetch_board", fetch)
    client.post("/api/v1/discovery/sources", json={"url": "boards.greenhouse.io/globex"})
    res = client.post("/api/v1/discovery/sources", json={"url": "himalayas.app"})
    assert res.json()["scan"]["duplicates"] == 1
    assert [p["ats"] for p in db.tables["job_postings"]] == ["greenhouse"]


def test_assistant_can_scan(board, client, db):  # noqa: F811
    from app.agents import assistant
    from app.services.auth import CurrentUser

    user = CurrentUser(id=USER_ID, token="t", email="ada@example.com")
    assert "hint" in asyncio.run(assistant.execute_tool("scan_jobs", {}, user))
    client.post("/api/v1/discovery/sources", json={"url": "boards.greenhouse.io/globex"})
    result = asyncio.run(assistant.execute_tool("scan_jobs", {}, user))
    assert result["sources"] == 1 and result["fetched"] == 4
