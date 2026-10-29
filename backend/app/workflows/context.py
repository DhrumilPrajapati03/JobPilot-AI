import asyncio
import json
import time

from app.services.runs import LeaseLost


class ExecutionContext:
    def __init__(self, store, run, lost=None):
        self.store, self.run = store, run
        self.token = run["lease_token"]
        self.lost = lost
        self.checkpoints = dict(run.get("checkpoints") or {})

    def check(self):
        if self.lost is not None and self.lost.is_set():
            raise LeaseLost("Worker lease was lost")

    async def emit(self, step, status, message, **data):
        self.check()
        event = {"type": "status", "step": step, "status": status, "message": message}
        if data:
            event["data"] = data
        await asyncio.to_thread(self.store.emit, self.run["id"], self.token, event)

    async def save(self, name, value):
        self.check()
        value = json.loads(json.dumps(value, default=str))
        await asyncio.to_thread(self.store.checkpoint, self.run["id"], self.token, name, value)
        self.checkpoints[name] = value
        return value

    async def stage(self, name, message, operation):
        self.check()
        if name in self.checkpoints:
            value = self.checkpoints[name]
            await self.emit(name, "warning" if value.get("warning") else "done",
                            value.get("warning") or "Restored completed step from checkpoint",
                            **{k: value[k] for k in ("score", "missing_keywords") if k in value})
            return value
        await self.emit(name, "running", message)
        started = time.perf_counter()
        value = await operation()
        await self.save(name, value)
        await self.emit(name, "warning" if value.get("warning") else "done", value.get("warning") or "Step completed",
                        duration_ms=round((time.perf_counter()-started)*1000,3),
                        **{k: value[k] for k in ("score", "missing_keywords") if k in value})
        return value
