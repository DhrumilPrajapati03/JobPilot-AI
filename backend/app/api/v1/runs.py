"""User-owned durable run status and replay. Mutations stay worker-only."""
import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.services.auth import CurrentUser, get_current_user
from app.services.runs import RunStore, public_run

router = APIRouter()


@router.post("/{run_id}/retry")
async def retry_run(run_id: UUID, user: CurrentUser = Depends(get_current_user)):
    try:
        row = await asyncio.to_thread(RunStore().rpc, "retry_agent_run", p_run_id=str(run_id), p_user_id=user.id)
    except Exception as exc:
        if "run_not_found" in str(exc):
            raise HTTPException(404, "Run not found") from exc
        if any(code in str(exc) for code in ("run_not_failed", "request_a_new_digest", "posting_unavailable")):
            raise HTTPException(409, "This run cannot be retried. Request new work or restore the source posting.") from exc
        raise HTTPException(503, "Run storage is unavailable.") from exc
    return public_run(row)


@router.get("/{run_id}")
async def get_run(run_id: UUID, user: CurrentUser = Depends(get_current_user)):
    try:
        row = await asyncio.to_thread(RunStore().get, str(run_id), user.id)
    except Exception as exc:
        raise HTTPException(503, "Run storage is unavailable.") from exc
    if not row:
        raise HTTPException(404, "Run not found")
    return public_run(row)


@router.get("/{run_id}/events")
async def get_events(run_id: UUID, after: int = Query(default=0, ge=0), user: CurrentUser = Depends(get_current_user)):
    try:
        rows = await asyncio.to_thread(RunStore().events, str(run_id), user.id, after)
    except Exception as exc:
        raise HTTPException(503, "Run storage is unavailable.") from exc
    if rows is None:
        raise HTTPException(404, "Run not found")
    return {"events": rows, "next_cursor": rows[-1]["id"] if rows else after}
