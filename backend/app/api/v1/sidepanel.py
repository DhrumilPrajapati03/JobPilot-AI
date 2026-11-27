"""JobDots side panel endpoints for the Chrome extension (plan section 6, screen 9; Day 7).

Same extension token as the other extension routes. Capture a job description, send a form's
questions to the Answerer, read its answers, and approve them. Nothing here fills or submits
a form: you review the answers in the side panel, and what you approve (and edit) is saved to
your answer bank as new versions.
"""
import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.answers import bank as answer_bank
from app.api.v1.extension import ExtensionUser, FieldIn, _key, get_extension_user
from app.core import cases as case_mod
from app.db import get_db
from app.experts import artifacts as artifact_mod
from app.experts import runtime as expert_runtime

router = APIRouter()
SAVE_SOURCE = {"reused": "reused", "adapted": "adapted", "generated": "generated", "needs_you": "user", "vault": "vault"}
SENSITIVE_KINDS = {"eeo", "pay", "dob"}


def case_for_url(user_id: str, url: str, case_id: str | None = None) -> dict | None:
    """The open case for this posting (the form page and the JD page share a key)."""
    if case_id:
        return case_mod.get_case(user_id, case_id)
    key = _key(url)
    if not key:
        return None
    rows = get_db(user_id).fetch("""select id::text, source_url from public.job_case where user_id = %s::uuid and not legacy
                                    and status = 'open' and source_url <> '' order by created_at desc limit 300""", [user_id])
    for found_id, source in rows:
        if _key(source) == key:
            return case_mod.get_case(user_id, found_id)
    return None


class PageIn(BaseModel):
    url: str = Field(max_length=2000)


@router.post("/page")
async def page(body: PageIn, user: ExtensionUser = Depends(get_extension_user)):
    """Is this page a job you've captured? (case, stage, and whether answers exist)."""
    case = await asyncio.to_thread(case_for_url, user.id, body.url)
    if case is None:
        return {"case": None}
    latest = await asyncio.to_thread(artifact_mod.latest, user.id, case["id"], "answer_set")
    return {"case": {"id": case["id"], "company": case["company"], "role": case["role"], "stage": case["stage"]},
            "answer_set_id": latest["id"] if latest else None}


class CaptureIn(BaseModel):
    url: str = Field(max_length=2000)
    title: str = Field(default="", max_length=500)
    text: str = Field(min_length=200, max_length=60000)
    company: str = Field(default="", max_length=200)
    role: str = Field(default="", max_length=300)


@router.post("/capture", status_code=201)
async def capture(body: CaptureIn, user: ExtensionUser = Depends(get_extension_user)):
    """Open a case for the job on this page (once per posting); Supervisor takes it from there."""
    if not body.url.startswith("https://"):
        raise HTTPException(422, "Capture works on https pages only.")
    existing = await asyncio.to_thread(case_for_url, user.id, body.url)
    if existing:
        return {"case_id": existing["id"], "company": existing["company"], "role": existing["role"], "created": False}
    company, role = body.company.strip(), body.role.strip()
    if not (company and role):
        from app.agents.jd_parser import JDParserAgent
        try:
            analysis = await JDParserAgent().parse(jd_text=body.text)
        except Exception:
            raise HTTPException(502, "Couldn't read the company and role from this page. "
                                     "Select the job description and try again.") from None
        company, role = company or analysis.company, role or analysis.role
    if not company:
        raise HTTPException(422, "Couldn't tell which company this is. Select the job description and try again.")
    case = await asyncio.to_thread(case_mod.create_case, user.id, company=company, role=role, jd_text=body.text,
                                   source_url=body.url, actor="user")
    await asyncio.to_thread(expert_runtime.enqueue_expert, user.id, "supervisor", case_id=case["id"],
                            key=f"supervisor:{case['id']}:created", trigger="case_created")
    return {"case_id": case["id"], "company": company, "role": role, "created": True}


class QuestionsIn(BaseModel):
    url: str = Field(max_length=2000)
    case_id: uuid.UUID | None = None
    questions: list[FieldIn] = Field(min_length=1, max_length=150)


