"""User-owned durable run status and replay. Mutations stay worker-only."""
import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.services.auth import CurrentUser, get_current_user
from app.services.runs import RunStore, public_run

router = APIRouter()


@router.get('')
async def recent_runs(user: CurrentUser = Depends(get_current_user)):
    from app.services.runs import durable_enabled
    if not durable_enabled(): return {'mode':'inline','runs':[]}
    try:
        rows = await asyncio.to_thread(RunStore().recent,user.id)
        # This summary never returns queued inputs, checkpoints, lease tokens or materials.
        return {'mode':'durable','runs':[{**{k:r.get(k) for k in ('id','kind','status','stage','attempts','max_attempts','created_at','updated_at')},
                                        'application_id':(r.get('result') or {}).get('application_id'),
                                        'mail_outcome':(r.get('result') or {}).get('state') if r.get('kind')=='mail_send' else None} for r in rows]}
    except Exception:
        raise HTTPException(503,'Background activity is unavailable. Try again later.') from None


@router.post("/{run_id}/retry")
async def retry_run(run_id: UUID, user: CurrentUser = Depends(get_current_user)):
    from app.services.usage import reserve
    await asyncio.to_thread(reserve,user.id,'run_retries',20)
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
