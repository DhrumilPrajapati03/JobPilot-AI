"""Telegram approvals (plan sections 2.4, 9.2): long polling, one allowed chat.

    python -m app.telegram.bot        (the `telegram` service in compose.yaml)

* Only TELEGRAM_CHAT_ID is answered; everything else is ignored without a reply.
* Each reviewed draft arrives with its PDF and two buttons: Approve and send, Reject. A
  button carries the first 8 hex of the payload hash, so a tap on an older version of an
  edited draft is refused.
* Approving dispatches Courier; the message is edited as the action moves on (sending,
  sent, held, failed). Reviewer-blocked drafts arrive as information, without buttons.
* A day before the Gmail connection expires (Testing mode, 7 days) it warns once.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from app.config import settings
from app.core import actions
from app.courier import connections
from app.courier import runner as courier
from app.db import get_db
from app.telegram.client import Telegram, TelegramError, esc

log = logging.getLogger("jobdots.telegram")
STATUS_LINE = {
    "approved": "✅ Approved. Sending…",
    "executing": "📤 Sending…",
    "provider_accepted": "📬 Sent. Gmail accepted it.",
    "delivered": "📬 Delivered.",
    "send_unknown": "⚠️ Send result unknown. Check your Sent folder before sending again.",
    "failed": "❌ Not sent.",
    "cancelled": "✖️ Rejected. Nothing was sent.",
    "blocked": "⛔ Blocked by the Reviewer.",
}


LINKEDIN_KINDS = ("send_linkedin_invite", "send_linkedin_dm", "referral_request")
LINKEDIN_STATUS = {"approved": "✅ Approved. Waiting in your LinkedIn queue.", "executing": "🔗 Opened from the queue.",
                   "provider_accepted": "📬 You sent it on LinkedIn.", "failed": "✖️ Not sent (you skipped it)."}


def linkedin_card(action: dict) -> str:
    p = action["payload"]
    invite = action["kind"] == "send_linkedin_invite"
    who = esc(p.get("name") or "someone") + (f", {esc(p.get('title'))}" if p.get("title") else "")
    what = "invitation" if invite else "referral ask" if action["kind"] == "referral_request" else "message"
    lines = [f"<b>LinkedIn {what} at {esc(p.get('company') or 'a company')}</b> "
             f"({'Connector' if invite else 'DM Outreach'})", f"<b>To:</b> {who}", esc(p.get("profile_url") or ""), "",
             esc(p.get("note") or p.get("body") or "(no note)")[:1500]]
    notes = (action.get("review") or {}).get("notes") or []
    if notes:
        lines += ["", "<b>Reviewer:</b> " + esc("; ".join(notes))]
    if action.get("block_reason"):
        lines += ["", "<b>Blocked:</b> " + esc(action["block_reason"])]
    if action["status"] == "reviewed":
        lines += ["", "Approved ones wait in the LinkedIn queue in the JobDots side panel; you send each one yourself."]
    return "\n".join(lines)


def calendar_card(action: dict) -> str:
    p = action["payload"]
    lines = [f"<b>Calendar event for {esc(p.get('company') or 'an interview')}</b> (Inbox)", f"<b>{esc(p.get('summary'))}</b>",
             f"{esc(p.get('start'))} to {esc(p.get('end'))} ({esc(p.get('timezone'))})"]
    if p.get("location"):
        lines.append(esc(p["location"]))
    notes = (action.get("review") or {}).get("notes") or []
    if notes:
        lines += ["", "<b>Reviewer:</b> " + esc("; ".join(notes))]
    return "\n".join(lines)


def card(action: dict) -> str:
    if action.get("kind") in LINKEDIN_KINDS:
        return linkedin_card(action)
    if action.get("kind") == "create_calendar_event":
        return calendar_card(action)
    p = action["payload"]
    to = f"{esc(p.get('to_name'))} &lt;{esc(p.get('to'))}&gt;" if p.get("to_name") else esc(p.get("to") or "(no recipient)")
    review = action.get("review") or {}
    notes = review.get("notes") or []
    lines = [f"<b>New email for {esc(p.get('company') or 'a company')}</b> (Email Outreach)",
             f"<b>To:</b> {to}", f"<b>Subject:</b> {esc(p.get('subject'))}", "", esc(p.get("body"))[:2500]]
    if notes:
        lines += ["", "<b>Reviewer:</b> " + esc("; ".join(notes))]
    if action.get("block_reason"):
        lines += ["", "<b>Blocked:</b> " + esc(action["block_reason"])]
    if p.get("attachment"):
        lines += ["", f"📎 {esc(p['attachment'].get('filename') or 'resume.pdf')} (above)"]
    return "\n".join(lines)


def buttons(action: dict) -> list[list[dict]]:
    tag = f"{action['id']}:{action['payload_sha256'][:8]}"
    verb = ("Approve and queue" if action.get("kind") in LINKEDIN_KINDS else
            "Approve and add" if action.get("kind") == "create_calendar_event" else "Approve and send")
    return [[{"text": verb, "callback_data": f"ap:{tag}"}, {"text": "Reject", "callback_data": f"rj:{tag}"}]]


class Bot:
    def __init__(self, user_id: str, chat_id: int, tg: Telegram):
        self.user_id, self.chat_id, self.tg = user_id, chat_id, tg
        self.db = get_db(user_id)

    # --- state ---------------------------------------------------------------------------
    def offset(self) -> int:
        rows = self.db.fetch("select update_offset from public.telegram_state where user_id = %s::uuid", [self.user_id])
        if rows:
            return rows[0][0]
        self.db.fetch("insert into public.telegram_state (user_id, chat_id) values (%s::uuid, %s) on conflict do nothing",
                      [self.user_id, self.chat_id])
        return 0

    def save_offset(self, value: int) -> None:
        self.db.fetch("update public.telegram_state set update_offset = %s where user_id = %s::uuid", [value, self.user_id])

    def _action(self, action_id: str) -> dict | None:
        rows = self.db.fetch("select to_jsonb(a) from public.action a where id = %s::uuid and user_id = %s::uuid",
                             [action_id, self.user_id])
        return rows[0][0] if rows else None

    # --- incoming --------------------------------------------------------------------------
    def handle(self, update: dict) -> None:
        if "callback_query" in update:
            return self.on_button(update["callback_query"])
        message = update.get("message") or {}
        if message.get("chat", {}).get("id") != self.chat_id:
            return  # not the owner: no reply at all
        text = (message.get("text") or "").strip()
        if text.startswith("/start"):
            self.tg.send(self.chat_id, "JobDots is connected. Drafts that need your approval will arrive here.")
        elif text.startswith("/pending"):
            count = self.db.fetch("select count(*) from public.action where user_id = %s::uuid and status = 'reviewed'",
                                  [self.user_id])[0][0]
            self.tg.send(self.chat_id, f"{count} draft{'s' if count != 1 else ''} waiting for your approval.")
        else:
            self.tg.send(self.chat_id, "I only handle approvals for now. Open JobDots to talk to your experts.")

    def on_button(self, query: dict) -> None:
        message = query.get("message") or {}
        if message.get("chat", {}).get("id") != self.chat_id:
            return
        try:
            verb, action_id, short = (query.get("data") or "").split(":")
        except ValueError:
            return self.tg.answer(query["id"], "Unknown button.")
        action = self._action(action_id)
        if action is None:
            return self.tg.answer(query["id"], "That draft no longer exists.")
        if action["payload_sha256"][:8] != short:
            return self.tg.answer(query["id"], "This draft was edited. Approve the new version instead.")
        try:
            if verb == "ap":
                actions.approve(self.user_id, action_id, payload_sha256=action["payload_sha256"], channel="telegram")
                if action["kind"] in courier.SENDERS:
                    courier.dispatch(self.user_id, action_id)
                    self.tg.answer(query["id"], "Approved. Sending…")
                else:
                    self.tg.answer(query["id"], "Approved. It's in your LinkedIn queue in the side panel.")
            elif verb == "rj":
                actions.reject(self.user_id, action_id, channel="telegram")
                self.tg.answer(query["id"], "Rejected. Nothing will be sent.")
        except actions.ActionError as exc:
            self.tg.answer(query["id"], str(exc))
        self.refresh(action_id)

    # --- outgoing --------------------------------------------------------------------------
    def notify_new(self) -> int:
        rows = self.db.fetch("""select to_jsonb(a) from public.action a where a.user_id = %s::uuid
                                and a.status in ('reviewed', 'blocked')
                                and a.kind in ('send_email', 'send_linkedin_invite', 'send_linkedin_dm', 'referral_request', 'create_calendar_event')
                                and not exists (select 1 from public.telegram_message t where t.action_id = a.id)
                                order by a.created_at limit 5""", [self.user_id])
        for (action,) in rows:
            att = action["payload"].get("attachment")
            if att and action["status"] == "reviewed":
                path = Path(settings.FILE_STORAGE_DIR) / att["path"]
                if path.is_file():
                    self.tg.document(self.chat_id, att.get("filename") or "resume.pdf", path.read_bytes(),
                                     caption=f"Resume for {action['payload'].get('company') or 'this role'}")
            text = card(action)
            if action["status"] == "blocked":
                text += "\n\n" + STATUS_LINE["blocked"] + " Open JobDots to fix it or ask for a new draft."
            sent = self.tg.send(self.chat_id, text, buttons(action) if action["status"] == "reviewed" else None)
            self.db.fetch("""insert into public.telegram_message (action_id, user_id, chat_id, message_id, notified_status)
                             values (%s::uuid, %s::uuid, %s, %s, %s) on conflict do nothing""",
                          [action["id"], self.user_id, self.chat_id, sent["message_id"], action["status"]])
        return len(rows)

    def refresh(self, action_id: str | None = None) -> None:
        """Edit sent cards whose action moved on (approved, sent, failed…)."""
        rows = self.db.fetch("""select t.message_id, t.notified_status, to_jsonb(a) from public.telegram_message t
                                join public.action a on a.id = t.action_id
                                where t.user_id = %s::uuid and a.status <> t.notified_status
                                and (%s::uuid is null or a.id = %s::uuid)""", [self.user_id, action_id, action_id])
        for message_id, _old, action in rows:
            line = (LINKEDIN_STATUS if action["kind"] in LINKEDIN_KINDS else {}).get(action["status"])                 or STATUS_LINE.get(action["status"], action["status"])
            if action["status"] == "failed" and action.get("error"):
                line += " " + esc(action["error"])
            if action["status"] == "approved":
                held = self.db.fetch("""select summary from public.case_event where data->>'action_id' = %s and kind = 'held'
                                        order by at desc limit 1""", [action["id"]])
                if held:
                    line = "⏸ Approved, waiting: " + esc(held[0][0].removeprefix("Not sent yet: "))
            self.tg.edit(self.chat_id, message_id, card(action) + "\n\n" + line)
            self.db.fetch("update public.telegram_message set notified_status = %s where action_id = %s::uuid",
                          [action["status"], action["id"]])

    def warn_gmail(self) -> None:
        conn = connections.get_google(self.user_id)
        if conn and connections.needs_warning(conn) and not self.db.fetch(
                "select 1 from public.connection where id = %s::uuid and warned_at is not null", [conn.id]):
            self.tg.send(self.chat_id, "Your Gmail connection ends within a day (Google's Testing mode lasts 7 days). "
                                       "Reconnect on the laptop: <code>python scripts/connect_google.py connect</code>")
            self.db.fetch("update public.connection set warned_at = now() where id = %s::uuid", [conn.id])

    def tick(self, timeout: int = 25) -> None:
        offset = self.offset()
        for update in self.tg.updates(offset, timeout=timeout):
            try:
                self.handle(update)
            except Exception as exc:  # one bad update must not stop the loop
                log.warning("Telegram update failed (%s)", type(exc).__name__)
            offset = max(offset, update["update_id"] + 1)
        self.save_offset(offset)
        self.notify_new()
        self.refresh()
        self.warn_gmail()
        self.send_alerts()

    def send_alerts(self) -> None:
        """Replies, interview invites, failing experts, budget (app/telegram/alerts.py); each once."""
        from app.telegram import alerts
        try:
            for text in alerts.pending(self.user_id):
                self.tg.send(self.chat_id, text)
        except Exception as exc:                      # an alert must never stop approvals
            log.warning("Alerts skipped (%s)", type(exc).__name__)


def main() -> None:
    from app.services.auth import owner_identity
    logging.basicConfig(level=logging.INFO)
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        # Idle instead of exiting, so `restart: unless-stopped` doesn't crash-loop the container.
        log.warning("Telegram approvals are off: set TELEGRAM_BOT_TOKEN and run scripts/connect_telegram.py")
        while True:
            time.sleep(3600)
    bot = Bot(owner_identity()[0], int(settings.TELEGRAM_CHAT_ID), Telegram(settings.TELEGRAM_BOT_TOKEN))
    log.info("Telegram approvals running")
    while True:
        try:
            bot.tick()
        except TelegramError as exc:
            log.warning("Telegram: %s", exc)
            time.sleep(5)
        except Exception as exc:
            log.warning("Telegram loop error (%s)", type(exc).__name__)
            time.sleep(5)


if __name__ == "__main__":
    main()