@router.post("/questions", status_code=202)
async def questions(body: QuestionsIn, user: ExtensionUser = Depends(get_extension_user)):
    """Ask the Answerer to answer this form's questions."""
    case = await asyncio.to_thread(case_for_url, user.id, body.url, str(body.case_id) if body.case_id else None)
    if case is None:
        raise HTTPException(404, "No case for this job yet. Capture the job first.")
    fields = [q.model_dump() for q in body.questions]
    run = await asyncio.to_thread(expert_runtime.enqueue_expert, user.id, "answerer", case_id=case["id"],
                                  trigger="form_questions", questions=fields, url=body.url)
    return {"case_id": case["id"], "run_id": run["id"]}


class AnswerSetQuery(BaseModel):
    case_id: uuid.UUID
    run_id: uuid.UUID | None = None


@router.post("/answer-set")
async def answer_set(body: AnswerSetQuery, user: ExtensionUser = Depends(get_extension_user)):
    """The Answerer's latest answers for a case, or what it is doing right now."""
    db = get_db(user.id)
    if body.run_id:
        rows = await asyncio.to_thread(db.fetch, """select status, last_error from public.agent_runs
                                                    where id = %s::uuid and user_id = %s::uuid""", [str(body.run_id), user.id])
        if not rows:
            raise HTTPException(404, "Run not found")
        status, error = rows[0]
        if status not in ("succeeded", "failed"):
            step = await asyncio.to_thread(db.fetch, """select summary from public.run_step where run_id = %s::uuid
                                                        order by id desc limit 1""", [str(body.run_id)])
            return {"status": "working", "step": step[0][0] if step else "Waiting to start"}
        if status != "succeeded":
            return {"status": "failed", "detail": str(error or "The Answerer stopped.")[:300]}
    latest = await asyncio.to_thread(artifact_mod.latest, user.id, str(body.case_id), "answer_set")
    if latest is None:
        return {"status": "none"}
    return {"status": "ready", "answer_set_id": latest["id"], "version": latest["version"], **latest["content"]}


class ApprovedAnswer(BaseModel):
    key: str = Field(max_length=300)
    value: str | list[str] | None = None
    edited: bool = False
    save: bool = True


class ApproveIn(BaseModel):
    case_id: uuid.UUID
    answer_set_id: uuid.UUID
    answers: list[ApprovedAnswer] = Field(min_length=1, max_length=150)


@router.post("/answer-set/approve")
async def approve_answers(body: ApproveIn, user: ExtensionUser = Depends(get_extension_user)):
    """You checked these answers. New or edited text goes to your answer bank (as a new version)."""
    rows = await asyncio.to_thread(get_db(user.id).fetch, """select content from public.artifact where id = %s::uuid
                                   and user_id = %s::uuid and case_id = %s::uuid and kind = 'answer_set'""",
                                   [str(body.answer_set_id), user.id, str(body.case_id)])
    if not rows:
        raise HTTPException(404, "Answer set not found")
    content = rows[0][0]
    by_key = {a["key"]: a for a in content.get("answers") or []}
    if any(a.key not in by_key for a in body.answers):
        raise HTTPException(422, "An answer doesn't belong to this form.")
    saved = 0
    for approved in body.answers:
        original = by_key[approved.key]
        value = approved.value if isinstance(approved.value, str) else ", ".join(approved.value or [])
        value = (value or "").strip()
        if not approved.save or not value or original["kind"] in ("legal", "file"):
            continue
        if original["badge"] in ("vault", "reused") and not approved.edited:
            continue                     # already in your vault or bank, unchanged
        source = "user" if approved.edited else SAVE_SOURCE[original["badge"]]
        scope = content.get("company", "") if original["kind"] == "company_specific" else ""
        stored = await asyncio.to_thread(answer_bank.save, user.id, original["label"], value, source=source,
                                         type_=original["kind"], company_scope=scope,
                                         sensitive=original["kind"] in SENSITIVE_KINDS)
        saved += not stored["unchanged"]        # approving the same text again adds no version
    await asyncio.to_thread(case_mod.add_event, user.id, str(body.case_id), "note", actor="user",
                            summary=f"You checked {len(body.answers)} answers; {saved} saved to your answer bank",
                            data={"answer_set_id": str(body.answer_set_id), "saved": saved})
    return {"saved": saved}


