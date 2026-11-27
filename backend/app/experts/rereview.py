"""Edit a draft and send it back through the Reviewer (web, Telegram or side panel).

An edit always clears the approval (actions.edit). Without a fresh review the draft would
sit at `proposed` and could never be approved, so every edit path ends here.
"""
from __future__ import annotations

from app.core import actions, cases
from app.core.policy import load_policy
from app.experts import artifacts, reviewer

LINKEDIN = ("send_linkedin_invite", "send_linkedin_dm", "referral_request")


def edit_and_review(user_id: str, action_id: str, payload: dict) -> dict:
    from app.db import get_db
    rows = get_db(user_id).fetch("select kind, case_id::text from public.action where id = %s::uuid and user_id = %s::uuid",
                                 [action_id, user_id])
    if not rows:
        raise actions.ActionError("action_not_found", "Action not found.")
    kind, case_id = rows[0]
    if kind in LINKEDIN:
        from app.experts import connector
        text = payload.get("note") if kind == "send_linkedin_invite" else payload.get("body")
        return connector.revise(user_id, action_id, str(text or ""))
    edited = actions.edit(user_id, action_id, payload)
    if edited["status"] != "proposed" or kind != "send_email":
        return edited
    from app.experts.email_outreach import last_touch
    from app.experts.tailor import load_inputs
    case = cases.get_case(user_id, case_id) if case_id else None
    brief = artifacts.latest(user_id, case_id, "company_brief") if case_id else None
    _, _, vault, _, _ = load_inputs()
    p = edited["payload"]
    review = reviewer.check_email(p, company=p.get("company") or (case or {}).get("company") or "", role=(case or {}).get("role") or "",
                                  job=(case or {}).get("jd_text") or "", brief=(brief or {}).get("content"), vault=vault,
                                  sender_name=vault.name, sender_links=" ".join(vault.links.values()),
                                  last_touch=last_touch(user_id, p.get("contact_id"), p.get("to") or "") if p.get("to") else None,
                                  cooldown_days=load_policy().caps["no_contact_if_touched_within_days"])
    return actions.review(user_id, action_id, ok=review.ok, notes=review.blocks + review.notes, reviewer="reviewer")
