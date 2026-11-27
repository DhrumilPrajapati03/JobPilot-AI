"""Day 10 against the throwaway Postgres, with Gmail and the model faked: a reply moves the
case and withdraws the pending follow-up; an interview invite with a time proposes a calendar
event; LinkedIn's acceptance email marks the contact; follow-ups are drafted once and only
pass Courier's gate as a real first follow-up; interval routines. Fictional people only."""
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("JOBDOTS_TEST_DATABASE_URL"),
                                reason="needs the throwaway database from scripts/check_database.py")

from app.config import settings  # noqa: E402
from app.core import actions, cases, contacts  # noqa: E402
from app.core import policy as policy_mod  # noqa: E402
from app.courier import connections, gmail  # noqa: E402
from app.db import get_db  # noqa: E402
from app.experts import inbox, routines, runtime, spec  # noqa: E402
from app.services.runs import RunStore  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "resume"
JOB = "Acme is hiring an ML Engineer to build RAG on pgvector with FastAPI."
POLICY = policy_mod.load_policy("""
version: 1
action_modes: {send_email: ask_first, send_linkedin_invite: ask_first, create_calendar_event: ask_first, save_artifact: act}
caps: {emails_per_day: 10, linkedin_invites_per_day: 5, linkedin_invites_per_week: 5, linkedin_dms_per_day: 5,
       max_people_per_company: 3, min_hours_accept_to_dm: 24, no_contact_if_touched_within_days: 14,
       follow_up_after_days: 5, quiet_hours: "", timezone: UTC}
budgets: {per_case: {steps: 200}, monthly_usd: 5}
""")


class FakeGmail:
    def __init__(self):
        self.messages: dict[str, gmail.Message] = {}
        self.queries: list[str] = []

    def search(self, client, token, query, limit=50):
        self.queries.append(query)
        linkedin = "accepted your invitation" in query
        return [m.id for m in self.messages.values() if (m.from_email.endswith("linkedin.com")) == linkedin]

    def fetch(self, client, token, gid):
        return self.messages[gid]


class FakeTime:
    async def ainvoke(self, prompt):
        start = (datetime.now(timezone.utc) + timedelta(days=2)).replace(microsecond=0)
        return inbox.InterviewTime(found=True, start=start.isoformat(), end=(start + timedelta(hours=1)).isoformat(),
                                   timezone="UTC", title="Interview with Acme", where="Video call")


@pytest.fixture()
def owner(monkeypatch):
    for name, value in {"RESUME_MASTER_PATH": str(FIXTURES / "master.tex"), "FACT_VAULT_PATH": str(FIXTURES / "fact_vault.yaml")}.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(policy_mod, "load_policy", lambda text=None: POLICY)
    monkeypatch.setattr(inbox, "load_policy", lambda: POLICY)
    fake = FakeGmail()
    monkeypatch.setattr(gmail, "search", fake.search)
    monkeypatch.setattr(gmail, "fetch", fake.fetch)
    monkeypatch.setattr(connections, "google_access_token", lambda uid, need, client=None: ("token", "ada@example.invalid"))
    monkeypatch.setattr(inbox.llm, "with_structured", lambda llm_, schema: FakeTime())
    import app.experts.email_outreach as eo
    monkeypatch.setattr(eo, "chat_model", lambda spec_: object())
    uid = str(uuid.uuid4())
    db = get_db()
    db.fetch("insert into auth.users(id, email) values (%s::uuid, %s)", [uid, f"{uid}@example.invalid"])
    spec.sync_builtins(db)
    yield uid, fake
    db.fetch("delete from auth.users where id = %s::uuid", [uid])


