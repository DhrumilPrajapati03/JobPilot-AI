"""Tool registry and per-expert allowlists (plan sections 3 and 4).

Tools belong to the account; each expert's spec lists the ones it may call. A ToolBox built
from a spec exposes only those, so a prompt-injected expert cannot reach anything else.

* `background_ok`: no outward side effects (reads public pages, writes JobDots' own rows).
  Routine-triggered experts may hold only these.
* No tool here sends anything. Outward actions are proposed through app.core.actions and
  executed by Courier after approval.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable


class ToolDenied(PermissionError):
    pass


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    background_ok: bool
    fn: Callable[..., Awaitable[Any]]


REGISTRY: dict[str, Tool] = {}


def tool(name: str, description: str, *, background_ok: bool = True):
    def register(fn):
        REGISTRY[name] = Tool(name, description, background_ok, fn)
        return fn
    return register


class ToolBox:
    """The tools one expert may call, with each call traced as a run_step."""

    def __init__(self, spec, step_log):
        self.spec, self.log = spec, step_log
        self.allowed = {n: REGISTRY[n] for n in spec.tools if n in REGISTRY}

    async def call(self, name: str, summary: str = "", /, **kwargs):
        if name not in self.allowed:
            await self.log.add("blocked", name, f"{self.spec.name} is not allowed to use {name}", {"tool": name})
            raise ToolDenied(f"{self.spec.id} may not call {name}")
        started = time.perf_counter()
        try:
            result = await self.allowed[name].fn(self.log.ctx, **kwargs)
        except Exception as exc:
            await self.log.add("error", name, f"{name} failed ({type(exc).__name__})", {"args": kwargs})
            raise
        await self.log.add("tool", name, summary or name, {"args": kwargs, "result": result},
                           duration_ms=int((time.perf_counter() - started) * 1000))
        return result


# --- built-in tools ----------------------------------------------------------------------------
# Each receives the expert context (user, case, database) first; keyword arguments after.

@tool("read_case", "Read a case with its timeline and artifacts")
async def read_case(ctx, case_id: str):
    from app.core import cases
    return await asyncio.to_thread(cases.get_case, ctx.user_id, case_id)


@tool("fetch_public_page", "Fetch the readable text of one public web page (no logins, no private hosts)")
async def fetch_public_page(ctx, url: str):
    from app.agents.research import ResearchAgent
    result = await ResearchAgent().research("", [url])
    return result["sources"][0] if result["sources"] else {"url": url, "error": "unreadable"}


@tool("save_artifact", "Save a typed artifact (validated against its schema) on the case")
async def save_artifact(ctx, kind: str, content: dict, title: str = ""):
    from app.experts import artifacts
    return await asyncio.to_thread(artifacts.save, ctx.user_id, ctx.case_id, kind, content,
                                   agent=ctx.spec.id, title=title)


@tool("scan_job_boards", "Scan the job boards you follow and score new postings")
async def scan_job_boards(ctx):
    from app.services import discovery
    return await discovery.scan_user(ctx.db, ctx.user_id, auto_draft=False)


@tool("open_case", "Open a case for a matching posting (once per posting)")
async def open_case(ctx, posting: dict):
    from app.experts import scout
    return await asyncio.to_thread(scout.open_case_for_posting, ctx.user_id, posting)


@tool("route_case", "Hand a case to the next expert")
async def route_case(ctx, case_id: str, agent: str, reason: str):
    from app.experts import supervisor
    return await asyncio.to_thread(supervisor.hand_off, ctx.user_id, case_id, agent, reason)


@tool("compile_resume", "Compile a resume .tex with Tectonic and count its pages")
async def compile_resume(ctx, tex: str):
    from app.tailor import compile as tex_compile
    return await asyncio.to_thread(tex_compile.compile_tex, tex)


@tool("propose_action", "Propose an outward action (it only runs after review, policy checks and your approval)")
async def propose_action(ctx, kind: str, payload: dict, idempotency_key: str):
    from app.core import actions
    if kind not in ctx.spec.action_kinds:
        raise ToolDenied(f"{ctx.spec.id} may not propose {kind}")
    return await asyncio.to_thread(actions.propose, ctx.user_id, kind, payload, agent=ctx.spec.id,
                                   idempotency_key=idempotency_key, case_id=ctx.case_id)


# --- Recon (Day 6): public lookups only; nothing here contacts anyone -------------------------------

@tool("search_people", "Search public LinkedIn results (Brave Search) for people at a company")
async def search_people(ctx, company: str, query: str, role_class: str = ""):
    from app.recon import people
    from app.services import brave
    results = await brave.web_search(query, goggles=brave.LINKEDIN_ONLY, count=10, extra_snippets=True)
    found = []
    for r in results:
        person = people.parse_result(r.url, r.title, [r.description, *r.extra_snippets], company)
        if person:
            found.append(person.__dict__)
    return {"results": len(results), "people": found}


@tool("search_pay", "Search public pay data for a role (Brave Search); returns result snippets as numbered sources")
async def search_pay(ctx, query: str):
    from app.services import brave
    results = await brave.web_search(query, count=8, extra_snippets=True)
    return {"results": [{"url": r.url, "title": r.title, "text": " ".join([r.description, *r.extra_snippets])[:2500]}
                        for r in results]}


@tool("find_work_email", "Find a verified work email with Hunter (only when HUNTER_API_KEY is set)")
async def find_work_email(ctx, domain: str, name: str):
    from app.recon import emails
    return {"email": await emails.hunter_find(domain, name)}


@tool("lookup_handles", "Find a person's GitHub and X handles from their public GitHub profile")
async def lookup_handles(ctx, name: str, company: str):
    from app.recon import handles
    found = await handles.lookup(name, company)
    return found.__dict__ if found else None


@tool("save_contact", "Save or merge one person in your contacts (never overwrites what you typed)")
async def save_contact(ctx, **fields):
    from app.core import contacts
    saved = await asyncio.to_thread(contacts.upsert, ctx.user_id, **fields)
    return {"id": saved["id"], "created": saved["created"]}


# --- Answerer (Day 7) ------------------------------------------------------------------------------

@tool("search_answers", "Search your answer bank for saved answers to a similar question")
async def search_answers(ctx, question: str):
    from app.answers import bank
    hits, vectors = await asyncio.to_thread(bank.search, ctx.user_id, question)
    return {"vectors": vectors, "hits": [h.__dict__ for h in hits]}
