"""What an incoming email is (plan section 2.1, Inbox). Rules, not a model, so a cleverly
worded email can't talk its way into a different class:

* `accepted`: LinkedIn's own "X accepted your invitation" notification;
* `auto_reply`: out-of-office and other automatic replies (headers first, then the subject);
* `interview`: an invitation to talk or to schedule (interview, a call, a scheduling link);
* `rejection`: "unfortunately… not moving forward" and similar;
* `reply`: anything else from a person on one of your cases.

A rejection is never acted on by itself: it is noted for you, and the case stays open.
"""
from __future__ import annotations

import re

LINKEDIN_SENDERS = ("linkedin.com",)
ACCEPTED = re.compile(r"^(?P<name>.+?)\s+(?:has\s+)?accepted your invitation", re.I)
AUTO_SUBJECT = re.compile(r"^(automatic reply|auto(?:matic)?[- ]?reply|out of (the )?office|ooo\b|away from)", re.I)
INTERVIEW = re.compile(r"\b(interview|schedule (a|some) time|set up (a|some) time|book a (time|slot)|calendly\.com|"
                       r"cal\.com/|your availability|available (for|to) (a|an) (call|chat|conversation)|next (round|step|stage)|"
                       r"hop on a call|quick (call|chat)|screening call|phone screen)\b", re.I)
REJECTION = re.compile(r"\b(not (be )?moving forward|decided (not )?to (move|proceed) .{0,40}other candidates|"
                       r"(will not|won't) be (moving|progressing)|position has been filled|no longer (considering|available)|"
                       r"(regret|sorry) to (inform|let you know)|unfortunately,? we (have|had) decided|"
                       r"(pursue|go with|move forward with) other candidates)\b", re.I)


def accepted_name(subject: str, from_email: str) -> str | None:
    """The name in LinkedIn's acceptance notification, or None."""
    host = from_email.rsplit("@", 1)[-1].lower() if "@" in from_email else ""
    if not any(host == d or host.endswith("." + d) for d in LINKEDIN_SENDERS):
        return None
    m = ACCEPTED.match(subject.strip())
    return m.group("name").strip().strip(",") if m else None


def is_auto_reply(headers: dict, subject: str) -> bool:
    auto = (headers.get("auto-submitted") or "").lower()
    if auto and auto != "no":
        return True
    if headers.get("x-autoreply") or headers.get("x-autorespond") or (headers.get("precedence") or "").lower() in ("auto_reply", "bulk", "junk"):
        return True
    return bool(AUTO_SUBJECT.match(subject.strip()))


def kind_of(subject: str, text: str, headers: dict, from_email: str) -> str:
    if accepted_name(subject, from_email):
        return "accepted"
    if is_auto_reply(headers, subject):
        return "auto_reply"
    body = f"{subject}\n{latest_part(text)}"
    if REJECTION.search(body):
        return "rejection"
    if INTERVIEW.search(body):
        return "interview"
    return "reply"


QUOTE = re.compile(r"^(>|On .{5,120} wrote:\s*$|-----\s*Original Message|From: .+$)", re.M)


def latest_part(text: str) -> str:
    """The new text of a reply, without the quoted earlier messages."""
    m = QUOTE.search(text or "")
    return (text[:m.start()] if m else text or "").strip()[:3000]
