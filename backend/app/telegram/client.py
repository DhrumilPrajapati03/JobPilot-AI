"""Minimal Telegram Bot API client over httpx (no extra dependency)."""
from __future__ import annotations

import html

import httpx

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(RuntimeError):
    pass


def esc(text: str) -> str:
    return html.escape(text or "", quote=False)


class Telegram:
    def __init__(self, token: str, client: httpx.Client | None = None):
        if not token:
            raise TelegramError("TELEGRAM_BOT_TOKEN is not set")
        self.token = token
        self.client = client or httpx.Client(timeout=httpx.Timeout(40.0, connect=10.0))

    def call(self, method: str, files=None, **params):
        url = API.format(token=self.token, method=method)
        response = self.client.post(url, data=params, files=files) if files else self.client.post(url, json=params)
        body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        if not body.get("ok"):
            # Never include the URL (it carries the token) in errors.
            raise TelegramError(f"{method} failed: {body.get('description') or response.status_code}")
        return body["result"]

    def send(self, chat_id: int, text: str, buttons: list[list[dict]] | None = None) -> dict:
        params = {"chat_id": chat_id, "text": text[:4096], "parse_mode": "HTML", "disable_web_page_preview": True}
        if buttons:
            params["reply_markup"] = {"inline_keyboard": buttons}
        return self.call("sendMessage", **params)

    def edit(self, chat_id: int, message_id: int, text: str, buttons: list[list[dict]] | None = None) -> None:
        params = {"chat_id": chat_id, "message_id": message_id, "text": text[:4096], "parse_mode": "HTML",
                  "disable_web_page_preview": True, "reply_markup": {"inline_keyboard": buttons or []}}
        try:
            self.call("editMessageText", **params)
        except TelegramError as exc:
            if "message is not modified" not in str(exc):
                raise

    def answer(self, callback_id: str, text: str = "") -> None:
        self.call("answerCallbackQuery", callback_query_id=callback_id, text=text[:200])

    def document(self, chat_id: int, filename: str, data: bytes, caption: str = "") -> dict:
        return self.call("sendDocument", files={"document": (filename, data, "application/pdf")},
                         chat_id=str(chat_id), caption=caption[:1024])

    def updates(self, offset: int, timeout: int = 25) -> list[dict]:
        return self.call("getUpdates", offset=offset, timeout=timeout, allowed_updates=["message", "callback_query"])
