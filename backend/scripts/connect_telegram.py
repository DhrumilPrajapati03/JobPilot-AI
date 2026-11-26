"""Link your Telegram chat to JobDots (once).

    1. In Telegram, open your bot and send it any message.
    2. cd backend && python scripts/connect_telegram.py
    3. docker compose up -d

Finds the one private chat that wrote to the bot, saves TELEGRAM_CHAT_ID in the root .env
and sends a confirmation. The bot answers only that chat. Nothing secret is printed.
"""
import json
import sys
import urllib.request

import _hostenv

_hostenv.load()
import os  # noqa: E402


def call(token: str, method: str, **params) -> dict:
    data = json.dumps(params).encode()
    request = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}", data=data,
                                     headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(request, timeout=20))


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("Put TELEGRAM_BOT_TOKEN (from @BotFather) in the root .env first.")
        return 2
    me = call(token, "getMe")["result"]
    updates = call(token, "getUpdates", timeout=0).get("result", [])
    chats = {}
    for update in updates:
        chat = (update.get("message") or {}).get("chat") or {}
        if chat.get("type") == "private":
            chats[chat["id"]] = chat.get("first_name") or "you"
    if not chats:
        print(f"No message to @{me['username']} yet. Send it any message in Telegram, then run this again.")
        return 1
    if len(chats) > 1:
        print(f"{len(chats)} different people wrote to @{me['username']}. Only the owner should; revoke the token "
              "with @BotFather if the bot was shared, or ask the others to stop, then run this again.")
        return 1
    chat_id, name = next(iter(chats.items()))
    _hostenv.set_env("TELEGRAM_CHAT_ID", str(chat_id))
    call(token, "sendMessage", chat_id=chat_id, text="JobDots is linked to this chat. Drafts that need your approval will arrive here.")
    print(f"Linked @{me['username']} to {name}'s chat; TELEGRAM_CHAT_ID saved in .env. Now: docker compose up -d")
    return 0


if __name__ == "__main__":
    sys.exit(main())