def sent_email(uid, company, to, name, days_ago, thread):
    case = cases.create_case(uid, company=company, role="ML Engineer", jd_text=JOB)
    cases.set_stage(uid, case["id"], "applied", actor="user")
    contact = contacts.upsert(uid, company=company, name=name, role_class="recruiter", email=to, email_source="job_description")
    payload = {"to": to, "to_name": name, "from_name": "Ada Example", "subject": f"ML Engineer at {company}",
               "body": f"Hi, about the ML Engineer role at {company}.", "company": company, "contact_id": contact["id"], "attachment": None}
    a = actions.propose(uid, "send_email", payload, agent="email_outreach", case_id=case["id"], idempotency_key=f"t:{uuid.uuid4()}", policy=POLICY)
    actions.review(uid, a["id"], ok=True)
    actions.approve(uid, a["id"], payload_sha256=a["payload_sha256"])
    actions.start_execution(uid, a["id"], policy=POLICY)
    actions.record_outcome(uid, a["id"], "provider_accepted", provider_ref="g-" + a["id"][:6])
    get_db().fetch("update public.action set executing_at = now() - %s::interval, thread_id = %s where id = %s::uuid",
                   [f"{days_ago} days", thread, a["id"]])
    return case, contact, a


def run(uid, task):
    ctx = runtime.ExpertContext(uid, spec.load_spec(get_db(), "inbox"), None, {"task": task})
    return asyncio.run(runtime.run_expert(ctx))


def message(gid, sender, name, subject, text, thread="", headers=None):
    return gmail.Message(gid, thread, sender, name, subject, text[:100], text, datetime.now(timezone.utc).isoformat(), headers or {})


def test_follow_up_then_reply_withdraws_it_and_moves_the_case(owner):
    uid, fake = owner
    case, contact, a = sent_email(uid, "Acme", "jane@acme.example", "Jane Example", 6, "t-acme")
    first = run(uid, "follow_up")
    assert first == {"proposed": 1}
    fu = get_db().fetch("select id::text, status, payload from public.action where payload->>'follow_up_of' = %s", [a["id"]])[0]
    assert fu[1] == "reviewed" and fu[2]["thread_id"] == "t-acme" and fu[2]["in_reply_to"].startswith(f"<jobdots.{a['id']}@")
    assert fu[2]["subject"] == "Re: ML Engineer at Acme" and "Acme" in fu[2]["body"]
    assert run(uid, "follow_up") == {"proposed": 0}                       # never twice

    # Courier's gate: this follow-up may go out despite the 14-day cooldown...
    actions.approve(uid, fu[0], payload_sha256=get_db().fetch("select payload_sha256 from public.action where id = %s::uuid", [fu[0]])[0][0])
    # ...but before it does, Jane replies (via a colleague, same thread).
    fake.messages["m1"] = message("m1", "hr@acme.example", "Acme HR", "Re: ML Engineer at Acme",
                                  "Thanks Ada, I've passed this on to the team.\n\nOn Mon, Ada wrote:\n> interview", thread="t-acme")
    out = run(uid, "poll")
    assert out["counts"] == {"reply": 1}
    assert get_db().fetch("select status from public.action where id = %s::uuid", [fu[0]])[0][0] == "cancelled"
    assert cases.get_case(uid, case["id"])["stage"] == "replied"
    assert get_db().fetch("select stage from public.contact where id = %s::uuid", [contact["id"]])[0][0] == "replied"
    timeline = [e["summary"] for e in cases.get_case(uid, case["id"])["events"]]
    assert any(s.startswith("Acme HR replied: Thanks Ada") for s in timeline)
    assert run(uid, "poll")["handled"] == 0                                 # each message once
    assert all("-from:me" in q for q in fake.queries if "linkedin" not in q)


def test_interview_invite_proposes_a_calendar_event_and_rejection_only_notes(owner):
    uid, fake = owner
    case, _, _ = sent_email(uid, "Acme", "jane@acme.example", "Jane Example", 2, "t-a")
    other, _, _ = sent_email(uid, "Globex", "raj@globex.example", "Raj Example", 2, "t-g")
    fake.messages["i1"] = message("i1", "jane@acme.example", "Jane", "Re: ML Engineer at Acme",
                                  "Great to hear from you. Could we do an interview on Wednesday at 3pm UTC?")
    fake.messages["r1"] = message("r1", "raj@globex.example", "Raj", "Re: ML Engineer at Globex",
                                  "Thank you. Unfortunately, we have decided to move forward with other candidates.")
    out = run(uid, "poll")
    assert out["counts"] == {"interview": 1, "rejection": 1}
    assert cases.get_case(uid, case["id"])["stage"] == "interview"
    event = get_db().fetch("""select status, payload from public.action where case_id = %s::uuid and kind = 'create_calendar_event'""",
                           [case["id"]])[0]
    assert event[0] == "reviewed" and event[1]["summary"] == "Interview with Acme" and "attendees" not in event[1]
    g = cases.get_case(uid, other["id"])
    assert g["stage"] == "applied" and g["status"] == "open"                     # a rejection never closes the case itself
    assert any("Looks like a no from Globex" in e["summary"] for e in g["events"])


