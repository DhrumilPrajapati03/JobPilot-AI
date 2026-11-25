"""Experts: the roster (with each expert's live state), one expert's detail, manual runs and
routines. State names match the avatar states in plan section 6.2."""
import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from app.core.policy import load_policy
from app.db import get_db
from app.experts import runtime
from app.services.auth import CurrentUser, get_current_user
from app.services.runs import durable_enabled

router = APIRouter()
DONE_FOR = timedelta(minutes=10)
FAILED_FOR = timedelta(hours=24)


def _state(spec: dict, run: dict | None, step: dict | None, pending: int, kill_switch: bool, now: datetime) -> str:
    """idle | acknowledged | working | waiting_approval | blocked | failed | done | paused | draft"""
    if spec["status"] == "draft":
        return "draft"
    if spec["status"] == "paused" or kill_switch:
        return "paused"
    if run and run["status"] == "running":
        return "working"
    if run and run["status"] in ("queued", "retry_wait"):
        return "acknowledged"
    if pending:
        return "waiting_approval"
    if step and step["kind"] == "blocked" and now - datetime.fromisoformat(step["at"]) < FAILED_FOR:
        return "blocked"
    if run and run["status"] == "failed" and now - datetime.fromisoformat(run["updated_at"]) < FAILED_FOR:
        return "failed"
    if run and run["status"] == "succeeded" and now - datetime.fromisoformat(run["updated_at"]) < DONE_FOR:
        return "done"
    return "idle"


def roster(user_id: str) -> list[dict]:
    db = get_db(user_id)
    specs = [r[0] for r in db.fetch("""select jsonb_build_object('id', id, 'name', name, 'role', role, 'status', status)
                                       from public.agent_spec order by array_position(array['supervisor','scout','researcher',
                                       'comp_analyst','tailor','answerer','applicant','recon','connector','email_outreach',
                                       'dm_outreach','inbox','interview_buddy','reviewer'], id), id""")]
    runs = {r[0]: r[1] for r in db.fetch("""select distinct on (inputs->>'agent') inputs->>'agent',
                                              jsonb_build_object('status', status, 'updated_at', updated_at, 'case_id', case_id)
                                            from public.agent_runs where user_id = %s::uuid and kind = 'agent'
                                            order by inputs->>'agent', updated_at desc""", [user_id])}
    steps = {r[0]: r[1] for r in db.fetch("""select distinct on (agent) agent,
                                               jsonb_build_object('kind', kind, 'summary', summary, 'at', at, 'case_id', case_id)
                                             from public.run_step where user_id = %s::uuid order by agent, at desc, id desc""", [user_id])}
    pending = dict(db.fetch("""select agent, count(*) from public.action where user_id = %s::uuid
                               and status in ('proposed', 'reviewed') group by agent""", [user_id]))
    try:
        kill = load_policy().kill_switch
    except Exception:
        kill = False
    now = datetime.now(timezone.utc)
    out = []
    for spec in specs:
        run, step = runs.get(spec["id"]), steps.get(spec["id"])
        state = _state(spec, run, step, pending.get(spec["id"], 0), kill, now)
        out.append({**spec, "state": state, "step": step["summary"] if step else "",
                    "step_at": step["at"] if step else None, "approvals": pending.get(spec["id"], 0)})
    return out


@router.get("")
async def list_experts(user: CurrentUser = Depends(get_current_user)):
    return {"experts": await asyncio.to_thread(roster, user.id)}


@router.get("/{agent_id}")
async def expert_detail(agent_id: str, user: CurrentUser = Depends(get_current_user)):
    def load():
        db = get_db(user.id)
        spec = db.fetch("""select to_jsonb(s) - 'user_id' - 'spec_sha256' from public.agent_spec s where id = %s""", [agent_id])
        if not spec:
            return None
        routines = [r[0] for r in db.fetch("""select to_jsonb(r) - 'user_id' from public.routine r
                                             where user_id = %s::uuid and agent = %s order by key""", [user.id, agent_id])]
        steps = [r[0] for r in db.fetch("""select jsonb_build_object('id', id, 'kind', kind, 'name', name, 'summary', summary,
                                             'detail', detail, 'case_id', case_id, 'at', at, 'tokens', tokens)
                                           from public.run_step where user_id = %s::uuid and agent = %s
                                           order by at desc, id desc limit 50""", [user.id, agent_id])]
        return {"spec": spec[0][0], "routines": routines, "steps": steps}
    detail = await asyncio.to_thread(load)
    if detail is None:
        raise HTTPException(404, "Unknown expert")
    return detail


def _require_worker():
    if not durable_enabled():
        raise HTTPException(503, "Experts run on the background worker. Start the stack with docker compose up -d.")


class ResearchIn(BaseModel):
    urls: list[HttpUrl] = Field(default_factory=list, max_length=4)


@router.post("/scout/run", status_code=202)
async def run_scout(user: CurrentUser = Depends(get_current_user)):
    _require_worker()
    run = await asyncio.to_thread(runtime.enqueue_expert, user.id, "scout", trigger="manual")
    return {"run_id": run["id"]}


@router.post("/cases/{case_id}/research", status_code=202)
async def research_case(case_id: str, body: ResearchIn, user: CurrentUser = Depends(get_current_user)):
    _require_worker()
    try:
        run = await asyncio.to_thread(runtime.enqueue_expert, user.id, "researcher", case_id=case_id, trigger="manual",
                                      urls=[str(u) for u in body.urls])
    except Exception as exc:
        if "case_not_found" in str(exc):
            raise HTTPException(404, "Case not found") from None
        raise
    return {"run_id": run["id"]}


@router.post("/cases/{case_id}/supervise", status_code=202)
async def supervise_case(case_id: str, user: CurrentUser = Depends(get_current_user)):
    _require_worker()
    try:
        run = await asyncio.to_thread(runtime.enqueue_expert, user.id, "supervisor", case_id=case_id, trigger="manual")
    except Exception as exc:
        if "case_not_found" in str(exc):
            raise HTTPException(404, "Case not found") from None
        raise
    return {"run_id": run["id"]}


class RoutineIn(BaseModel):
    enabled: bool


@router.patch("/routines/{routine_id}")
async def toggle_routine(routine_id: str, body: RoutineIn, user: CurrentUser = Depends(get_current_user)):
    rows = await asyncio.to_thread(get_db(user.id).fetch, """update public.routine set enabled = %s
        where id = %s::uuid and user_id = %s::uuid returning key, enabled""", [body.enabled, routine_id, user.id])
    if not rows:
        raise HTTPException(404, "Routine not found")
    return {"key": rows[0][0], "enabled": rows[0][1]}