class AppliedIn(BaseModel):
    case_id: uuid.UUID
    applied: bool = True
    seen: bool = False          # True when the panel saw the employer's confirmation page


BEFORE_APPLIED = ("found", "researched", "tailored", "ready")


@router.post("/case/applied")
async def case_applied(body: AppliedIn, user: ExtensionUser = Depends(get_extension_user)):
    """You submitted this application (or undo that). Moves the case to applied and stamps the date."""
    case = await asyncio.to_thread(case_mod.get_case, user.id, str(body.case_id))
    if case is None:
        raise HTTPException(404, "Case not found")
    if body.applied and case["stage"] in BEFORE_APPLIED:
        case = await asyncio.to_thread(case_mod.set_stage, user.id, case["id"], "applied", actor="user")
        await asyncio.to_thread(case_mod.add_event, user.id, case["id"], "note", actor="user",
                                summary="You submitted the application" + (" (JobDots saw the confirmation page)" if body.seen else ""),
                                data={"evidence": "confirmation_page" if body.seen else "you"})
    elif not body.applied and case["stage"] == "applied":
        case = await asyncio.to_thread(case_mod.set_stage, user.id, case["id"], "ready", actor="user")
    return {"stage": case["stage"], "applied_at": case.get("applied_at")}


# --- Applicant: the resume to attach, and a record of each fill ---------------------------------

class CaseIn(BaseModel):
    case_id: uuid.UUID


@router.post("/resume")
async def resume_document(body: CaseIn, user: ExtensionUser = Depends(get_extension_user)):
    """The case's tailored resume PDF for the form engine to attach (hash-checked on both ends)."""
    from app.experts import applicant
    doc = await asyncio.to_thread(applicant.document, user.id, str(body.case_id))
    if doc is None:
        raise HTTPException(404, "No tailored resume PDF for this case. Ask Tailor for one, or attach yours yourself.")
    return doc


class FillResult(BaseModel):
    label: str = Field(default="", max_length=1000)
    outcome: str = Field(max_length=20)


class FillReportIn(BaseModel):
    case_id: uuid.UUID
    url: str = Field(default="", max_length=2000)
    results: list[FillResult] = Field(default_factory=list, max_length=150)
    attached_resume: bool = False


@router.post("/fill-report")
async def fill_report(body: FillReportIn, user: ExtensionUser = Depends(get_extension_user)):
    """What Applicant filled on this form, for the case timeline."""
    from app.experts import applicant
    try:
        event = await asyncio.to_thread(applicant.record_fill, user.id, str(body.case_id), body.url,
                                        [r.model_dump() for r in body.results], body.attached_resume)
    except LookupError:
        raise HTTPException(404, "Case not found") from None
    return {"summary": event["summary"]}


# --- LinkedIn queue: approved invitations and DMs, sent by you one at a time ---------------------

LINKEDIN = ("send_linkedin_invite", "send_linkedin_dm", "referral_request")


