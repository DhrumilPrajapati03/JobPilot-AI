"""Recon without a database: result parsing, company matching, role classes, emails that are
never guessed, GitHub handle checks, ranking within caps, and the Brave/Hunter clients
against mocked HTTP. All people and companies here are fictional."""
import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.config import settings
from app.core.contacts import contact_blocker, dedupe_key
from app.experts import artifacts, recon
from app.recon import emails, handles, people
from app.services import brave

EXP = "· Experience: {c} · Education: Example Institute of Technology · Location: Bengaluru · 500+ connections on LinkedIn."


@pytest.mark.parametrize("a,b,same", [("Acme AI", "acme.ai", True), ("Acme AI", "Acme", True), ("Postbox!", "Postbox", True),
                                      ("Acme AI", "Acme Infotech", False), ("Acme Labs Pvt Ltd", "ACME", True),
                                      ("Acme", "Acmewise", False), ("", "Acme", False)])
def test_company_match_is_exact_after_suffixes(a, b, same):
    assert people.same_company(a, b) is same


@pytest.mark.parametrize("title,role", [
    ("Talent Acquisition Partner", "recruiter"), ("Tech Recruiting @ Acme", "recruiter"), ("Co-founder & CTO", "cto"),
    ("Founder & CEO", "ceo"), ("Engineering Manager, Platform", "hiring_manager"), ("Head of Engineering", "hiring_manager"),
    ("Machine Learning Engineer", "employee"), ("Talented engineer", "employee"), ("", "unknown")])
def test_role_classes(title, role):
    assert people.classify_role(title) == role


def test_headline_title_with_company_is_a_person():
    p = people.parse_result("https://in.linkedin.com/in/asha-rao-12ab?_l=en", "Asha Rao - ML Engineer at Acme AI | Example University | LinkedIn",
                            [], "Acme AI")
    assert p.name == "Asha Rao" and p.title == "ML Engineer" and p.role_class == "employee"
    assert p.linkedin_url == "https://www.linkedin.com/in/asha-rao-12ab" and p.confidence >= 0.6


def test_lookalike_company_is_rejected():
    title = "Neel P. - Director Talent acquisition at Acme Infotech - Acme Infotech | LinkedIn"
    assert people.parse_result("https://www.linkedin.com/in/neelp/", title, [EXP.format(c="Acme Infotech")], "Acme AI") is None


def test_name_company_title_uses_the_profile_snippet():
    snippet = "As an Engineering Manager at Acme, I lead a team of six engineers… " + EXP.format(c="Acme")
    p = people.parse_result("https://www.linkedin.com/in/ravi-k/", "Ravi Kumar - Acme | LinkedIn", [snippet], "Acme")
    assert p.role_class == "hiring_manager" and p.title == "Engineering Manager"
    assert any("experience at acme" in e.lower() for e in p.evidence)


def test_news_about_someone_else_is_not_a_title():
    snippet = "Sharma announced she will lead Acme's people function as the company grows its research teams."
    assert people.parse_result("https://www.linkedin.com/in/ganesh-x/", "Ganesh S. - Acme | LinkedIn", [snippet], "Acme") is None


def test_current_experience_elsewhere_rejects_a_bare_result():
    assert people.parse_result("https://www.linkedin.com/in/x-y/", "Xia Yu - Senior Engineer",
                               [EXP.format(c="Other Corp")], "Acme") is None


def test_first_person_post_gives_title_and_company():
    post = "I'm thrilled to share that I am starting a new position as a Data Scientist at Acme 🚀 so excited"
    p = people.parse_result("https://www.linkedin.com/in/mira-d/", "Mira Desai - Building things", [post], "Acme")
    assert p and p.title == "Data Scientist" and p.role_class == "employee"


@pytest.mark.parametrize("url", ["https://www.linkedin.com/company/acme", "https://acme.example/in/x", "http://www.linkedin.com/in/abc"])
def test_only_profile_urls_count(url):
    assert people.parse_result(url, "Asha Rao - Engineer at Acme", [], "Acme") is None


