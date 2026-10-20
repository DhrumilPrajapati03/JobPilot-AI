"""Supervised autopilot: form answers, apply queue, digest, nightly schedule, extension API."""

import asyncio

import pytest

from app.api.v1 import autopilot as autopilot_api
from app.api.v1 import extension as extension_api
from app.services import autopilot, digest, form_answers
from app.services.form_answers import FormField
from test_application_flow import USER_ID, client, db  # noqa: F401  (pytest fixtures)

APP_ID = "0b0c9b3e-5d55-4b0a-9a39-9a7a2c1e0042"
ANSWERS = [
    {"question": "Phone number", "answer": "+91 98765 43210", "sensitive": False},
    {"question": "Will you now or in the future require visa sponsorship?", "answer": "No", "sensitive": False},
    {"question": "Total years of professional experience", "answer": "4", "sensitive": False},
    {"question": "Years of experience with Python", "answer": "4", "sensitive": False},
    {"question": "Gender", "answer": "Woman", "sensitive": True},
    {"question": "Notice period", "answer": "30 days", "sensitive": False},
]


def _ctx(**over):
    base = dict(
        email="ada@example.com",
        profile={"name": "Ada Lovelace", "location": "Pune, India", "linkedin_url": "https://linkedin.com/in/ada"},
        resume={"headline": "ML Engineer", "experience": [{"company": "Acme", "role": "ML Engineer", "bullets": ["Built RAG"]}]},
        answers=ANSWERS,
        application={"company": "Globex", "role": "ML Engineer", "cover_letter": "Dear Globex team"},
        prefs={},
    )
    base.update(over)
    return form_answers.build_context(**base)


class StubLLM:
    def __init__(self, text):
        self.text, self.prompts = text, []

    async def ainvoke(self, prompt):
        self.prompts.append(prompt)
        return type("R", (), {"content": self.text})()


# --- Form answers ------------------------------------------------------------------------

def test_profile_bank_and_safety_rules():
    fields = [
        FormField("fn", "First Name", required=True),
        FormField("ln", "Last Name", required=True),
        FormField("em", "Email", type="email", required=True),
        FormField("ph", "Phone", required=True),
        FormField("cv", "Resume/CV", type="file", required=True),
        FormField("sp", "Will you require visa sponsorship?", type="select", required=True, options=["Yes", "No"]),
        FormField("yrs", "How many years of experience do you have?", type="select", options=["0-2", "3-5", "6+"]),
        FormField("py", "Years of experience with Python?", type="text"),
        FormField("arb", "Agreement to Arbitrate", type="select", required=True, options=["I agree"]),
        FormField("g", "Gender", type="select", options=["Woman", "Man", "Decline to self-identify"]),
        FormField("v", "Veteran status", type="select", options=["I am not a veteran", "I don't wish to answer"]),
        FormField("cl", "Cover Letter", type="textarea"),
        FormField("hear", "How did you hear about us?", type="select", required=True, options=["LinkedIn", "Other"]),
    ]
    by_key = {a.key: a for a in asyncio.run(form_answers.answer_fields(fields, _ctx(), use_ai=False))}
    assert by_key["fn"].value == "Ada" and by_key["ln"].value == "Lovelace" and by_key["em"].value == "ada@example.com"
    assert by_key["ph"].value == "+91 98765 43210" and by_key["cv"].value == form_answers.RESUME_FILE
    assert by_key["sp"].value == "No" and not by_key["sp"].flagged
    assert by_key["yrs"].value == "3-5"  # "4" fits the range option
    assert by_key["py"].value == "4"
    assert by_key["arb"].value is None and by_key["arb"].flagged and "Legal" in by_key["arb"].note
    assert by_key["g"].value == "Woman"  # sensitive answers are used for EEO fields (never sent to an LLM)
    assert by_key["v"].value == "I don't wish to answer" and by_key["v"].source == "default"
    assert by_key["cl"].value == "Dear Globex team"
    assert by_key["hear"].flagged and by_key["hear"].value is None


def test_option_matching():
    assert form_answers.match_option("yes, I am", ["Yes", "No"]) == "Yes"
    assert form_answers.match_option("12", ["Less than 5", "5-10", "More than 10"]) == "More than 10"
    assert form_answers.match_option("2", ["Less than 5", "5-10"]) == "Less than 5"
    assert form_answers.match_option("Maybe", ["Yes", "No"]) is None


def test_open_questions_get_flagged_ai_drafts(monkeypatch):
    stub = StubLLM('{"1": "I build RAG systems at Acme, which is close to Globex\'s search work."}')
    monkeypatch.setattr(form_answers, "get_default_llm", lambda **_kw: stub)
    fields = [FormField("why", "Why Globex?", type="textarea", required=True), FormField("x", "Anything else?", type="text")]
    a, b = asyncio.run(form_answers.answer_fields(fields, _ctx()))
    assert a.source == "ai" and a.flagged and "RAG" in a.value
    assert b.value is None and not b.flagged  # optional short text isn't drafted
    assert "Woman" not in stub.prompts[0]  # sensitive answers never reach the model


