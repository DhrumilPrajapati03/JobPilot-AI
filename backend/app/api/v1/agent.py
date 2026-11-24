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
    import asyncio
    from app.services.usage import reserve
    from app.config import settings
    from fastapi import HTTPException
    if sum(len(m.content) for m in request.messages)>120000:
        raise HTTPException(413,'Conversation is too large. Start a new conversation.')
    await asyncio.to_thread(reserve,current_user.id,'chat',settings.CHAT_DAILY_LIMIT)
    messages = [m.model_dump() for m in request.messages]

    async def events():
        import time
        from contextlib import aclosing
        from app.services.auth import _verify_token
        checked=time.monotonic()
        async with aclosing(run_assistant(messages,current_user)) as stream:
            async for event in stream:
                if settings.APP_ENV=='production' and time.monotonic()-checked>=5:
                    try:
                        payload=await _verify_token(current_user.token)
                        if payload.get('sub')!=current_user.id:raise HTTPException(401)
                    except HTTPException:
                        yield 'data: '+json.dumps({'type':'error','message':'Your session could not be verified. Sign in again or retry shortly.'})+'\n\n'
                        yield 'data: {"type":"done"}\n\n'
                        return
                    checked=time.monotonic()
                yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
