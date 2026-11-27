"""Agent runtime without a database: spec validation, tool allowlists, Supervisor routing,
redaction, and the Researcher's source/citation rules."""
import asyncio

import pytest

from app.experts import researcher, supervisor
from app.experts.artifacts import CompanyBrief, check_citations
from app.experts.runtime import redact
from app.experts.spec import AgentSpec, SpecError, builtin_specs, validate
from app.experts.tools import REGISTRY, Tool, ToolBox, ToolDenied


def test_builtin_roster_is_valid_and_only_built_experts_are_active():
    from app.core.policy import load_policy
    specs = builtin_specs()
    assert len(specs) == 14
    assert {s.id for s in specs.values() if s.status == "active"} == {
        "supervisor", "scout", "researcher", "recon", "tailor", "answerer", "email_outreach", "reviewer",
        "applicant", "connector", "inbox", "dm_outreach"}
    modes = load_policy().action_modes
    # An active expert may only propose outward actions that wait for your approval.
    assert all(modes[k] == "ask_first" for s in specs.values() if s.status == "active" for k in s.action_kinds)


@pytest.mark.parametrize("change,error", [
    ({"tools": ["send_everything"]}, "unknown tools"),
    ({"action_kinds": ["bulk_send"]}, "never-kinds"),
    ({"action_kinds": ["wire_money"]}, "not in policy.yaml"),
    ({"budgets": {"steps": 10_000}}, "above the per-case caps"),
    ({"outputs": ["html_page"]}, "unknown outputs"),
])
def test_specs_cannot_exceed_registry_policy_or_budgets(change, error):
    with pytest.raises(SpecError, match=error):
        validate(AgentSpec(id="custom_one", name="Custom", owner="user", **change))


def test_background_experts_get_no_outward_tools(monkeypatch):
    async def send(ctx, **kw):
        return {}
    monkeypatch.setitem(REGISTRY, "send_dm_now", Tool("send_dm_now", "test", False, send))
    with pytest.raises(SpecError, match="read-only tools only"):
        validate(AgentSpec(id="night_owl", name="Night", tools=["send_dm_now"], triggers=[{"kind": "routine"}]))
    validate(AgentSpec(id="day_owl", name="Day", tools=["send_dm_now"], triggers=[{"kind": "manual"}]))


def test_toolbox_refuses_tools_outside_the_allowlist():
    logged = []

    class Log:
        ctx = None

        async def add(self, kind, name, summary, detail=None, **kw):
            logged.append((kind, name))

    box = ToolBox(AgentSpec(id="scout_like", name="S", tools=["read_case"]), Log())
    with pytest.raises(ToolDenied):
        asyncio.run(box.call("route_case", case_id="x", agent="tailor", reason="r"))
    assert logged == [("blocked", "route_case")]


ACTIVE = {"supervisor", "scout", "researcher"}


def case(**kw):
    return {"id": "c", "stage": "found", "status": "open", "legacy": False, "company": "Acme", "role": "ML Engineer", **kw}


def test_supervisor_routes_research_then_recon_then_waits_for_tailor():
    first = supervisor.decide(case(), set(), ACTIVE)
    assert first.action == "route" and first.route.agent == "researcher"
    recon = supervisor.decide(case(), {"company_brief"}, ACTIVE | {"recon"})
    assert recon.action == "route" and recon.route.agent == "recon" and recon.stage == "researched"
    after = supervisor.decide(case(), {"company_brief", "contact_list"}, ACTIVE)
    assert after.action == "wait" and after.route.agent == "tailor" and after.stage == "researched"
    later = supervisor.decide(case(stage="researched"), {"company_brief", "contact_list", "resume_version"}, ACTIVE | {"tailor"})
    assert later.action == "wait" and later.route.agent == "email_outreach" and later.stage == "tailored"
    connect = supervisor.decide(case(stage="tailored"), {"company_brief", "contact_list", "resume_version", "draft"}, ACTIVE)
    assert connect.action == "wait" and connect.route.agent == "connector" and connect.stage == "ready"
    refer = supervisor.decide(case(stage="tailored"), {"company_brief", "contact_list", "resume_version", "draft", "invite_set"}, ACTIVE)
    assert refer.action == "wait" and refer.route.agent == "dm_outreach"
    done = supervisor.decide(case(stage="tailored"), {"company_brief", "contact_list", "resume_version", "draft", "invite_set", "dm_set"}, ACTIVE)
    assert done.action == "done" and done.stage == "ready"


@pytest.mark.parametrize("override", [{"legacy": True}, {"status": "closed"}, {"stage": "applied"}])
def test_supervisor_leaves_imported_closed_and_applied_cases_alone(override):
    assert supervisor.decide(case(**override), set(), ACTIVE).action == "skip"


def test_stage_never_moves_backwards():
    assert supervisor.decide(case(stage="tailored"), {"company_brief"}, ACTIVE).stage == "tailored"


def test_redaction_drops_secrets_and_bounds_text():
    out = redact({"url": "https://x", "access_token": "abc", "nested": {"Authorization": "Bearer y"}, "body": "z" * 2000,
                  "items": list(range(50))})
    assert out["access_token"] == "[redacted]" and out["nested"]["Authorization"] == "[redacted]"
    assert len(out["body"]) < 600 and len(out["items"]) == 20


def test_researcher_sources_skip_social_and_duplicates():
    c = case(source_url="https://jobs.lever.co/acme/1",
             jd_text="About us: https://acme.example/about. Follow https://www.linkedin.com/company/acme and https://acme.example/about.")
    assert researcher.source_urls(c, ["https://acme.example/blog"]) == [
        "https://jobs.lever.co/acme/1", "https://acme.example/blog", "https://acme.example/about"]


def test_uncited_claims_are_dropped_and_saved_briefs_must_cite_real_sources():
    draft = researcher.BriefDraft(product=[{"text": "Makes rockets", "sources": [1]}, {"text": "Invented", "sources": [9]}],
                                  tech_stack=[{"text": "Python", "sources": [1, 2]}], confidence="certain")
    data, dropped = researcher.keep_cited(draft, {1})
    assert dropped == 1 and data["tech_stack"] == [{"text": "Python", "sources": [1]}] and data["confidence"] == "low"
    brief = CompanyBrief(company="Acme", sources=[{"n": 1, "title": "Job description"}], **data)
    assert check_citations(brief) == []
    bad = CompanyBrief(company="Acme", sources=[{"n": 1}], product=[{"text": "x", "sources": [2]}])
    assert check_citations(bad)
    with pytest.raises(ValueError):
        CompanyBrief(company="Acme", sources=[{"n": 1}], html="<b>no</b>")


@pytest.mark.parametrize("stated,count,expected", [("high", 1, "low"), ("high", 2, "medium"), ("high", 4, "high"),
                                                   ("medium", 1, "low"), ("certain", 5, "low")])
def test_confidence_never_exceeds_the_evidence(stated, count, expected):
    assert researcher.cap_confidence(stated, count) == expected
