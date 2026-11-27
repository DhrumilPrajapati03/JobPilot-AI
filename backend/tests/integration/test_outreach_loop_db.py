"""Day 11: the outreach loop end to end on the throwaway Postgres (model, Gmail faked):

    Recon's list -> Connector invitations -> you approve and send them from the queue
    -> LinkedIn's "accepted" email -> Inbox marks the contact -> after the wait, DM Outreach
    drafts a message -> you approve and send it; referral asks to existing connections.

Caps are enforced at Courier's door at every send: invitations per day, messages per day
(shared by DMs and referral asks), and the accept-to-DM wait. Fictional people only."""
import asyncio
import os
import re
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
from app.experts import artifacts, connector, dm_outreach, inbox, runtime, spec  # noqa: E402
from app.services import autopilot  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "resume"
JOB = "Acme is hiring an ML Engineer to build RAG on pgvector with FastAPI."
POLICY = policy_mod.load_policy("""
version: 1
action_modes: {send_email: ask_first, send_linkedin_invite: ask_first, send_linkedin_dm: ask_first, referral_request: ask_first,
               create_calendar_event: ask_first, save_artifact: act}
caps: {emails_per_day: 5, linkedin_invites_per_day: 2, linkedin_invites_per_week: 10, linkedin_dms_per_day: 1,
       max_people_per_company: 3, min_hours_accept_to_dm: 24, no_contact_if_touched_within_days: 14, quiet_hours: "", timezone: UTC}
budgets: {per_case: {steps: 200}, monthly_usd: 5}
""")


class FakeModel:
    """Short, true notes and messages from the fixture vault, one per id in the prompt."""
    async def ainvoke(self, prompt):
        ids = re.findall(r"^([0-9a-f-]{36}) \|", prompt[1].content, re.M)
        if prompt[0].content.startswith("You write short LinkedIn connection notes"):
            return connector.InviteNotes(notes=[connector.Note(contact_id=i, note="Hi there, I applied for the ML Engineer role at Acme; "
                                                               "I built a RAG service on PostgreSQL and pgvector at Example Labs.") for i in ids])
        return dm_outreach.Messages(messages=[dm_outreach.Message(contact_id=i, text="Hi there, thanks for connecting. I applied for "
                                    "the ML Engineer role at Acme; I built a RAG service on PostgreSQL and pgvector at Example Labs. "
                                    "Who on the team would be best to talk to?") for i in ids])


class FakeGmail:
    messages: dict = {}

    def search(self, client, token, query, limit=50):
        return [m.id for m in self.messages.values() if ("accepted your invitation" in query) == m.from_email.endswith("linkedin.com")]

    def fetch(self, client, token, gid):
        return self.messages[gid]


@pytest.fixture()
def owner(monkeypatch):
    for name, value in {"RESUME_MASTER_PATH": str(FIXTURES / "master.tex"), "FACT_VAULT_PATH": str(FIXTURES / "fact_vault.yaml")}.items():
        monkeypatch.setattr(settings, name, value)
    for module in (policy_mod,):
        monkeypatch.setattr(module, "load_policy", lambda text=None: POLICY)
    for module in (connector, dm_outreach, inbox):
        monkeypatch.setattr(module, "load_policy", lambda: POLICY)
    model = FakeModel()
    monkeypatch.setattr(connector.llm, "with_structured", lambda llm_, schema: model)
    import app.experts.email_outreach as eo
    monkeypatch.setattr(eo, "chat_model", lambda spec_: object())
    fake = FakeGmail()
    fake.messages = {}
    monkeypatch.setattr(gmail, "search", fake.search)
    monkeypatch.setattr(gmail, "fetch", fake.fetch)
    monkeypatch.setattr(connections, "google_access_token", lambda uid, need, client=None: ("token", "ada@example.invalid"))
    uid = str(uuid.uuid4())
    db = get_db()
    db.fetch("insert into auth.users(id, email) values (%s::uuid, %s)", [uid, f"{uid}@example.invalid"])
    spec.sync_builtins(db)
    token = autopilot.new_token()
    db.fetch("insert into public.extension_tokens (user_id, token_hash) values (%s::uuid, %s)", [uid, autopilot.hash_token(token)])
    yield uid, token, fake
    db.fetch("delete from auth.users where id = %s::uuid", [uid])


def expert(uid, agent, case_id=None, **inputs):
    ctx = runtime.ExpertContext(uid, spec.load_spec(get_db(), agent), case_id, inputs)
    return asyncio.run(runtime.run_expert(ctx))


def person(uid, name, cls, *, connected=False):
    slug = name.lower().replace(" ", "-")
    c = contacts.upsert(uid, company="Acme", name=name, role_class=cls, linkedin_url=f"https://www.linkedin.com/in/{slug}/")
    return {"contact_id": c["id"], "name": name, "title": cls.title(), "role_class": cls, "linkedin_url": f"https://www.linkedin.com/in/{slug}/",
            "email": "", "connected": connected, "suggested": True, "channel": "referral" if connected else "linkedin", "blocked": ""}


