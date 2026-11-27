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
    thread_id: str | None = None


def message_id(action_id: str, sender: str) -> str:
    return f"<jobdots.{action_id}@{sender.rsplit('@', 1)[-1] or 'jobdots.local'}>"


def build(payload: dict, sender: str, sender_name: str, action_id: str, attachment: tuple[str, bytes] | None) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr((sender_name, sender)) if sender_name else sender
    msg["To"] = formataddr((payload.get("to_name") or "", payload["to"])) if payload.get("to_name") else payload["to"]
    msg["Subject"] = payload["subject"]
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = message_id(action_id, sender)
    if payload.get("in_reply_to"):                  # a follow-up: stays in the same thread
        msg["In-Reply-To"] = payload["in_reply_to"]
        msg["References"] = payload["in_reply_to"]
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


def send(client: httpx.Client, token: str, msg: EmailMessage, *, check_first: bool = True, thread_id: str | None = None) -> SendResult:
    mid = msg["Message-ID"]
    if check_first and (existing := already_sent(client, token, mid)):
        return SendResult("provider_accepted", existing)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    body = {"raw": raw, **({"threadId": thread_id} if thread_id else {})}
    try:
        response = client.post(f"{API}/messages/send", json=body, headers={"Authorization": f"Bearer {token}"})
    except httpx.TimeoutException:
        return SendResult("send_unknown", error="Gmail did not answer in time; the email may or may not have been sent.")
    except httpx.HTTPError as exc:
        return SendResult("failed", error=f"Could not reach Gmail ({type(exc).__name__}); nothing was sent.")
    if response.status_code == 200:
        return SendResult("provider_accepted", response.json().get("id"), thread_id=response.json().get("threadId"))
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


# --- reading (Inbox; gmail.readonly) -----------------------------------------------------------

@dataclass
class Message:
    id: str
    thread_id: str
    from_email: str
    from_name: str
    subject: str
    snippet: str
    text: str                  # plain-text body, trimmed; for classification only, never stored
    received_at: str           # RFC 3339
    headers: dict


def search(client: httpx.Client, token: str, query: str, *, limit: int = 50) -> list[str]:
    """Message ids matching a Gmail search query, newest first."""
    response = client.get(f"{API}/messages", params={"q": query, "maxResults": min(limit, 100)},
                          headers={"Authorization": f"Bearer {token}"})
    response.raise_for_status()
    return [m["id"] for m in response.json().get("messages") or []]


def thread_of(client: httpx.Client, token: str, gmail_id: str) -> str | None:
    response = client.get(f"{API}/messages/{gmail_id}", params={"format": "minimal"}, headers={"Authorization": f"Bearer {token}"})
    return response.json().get("threadId") if response.status_code == 200 else None


def _text(part: dict) -> str:
    if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(part["body"]["data"] + "===").decode("utf-8", "replace")
    return "\n".join(t for t in (_text(p) for p in part.get("parts") or []) if t)


def fetch(client: httpx.Client, token: str, gmail_id: str) -> Message:
    from datetime import datetime, timezone
    from email.utils import parseaddr
    response = client.get(f"{API}/messages/{gmail_id}", params={"format": "full"}, headers={"Authorization": f"Bearer {token}"})
    response.raise_for_status()
    body = response.json()
    payload = body.get("payload") or {}
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers") or []}
    name, address = parseaddr(headers.get("from", ""))
    received = datetime.fromtimestamp(int(body.get("internalDate", "0")) / 1000, tz=timezone.utc).isoformat()
    return Message(body["id"], body.get("threadId", ""), address.lower(), name, headers.get("subject", ""),
                   body.get("snippet", ""), _text(payload)[:6000], received, headers)