def test_greenhouse_fields_parse_questions_and_eeo():
    job = {
        "questions": [
            {"required": True, "label": "First Name", "fields": [{"name": "first_name", "type": "input_text"}]},
            {"required": True, "label": "Resume/CV", "fields": [{"name": "resume", "type": "input_file"}, {"name": "resume_text", "type": "textarea"}]},
            {"required": False, "label": "Hidden", "fields": [{"name": "h", "type": "input_hidden"}]},
            {"required": True, "label": "Sponsorship?", "fields": [{"name": "q1", "type": "multi_value_single_select", "values": [{"label": "Yes"}, {"label": "No"}]}]},
        ],
        "compliance": [{"questions": [{"required": False, "label": "VeteranStatus", "fields": [{"name": "veteran_status", "type": "multi_value_single_select", "values": [{"label": "I don't wish to answer"}]}]}]}],
    }
    fields = form_answers.greenhouse_fields(job)
    assert [f.key for f in fields] == ["first_name", "resume", "q1", "veteran_status"]
    assert fields[1].type == "file" and fields[2].options == ["Yes", "No"] and fields[3].label == "Veteran status"


def test_apply_urls():
    assert autopilot.apply_url("greenhouse", "https://stripe.com/jobs?gh_jid=1", "stripe", "1") == "https://job-boards.greenhouse.io/stripe/jobs/1"
    assert autopilot.apply_url("lever", "https://jobs.lever.co/paytm/abc") == "https://jobs.lever.co/paytm/abc/apply"
    assert autopilot.apply_url("ashby", "https://jobs.ashbyhq.com/sarvam/x/") == "https://jobs.ashbyhq.com/sarvam/x/application"
    assert autopilot.apply_url("himalayas", "https://himalayas.app/companies/a/jobs/b") == "https://himalayas.app/companies/a/jobs/b"


# --- API ------------------------------------------------------------------------------------

@pytest.fixture
def ap(db, monkeypatch):
    for module in (autopilot_api,):
        monkeypatch.setattr(module, "get_supabase_client", lambda user_jwt=None: db)
    monkeypatch.setattr(autopilot_api, "get_supabase_admin_client", lambda: db)
    monkeypatch.setattr(extension_api, "get_supabase_admin_client", lambda: db)
    monkeypatch.setattr(autopilot, "server_ready", lambda: True)
    monkeypatch.setattr(autopilot, "account_email", lambda admin, uid: "ada@example.com")
    monkeypatch.setattr(form_answers, "get_default_llm", lambda **_kw: StubLLM('{"1": "Because of the search team."}'))
    db.tables["qa_answers"] = [{**a, "user_id": USER_ID} for a in ANSWERS]
    db.tables["job_applications"] = [{
        "id": APP_ID, "user_id": USER_ID, "company": "Globex", "role": "ML Engineer", "status": "saved",
        "jd_url": "https://job-boards.greenhouse.io/globex/jobs/77", "jd_text": "Python RAG", "notes": "",
        "cover_letter": "Dear Globex team", "linkedin_dm": {}, "created_at": "2026-10-10T00:00:00+00:00", "jd_analysis": {},
    }]
    db.tables["tailored_resumes"] = [{"id": "t1", "application_id": APP_ID, "user_id": USER_ID, "version": 1, "content": {}, "keyword_match_score": 81.0}]

    async def gh_form(_url):
        return [FormField("first_name", "First Name", required=True), FormField("q1", "Why Globex?", type="textarea", required=True),
                FormField("q2", "Agreement to Arbitrate", type="select", required=True, options=["I agree"])]

    monkeypatch.setattr(autopilot, "_greenhouse_form", gh_form)
    return db


def test_prepare_and_queue(ap, client):
    prepared = client.post(f"/api/v1/autopilot/prepare/{APP_ID}").json()
    assert prepared["apply_url"] == "https://job-boards.greenhouse.io/globex/jobs/77" and prepared["ats"] == "greenhouse"
    assert prepared["summary"] == {"total": 3, "filled": 2, "flagged": 2, "required_missing": 1}

    queue = client.get("/api/v1/autopilot/queue").json()["queue"]
    assert queue[0]["id"] == APP_ID and queue[0]["match_score"] == 81.0
    assert {f["label"] for f in queue[0]["flagged"]} == {"Why Globex?", "Agreement to Arbitrate"}

    listing = client.get("/api/v1/applications/").json()["applications"][0]
    assert "prepared_form" not in listing and listing["prepared_summary"]["total"] == 3


