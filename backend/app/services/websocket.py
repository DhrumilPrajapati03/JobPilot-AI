"""WebSocket manager for real-time agent progress streaming.

Every event sent for a run is buffered, so a client that connects after the
pipeline has already started (the background task begins as soon as
POST /applications/generate returns) still receives the full history.
"""

import time

from fastapi import WebSocket

# How long a finished run's event history is kept for late (re)connects.
RUN_HISTORY_TTL_SECONDS = 15 * 60
TERMINAL_STEPS = {"complete"}


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, set[WebSocket]] = {}
        self.history: dict[str, list[dict]] = {}
        self.finished_at: dict[str, float] = {}

    def register(self, run_id: str):
        """Mark a run as known before its background task emits anything."""
        self.history.setdefault(run_id, [])

    async def connect(self, run_id: str, websocket: WebSocket) -> bool:
        """Accept a subscriber and replay the run's history.

        Returns False (after telling the client) when the run is unknown or
        its history has expired.
        """
        await websocket.accept()
        if run_id not in self.history:
            await websocket.send_json({"type": "unknown_run", "run_id": run_id})
            await websocket.close()
            return False
        self.active_connections.setdefault(run_id, set()).add(websocket)
        try:
            for message in self.history.get(run_id, []):
                await websocket.send_json(message)
        except Exception:
            # The client went away mid-replay (page closed, React remount); nothing to do.
            self.disconnect(run_id, websocket)
            return False
        return True

    def disconnect(self, run_id: str, websocket: WebSocket | None = None):
        sockets = self.active_connections.get(run_id)
        if sockets is None:
            return
        if websocket is not None:
            sockets.discard(websocket)
        if websocket is None or not sockets:
            del self.active_connections[run_id]

    def is_finished(self, run_id: str) -> bool:
        return run_id in self.finished_at

    async def send_update(self, run_id: str, message: dict):
        message = {**message, "run_id": run_id, "ts": time.time()}
        self.history.setdefault(run_id, []).append(message)
        if message.get("step") in TERMINAL_STEPS or message.get("status") == "error":
            self.finished_at[run_id] = time.time()
        self._prune()

        for websocket in list(self.active_connections.get(run_id, ())):
            try:
                await websocket.send_json(message)
            except Exception as e:
                print(f"Error sending WebSocket update for run {run_id}: {str(e)}")
                self.disconnect(run_id, websocket)

    def _prune(self):
        cutoff = time.time() - RUN_HISTORY_TTL_SECONDS
        for run_id, finished in list(self.finished_at.items()):
            if finished < cutoff:
                self.finished_at.pop(run_id, None)
                self.history.pop(run_id, None)


manager = ConnectionManager()
