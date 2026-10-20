"""Referral first: LinkedIn import, company matching, referral requests, pipeline check."""

import asyncio

import pytest

from app.agents import assistant, orchestrator
from app.api.v1 import network
from app.services import referrals
from app.services.auth import CurrentUser
from app.services.websocket import manager
from test_application_flow import USER_ID, client, db  # noqa: F401  (pytest fixtures)

USER = CurrentUser(id=USER_ID, token="t", email="ada@example.com")

CONNECTIONS_CSV = """Notes:
"When exporting your connection data, you may notice that some of the email addresses are missing."

First Name,Last Name,URL,Email Address,Company,Position,Connected On
Priya,Sharma,https://www.linkedin.com/in/priya-sharma,,Bundl Technologies Private Limited,Software Development Engineer II,12 Oct 2024
Ravi,Kumar,https://www.linkedin.com/in/ravikumar,ravi@example.com,Globex,Talent Acquisition Partner,03 Jan 2025
Meera,Iyer,https://www.linkedin.com/in/meera,,Globex Inc.,Senior ML Engineer,15 Mar 2023
Arjun,Rao,https://www.linkedin.com/in/arjun,,Initech,Product Manager,01 Feb 2022
,,,,,,
Priya,Sharma,https://www.linkedin.com/in/priya-sharma/,,Bundl Technologies Private Limited,Software Development Engineer II,12 Oct 2024
"""


class FakeLLM:
    def __init__(self, text=None, fail=False):
        self.text, self.fail = text, fail

    async def ainvoke(self, prompt):
        if self.fail:
            raise RuntimeError("429 rate limited")
        return type("R", (), {"content": self.text})()


@pytest.fixture
def net(db, monkeypatch):
    for module in (network, assistant):
        monkeypatch.setattr(module, "get_supabase_client", lambda user_jwt=None: db)
    monkeypatch.setattr(referrals, "get_default_llm", lambda temperature=0.4, **_kw: FakeLLM("Hi Meera, would you refer me for the ML Engineer role?"))
    return db


def _import(client):
    return client.post("/api/v1/network/import", files={"file": ("Connections.csv", CONNECTIONS_CSV.encode(), "text/csv")})


def test_parse_linkedin_export():
    rows, skipped = referrals.parse_linkedin_connections(CONNECTIONS_CSV.encode(), USER_ID)
    assert len(rows) == 4 and skipped == 1  # blank row skipped, trailing-slash duplicate merged
    priya = rows[0]
    assert priya["full_name"] == "Priya Sharma" and priya["company_key"] == "bundl"
    assert priya["connected_on"] == "2024-10-12" and priya["source"] == "linkedin"
    with pytest.raises(referrals.ImportError_, match="Connections.csv"):
        referrals.parse_linkedin_connections(b"name,company\nA,B", USER_ID)


@pytest.mark.parametrize("a, b, same", [
    ("Bundl Technologies Private Limited", "Swiggy", True),
    ("Sarvam", "Sarvam AI", True),
    ("Eternal Ltd", "Blinkit", True),
    ("Meta", "Metamorphosis Labs", False),
    ("CRED", "Credgenics", False),
    ("AI Labs", "Sarvam AI", False),
])
def test_company_matching(a, b, same):
    assert referrals.companies_match(referrals.company_key(a), referrals.company_key(b)) is same


def test_import_and_reimport(net, client):
    res = _import(client)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["imported"] == 4 and body["updated"] == 0 and body["with_company"] == 4
    again = _import(client).json()
    assert again["imported"] == 0 and again["updated"] == 4
    assert len(net.tables["network_contacts"]) == 4

    contacts = client.get("/api/v1/network/contacts?company=Swiggy").json()
    assert [c["full_name"] for c in contacts["contacts"]] == ["Priya Sharma"]
    assert client.get("/api/v1/network/contacts?q=talent").json()["total"] == 1

    bad = client.post("/api/v1/network/import", files={"file": ("x.csv", b"hello", "text/csv")})
    assert bad.status_code == 400 and "Connections.csv" in bad.json()["detail"]


def test_manual_contact_and_companies(net, client):
    res = client.post("/api/v1/network/contacts", json={"full_name": "Sam Lee", "company": "Sarvam AI", "position": "Research Engineer"})
    assert res.status_code == 201 and res.json()["company_key"] == "sarvam ai"
    _import(client)
    net.tables["job_applications"] = [{"id": "a1", "user_id": USER_ID, "company": "Globex", "role": "ML Engineer"}]
    companies = client.get("/api/v1/network/companies").json()
    assert companies["total_contacts"] == 5
    first = companies["companies"][0]
    assert first["company"].startswith("Globex") and first["count"] == 2 and first["applications"] == 1


