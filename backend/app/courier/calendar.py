"""Google Calendar executor (Courier): an approved event on your own primary calendar.

* The event id is fixed per action ("jd" + the action's uuid in hex), so a retry or a crash
  mid-insert never creates a second event: Google answers 409 and that counts as done.
* No attendees are added, so nobody else receives an invitation from JobDots.
"""
from __future__ import annotations

import httpx

from app.courier.gmail import SendResult

SCOPE = "https://www.googleapis.com/auth/calendar.events"
API = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


def event_id(action_id: str) -> str:
    # Calendar ids use base32hex characters (0-9, a-v); hex digits are a subset.
    return "jd" + action_id.replace("-", "").lower()


def body(action_id: str, payload: dict) -> dict:
    tz = payload.get("timezone") or "UTC"
    return {"id": event_id(action_id), "summary": payload["summary"][:200],
            "description": (payload.get("description") or "")[:4000], "location": (payload.get("location") or "")[:300],
            "start": {"dateTime": payload["start"], "timeZone": tz}, "end": {"dateTime": payload["end"], "timeZone": tz},
            "reminders": {"useDefault": True}}


def insert(client: httpx.Client, token: str, action_id: str, payload: dict) -> SendResult:
    try:
        response = client.post(API, json=body(action_id, payload), headers={"Authorization": f"Bearer {token}"})
    except httpx.TimeoutException:
        return SendResult("send_unknown", error="Google Calendar did not answer in time; check your calendar before adding it again.")
    except httpx.HTTPError as exc:
        return SendResult("failed", error=f"Could not reach Google Calendar ({type(exc).__name__}); nothing was added.")
    if response.status_code in (200, 201):
        return SendResult("provider_accepted", response.json().get("id"))
    if response.status_code == 409:                       # added before (retry or restart): done
        return SendResult("provider_accepted", event_id(action_id))
    if response.status_code >= 500:
        return SendResult("send_unknown", error=f"Google Calendar returned HTTP {response.status_code}; check your calendar.")
    try:
        detail = response.json().get("error", {}).get("message", "")
    except ValueError:
        detail = ""
    return SendResult("failed", error=f"Google Calendar refused the event (HTTP {response.status_code}) {detail}"[:300])
