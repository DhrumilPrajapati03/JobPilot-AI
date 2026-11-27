"""Cases and actions: the spine the experts and the approval inbox work on (plan sections 4 and 5)."""
import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core import actions, budgets, cases
from app.core.policy import PolicyError, load_policy
from app.services.auth import CurrentUser, get_current_user

router = APIRouter()

_STATUS = {"action_not_found": 404, "idempotency_key_conflict": 409, "stale_payload": 409, "invalid_transition": 409,
           "payload_frozen": 409, "not_approvable": 409, "not_approved": 409, "approval_required": 409,
           "circuit_open": 429, "invalid_payload": 422, "invalid_channel": 422}


def _action_error(exc: actions.ActionError) -> HTTPException:
    return HTTPException(_STATUS.get(exc.code, 400), {"code": exc.code, "message": str(exc)})


class CaseIn(BaseModel):
    company: str = Field(default="", max_length=300)
    role: str = Field(default="", max_length=300)
    source_url: str = Field(default="", max_length=2000)
    jd_text: str = Field(default="", max_length=60_000)


class StageIn(BaseModel):
    stage: Literal[cases.STAGES]  # type: ignore[valid-type]


class ApproveIn(BaseModel):
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    note: str = Field(default="", max_length=1000)


class RejectIn(BaseModel):
    note: str = Field(default="", max_length=1000)


class EditIn(BaseModel):
    payload: dict


@router.get("")
async def list_cases(stage: str | None = Query(default=None), user: CurrentUser = Depends(get_current_user)):
    if stage is not None and stage not in cases.STAGES:
        raise HTTPException(422, "Unknown stage")
    return {"cases": await asyncio.to_thread(cases.list_cases, user.id, stage=stage)}


@router.post("", status_code=201)
async def create_case(body: CaseIn, user: CurrentUser = Depends(get_current_user)):
    return await asyncio.to_thread(cases.create_case, user.id, **body.model_dump(), actor="user")


@router.get("/policy")
async def policy_summary(user: CurrentUser = Depends(get_current_user)):
    """What the experts may do (the 'policy preview'), plus this month's LLM budget."""
    try:
        policy = load_policy()
    except PolicyError as exc:
        raise HTTPException(503, str(exc)) from None
    month = await asyncio.to_thread(budgets.month_status, user.id, policy=policy)
    return {"kill_switch": policy.kill_switch, "action_modes": policy.action_modes,
            "caps": {k: v for k, v in policy.caps.items()}, "budgets": policy.budgets,
            "month_usd_used": month.used["usd"]}


@router.get("/actions/pending")
async def pending_actions(user: CurrentUser = Depends(get_current_user)):
    return {"actions": await asyncio.to_thread(actions.pending, user.id)}


@router.post("/actions/{action_id}/approve")
async def approve_action(action_id: str, body: ApproveIn, user: CurrentUser = Depends(get_current_user)):
    try:
        approved = await asyncio.to_thread(actions.approve, user.id, action_id, payload_sha256=body.payload_sha256,
                                           channel="web", note=body.note)
    except actions.ActionError as exc:
        raise _action_error(exc) from None
    from app.courier import runner as courier
    if approved["kind"] in courier.SENDERS:
        await asyncio.to_thread(courier.dispatch, user.id, action_id)
    return approved


@router.post("/actions/{action_id}/reject")
async def reject_action(action_id: str, body: RejectIn, user: CurrentUser = Depends(get_current_user)):
    try:
        return await asyncio.to_thread(actions.reject, user.id, action_id, channel="web", note=body.note)
    except actions.ActionError as exc:
        raise _action_error(exc) from None


@router.put("/actions/{action_id}")
async def edit_action(action_id: str, body: EditIn, user: CurrentUser = Depends(get_current_user)):
    from app.experts.rereview import edit_and_review
    try:
        return await asyncio.to_thread(edit_and_review, user.id, action_id, body.payload)
    except actions.ActionError as exc:
        raise _action_error(exc) from None


@router.get("/{case_id}")
async def get_case(case_id: str, user: CurrentUser = Depends(get_current_user)):
    try:
        case = await asyncio.to_thread(cases.get_case, user.id, case_id)
    except Exception:
        case = None
    if case is None:
        raise HTTPException(404, "Case not found")
    return case


@router.patch("/{case_id}/stage")
async def set_stage(case_id: str, body: StageIn, user: CurrentUser = Depends(get_current_user)):
    try:
        return await asyncio.to_thread(cases.set_stage, user.id, case_id, body.stage, actor="user")
    except LookupError:
        raise HTTPException(404, "Case not found") from None


# --- artifacts: files and review -------------------------------------------------------------

class ArtifactReviewIn(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str = Field(default="", max_length=1000)


def _artifact(user_id: str, case_id: str, artifact_id: str) -> dict | None:
    from app.db import get_db
    try:
        rows = get_db(user_id).fetch("""select kind, content from public.artifact where id = %s::uuid
                                        and case_id = %s::uuid and user_id = %s::uuid""", [artifact_id, case_id, user_id])
    except Exception:
        return None
    return {"kind": rows[0][0], "content": rows[0][1]} if rows else None


@router.get("/{case_id}/artifacts/{artifact_id}/file")
async def artifact_file(case_id: str, artifact_id: str, format: Literal["pdf", "tex"] = "pdf",
                        user: CurrentUser = Depends(get_current_user)):
    """The tailored resume's PDF (or .tex), for the diff card and for opening in Overleaf."""
    from pathlib import Path

    from fastapi.responses import FileResponse

    from app.config import settings
    artifact = await asyncio.to_thread(_artifact, user.id, case_id, artifact_id)
    meta = (artifact or {}).get("content", {}).get(format) if artifact and artifact["kind"] == "resume_version" else None
    if not meta:
        raise HTTPException(404, "No such file for this artifact")
    root = Path(settings.FILE_STORAGE_DIR).resolve()
    path = (root / meta["path"]).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404, "The file is missing; ask Tailor for a new version.")
    return FileResponse(path, media_type="application/pdf" if format == "pdf" else "application/x-tex",
                        filename=f"resume-{case_id[:8]}.{format}")


@router.post("/{case_id}/artifacts/{artifact_id}/review")
async def review_artifact(case_id: str, artifact_id: str, body: ArtifactReviewIn, user: CurrentUser = Depends(get_current_user)):
    """Approve or reject a resume version (the diff card's buttons)."""
    from psycopg.types.json import Jsonb

    from app.db import get_db
    artifact = await asyncio.to_thread(_artifact, user.id, case_id, artifact_id)
    if not artifact or artifact["kind"] != "resume_version":
        raise HTTPException(404, "Resume version not found")
    content = {**artifact["content"], "status": body.decision}
    await asyncio.to_thread(get_db(user.id).fetch, "update public.artifact set content = %s where id = %s::uuid",
                            [Jsonb(content), artifact_id])
    await asyncio.to_thread(cases.add_event, user.id, case_id, f"resume_{body.decision}", actor="user",
                            summary=f"You {body.decision} the tailored resume" + (f": {body.note}" if body.note else ""),
                            data={"artifact_id": artifact_id})
    return {"status": body.decision}