def test_merge_keeps_best_and_relevance_drops_non_technical():
    a = people.Person("Asha Rao", "https://www.linkedin.com/in/asha", "Engineer", "employee", 0.55, ["one"])
    b = people.Person("Asha Rao", "https://www.linkedin.com/in/asha", "ML Engineer", "employee", 0.8, ["two"])
    ops = people.Person("Om P", "https://www.linkedin.com/in/om", "Order Management Specialist", "employee", 0.8)
    merged = people.merge([a, b, ops])
    assert len(merged) == 2 and next(p for p in merged if p.slug == "asha").title == "ML Engineer"
    assert [p.name for p in merged if people.relevant(p)] == ["Asha Rao"]


def test_queries_put_recruiters_first_and_never_hold_personal_data():
    qs = people.queries("Acme AI", "Senior ML Engineer II")
    assert qs[0].role_class == "recruiter" and all(q.text.startswith('site:linkedin.com/in "Acme AI"') for q in qs)
    assert people.area_words("Senior ML Engineer II") == "ML"
    assert not any("@" in q.text for q in qs)


def test_jd_emails_split_team_and_person_and_skip_noreply():
    found = emails.in_text("Apply: careers@acme.ai or write to asha.rao@acme.ai. Updates from no-reply@acme.ai. logo@2x.png")
    assert [(f.email, f.kind) for f in found] == [("careers@acme.ai", "team"), ("asha.rao@acme.ai", "person")]
    assert emails.name_matches("asha.rao", "Asha Rao") and emails.name_matches("arao", "Asha Rao")
    assert not emails.name_matches("asha.rao", "Ravi Kumar")


def test_company_domain_needs_evidence_and_skips_job_boards():
    found = emails.in_text("careers@acme.ai")
    assert emails.company_domain("Acme AI", emails=found, urls=[]) == "acme.ai"
    assert emails.company_domain("Acme", emails=[], urls=["https://boards.greenhouse.io/acme/1", "https://www.acme.io/about"]) == "acme.io"
    assert emails.company_domain("Acme", emails=emails.in_text("hr.acme@gmail.com"), urls=["https://jobs.lever.co/acme"]) is None


def test_github_profile_must_name_the_person_and_the_company():
    good = {"name": "Asha Rao", "company": "@acme-ai", "twitter_username": "asha_r"}
    assert handles.profile_matches(good, "Asha Rao", "Acme AI")
    assert handles.profile_matches({"name": "Asha Rao", "company": "Other"}, "Asha Rao", "Acme AI") is None
    assert handles.profile_matches({"name": "Asha R", "company": "Acme"}, "Asha Rao", "Acme") is None
    assert handles.profile_matches({"name": "Asha Rao", "bio": "Infra at Acme. Opinions mine."}, "Asha Rao", "Acme")


def entry(role, *, name="X Y", email="", blocked="", connected=False, conf=0.7):
    e = {"contact_id": f"{role}-{name}", "name": name, "role_class": role, "email": email, "email_source": "hunter" if email else "",
         "blocked": blocked, "connected": connected, "confidence": conf}
    e["channel"] = recon.channel_for(e)
    return e


def test_suggestions_respect_slots_order_and_cooldown():
    rows = [entry("employee", name="Peer One"), entry("recruiter", name="Rec Busy", blocked="Contacted on 20 Nov"),
            entry("recruiter", name="Rec Two", email="rec@acme.ai"), entry("hiring_manager", name="Lead One"),
            entry("employee", name="Friend", connected=True), entry("ceo", name="Boss")]
    recon.suggest(rows, 3)
    # recruiter (the busy one is in cooldown), hiring manager, then a referral from your connections
    assert sorted(r["name"] for r in rows if r["suggested"]) == ["Friend", "Lead One", "Rec Two"]
    assert next(r for r in rows if r["name"] == "Friend")["channel"] == "referral"
    recon.suggest(rows, 0)
    assert not any(r["suggested"] for r in rows)


def test_recipient_is_a_real_address_never_a_blocked_person():
    rows = [entry("recruiter", name="Rec Busy", email="busy@acme.ai", blocked="cooldown"),
            entry("employee", name="Peer", email="peer@acme.ai"), entry("hiring_manager", name="Lead", email="lead@acme.ai")]
    assert recon.pick_recipient(rows)["email"] == "lead@acme.ai"
    assert recon.pick_recipient([entry("employee", email="peer@acme.ai")]) is None