def test_digest_preview_and_send(ap, client, monkeypatch):
    preview = client.get("/api/v1/autopilot/digest/preview").json()
    assert preview["subject"].startswith("JobPilot: 1 application ready to send")
    assert "ML Engineer · Globex" in preview["html"] and "never submits" in preview["html"]

    monkeypatch.setattr(digest.settings, "RESEND_API_KEY", "")
    res = client.post("/api/v1/autopilot/digest/send")
    assert res.status_code == 400 and "RESEND_API_KEY" in res.json()["detail"]

    sent = []

    async def fake_send(to, subject, html, text):
        sent.append((to, subject))

    monkeypatch.setattr(digest, "send_email", fake_send)
    assert client.post("/api/v1/autopilot/digest/send").json()["to"] == "ada@example.com"
    assert sent[0][0] == "ada@example.com"


def test_nightly_tick_scans_then_sends_once(ap, monkeypatch):
    ap.tables["user_profiles"][0]["work_preferences"] = {"digest_enabled": True, "digest_hour": 0, "timezone": "Asia/Kolkata"}
    ap.tables["job_sources"] = [{"id": "s1", "user_id": USER_ID, "ats": "lever", "slug": "x", "enabled": True}]
    scans, digests = [], []

    async def fake_scan(admin, user_id, **kw):
        scans.append(user_id)
        return {"new": 2, "auto_drafting": []}

    async def fake_digest(admin, user_id, prefs, to):
        digests.append(to)

    from app.services import discovery
    monkeypatch.setattr(discovery, "scan_user", fake_scan)
    monkeypatch.setattr(digest, "send_digest", fake_digest)

    report = asyncio.run(autopilot.tick(ap))
    assert report["scanned"][0]["new"] == 2 and report["digests"] == [USER_ID]
    assert scans == [USER_ID] and digests == ["ada@example.com"]
    state = ap.tables["autopilot_state"][0]
    assert state["last_scan_on"] and state["last_digest_on"]

    asyncio.run(autopilot.tick(ap))  # same day: nothing runs twice
    assert len(scans) == 1 and len(digests) == 1


def test_cron_tick_needs_the_secret(ap, client, monkeypatch):
    monkeypatch.setattr(autopilot_api.settings, "CRON_SECRET", "s3cret")
    assert client.post("/api/v1/autopilot/tick").status_code == 401
    assert client.post("/api/v1/autopilot/tick", headers={"X-Cron-Secret": "nope"}).status_code == 401

    async def fake_tick(_admin):
        return {}

    monkeypatch.setattr(autopilot, "tick", fake_tick)
    assert client.post("/api/v1/autopilot/tick", headers={"X-Cron-Secret": "s3cret"}).json() == {"status": "started"}


def test_extension_flow(ap, client):
    token = client.post("/api/v1/autopilot/extension-tokens").json()["token"]
    assert token.startswith("jpx_") and token not in str(ap.tables["extension_tokens"])  # only the hash is stored
    h = {"X-JobPilot-Token": token}

    assert client.get("/api/v1/extension/me", headers={"X-JobPilot-Token": "jpx_wrong"}).status_code == 401
    assert client.get("/api/v1/extension/me", headers=h).json()["email"] == "ada@example.com"

    matched = client.post("/api/v1/extension/match", headers=h, json={"url": "https://job-boards.greenhouse.io/globex/jobs/77?utm=x"}).json()
    assert matched["application"]["id"] == APP_ID

    fill = client.post("/api/v1/extension/fill", headers=h, json={"application_id": APP_ID, "fields": [
        {"key": "a", "label": "First name", "required": True},
        {"key": "b", "label": "Phone number"},
        {"key": "c", "label": "Why do you want to join Globex?", "type": "textarea", "required": True},
    ]}).json()
    values = {a["key"]: a for a in fill["answers"]}
    assert values["a"]["value"] == "Ada" and values["b"]["value"] == "+91 98765 43210"
    assert values["c"]["source"] == "ai" and values["c"]["flagged"]

    saved = client.post("/api/v1/extension/answers", headers=h, json={"answers": [{"question": "Why do you want to join Globex?", "answer": "Search."}]})
    assert saved.json()["saved"] == 1 and any(a["question"].startswith("Why do you want") for a in ap.tables["qa_answers"])

    assert client.post("/api/v1/extension/applied", headers=h, json={"application_id": APP_ID}).json()["status"] == "applied"
    app = ap.tables["job_applications"][0]
    assert app["status"] == "applied" and app["follow_up_at"]

    token_id = ap.tables["extension_tokens"][0]["id"]
    assert client.delete(f"/api/v1/autopilot/extension-tokens/{token_id}").status_code == 204
    assert client.get("/api/v1/extension/me", headers=h).status_code == 401