def test_linkedin_acceptance_marks_the_invited_contact(owner):
    uid, fake = owner
    case = cases.create_case(uid, company="Acme", role="ML Engineer", jd_text=JOB)
    lee = contacts.upsert(uid, company="Acme", name="Lee Example", role_class="employee", linkedin_url="https://www.linkedin.com/in/lee-example/")
    a = actions.propose(uid, "send_linkedin_invite", {"contact_id": lee["id"], "name": "Lee Example", "company": "Acme",
                        "profile_url": "https://www.linkedin.com/in/lee-example/", "note": "Hi Lee"}, agent="connector",
                        case_id=case["id"], idempotency_key=f"t:{uuid.uuid4()}", policy=POLICY)
    actions.review(uid, a["id"], ok=True)
    actions.approve(uid, a["id"], payload_sha256=a["payload_sha256"])
    actions.start_execution(uid, a["id"], policy=POLICY)
    actions.record_outcome(uid, a["id"], "provider_accepted")
    fake.messages["l1"] = message("l1", "invitations@linkedin.com", "LinkedIn", "Lee Example accepted your invitation", "")
    fake.messages["l2"] = message("l2", "invitations@linkedin.com", "LinkedIn", "Stranger Example accepted your invitation", "")
    out = run(uid, "poll")
    assert out["counts"] == {"accepted": 2}
    row = get_db().fetch("select stage, accepted_at from public.contact where id = %s::uuid", [lee["id"]])[0]
    assert row[0] == "accepted" and row[1] is not None
    assert any(e["summary"] == "Lee Example accepted your LinkedIn invitation" for e in cases.get_case(uid, case["id"])["events"])


def test_interval_routines_run_every_half_hour(owner):
    uid, _ = owner
    routines.ensure_defaults(uid)
    now = datetime.now(timezone.utc)
    assert "inbox_poll" in [r["key"] for r in routines.due_routines(uid, now)]
    out = asyncio.run(routines.tick(RunStore(), uid, now=now))
    assert "inbox_poll" in out["queued"]
    assert "inbox_poll" not in [r["key"] for r in routines.due_routines(uid, now + timedelta(minutes=10))]
    assert "inbox_poll" in [r["key"] for r in routines.due_routines(uid, now + timedelta(minutes=31))]
    queued = get_db().fetch("""select inputs from public.agent_runs where user_id = %s::uuid and inputs->>'agent' = 'inbox'""", [uid])
    assert queued[0][0]["task"] == "poll"


def test_courier_lets_only_a_real_first_follow_up_through_the_cooldown(owner):
    uid, _ = owner
    _, _, a = sent_email(uid, "Acme", "jane@acme.example", "Jane Example", 6, "t-x")

    def approved(to, key):
        p = {"to": to, "to_name": "X", "subject": "Re: ML Engineer at Acme", "body": "Following up.", "company": "Acme",
             "contact_id": None, "attachment": None, "follow_up_of": a["id"]}
        f = actions.propose(uid, "send_email", p, agent="inbox", idempotency_key=key, policy=POLICY)
        actions.review(uid, f["id"], ok=True)
        return actions.approve(uid, f["id"], payload_sha256=f["payload_sha256"])
    fake = actions.start_execution(uid, approved("someone@else.example", "f-fake")["id"], policy=POLICY)
    assert not fake.run and any("follow-up must answer" in r for r in fake.verdict.reasons)
    real = actions.start_execution(uid, approved("jane@acme.example", "f-real")["id"], policy=POLICY)
    assert real.run                                                     # inside the 14-day cooldown, allowed once
    actions.record_outcome(uid, real.action["id"], "provider_accepted")
    second = actions.start_execution(uid, approved("jane@acme.example", "f-second")["id"], policy=POLICY)
    assert not second.run                                               # never a second follow-up
