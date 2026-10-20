"""JobPilot Assistant endpoints (chat agent)."""

import json
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents.assistant import run_assistant
from app.services.auth import CurrentUser, get_current_user

router = APIRouter()


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=24_000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)


@router.post("/chat")
async def chat(request: ChatRequest, current_user: CurrentUser = Depends(get_current_user)):
    """Stream the assistant's reply as Server-Sent Events.

    Each event is `data: <json>` where the JSON is one of the events
    documented in app.agents.assistant (text / tool_start / tool_result / error / done).
    The client sends the conversation so far; history lives client-side.
    """
    messages = [m.model_dump() for m in request.messages]

    async def events():
        async for event in run_assistant(messages, current_user):
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
