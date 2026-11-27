"""Supervisor: a small deterministic graph that moves a case between experts (plan section 2.1).

No model calls. Each route says which expert does the next piece of work and how to tell it
is done (an artifact exists). Supervisor walks the routes in order:

    found --Researcher(company_brief)--> researched --Recon(contact_list)--> researched
          --Tailor(resume_version)--> tailored --Email Outreach(draft)--> ready

Recon runs before Email Outreach so the draft can go to the recruiter it found.

* A finished route advances the case stage (never backwards).
* The first unfinished route is handed to its expert, unless that expert is paused or not
  built yet; then Supervisor posts one "waiting for …" event and stops.
* Budgets are checked by the runtime before Supervisor runs; a case over budget stops here.
* Imported (legacy) and closed cases are never routed.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.core import cases
from app.db import get_db

STAGE_ORDER = {s: i for i, s in enumerate(cases.STAGES)}
ROUTABLE_STAGES = ("found", "researched", "tailored")


@dataclass(frozen=True)
class Route:
    name: str
    agent: str
    produces: str          # artifact kind that marks the route done
    stage_after: str
    ask: str               # plain words for the hand-off line


GRAPH: tuple[Route, ...] = (
    Route("research", "researcher", "company_brief", "researched", "research {company}"),
    Route("comp", "comp_analyst", "comp_report", "researched", "research pay for {role} at {company}"),
    Route("recon", "recon", "contact_list", "researched", "find the people at {company}"),
    Route("tailor", "tailor", "resume_version", "tailored", "tailor your resume for {role} at {company}"),
    Route("outreach", "email_outreach", "draft", "ready", "draft outreach to {company}"),
    Route("connect", "connector", "invite_set", "ready", "propose LinkedIn invitations at {company}"),
    Route("refer", "dm_outreach", "dm_set", "ready", "ask your connections at {company} for a referral"),
)


@dataclass
class Decision:
    action: str            # 'route' | 'wait' | 'done' | 'skip'
    route: Route | None = None
    stage: str | None = None
    reason: str = ""


def decide(case: dict, artifact_kinds: set[str], active_agents: set[str]) -> Decision:
    """Pure routing decision for one case (unit-tested without a database)."""
    if case.get("legacy") or case.get("status") != "open" or case.get("stage") not in ROUTABLE_STAGES:
        return Decision("skip", reason="not a case Supervisor routes")
    stage = case["stage"]
    for route in GRAPH:
        if route.produces in artifact_kinds:
            if STAGE_ORDER[route.stage_after] > STAGE_ORDER[stage]:
                stage = route.stage_after
            continue
        if route.agent not in active_agents:
            return Decision("wait", route, stage, f"waiting for {route.agent.replace('_', ' ').title()}")
        return Decision("route", route, stage)
    return Decision("done", None, stage, "every route is done")


def _facts(user_id: str, case_id: str) -> tuple[dict | None, set[str], set[str]]:
    db = get_db(user_id)
    case = cases.get_case(user_id, case_id)
    if case is None:
        return None, set(), set()
    kinds = {a["kind"] for a in case["artifacts"] if not a.get("legacy")}
    active = {r[0] for r in db.fetch("select id from public.agent_spec where status = 'active'")}
    return case, kinds, active


def hand_off(user_id: str, case_id: str, agent: str, reason: str) -> dict:
    """Queue `agent` on the case, once per route attempt (idempotent per artifact count)."""
    from app.experts.runtime import enqueue_expert
    attempt = get_db(user_id).fetch("""select count(*) from public.case_event where case_id = %s::uuid
                                       and kind = 'handoff' and data->>'agent' = %s""", [case_id, agent])[0][0]
    run = enqueue_expert(user_id, agent, case_id=case_id, key=f"{agent}:{case_id}:{attempt + 1}", trigger="routed")
    cases.add_event(user_id, case_id, "handoff", actor="agent", actor_name="supervisor", summary=reason,
                    data={"agent": agent, "run_id": run["id"], "attempt": attempt + 1})
    return {"run_id": run["id"], "agent": agent}


async def run(ctx) -> dict:
    case_id = ctx.case_id
    if not case_id:
        return {"skipped": "Supervisor needs a case"}
    case, kinds, active = await asyncio.to_thread(_facts, ctx.user_id, case_id)
    if case is None:
        return {"skipped": "case not found"}
    decision = decide(case, kinds, active)
    words = {"route": f"Next for {case.get('company') or 'this case'}: "
                      f"{decision.route.agent.replace('_', ' ').title() if decision.route else ''}",
             "wait": f"{case.get('company') or 'This case'} is {decision.reason}",
             "done": f"{case.get('company') or 'This case'}: every step is done",
             "skip": "Not a case Supervisor routes"}[decision.action]
    await ctx.log.add("route", decision.action, words,
                      {"stage": case["stage"], "artifacts": sorted(kinds), "route": decision.route.name if decision.route else None})
    if decision.action == "skip":
        return {"action": "skip"}
    if decision.stage and decision.stage != case["stage"]:
        await asyncio.to_thread(cases.set_stage, ctx.user_id, case_id, decision.stage, actor="agent", actor_name="supervisor")
    if decision.action == "done":
        return {"action": "done", "stage": decision.stage}
    route = decision.route
    ask = route.ask.format(company=case.get("company") or "the company", role=case.get("role") or "this role")
    if decision.action == "wait":
        last = case["events"][-1] if case["events"] else {}
        if not (last.get("kind") == "waiting" and (last.get("data") or {}).get("agent") == route.agent):
            await asyncio.to_thread(cases.add_event, ctx.user_id, case_id, "waiting", actor="agent", actor_name="supervisor",
                                    summary=f"Next: {ask}. Waiting for {route.agent.replace('_', ' ').title()}.",
                                    data={"agent": route.agent})
        return {"action": "wait", "agent": route.agent, "stage": decision.stage}
    handed = await ctx.tools.call("route_case", f"Asked {route.agent.replace('_', ' ').title()} to {ask}", case_id=case_id,
                                  agent=route.agent, reason=f"Supervisor asked {route.agent.replace('_', ' ').title()} to {ask}")
    return {"action": "route", **handed}
