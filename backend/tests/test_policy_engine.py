"""Policy engine (plan section 8.1, Courier/policy row): every kind has a mode, unknown kinds
are rejected, caps/cooldowns/quiet hours/kill switch are enforced. Pure; no database."""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.policy import (EXECUTABLE, MODES, PolicyError, UnknownActionKind, Usage, check_execution,
                             load_policy)

BASE = """
version: 1
kill_switch: false
action_modes:
  save_artifact: act
  fill_form: act_with_preview
  send_email: ask_first
  send_linkedin_invite: ask_first
  send_linkedin_dm: ask_first
  referral_request: ask_first
  captcha_or_2fa: hand_off
  bulk_send: never
caps:
  emails_per_day: 2
  linkedin_invites_per_day: 3
  linkedin_invites_per_week: 5
  linkedin_dms_per_day: 2
  max_people_per_company: 2
  min_hours_accept_to_dm: 24
  no_contact_if_touched_within_days: 14
  quiet_hours: "22:00-08:00"
  timezone: Asia/Kolkata
autonomy:
  send_email:
    auto_after_clean_approvals: 15
    daily_cap: 5
"""
# 12:00 in Kolkata (06:30 UTC): outside quiet hours.
NOON = datetime(2026, 11, 25, 6, 30, tzinfo=timezone.utc)


def policy(text=BASE):
    return load_policy(text)


def test_repo_policy_file_is_valid_and_every_kind_has_a_known_mode():
    p = load_policy()
    assert p.version == 1 and p.action_modes
    assert set(p.action_modes.values()) <= set(MODES)
    for kind in ("send_email", "send_linkedin_invite", "send_linkedin_dm", "submit_application", "referral_request"):
        assert p.mode_for(kind) == "ask_first"
    for kind in ("bulk_send", "fake_identity", "scrape_behind_login"):
        assert p.mode_for(kind) == "never"


def test_unknown_kind_is_rejected_not_defaulted():
    with pytest.raises(UnknownActionKind):
        policy().mode_for("delete_everything")
    verdict = check_execution(policy(), "delete_everything", {}, Usage(), NOON)
    assert not verdict.allowed and verdict.mode == "never"


@pytest.mark.parametrize("kind", ["captcha_or_2fa", "bulk_send"])
def test_hand_off_and_never_are_not_executable(kind):
    verdict = check_execution(policy(), kind, {}, Usage(), NOON)
    assert not verdict.allowed and verdict.mode not in EXECUTABLE


def test_daily_and_weekly_caps():
    p = policy()
    assert check_execution(p, "send_email", {}, Usage(executed_today=1), NOON).allowed
    assert not check_execution(p, "send_email", {}, Usage(executed_today=2), NOON).allowed
    assert not check_execution(p, "send_linkedin_invite", {}, Usage(executed_today=0, executed_this_week=5), NOON).allowed


def test_kill_switch_pauses_outward_actions_only():
    p = policy(BASE.replace("kill_switch: false", "kill_switch: true"))
    assert not check_execution(p, "send_email", {}, Usage(), NOON).allowed
    assert check_execution(p, "save_artifact", {}, Usage(), NOON).allowed


def test_people_per_company_counts_new_people_only():
    p = policy()
    reached = Usage(company_people={"c1", "c2"})
    assert not check_execution(p, "send_email", {"contact_id": "c3", "company": "Co"}, reached, NOON).allowed
    assert check_execution(p, "send_linkedin_dm", {"contact_id": "c1", "company": "Co"},
                           Usage(company_people={"c1", "c2"}, accepted_at=NOON - timedelta(days=2)), NOON).allowed


def test_recent_touch_blocks_openers_but_dm_follows_acceptance_delay():
    p = policy()
    touched = Usage(last_touch_at=NOON - timedelta(days=3))
    assert not check_execution(p, "send_email", {"contact_id": "c1"}, touched, NOON).allowed
    assert check_execution(p, "send_email", {"contact_id": "c1"}, Usage(last_touch_at=NOON - timedelta(days=20)), NOON).allowed
    assert not check_execution(p, "send_linkedin_dm", {"contact_id": "c1"}, Usage(), NOON).allowed  # no acceptance
    early = Usage(accepted_at=NOON - timedelta(hours=2), last_touch_at=NOON - timedelta(days=3))
    assert not check_execution(p, "send_linkedin_dm", {"contact_id": "c1"}, early, NOON).allowed
    late = Usage(accepted_at=NOON - timedelta(hours=30), last_touch_at=NOON - timedelta(days=3))
    assert check_execution(p, "send_linkedin_dm", {"contact_id": "c1"}, late, NOON).allowed


def test_quiet_hours_wait_until_morning():
    night = datetime(2026, 11, 25, 18, 0, tzinfo=timezone.utc)  # 23:30 in Kolkata
    verdict = check_execution(policy(), "send_email", {}, Usage(), night)
    assert not verdict.allowed and verdict.retry_at is not None
    assert verdict.retry_at.astimezone(timezone.utc) == datetime(2026, 11, 26, 2, 30, tzinfo=timezone.utc)
    capped = check_execution(policy(), "send_email", {}, Usage(executed_today=9), night)
    assert capped.retry_at is None  # waiting won't help when a cap is also hit


def test_autonomy_daily_cap_never_exceeds_the_channel_cap():
    assert policy().autonomy["send_email"]["daily_cap"] == 2  # capped by emails_per_day


@pytest.mark.parametrize("bad", [
    BASE.replace("version: 1", "version: 2"),
    BASE.replace("send_email: ask_first", "send_email: sometimes"),
    BASE.replace("emails_per_day: 2", "emails_per_day: -1"),
    BASE.replace('quiet_hours: "22:00-08:00"', 'quiet_hours: "late"'),
    BASE.replace("timezone: Asia/Kolkata", "timezone: Mars/Base"),
    BASE.replace("  send_email:\n    auto_after", "  unknown_kind:\n    auto_after"),
])
def test_invalid_policy_is_refused(bad):
    with pytest.raises(PolicyError):
        load_policy(bad)
