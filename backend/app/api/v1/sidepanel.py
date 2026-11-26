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
