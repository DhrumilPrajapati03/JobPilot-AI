"""Answer bank (plan section 6, screen 6): search, source badge, version history, delete."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from app.answers import bank
from app.services.auth import CurrentUser, get_current_user

router = APIRouter()


@router.get("")
async def list_answers(q: str = Query("", max_length=200), user: CurrentUser = Depends(get_current_user)):
    rows = await asyncio.to_thread(bank.list_latest, user.id, q)
    return {"answers": rows, "total": len(rows)}


@router.get("/{answer_id}/history")
async def answer_history(answer_id: str, user: CurrentUser = Depends(get_current_user)):
    rows = await asyncio.to_thread(bank.history, user.id, answer_id)
    if not rows:
        raise HTTPException(404, "Answer not found")
    return {"versions": rows}


@router.delete("/{answer_id}", status_code=204)
async def delete_answer(answer_id: str, user: CurrentUser = Depends(get_current_user)):
    """Deletes every version of this answer."""
    if not await asyncio.to_thread(bank.delete, user.id, answer_id):
        raise HTTPException(404, "Answer not found")