def _queue(user_id: str) -> dict:
    from datetime import datetime, timezone

    from app.core.policy import load_policy
    policy = load_policy()
    now = datetime.now(timezone.utc)
    db = get_db(user_id)
    rows = db.fetch("""select to_jsonb(a) from (select id::text, case_id::text, kind, status, payload, payload_sha256, review,
                              block_reason, created_at from public.action where user_id = %s::uuid and kind = any(%s)
                              and status in ('reviewed', 'blocked', 'approved', 'executing')
                              order by array_position(array['executing','approved','reviewed','blocked'], status), created_at
                              limit 50) a""",
                    [user_id, list(LINKEDIN)])
    used = db.fetch("""select count(*) filter (where kind = 'send_linkedin_invite' and executing_at >= %s),
                              count(*) filter (where kind = 'send_linkedin_invite' and executing_at >= %s),
                              count(*) filter (where kind in ('send_linkedin_dm', 'referral_request') and executing_at >= %s)
                       from public.action where user_id = %s::uuid and kind = any(%s) and executing_at is not null""",
                    [policy.day_start(now), policy.week_start(now), policy.day_start(now), user_id, list(LINKEDIN)])[0]
    caps = policy.caps
    items = []
    for (a,) in rows:
        p = a["payload"]
        items.append({"id": a["id"], "case_id": a["case_id"], "kind": "invite" if a["kind"] == "send_linkedin_invite" else "dm",
                      "status": a["status"], "name": p.get("name") or "", "title": p.get("title") or "",
                      "company": p.get("company") or "", "profile_url": p.get("profile_url") or "",
                      "text": p.get("note") or p.get("body") or "", "payload_sha256": a["payload_sha256"],
                      "notes": [] if a["status"] == "blocked" else (a.get("review") or {}).get("notes") or [],
                      "blocked": (a.get("block_reason") or "Blocked by the Reviewer.") if a["status"] == "blocked" else ""})
    return {"items": items, "kill_switch": policy.kill_switch, "quiet_hours": policy.in_quiet_hours(now),
            "usage": {"invites_today": used[0], "invites_per_day": caps["linkedin_invites_per_day"],
                      "invites_this_week": used[1], "invites_per_week": caps["linkedin_invites_per_week"],
                      "dms_today": used[2], "dms_per_day": caps["linkedin_dms_per_day"]}}


@router.post("/linkedin/queue")
async def linkedin_queue(user: ExtensionUser = Depends(get_extension_user)):
    """Approved LinkedIn invitations and DMs waiting for you, and today's counts against your caps."""
    return await asyncio.to_thread(_queue, user.id)


class QueueItemIn(BaseModel):
    action_id: uuid.UUID


def _linkedin_action(user_id: str, action_id: str) -> dict:
    rows = get_db(user_id).fetch("""select to_jsonb(a) from (select id::text, case_id::text, kind, status, payload
                                    from public.action where id = %s::uuid and user_id = %s::uuid) a""", [action_id, user_id])
    if not rows or rows[0][0]["kind"] not in LINKEDIN:
        raise HTTPException(404, "Not in your LinkedIn queue")
    return rows[0][0]


@router.post("/linkedin/start")
async def linkedin_start(body: QueueItemIn, user: ExtensionUser = Depends(get_extension_user)):
    """Courier's door for one queued item: caps, cooldowns, quiet hours and the kill switch are
    checked now. Allowed -> it counts against today's cap and the panel opens the profile."""
    from app.core import actions
    action = await asyncio.to_thread(_linkedin_action, user.id, str(body.action_id))
    if action["status"] == "executing":           # opened before and not finished: open it again
        p = action["payload"]
        return {"ok": True, "profile_url": p.get("profile_url"), "text": p.get("note") or p.get("body") or ""}
    try:
        gate = await asyncio.to_thread(actions.start_execution, user.id, action["id"])
    except actions.ActionError as exc:
        raise HTTPException(409, str(exc)) from None
    if not gate.run:
        return {"ok": False, "reasons": gate.verdict.reasons}
    p = gate.action["payload"]
    return {"ok": True, "profile_url": p.get("profile_url"), "text": p.get("note") or p.get("body") or ""}


class QueueApproveIn(BaseModel):
    action_id: uuid.UUID
    payload_sha256: str = Field(min_length=64, max_length=64)


@router.post("/linkedin/approve")
async def linkedin_approve(body: QueueApproveIn, user: ExtensionUser = Depends(get_extension_user)):
    """Approve exactly the text you see in the panel (a stale hash is refused)."""
    from app.core import actions
    await asyncio.to_thread(_linkedin_action, user.id, str(body.action_id))
    try:
        done = await asyncio.to_thread(actions.approve, user.id, str(body.action_id), payload_sha256=body.payload_sha256,
                                       channel="extension")
    except actions.ActionError as exc:
        raise HTTPException(409, str(exc)) from None
    return {"status": done["status"]}


