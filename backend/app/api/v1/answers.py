"""Answer bank endpoints: saved answers to application screening questions."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.services.auth import CurrentUser, get_current_user
from app.services.supabase import get_supabase_client

router = APIRouter()

Category = Literal["contact", "work_auth", "experience", "compensation", "availability", "eeo", "custom"]


class Answer(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(default="", max_length=4000)
    category: Category = "custom"
    sensitive: bool = False


class AnswerBatch(BaseModel):
    answers: list[Answer] = Field(max_length=200)


def _table_missing(error: Exception) -> bool:
    message = str(error)
    return "PGRST205" in message or ("qa_answers" in message and "does not exist" in message)


def _raise_for(error: Exception):
    if _table_missing(error):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The answer bank table doesn't exist yet. Run supabase/migrations/20261010_answer_bank.sql in Supabase.",
        )
    raise error


@router.get("/")
async def list_answers(current_user: CurrentUser = Depends(get_current_user)):
    """All saved answers, grouped client-side by category."""
    supabase = get_supabase_client(user_jwt=current_user.token)
    try:
        res = supabase.table("qa_answers").select("*").eq("user_id", current_user.id).order("question").execute()
    except Exception as e:
        _raise_for(e)
    return {"answers": res.data}


@router.put("/")
async def save_answers(batch: AnswerBatch, current_user: CurrentUser = Depends(get_current_user)):
    """Create or update answers, matched by question text."""
    supabase = get_supabase_client(user_jwt=current_user.token)
    rows = [{**a.model_dump(), "question": a.question.strip(), "user_id": current_user.id} for a in batch.answers]
    if not rows:
        return {"answers": []}
    try:
        res = supabase.table("qa_answers").upsert(rows, on_conflict="user_id,question").execute()
    except Exception as e:
        _raise_for(e)
    return {"answers": res.data}


@router.delete("/{answer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_answer(answer_id: str, current_user: CurrentUser = Depends(get_current_user)):
    supabase = get_supabase_client(user_jwt=current_user.token)
    try:
        supabase.table("qa_answers").delete().eq("id", answer_id).eq("user_id", current_user.id).execute()
    except Exception as e:
        _raise_for(e)


async def answers_for_llm(current_user: CurrentUser) -> list[dict]:
    """Answers safe to include in a prompt — sensitive ones are excluded."""
    supabase = get_supabase_client(user_jwt=current_user.token)
    try:
        res = supabase.table("qa_answers").select("question, answer, category, sensitive").eq("user_id", current_user.id).execute()
    except Exception as e:
        if _table_missing(e):
            return []
        raise
    return [{"question": r["question"], "answer": r["answer"]} for r in res.data if not r.get("sensitive") and r.get("answer")]
