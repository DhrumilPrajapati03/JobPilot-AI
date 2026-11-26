"""Expert runtime: runs one expert on the durable queue (run kind 'agent').

* The spec is loaded from agent_spec and validated again; paused and draft experts don't run.
* Budgets are checked before work starts (per case, per spec, monthly) and charged after
  (steps, tokens, seconds), so a looping case stops instead of spending.
* Every step is a run_step row with plain-words summary (shown on hover in the roster) and a
  redacted detail (the Details toggle). Secrets and long texts never land there.
* When an expert finishes work on a case, Supervisor is woken to route the next step.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field

from psycopg.types.json import Jsonb

from app.core import budgets, cases
from app.db import get_db
from app.experts import spec as spec_mod
from app.experts.tools import ToolBox
from app.services.runs import PermanentRunError, RunStore

SECRET_HINTS = ("token", "secret", "password", "authorization", "cookie", "api_key", "apikey", "key_")
MAX_TEXT = 500


def redact(value, depth: int = 0):
    """Bounded, secret-free copy of a tool input/output for the trace."""
    if depth > 4:
        return "…"
    if isinstance(value, dict):
        return {k: ("[redacted]" if any(h in str(k).lower() for h in SECRET_HINTS) else redact(v, depth + 1))
                for k, v in list(value.items())[:30]}
    if isinstance(value, (list, tuple)):
        return [redact(v, depth + 1) for v in list(value)[:20]]
    if isinstance(value, str):
        return value if len(value) <= MAX_TEXT else value[:MAX_TEXT] + f"… ({len(value)} chars)"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    return str(value)[:MAX_TEXT]


class BudgetStop(PermanentRunError):
    pass


@dataclass
class ExpertContext:
    user_id: str
    spec: spec_mod.AgentSpec
    case_id: str | None
    inputs: dict
    run_id: str | None = None
    db: object = field(default_factory=get_db)
    steps: int = 0
    tokens: int = 0

    def __post_init__(self):
        self.log = StepLog(self)
        self.tools = ToolBox(self.spec, self.log)


class StepLog:
    def __init__(self, ctx: ExpertContext):
        self.ctx = ctx

    async def add(self, kind: str, name: str, summary: str, detail: dict | None = None, *, tokens: int = 0,
                  duration_ms: int = 0) -> None:
        self.ctx.steps += 1
        self.ctx.tokens += tokens
        limit = self.ctx.spec.budgets.get("steps")
        await asyncio.to_thread(get_db(self.ctx.user_id).fetch, """
            insert into public.run_step (run_id, user_id, case_id, agent, kind, name, summary, detail, tokens, duration_ms)
            values (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s)""",
            [self.ctx.run_id, self.ctx.user_id, self.ctx.case_id, self.ctx.spec.id, kind, name, summary[:300],
             Jsonb(redact(detail or {})), tokens, duration_ms])
        if limit and self.ctx.steps > limit and kind not in ("blocked", "error"):
            raise BudgetStop(f"{self.ctx.spec.name} reached its step budget ({limit:g}).")


async def note(user_id: str, agent: str, summary: str, *, case_id: str | None = None, kind: str = "note",
               detail: dict | None = None) -> None:
    """A quiet system line in an expert's thread (routine ran, woke up, waiting for…)."""
    await asyncio.to_thread(get_db(user_id).fetch, """
        insert into public.run_step (user_id, case_id, agent, kind, summary, detail)
        values (%s::uuid, %s::uuid, %s, %s, %s, %s)""", [user_id, case_id, agent, kind, summary[:300], Jsonb(detail or {})])


def enqueue_expert(user_id: str, agent: str, *, case_id: str | None = None, key: str | None = None,
                   store: RunStore | None = None, **inputs) -> dict:
    """Queue an expert run. Runs on the same case wait for each other; different cases run side by side."""
    store = store or RunStore()
    payload = {"agent": agent, **({"case_id": case_id} if case_id else {}), **inputs}
    return store.enqueue(user_id, "agent", payload, key or f"{agent}:{case_id or 'none'}:{uuid.uuid4()}", case_id=case_id)


async def run_expert(ctx: ExpertContext) -> dict:
    """Budget gate, the expert's own work, then charges and the hand-back to Supervisor."""
    from app.experts import answerer, email_outreach, recon, researcher, scout, supervisor, tailor
    handlers = {"supervisor": supervisor.run, "scout": scout.run, "researcher": researcher.run, "tailor": tailor.run,
                "email_outreach": email_outreach.run, "recon": recon.run, "answerer": answerer.run}
    if ctx.spec.status != "active":
        raise PermanentRunError(f"{ctx.spec.name} is {ctx.spec.status}; nothing was run.")
    handler = handlers.get(ctx.spec.id)
    if handler is None:
        raise PermanentRunError(f"{ctx.spec.name} is not built yet.")
    reasons = await asyncio.to_thread(budgets.check, ctx.user_id, ctx.case_id)
    if reasons:
        await ctx.log.add("blocked", "budget", reasons[0], {"reasons": reasons})
        if ctx.case_id:
            await asyncio.to_thread(cases.add_event, ctx.user_id, ctx.case_id, "blocked", actor="agent",
                                    actor_name=ctx.spec.id, summary=reasons[0])
        raise BudgetStop(reasons[0])
    started = time.perf_counter()
    try:
        result = await handler(ctx)
    finally:
        seconds = time.perf_counter() - started
        for unit, amount in (("steps", ctx.steps), ("tokens", ctx.tokens), ("seconds", round(seconds, 2))):
            if amount:
                await asyncio.to_thread(budgets.charge, ctx.user_id, unit, amount, case_id=ctx.case_id,
                                        run_id=ctx.run_id, agent=ctx.spec.id)
    if ctx.case_id and ctx.spec.id != "supervisor":
        await asyncio.to_thread(enqueue_expert, ctx.user_id, "supervisor", case_id=ctx.case_id,
                                key=f"supervisor:{ctx.case_id}:after:{ctx.run_id or uuid.uuid4()}", trigger="expert_done")
    return result


async def execute(run_ctx) -> dict:
    """Worker entry point for run kind 'agent'."""
    run = run_ctx.run
    inputs = dict(run.get("inputs") or {})
    db = get_db()
    spec = await asyncio.to_thread(spec_mod.load_spec, db, inputs.get("agent", ""))
    if spec is None:
        raise PermanentRunError(f"Unknown expert {inputs.get('agent')!r}.")
    ctx = ExpertContext(run["user_id"], spec, run.get("case_id") or inputs.get("case_id"), inputs, run_id=run["id"], db=db)

    async def work():
        return await run_expert(ctx)
    return await run_ctx.stage(f"expert:{spec.id}", f"{spec.name} is working", work)