@router.post("/linkedin/reject")
async def linkedin_reject(body: QueueItemIn, user: ExtensionUser = Depends(get_extension_user)):
    from app.core import actions
    await asyncio.to_thread(_linkedin_action, user.id, str(body.action_id))
    try:
        done = await asyncio.to_thread(actions.reject, user.id, str(body.action_id), channel="extension")
    except actions.ActionError as exc:
        raise HTTPException(409, str(exc)) from None
    return {"status": done["status"]}


class QueueEditIn(BaseModel):
    action_id: uuid.UUID
    text: str = Field(max_length=2000)


@router.post("/linkedin/edit")
async def linkedin_edit(body: QueueEditIn, user: ExtensionUser = Depends(get_extension_user)):
    """Change the note before it goes out; the Reviewer checks the new text again."""
    from app.core import actions
    from app.experts import connector
    await asyncio.to_thread(_linkedin_action, user.id, str(body.action_id))
    try:
        done = await asyncio.to_thread(connector.revise, user.id, str(body.action_id), body.text)
    except actions.ActionError as exc:
        raise HTTPException(409, str(exc)) from None
    return {"status": done["status"], "payload_sha256": done["payload_sha256"],
            "notes": (done.get("review") or {}).get("notes") or [], "blocked": done.get("block_reason") or ""}


class QueueDoneIn(BaseModel):
    action_id: uuid.UUID
    sent: bool


@router.post("/linkedin/done")
async def linkedin_done(body: QueueDoneIn, user: ExtensionUser = Depends(get_extension_user)):
    """You say whether you sent it on LinkedIn. Sent -> recorded on the contact and the case."""
    from app.core import actions
    action = await asyncio.to_thread(_linkedin_action, user.id, str(body.action_id))
    if action["status"] != "executing":
        raise HTTPException(409, "Open it from the queue first.")
    invite = action["kind"] == "send_linkedin_invite"
    p, who = action["payload"], action["payload"].get("name") or "them"
    db = get_db(user.id)
    if body.sent:
        await asyncio.to_thread(actions.record_outcome, user.id, action["id"], "provider_accepted", provider_ref="sent_by_you")
        if p.get("contact_id"):
            await asyncio.to_thread(db.fetch, """insert into public.contact_touch (contact_id, user_id, case_id, channel, action_id,
                                                  sent_at, outcome) values (%s::uuid, %s::uuid, %s::uuid, %s, %s::uuid, now(), 'sent')""",
                                    [p["contact_id"], user.id, action["case_id"], "linkedin_invite" if invite
                                     else "referral" if action["kind"] == "referral_request" else "linkedin_dm",
                                     action["id"]])
            before = ["unknown", "discovered", "classified", "invite_proposed", "invite_approved"] if invite \
                else ["accepted", "message_proposed", "message_approved"]
            await asyncio.to_thread(db.fetch, """update public.contact set stage = %s where id = %s::uuid and user_id = %s::uuid
                                                  and stage = any(%s)""",
                                    ["invite_sent" if invite else "message_sent", p["contact_id"], user.id, before])
        summary = f"You sent the LinkedIn {'invitation' if invite else 'message'} to {who}"
    else:
        # It still counts against today's cap: it was opened, and LinkedIn may have seen it.
        await asyncio.to_thread(actions.record_outcome, user.id, action["id"], "failed", error="Not sent: you skipped it on LinkedIn.")
        summary = f"You didn't send the LinkedIn {'invitation' if invite else 'message'} to {who}"
    if action["case_id"]:
        await asyncio.to_thread(case_mod.add_event, user.id, action["case_id"], "note", actor="user", summary=summary,
                                data={"action_id": action["id"], "sent": body.sent})
    return {"status": "provider_accepted" if body.sent else "failed"}