def test_cooldown_and_do_not_contact():
    now = datetime(2026, 11, 26, tzinfo=timezone.utc)
    assert contact_blocker({"do_not_contact": True}, None, 14, now) == "Marked do not contact."
    assert "cooldown" in contact_blocker({}, now - timedelta(days=3), 14, now)
    assert contact_blocker({}, now - timedelta(days=30), 14, now) == ""


def test_dedupe_identity_prefers_linkedin_then_email():
    assert dedupe_key("Acme", "Asha Rao", "https://in.linkedin.com/in/Asha-Rao/", "a@acme.ai") == "li:asha-rao"
    assert dedupe_key("Acme", "Asha Rao", "", "A@Acme.ai") == "email:a@acme.ai"
    assert dedupe_key("Acme AI", "Asha  Rao") == "name:acme:asha rao"


def test_contact_list_artifact_is_strict():
    card = artifacts.ContactList(company="Acme", people=[{"contact_id": "c1", "name": "Asha Rao", "role_class": "employee",
                                                          "linkedin_url": "https://www.linkedin.com/in/asha", "suggested": True}])
    assert card.people[0].suggested
    with pytest.raises(ValueError):
        artifacts.ContactList(company="Acme", people=[{"contact_id": "c1", "role_class": "employee", "html": "<b>x</b>"}])


def brave_client(responses):
    calls = []

    def respond(request):
        calls.append(request)
        status, body = responses[min(len(calls) - 1, len(responses) - 1)]
        return httpx.Response(status, json=body)
    return httpx.AsyncClient(transport=httpx.MockTransport(respond)), calls


def test_brave_search_retries_then_parses_and_sends_the_goggle(monkeypatch):
    monkeypatch.setattr(settings, "BRAVE_API_KEY", "test-key")
    real_sleep = asyncio.sleep
    monkeypatch.setattr(brave.asyncio, "sleep", lambda s: real_sleep(0))
    body = {"web": {"results": [{"url": "https://www.linkedin.com/in/asha", "title": "Asha Rao - ML Engineer at <strong>Acme</strong>",
                                 "description": "Asha &amp; team", "extra_snippets": ["one"]},
                                {"url": "http://insecure.example", "title": "x"}]}}
    client, calls = brave_client([(429, {}), (200, body)])
    results = asyncio.run(brave.web_search("q", goggles=brave.LINKEDIN_ONLY, client=client))
    assert len(calls) == 2 and calls[-1].headers["X-Subscription-Token"] == "test-key"
    assert calls[-1].url.params["goggles"] == brave.LINKEDIN_ONLY
    assert [(r.title, r.description) for r in results] == [("Asha Rao - ML Engineer at Acme", "Asha & team")]


def test_brave_errors_are_plain_and_never_show_the_key(monkeypatch):
    monkeypatch.setattr(settings, "BRAVE_API_KEY", "")
    with pytest.raises(brave.SearchNotConfigured):
        asyncio.run(brave.web_search("q"))
    monkeypatch.setattr(settings, "BRAVE_API_KEY", "secret-123")
    client, _ = brave_client([(401, {})])
    with pytest.raises(brave.SearchError) as err:
        asyncio.run(brave.web_search("q", client=client))
    assert "secret-123" not in str(err.value)


@pytest.mark.parametrize("status,email,expected", [("valid", "asha@acme.ai", "asha@acme.ai"), ("accept_all", "asha@acme.ai", None),
                                                   ("valid", "asha@other.io", None)])
def test_hunter_only_returns_verified_addresses_on_the_domain(monkeypatch, status, email, expected):
    monkeypatch.setattr(settings, "HUNTER_API_KEY", "hk")
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(
        200, json={"data": {"email": email, "verification": {"status": status}}})))
    assert asyncio.run(emails.hunter_find("acme.ai", "Asha Rao", client=client)) == expected


def test_hunter_is_off_without_a_real_key(monkeypatch):
    monkeypatch.setattr(settings, "HUNTER_API_KEY", "your-hunter-key")
    assert not emails.hunter_configured()
    assert asyncio.run(emails.hunter_find("acme.ai", "Asha Rao")) is None
