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
        return await asyncio.to_thread(actions.approve, user.id, action_id, payload_sha256=body.payload_sha256,
                                       channel="web", note=body.note)
    except actions.ActionError as exc:
        raise _action_error(exc) from None


@router.post("/actions/{action_id}/reject")
async def reject_action(action_id: str, body: RejectIn, user: CurrentUser = Depends(get_current_user)):
    try:
        return await asyncio.to_thread(actions.reject, user.id, action_id, channel="web", note=body.note)
    except actions.ActionError as exc:
        raise _action_error(exc) from None


@router.put("/actions/{action_id}")
async def edit_action(action_id: str, body: EditIn, user: CurrentUser = Depends(get_current_user)):
    try:
        return await asyncio.to_thread(actions.edit, user.id, action_id, body.payload)
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
