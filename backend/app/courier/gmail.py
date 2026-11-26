"""Gmail executor (Courier). Sends exactly the approved payload from the connected account.

* Each action gets a fixed Message-ID (<jobdots.{action id}@{sender domain}>). Before
  sending, Sent mail is searched for it, so a retry after a crash finds the earlier send
  instead of sending twice.
* A definite refusal (4xx) is `failed`. A timeout or 5xx after the request went out is
  `send_unknown`: it is never retried blindly.
* Gmail accepting a message is `provider_accepted`, not delivered.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, formatdate
from pathlib import Path

import httpx

API = "https://gmail.googleapis.com/gmail/v1/users/me"
SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


@dataclass
class SendResult:
    status: str                 # provider_accepted | failed | send_unknown
    provider_ref: str | None = None
    error: str | None = None


def message_id(action_id: str, sender: str) -> str:
    return f"<jobdots.{action_id}@{sender.rsplit('@', 1)[-1] or 'jobdots.local'}>"


def build(payload: dict, sender: str, sender_name: str, action_id: str, attachment: tuple[str, bytes] | None) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr((sender_name, sender)) if sender_name else sender
    msg["To"] = formataddr((payload.get("to_name") or "", payload["to"])) if payload.get("to_name") else payload["to"]
    msg["Subject"] = payload["subject"]
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = message_id(action_id, sender)
    msg.set_content(payload["body"])
    if attachment:
        name, data = attachment
        msg.add_attachment(data, maintype="application", subtype="pdf", filename=name)
    return msg


def already_sent(client: httpx.Client, token: str, mid: str) -> str | None:
    """The Gmail id of a sent message with this Message-ID, if one exists."""
    response = client.get(f"{API}/messages", params={"q": f"in:sent rfc822msgid:{mid}", "maxResults": 1},
                          headers={"Authorization": f"Bearer {token}"})
    if response.status_code != 200:
        return None
    found = response.json().get("messages") or []
    return found[0]["id"] if found else None


def send(client: httpx.Client, token: str, msg: EmailMessage, *, check_first: bool = True) -> SendResult:
    mid = msg["Message-ID"]
    if check_first and (existing := already_sent(client, token, mid)):
        return SendResult("provider_accepted", existing)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    try:
        response = client.post(f"{API}/messages/send", json={"raw": raw}, headers={"Authorization": f"Bearer {token}"})
    except httpx.TimeoutException:
        return SendResult("send_unknown", error="Gmail did not answer in time; the email may or may not have been sent.")
    except httpx.HTTPError as exc:
        return SendResult("failed", error=f"Could not reach Gmail ({type(exc).__name__}); nothing was sent.")
    if response.status_code == 200:
        return SendResult("provider_accepted", response.json().get("id"))
    if response.status_code >= 500:
        return SendResult("send_unknown", error=f"Gmail returned HTTP {response.status_code}; check Sent before retrying.")
    detail = ""
    try:
        detail = response.json().get("error", {}).get("message", "")
    except ValueError:
        pass
    return SendResult("failed", error=f"Gmail refused the email (HTTP {response.status_code}) {detail}"[:300])


def attachment_for(payload: dict, storage: str) -> tuple[str, bytes] | None:
    """The approved attachment: a file under FILE_STORAGE_DIR whose sha256 is frozen in the payload."""
    import hashlib
    att = payload.get("attachment")
    if not att:
        return None
    root = Path(storage).resolve()
    path = (root / att["path"]).resolve()
    if root not in path.parents or not path.is_file():
        raise FileNotFoundError("The approved attachment is missing")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != att["sha256"]:
        raise ValueError("The attachment changed after approval")
    return att.get("filename") or "resume.pdf", data
