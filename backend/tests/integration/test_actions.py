"""Action state machine, Courier gate and budgets against the throwaway Postgres."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("JOBDOTS_TEST_DATABASE_URL"),
                                reason="needs the throwaway database from scripts/check_database.py")

from app.core import actions, budgets, cases  # noqa: E402
from app.core.policy import load_policy  # noqa: E402
from app.db import get_db  # noqa: E402

POLICY = load_policy("""
version: 1
action_modes: {send_email: ask_first, captcha_or_2fa: hand_off, bulk_send: never, save_artifact: act}
caps: {emails_per_day: 1, linkedin_invites_per_day: 1, linkedin_invites_per_week: 1, linkedin_dms_per_day: 1,
       max_people_per_company: 5, min_hours_accept_to_dm: 24, no_contact_if_touched_within_days: 14,
       quiet_hours: "", timezone: UTC}
autonomy: {send_email: {auto_after_clean_approvals: 2, daily_cap: 1}}
budgets: {per_case: {steps: 3}, monthly_usd: 1}
""")
NOW = datetime.now(timezone.utc)


@pytest.fixture()
def owner():
    uid = str(uuid.uuid4())
    get_db().fetch("insert into auth.users(id, email) values (%s::uuid, %s)", [uid, f"{uid}@example.invalid"])
    yield uid
    get_db().fetch("delete from auth.users where id = %s::uuid", [uid])


def _ready(owner, key, payload=None, case_id=None):
    a = actions.propose(owner, "send_email", payload or {"to": f"{key}@example.invalid", "body": "Hi"}, agent="email_outreach",
                        idempotency_key=key, case_id=case_id, policy=POLICY, now=NOW)
    a = actions.review(owner, a["id"], ok=True)
    return actions.approve(owner, a["id"], payload_sha256=a["payload_sha256"])


def test_full_lifecycle_and_idempotent_replay(owner):
    case = cases.create_case(owner, company="Acme", role="ML Engineer")
    first = actions.propose(owner, "send_email", {"to": "hr@example.invalid"}, agent="email_outreach",
                            idempotency_key="k1", case_id=case["id"], policy=POLICY, now=NOW)
    again = actions.propose(owner, "send_email", {"to": "hr@example.invalid"}, agent="email_outreach",
                            idempotency_key="k1", case_id=case["id"], policy=POLICY, now=NOW)
    assert first["id"] == again["id"] and first["status"] == "proposed"
    with pytest.raises(actions.ActionError) as conflict:
        actions.propose(owner, "send_email", {"to": "other@example.invalid"}, agent="x", idempotency_key="k1", policy=POLICY)
    assert conflict.value.code == "idempotency_key_conflict"
    reviewed = actions.review(owner, first["id"], ok=True, notes=["claims match the vault"])
    approved = actions.approve(owner, first["id"], payload_sha256=reviewed["payload_sha256"])
    gate = actions.start_execution(owner, first["id"], policy=POLICY, now=NOW)
    assert gate.run and gate.action["status"] == "executing" and gate.action["payload"] == {"to": "hr@example.invalid"}
    actions.record_outcome(owner, first["id"], "provider_accepted", provider_ref="msg-1")
    done = actions.record_outcome(owner, first["id"], "delivered")
    assert done["status"] == "delivered" and done["provider_ref"] == "msg-1"
    assert approved["status"] == "approved"
    assert [a["status"] for a in cases.get_case(owner, case["id"])["actions"]] == ["delivered"]


def test_edit_clears_approval_and_stale_hash_is_refused(owner):
    a = _ready(owner, "edit")
    edited = actions.edit(owner, a["id"], {"to": "edit@example.invalid", "body": "Changed"})
    assert edited["status"] == "proposed" and edited["revision"] == 2
    with pytest.raises(actions.ActionError):
        actions.start_execution(owner, a["id"], policy=POLICY, now=NOW)
    reviewed = actions.review(owner, a["id"], ok=True)
    with pytest.raises(actions.ActionError) as stale:
        actions.approve(owner, a["id"], payload_sha256=a["payload_sha256"])  # the old draft's hash
    assert stale.value.code == "stale_payload"
    actions.approve(owner, a["id"], payload_sha256=reviewed["payload_sha256"])
    assert actions.start_execution(owner, a["id"], policy=POLICY, now=NOW).run


def test_unknown_never_and_hand_off(owner):
    with pytest.raises(ValueError):
        actions.propose(owner, "wire_money", {}, agent="x", idempotency_key="u", policy=POLICY)
    blocked = actions.propose(owner, "bulk_send", {}, agent="x", idempotency_key="b", policy=POLICY, now=NOW)
    assert blocked["status"] == "blocked"
    hand_off = actions.propose(owner, "captcha_or_2fa", {}, agent="applicant", idempotency_key="h", policy=POLICY)
    reviewed = actions.review(owner, hand_off["id"], ok=True)
    with pytest.raises(actions.ActionError) as refused:
        actions.approve(owner, hand_off["id"], payload_sha256=reviewed["payload_sha256"])
    assert refused.value.code == "not_approvable"


def test_daily_cap_is_enforced_at_the_courier_gate(owner):
    first, second = _ready(owner, "cap-1"), _ready(owner, "cap-2")
    assert actions.start_execution(owner, first["id"], policy=POLICY, now=NOW).run
    gate = actions.start_execution(owner, second["id"], policy=POLICY, now=NOW)
    assert not gate.run and "Daily cap" in gate.verdict.reasons[0]
    assert gate.action["status"] == "approved"  # still approved; runs tomorrow
    assert actions.start_execution(owner, second["id"], policy=POLICY, now=NOW + timedelta(days=1)).run


def test_refused_action_circuit_breaker(owner):
    case = cases.create_case(owner, company="Loop Co")
    for i in range(3):
        actions.propose(owner, "bulk_send", {"n": i}, agent="x", idempotency_key=f"loop-{i}", case_id=case["id"],
                        policy=POLICY, now=NOW)
    with pytest.raises(actions.CircuitOpen):
        actions.propose(owner, "send_email", {"to": "a@example.invalid"}, agent="x", idempotency_key="after",
                        case_id=case["id"], policy=POLICY, now=NOW)


def test_autonomy_is_earned_by_clean_approvals(owner):
    assert not actions.auto_approval_allowed(owner, "send_email", policy=POLICY, now=NOW)
    _ready(owner, "clean-1"), _ready(owner, "clean-2")
    assert actions.auto_approval_allowed(owner, "send_email", policy=POLICY, now=NOW)
    edited = _ready(owner, "edited")
    actions.edit(owner, edited["id"], {"to": "edited@example.invalid", "body": "v2"})
    reviewed = actions.review(owner, edited["id"], ok=True)
    actions.approve(owner, edited["id"], payload_sha256=reviewed["payload_sha256"])
    assert not actions.auto_approval_allowed(owner, "send_email", policy=POLICY, now=NOW)


def test_budgets(owner):
    case = cases.create_case(owner, company="Budget Co")
    budgets.charge(owner, "steps", 2, case_id=case["id"], agent="tailor")
    assert budgets.check(owner, case["id"], policy=POLICY) == []
    budgets.charge(owner, "steps", 1, case_id=case["id"], agent="tailor")
    budgets.charge(owner, "usd", 1.5, agent="tailor")
    reasons = budgets.check(owner, case["id"], policy=POLICY)
    assert any("steps" in r for r in reasons) and any("Monthly" in r for r in reasons)


def test_case_timeline(owner):
    case = cases.create_case(owner, company="Timeline Co", role="Engineer")
    cases.add_event(owner, case["id"], "note", actor="agent", actor_name="scout", summary="Found it")
    cases.set_stage(owner, case["id"], "applied")
    full = cases.get_case(owner, case["id"])
    assert full["stage"] == "applied"
    assert [e["kind"] for e in full["events"]] == ["created", "note", "stage_changed"]
    with pytest.raises(LookupError):
        cases.add_event(str(uuid.uuid4()), case["id"], "note", actor="agent")