def test_referrals_for_an_application_rank_and_draft(net, client):
    _import(client)
    asyncio.run(orchestrator.run_agent_pipeline("run-ref", USER_ID, "t", jd_text="ML Engineer at Globex"))
    app = net.tables["job_applications"][0]

    # The pipeline found both Globex contacts and drafted a request to the closest match.
    check = next(e for e in manager.history["run-ref"] if e["step"] == "referral_check" and e["status"] == "done")
    assert "You know 2 people at Globex" in check["message"] and "Meera Iyer" in check["message"]
    assert len(net.tables["referral_requests"]) == 1

    res = client.get(f"/api/v1/network/referrals/{app['id']}").json()
    names = [c["contact"]["full_name"] for c in res["contacts"]]
    assert names == ["Meera Iyer", "Ravi Kumar"]  # similar role first, then the recruiter
    assert res["contacts"][0]["request"]["status"] == "drafted"
    assert "Recruits at Globex" in res["contacts"][1]["reason"]

    ravi = res["contacts"][1]["contact"]
    created = client.post("/api/v1/network/referrals", json={"application_id": app["id"], "contact_id": ravi["id"]}).json()
    assert created["message"].startswith("Hi Meera") and created["used_fallback"] is False  # stub LLM text
    sent = client.patch(f"/api/v1/network/referrals/{created['id']}", json={"status": "sent"}).json()
    assert sent["status"] == "sent" and sent["sent_at"]

    listing = client.get("/api/v1/applications/").json()["applications"]
    assert listing[0]["referral_count"] == 2


def test_referral_message_falls_back_to_template(net, client, monkeypatch):
    monkeypatch.setattr(referrals, "get_default_llm", lambda temperature=0.4, **_kw: FakeLLM(fail=True))
    _import(client)
    net.tables.setdefault("job_applications", []).append(
        {"id": "0b0c9b3e-5d55-4b0a-9a39-9a7a2c1e0009", "user_id": USER_ID, "company": "Initech", "role": "PM", "jd_url": "https://x/1"}
    )
    arjun = next(c for c in net.tables["network_contacts"] if c["first_name"] == "Arjun")
    res = client.post("/api/v1/network/referrals", json={"application_id": "0b0c9b3e-5d55-4b0a-9a39-9a7a2c1e0009", "contact_id": arjun["id"]}).json()
    assert res["used_fallback"] is True and res["message"].startswith("Hi Arjun") and "https://x/1" in res["message"]


def test_pipeline_without_network_suggests_import(db):
    asyncio.run(orchestrator.run_agent_pipeline("run-noref", USER_ID, "t", jd_text="ML Engineer at Globex"))
    check = next(e for e in manager.history["run-noref"] if e["step"] == "referral_check" and e["status"] == "done")
    assert "Import your LinkedIn connections" in check["message"]
    assert manager.history["run-noref"][-1]["step"] == "complete"


def test_assistant_referral_tools(net, client):
    _import(client)
    asyncio.run(orchestrator.run_agent_pipeline("run-asst", USER_ID, "t", jd_text="ML Engineer at Globex"))
    app = net.tables["job_applications"][0]
    found = asyncio.run(assistant.execute_tool("find_referrals", {"application_id": app["id"]}, USER))
    assert found["total"] == 2 and found["contacts"][0]["full_name"] == "Meera Iyer"
    by_company = asyncio.run(assistant.execute_tool("find_referrals", {"company": "Swiggy"}, USER))
    assert [c["full_name"] for c in by_company["contacts"]] == ["Priya Sharma"]

    ravi = found["contacts"][1]
    proposal = asyncio.run(assistant.execute_tool("propose_referral_request", {"application_id": app["id"], "contact_id": ravi["id"]}, USER))
    assert proposal["awaiting_approval"] and proposal["action"] == "save_referral"
    assert proposal["args"]["message"] and proposal["contact"]["name"] == "Ravi Kumar"
    bad = asyncio.run(assistant.execute_tool("propose_referral_request", {"application_id": app["id"], "contact_id": "c_1"}, USER))
    assert "find_referrals" in bad["error"]


def test_missing_tables_explain_the_migration(net, client, monkeypatch):
    real = net.table

    def table(name):
        if name in ("network_contacts", "referral_requests"):
            raise Exception("{'code': 'PGRST205', 'message': \"Could not find the table 'public.network_contacts'\"}")
        return real(name)

    monkeypatch.setattr(net, "table", table)
    res = client.get("/api/v1/network/contacts")
    assert res.status_code == 503 and "20261013_referrals.sql" in res.json()["detail"]
    # Everything else keeps working without the tables.
    assert client.get("/api/v1/applications/").status_code == 200


def test_import_accepts_the_linkedin_zip(net, client):
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Basic_LinkedInDataExport_10-10-2026/Connections.csv", CONNECTIONS_CSV)
        z.writestr("Basic_LinkedInDataExport_10-10-2026/Profile.csv", "First Name,Last Name\nAda,Lovelace")
    res = client.post("/api/v1/network/import", files={"file": ("export.zip", buf.getvalue(), "application/zip")})
    assert res.status_code == 200, res.text
    assert res.json()["imported"] == 4

    empty = io.BytesIO()
    with zipfile.ZipFile(empty, "w") as z:
        z.writestr("Profile.csv", "First Name,Last Name\nAda,Lovelace")
    res = client.post("/api/v1/network/import", files={"file": ("export.zip", empty.getvalue(), "application/zip")})
    assert res.status_code == 400 and "no Connections.csv yet" in res.json()["detail"]