def test_the_outreach_loop_from_invitation_to_message_with_caps(owner):
    from fastapi.testclient import TestClient

    from app.main import app
    uid, token, fake = owner
    client = TestClient(app, headers={"X-JobPilot-Token": token})
    case = cases.create_case(uid, company="Acme", role="ML Engineer", jd_text=JOB)
    jane, raj, kim = person(uid, "Jane Example", "recruiter"), person(uid, "Raj Example", "hiring_manager"), \
        person(uid, "Kim Example", "employee", connected=True)
    artifacts.save(uid, case["id"], "contact_list", {"company": "Acme", "people": [jane, raj, kim]}, agent="recon")

    # 1. Connector: invitations for the two LinkedIn people; the connection gets a referral ask instead.
    assert expert(uid, "connector", case["id"])["ready"] == 2
    referral = expert(uid, "dm_outreach", case["id"])
    assert referral["ready"] == 1
    queue = client.post("/api/v1/extension/linkedin/queue").json()["items"]
    by_name = {i["name"]: i for i in queue}
    assert set(by_name) == {"Jane Example", "Raj Example", "Kim Example"} and by_name["Kim Example"]["kind"] == "dm"

    def send(item):
        assert client.post("/api/v1/extension/linkedin/approve", json={"action_id": item["id"], "payload_sha256": item["payload_sha256"]}).is_success
        opened = client.post("/api/v1/extension/linkedin/start", json={"action_id": item["id"]}).json()
        if opened["ok"]:
            assert client.post("/api/v1/extension/linkedin/done", json={"action_id": item["id"], "sent": True}).is_success
        return opened

    # 2. You send both invitations; a third the same day would be over the cap of 2.
    assert send(by_name["Jane Example"])["ok"] and send(by_name["Raj Example"])["ok"]
    extra = actions.propose(uid, "send_linkedin_invite", {"contact_id": str(uuid.uuid4()), "name": "Other", "company": "Beta",
                            "profile_url": "https://www.linkedin.com/in/other/", "note": "Hi"}, agent="connector",
                            idempotency_key=f"t:{uuid.uuid4()}", policy=POLICY)
    actions.review(uid, extra["id"], ok=True)
    over = send({"id": extra["id"], "payload_sha256": extra["payload_sha256"]})
    assert not over["ok"] and "Daily cap" in over["reasons"][0]

    # 3. LinkedIn emails that Jane accepted; Inbox marks her. No DM before the 24-hour wait.
    fake.messages["l1"] = gmail.Message("l1", "", "invitations@linkedin.com", "LinkedIn", "Jane Example accepted your invitation",
                                        "", "", datetime.now(timezone.utc).isoformat(), {})
    assert expert(uid, "inbox", task="poll")["counts"] == {"accepted": 1}
    assert get_db().fetch("select stage from public.contact where id = %s::uuid", [jane["contact_id"]])[0][0] == "accepted"
    assert expert(uid, "dm_outreach", task="after_accept") == {"messages": 0}

    # 4. A day later: one message to Jane (not Raj, who never accepted).
    get_db().fetch("update public.contact set accepted_at = now() - interval '25 hours' where id = %s::uuid", [jane["contact_id"]])
    assert expert(uid, "dm_outreach", task="after_accept") == {"messages": 1}
    queue = {i["name"] + ":" + i["status"]: i for i in client.post("/api/v1/extension/linkedin/queue").json()["items"]}
    dm = queue["Jane Example:reviewed"]
    assert dm["kind"] == "dm" and "thanks for connecting" in dm["text"]
    assert expert(uid, "dm_outreach", task="after_accept") == {"messages": 0}           # once

    # 5. Messages per day is 1, shared by DMs and referral asks: Jane's goes, Kim's waits.
    assert send(dm)["ok"]
    held = send(queue["Kim Example:reviewed"])
    assert not held["ok"] and "Daily cap reached: linkedin_dms_per_day" in held["reasons"][0]
    stages = dict(get_db().fetch("select name, stage from public.contact where user_id = %s::uuid", [uid]))
    assert stages["Jane Example"] == "message_sent" and stages["Raj Example"] == "invite_sent"
    touches = [r[0] for r in get_db().fetch("select channel from public.contact_touch where user_id = %s::uuid order by sent_at", [uid])]
    assert touches == ["linkedin_invite", "linkedin_invite", "linkedin_dm"]
    kinds = {a["kind"] for a in cases.get_case(uid, case["id"])["artifacts"]}
    assert {"invite_set", "dm_set"} <= kinds


def test_a_dm_without_a_recorded_acceptance_never_goes_out(owner):
    uid, token, _ = owner
    c = contacts.upsert(uid, company="Acme", name="Lee Example", role_class="employee", linkedin_url="https://www.linkedin.com/in/lee-example/")
    a = actions.propose(uid, "send_linkedin_dm", {"contact_id": c["id"], "name": "Lee", "company": "Acme",
                        "profile_url": "https://www.linkedin.com/in/lee-example/", "body": "Hi Lee"}, agent="dm_outreach",
                        idempotency_key=f"t:{uuid.uuid4()}", policy=POLICY)
    actions.review(uid, a["id"], ok=True)
    actions.approve(uid, a["id"], payload_sha256=a["payload_sha256"])
    gate = actions.start_execution(uid, a["id"], policy=POLICY)
    assert not gate.run and any("No recorded invite acceptance" in r for r in gate.verdict.reasons)
