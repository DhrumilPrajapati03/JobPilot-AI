"""Set who a case's email goes to, then Email Outreach drafts again for that person.

    cd backend
    python scripts/set_recipient.py <case id> <email> ["Name"]

The address is yours to type: it goes only to your local JobDots API. Nothing is sent until
you tap "Approve and send" on Telegram (or approve in the web app).
"""
import json
import sys
import urllib.request

import _hostenv

_hostenv.load()
import os  # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    case_id, email = sys.argv[1], sys.argv[2]
    name = sys.argv[3] if len(sys.argv) > 3 else ""
    port = os.environ.get("API_PORT") or "8000"
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/v1/experts/cases/{case_id}/recipient",
        data=json.dumps({"email": email, "name": name}).encode(), method="POST",
        headers={"Authorization": f"Bearer {os.environ['OWNER_API_TOKEN']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        json.load(response)
    print("Recipient set. Email Outreach is drafting again; the draft will arrive on Telegram for your approval.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
