"""Day 10 without a database: classifying mail, matching it to what you sent, the calendar
request, and the policy rule for follow-ups. Fictional people only."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.core import policy as policy_mod
from app.courier import calendar, gmail
from app.experts import inbox
from app.inbox import classify

LI = "invitations@linkedin.com"


@pytest.mark.parametrize("subject,text,headers,sender,kind", [
    ("Jane Example accepted your invitation", "", {}, LI, "accepted"),
    ("Jane Example accepted your invitation", "", {}, "jane@acme.example", "reply"),       # only LinkedIn's own mail
    ("Automatic reply: ML Engineer", "I'm away until Monday.", {}, "jane@acme.example", "auto_reply"),
    ("Re: ML Engineer", "Thanks", {"auto-submitted": "auto-replied"}, "jane@acme.example", "auto_reply"),
    ("Re: ML Engineer", "Thanks Ada! Could we schedule a call this week? Here's my calendly.com/jane link.", {}, "jane@acme.example", "interview"),
    ("Re: ML Engineer", "We'd like to invite you to an interview on Tuesday at 3pm.", {}, "jane@acme.example", "interview"),
    ("Re: ML Engineer", "Thank you for your interest. Unfortunately, we have decided to move forward with other candidates.", {}, "hr@acme.example", "rejection"),
    ("Re: ML Engineer", "The position has been filled.", {}, "hr@acme.example", "rejection"),
    ("Re: ML Engineer", "Unfortunately, we can't do Tuesday; could you do an interview on Wednesday?", {}, "jane@acme.example", "interview"),
    ("Re: ML Engineer", "Thanks for reaching out, I've passed your resume to the team.", {}, "jane@acme.example", "reply"),
    # Only the new part of a reply counts: an old quoted "interview" doesn't make this one.
    ("Re: ML Engineer", "Got it, thanks.\n\nOn Mon, 1 Dec 2026 at 10:00, Ada wrote:\n> happy to interview any time", {}, "jane@acme.example", "reply"),
])
def test_classify(subject, text, headers, sender, kind):
    assert classify.kind_of(subject, text, headers, sender) == kind


def test_accepted_name_comes_only_from_linkedin():
    assert classify.accepted_name("Jane Example accepted your invitation", LI) == "Jane Example"
    assert classify.accepted_name("Jane Example has accepted your invitation", "messages-noreply@linkedin.com") == "Jane Example"
    assert classify.accepted_name("Jane Example accepted your invitation", "spoof@linkedin.com.evil.example") is None
    assert classify.accepted_name("Jane Example accepted your invitation", "x@evil-linkedin.com") is None
    assert classify.accepted_name("Jane Example accepted your invitation", "x@e.linkedin.com") == "Jane Example"


def msg(**kw):
    base = dict(id="m1", thread_id="t9", from_email="jane@acme.example", from_name="Jane", subject="Re: hi", snippet="", text="",
                received_at="2026-12-01T10:00:00+00:00", headers={})
    return gmail.Message(**{**base, **kw})


SENT = [{"id": "a1", "case_id": "c1", "to": "jane@acme.example", "to_name": "Jane", "contact_id": "k1", "company": "Acme",
         "subject": "hi", "thread_id": "t1", "gmail_id": "g1", "sent_at": None, "follow_up_of": None},
        {"id": "a2", "case_id": "c2", "to": "raj@globex.example", "to_name": "Raj", "contact_id": "k2", "company": "Globex",
         "subject": "hello", "thread_id": None, "gmail_id": "g2", "sent_at": None, "follow_up_of": None},
        {"id": "a3", "case_id": "c3", "to": "lee@gmail.com", "to_name": "Lee", "contact_id": "k3", "company": "Initech",
         "subject": "hey", "thread_id": None, "gmail_id": "g3", "sent_at": None, "follow_up_of": None}]


def test_matching_by_thread_sender_or_company_domain_never_webmail():
    assert inbox.match(msg(thread_id="t1", from_email="someone@else.example"), SENT)["id"] == "a1"
    assert inbox.match(msg(from_email="raj@globex.example"), SENT)["id"] == "a2"
    assert inbox.match(msg(from_email="hr@globex.example"), SENT)["id"] == "a2"          # same company domain
    assert inbox.match(msg(from_email="friend@gmail.com"), SENT) is None                 # webmail is not a company
    assert inbox.match(msg(from_email="news@unrelated.example"), SENT) is None


def test_gmail_queries_only_ask_for_people_you_emailed():
    qs = inbox.queries(SENT)
    assert "jane@acme.example" in qs[0] and "globex.example" in qs[0] and " gmail.com" not in qs[0]
    assert qs[-1].startswith("newer_than:") and "accepted your invitation" in qs[-1]
    assert inbox.queries([]) == [qs[-1]]


def test_calendar_request_is_idempotent_and_private():
    aid = "1f2e3d4c-0000-4000-8000-000000000001"
    body = calendar.body(aid, {"summary": "Interview with Acme", "start": "2026-12-03T15:00:00+05:30", "end": "2026-12-03T16:00:00+05:30",
                               "timezone": "Asia/Kolkata"})
    assert body["id"] == "jd1f2e3d4c000040008000000000000001" and "attendees" not in body
    assert set(body["id"]) <= set("0123456789abcdefghijklmnopqrstuv")
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(409 if len(seen) > 1 else 200, json={"id": body["id"]})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert calendar.insert(client, "t", aid, {"summary": "x", "start": "a", "end": "b"}).status == "provider_accepted"
    again = calendar.insert(client, "t", aid, {"summary": "x", "start": "a", "end": "b"})
    assert again.status == "provider_accepted" and again.provider_ref == body["id"]        # 409: already added


POLICY = policy_mod.load_policy("""
version: 1
action_modes: {send_email: ask_first}
caps: {emails_per_day: 5, linkedin_invites_per_day: 1, linkedin_invites_per_week: 1, linkedin_dms_per_day: 1,
       max_people_per_company: 3, min_hours_accept_to_dm: 24, no_contact_if_touched_within_days: 14, quiet_hours: "", timezone: UTC}
""")
NOW = datetime(2026, 12, 1, 12, tzinfo=timezone.utc)


def test_a_follow_up_skips_the_cooldown_only_when_it_is_a_real_first_follow_up():
    recent = policy_mod.Usage(last_touch_at=NOW - timedelta(days=5))
    plain = policy_mod.check_execution(POLICY, "send_email", {"to": "jane@acme.example"}, recent, NOW)
    assert not plain.allowed and "contacted in the last 14 days" in plain.reasons[0]
    ok = policy_mod.check_execution(POLICY, "send_email", {"to": "jane@acme.example", "follow_up_of": "a1"},
                                    policy_mod.Usage(last_touch_at=NOW - timedelta(days=5), follow_up_ok=True), NOW)
    assert ok.allowed
    fake = policy_mod.check_execution(POLICY, "send_email", {"to": "jane@acme.example", "follow_up_of": "a1"},
                                      policy_mod.Usage(last_touch_at=NOW - timedelta(days=5), follow_up_ok=False), NOW)
    assert not fake.allowed and any("follow-up must answer" in r for r in fake.reasons)


def test_follow_ups_reply_in_the_same_thread():
    m = gmail.build({"to": "jane@acme.example", "subject": "Re: hi", "body": "Following up.", "in_reply_to": "<jobdots.a1@x.example>"},
                    "ada@example.invalid", "Ada", "f1", None)
    assert m["In-Reply-To"] == "<jobdots.a1@x.example>" and m["References"] == "<jobdots.a1@x.example>"
