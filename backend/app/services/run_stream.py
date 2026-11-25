"""Database replay works across API processes without sticky sessions."""
import asyncio
import time
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect

from app.services.runs import RunStore, TERMINAL
from app.db import get_db
from app.config import settings


async def stream_run(websocket: WebSocket, run_id: str, user_id: str, token: str):
    try:
        UUID(run_id)
        store = RunStore(get_db(user_id))
        if not await asyncio.to_thread(store.get, run_id, user_id):
            await websocket.send_json({"type": "unknown_run", "run_id": run_id})
            await websocket.close()
            return
        # An explicit retry starts a new replay segment. Otherwise an older
        # terminal failure would close the browser before it saw the retry.
        cursor = await asyncio.to_thread(store.replay_cursor, run_id, user_id)
        checked=0.0
        while True:
            if settings.APP_ENV=='production' and time.monotonic()-checked>=5:
                from app.services.auth import _verify_token
                from fastapi import HTTPException
                try:
                    if (await _verify_token(token)).get('sub')!=user_id:raise HTTPException(401)
                except HTTPException as exc:
                    await websocket.close(code=4401 if exc.status_code==401 else 1013,reason='Session validation required')
                    return
                checked=time.monotonic()
            rows = await asyncio.to_thread(store.events, run_id, user_id, cursor)
            if rows is None:
                await websocket.close(code=4403)
                return
            for row in rows:
                await websocket.send_json({**row["event"], "run_id": run_id, "event_id": row["id"], "ts": time.time()})
                cursor = row["id"]
            if len(rows) == 200:
                continue
            run = await asyncio.to_thread(store.get, run_id, user_id)
            if run is None:
                await websocket.close(code=4403)
                return
            if run["status"] in TERMINAL:
                # Finish may have committed between event and status reads. Read
                # events once more before closing so the terminal frame isn't lost.
                tail = await asyncio.to_thread(store.events, run_id, user_id, cursor)
                if tail:
                    for row in tail:
                        await websocket.send_json({**row["event"], "run_id": run_id, "event_id": row["id"], "ts": time.time()})
                        cursor = row["id"]
                    if len(tail) == 200:
                        continue
                await websocket.close()
                return
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=1)
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        return
    except Exception:
        await websocket.close(code=1013, reason="Run storage temporarily unavailable")
