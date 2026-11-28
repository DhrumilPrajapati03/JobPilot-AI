"""Experts: the roster (with each expert's live state), one expert's detail, manual runs and
routines. State names match the avatar states in plan section 6.2."""
import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from app.core.policy import load_policy
from app.db import get_db
from app.experts import runtime
from app.services.auth import CurrentUser, get_current_user
from app.services.runs import durable_enabled

router = APIRouter()
DONE_FOR = timedelta(minutes=10)
FAILED_FOR = timedelta(hours=24)


def _state(spec: dict, run: dict | None, step: dict | None, pending: int, kill_switch: bool, now: datetime) -> str:
    """idle | acknowledged | working | waiting_approval | blocked | failed | done | paused | draft"""
    if spec["status"] == "draft":
        return "draft"
    if spec["status"] == "paused" or kill_switch:
        return "paused"
    if run and run["status"] == "running":
        return "working"
    if run and run["status"] in ("queued", "retry_wait"):
        return "acknowledged"
    if pending:
        return "waiting_approval"
    if step and step["kind"] == "blocked" and now - datetime.fromisoformat(step["at"]) < FAILED_FOR:
        return "blocked"
    if run and run["status"] == "failed" and now - datetime.fromisoformat(run["updated_at"]) < FAILED_FOR:
        return "failed"
    if run and run["status"] == "succeeded" and now - datetime.fromisoformat(run["updated_at"]) < DONE_FOR:
        return "done"
    return "idle"


def roster(user_id: str) -> list[dict]:
    db = get_db(user_id)
    specs = [r[0] for r in db.fetch("""select jsonb_build_object('id', id, 'name', name, 'role', role, 'status', status, 'owner', owner)
                                       from public.agent_spec order by array_position(array['supervisor','scout','researcher',
                                       'comp_analyst','tailor','answerer','applicant','recon','connector','email_outreach',
                                       'dm_outreach','inbox','interview_buddy','reviewer'], id), id""")]
    runs = {r[0]: r[1] for r in db.fetch("""select distinct on (inputs->>'agent') inputs->>'agent',
                                              jsonb_build_object('status', status, 'updated_at', updated_at, 'case_id', case_id)
                                            from public.agent_runs where user_id = %s::uuid and kind = 'agent'
                                            order by inputs->>'agent', updated_at desc""", [user_id])}
    steps = {r[0]: r[1] for r in db.fetch("""select distinct on (agent) agent,
                                               jsonb_build_object('kind', kind, 'summary', summary, 'at', at, 'case_id', case_id)
                                             from public.run_step where user_id = %s::uuid order by agent, at desc, id desc""", [user_id])}
    pending = dict(db.fetch("""select agent, count(*) from public.action where user_id = %s::uuid
                               and status in ('proposed', 'reviewed') group by agent""", [user_id]))
    try:
        kill = load_policy().kill_switch
    except Exception:
        kill = False
    now = datetime.now(timezone.utc)
    out = []
    for spec in specs:
        run, step = runs.get(spec["id"]), steps.get(spec["id"])
        state = _state(spec, run, step, pending.get(spec["id"], 0), kill, now)
        out.append({**spec, "state": state, "step": step["summary"] if step else "",
                    "step_at": step["at"] if step else None, "approvals": pending.get(spec["id"], 0)})
    return out


@router.get("")
async def list_experts(user: CurrentUser = Depends(get_current_user)):
    return {"experts": await asyncio.to_thread(roster, user.id)}


@router.get("/{agent_id}")
async def expert_detail(agent_id: str, user: CurrentUser = Depends(get_current_user)):
    def load():
        db = get_db(user.id)
        spec = db.fetch("""select to_jsonb(s) - 'user_id' - 'spec_sha256' from public.agent_spec s where id = %s""", [agent_id])
        if not spec:
            return None
        routines = [r[0] for r in db.fetch("""select to_jsonb(r) - 'user_id' from public.routine r
                                             where user_id = %s::uuid and agent = %s order by key""", [user.id, agent_id])]
        steps = [r[0] for r in db.fetch("""select jsonb_build_object('id', id, 'kind', kind, 'name', name, 'summary', summary,
                                             'detail', detail, 'case_id', case_id, 'at', at, 'tokens', tokens)
                                           from public.run_step where user_id = %s::uuid and agent = %s
                                           order by at desc, id desc limit 50""", [user.id, agent_id])]
        return {"spec": spec[0][0], "routines": routines, "steps": steps}
    detail = await asyncio.to_thread(load)
    if detail is None:
        raise HTTPException(404, "Unknown expert")
    return detail


def _require_worker():
    if not durable_enabled():
        raise HTTPException(503, "Experts run on the background worker. Start the stack with docker compose up -d.")


class ResearchIn(BaseModel):
    urls: list[HttpUrl] = Field(default_factory=list, max_length=4)


@router.post("/scout/run", status_code=202)
async def run_scout(user: CurrentUser = Depends(get_current_user)):
    _require_worker()
    run = await asyncio.to_thread(runtime.enqueue_expert, user.id, "scout", trigger="manual")
    return {"run_id": run["id"]}


@router.post("/cases/{case_id}/research", status_code=202)
async def research_case(case_id: str, body: ResearchIn, user: CurrentUser = Depends(get_current_user)):
    _require_worker()
    try:
        run = await asyncio.to_thread(runtime.enqueue_expert, user.id, "researcher", case_id=case_id, trigger="manual",
                                      urls=[str(u) for u in body.urls])
    except Exception as exc:
        if "case_not_found" in str(exc):
            raise HTTPException(404, "Case not found") from None
        raise
    return {"run_id": run["id"]}


@router.post("/cases/{case_id}/recon", status_code=202)
async def recon_case(case_id: str, user: CurrentUser = Depends(get_current_user)):
    """Find the people at the case's company again (public sources; caps from policy.yaml)."""
    _require_worker()
    try:
        run = await asyncio.to_thread(runtime.enqueue_expert, user.id, "recon", case_id=case_id, trigger="manual")
    except Exception as exc:
        if "case_not_found" in str(exc):
            raise HTTPException(404, "Case not found") from None
        raise
    return {"run_id": run["id"]}


@router.post("/cases/{case_id}/prep", status_code=202)
async def prep_case(case_id: str, user: CurrentUser = Depends(get_current_user)):
    """Ask Interview Buddy for a prep pack for this case."""
    _require_worker()
    try:
        run = await asyncio.to_thread(runtime.enqueue_expert, user.id, "interview_buddy", case_id=case_id, trigger="manual")
    except Exception as exc:
        if "case_not_found" in str(exc):
            raise HTTPException(404, "Case not found") from None
        raise
    return {"run_id": run["id"]}


@router.post("/cases/{case_id}/connect", status_code=202)
async def connect_case(case_id: str, user: CurrentUser = Depends(get_current_user)):
    """Ask Connector for LinkedIn invitations to the people Recon suggested (proposals only)."""
    _require_worker()
    try:
        run = await asyncio.to_thread(runtime.enqueue_expert, user.id, "connector", case_id=case_id, trigger="manual")
    except Exception as exc:
        if "case_not_found" in str(exc):
            raise HTTPException(404, "Case not found") from None
        raise
    return {"run_id": run["id"]}


@router.post("/cases/{case_id}/tailor", status_code=202)
async def tailor_case(case_id: str, user: CurrentUser = Depends(get_current_user)):
    """Ask Tailor for a new resume version of this case (each run is a new, reviewable version)."""
    _require_worker()
    try:
        run = await asyncio.to_thread(runtime.enqueue_expert, user.id, "tailor", case_id=case_id, trigger="manual")
    except Exception as exc:
        if "case_not_found" in str(exc):
            raise HTTPException(404, "Case not found") from None
        raise
    return {"run_id": run["id"]}


@router.post("/cases/{case_id}/supervise", status_code=202)
async def supervise_case(case_id: str, user: CurrentUser = Depends(get_current_user)):
    _require_worker()
    try:
        run = await asyncio.to_thread(runtime.enqueue_expert, user.id, "supervisor", case_id=case_id, trigger="manual")
    except Exception as exc:
        if "case_not_found" in str(exc):
            raise HTTPException(404, "Case not found") from None
        raise
    return {"run_id": run["id"]}


class RoutineIn(BaseModel):
    enabled: bool


@router.patch("/routines/{routine_id}")
async def toggle_routine(routine_id: str, body: RoutineIn, user: CurrentUser = Depends(get_current_user)):
    rows = await asyncio.to_thread(get_db(user.id).fetch, """update public.routine set enabled = %s
        where id = %s::uuid and user_id = %s::uuid returning key, enabled""", [body.enabled, routine_id, user.id])
    if not rows:
        raise HTTPException(404, "Routine not found")
    return {"key": rows[0][0], "enabled": rows[0][1]}


# --- MVP: paste a JD, get a tailored PDF and a recruiter email to approve -------------------

class QuickCaseIn(BaseModel):
    jd_text: str = Field(default="", max_length=60_000)
    source_url: HttpUrl | None = None
    company: str = Field(default="", max_length=200)
    role: str = Field(default="", max_length=200)
    recipient_email: str = Field(default="", max_length=254)
    recipient_name: str = Field(default="", max_length=120)


class RecipientIn(BaseModel):
    """An address you type, or a contact from the case's contact list (its stored address)."""
    email: str = Field(default="", max_length=254)
    name: str = Field(default="", max_length=120)
    contact_id: str | None = Field(default=None, max_length=36)


@router.post("/cases/quick", status_code=202)
async def quick_case(body: QuickCaseIn, user: CurrentUser = Depends(get_current_user)):
    """Paste a job description (or its URL): Researcher -> Tailor -> Email Outreach -> Reviewer -> your approval."""
    _require_worker()
    from app.agents.jd_parser import JDParserAgent
    from app.core import cases as case_mod
    from app.experts.email_outreach import set_recipient
    from app.experts.reviewer import EMAIL
    if body.recipient_email and not EMAIL.match(body.recipient_email.strip()):
        raise HTTPException(422, "The recipient email doesn't look valid.")
    if not body.jd_text.strip() and not body.source_url:
        raise HTTPException(422, "Paste the job description or its URL.")
    company, role, text, analysis = body.company.strip(), body.role.strip(), body.jd_text.strip(), None
    if not (company and role and text):
        parser = JDParserAgent()
        analysis = await parser.parse(jd_url=str(body.source_url) if body.source_url and not text else None, jd_text=text or None)
        text = text or getattr(parser, "source_text", "")
        company, role = company or analysis.company, role or analysis.role
    case = await asyncio.to_thread(case_mod.create_case, user.id, company=company, role=role, jd_text=text,
                                   source_url=str(body.source_url or ""), actor="user")
    if analysis is not None:
        await asyncio.to_thread(get_db(user.id).fetch, "update public.job_case set jd_analysis = %s where id = %s::uuid",
                                [analysis.model_dump_json(), case["id"]])
    if body.recipient_email:
        await asyncio.to_thread(set_recipient, user.id, case["id"], body.recipient_email, body.recipient_name, company)
    run = await asyncio.to_thread(runtime.enqueue_expert, user.id, "supervisor", case_id=case["id"],
                                  key=f"supervisor:{case['id']}:created", trigger="case_created")
    return {"case_id": case["id"], "company": company, "role": role, "run_id": run["id"]}


@router.post("/cases/{case_id}/recipient", status_code=202)
async def add_recipient(case_id: str, body: RecipientIn, user: CurrentUser = Depends(get_current_user)):
    """Set who the email goes to; Email Outreach drafts again for that person."""
    _require_worker()
    from app.core import cases as case_mod
    from app.core import contacts
    from app.experts.email_outreach import set_recipient
    from app.experts.reviewer import EMAIL
    case = await asyncio.to_thread(case_mod.get_case, user.id, case_id)
    if case is None:
        raise HTTPException(404, "Case not found")
    email, name, contact_id = body.email.strip(), body.name, None
    if body.contact_id:
        contact = await asyncio.to_thread(contacts.get_contact, user.id, body.contact_id)
        if contact is None:
            raise HTTPException(404, "Contact not found")
        if contact["do_not_contact"]:
            raise HTTPException(409, "That contact is marked do not contact.")
        email, name, contact_id = email or contact["email"], name or contact["name"], contact["id"]
        if not email:
            raise HTTPException(422, "That contact has no email address yet; add one first.")
        if email.lower() != contact["email"]:
            await asyncio.to_thread(contacts.update_contact, user.id, contact_id, {"email": email})
    if not EMAIL.match(email):
        raise HTTPException(422, "The recipient email doesn't look valid.")
    await asyncio.to_thread(set_recipient, user.id, case_id, email, name, case.get("company") or "", contact_id=contact_id)
    run = await asyncio.to_thread(runtime.enqueue_expert, user.id, "email_outreach", case_id=case_id, trigger="manual")
    return {"run_id": run["id"]}


@router.get("/connections/status")
async def connections_status(user: CurrentUser = Depends(get_current_user)):
    """Gmail and Telegram, as status only (never secrets)."""
    from app.config import settings
    from app.courier import connections
    conn = await asyncio.to_thread(connections.get_google, user.id)
    return {"gmail": None if conn is None else {"status": conn.status, "account": conn.account_email,
                                                 "expires_hint": conn.expires_hint,
                                                 "can_send": any(s.endswith("gmail.send") for s in conn.scopes)},
            "telegram": {"configured": bool(settings.TELEGRAM_BOT_TOKEN), "linked": bool(settings.TELEGRAM_CHAT_ID)}}


# --- custom experts (Day 14): write, preview, dry-run, activate ----------------------------------

def _custom(user_id: str, agent_id: str):
    from app.experts import spec as spec_mod
    rows = get_db(user_id).fetch("""select to_jsonb(s) from public.agent_spec s where id = %s and owner = 'user'
                                    and user_id = %s::uuid""", [agent_id, user_id])
    if not rows:
        raise HTTPException(404, "No custom expert with that id")
    row = rows[0][0]
    return spec_mod.AgentSpec.model_validate({k: row[k] for k in spec_mod.AgentSpec.model_fields if k in row})


def _save_custom(user_id: str, spec) -> None:
    import json
    get_db(user_id).fetch("""
        insert into public.agent_spec (id, owner, user_id, name, role, description, instructions, policy_notes, model, tools,
                                       outputs, triggers, action_kinds, budgets, autonomy, status, spec_sha256)
        values (%s, 'user', %s::uuid, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s::jsonb, %s, %s::jsonb, %s::jsonb, %s, %s)
        on conflict (id) do update set name = excluded.name, role = excluded.role, description = excluded.description,
            instructions = excluded.instructions, tools = excluded.tools, budgets = excluded.budgets, autonomy = excluded.autonomy,
            status = excluded.status, version = public.agent_spec.version + (public.agent_spec.spec_sha256 <> excluded.spec_sha256)::int,
            spec_sha256 = excluded.spec_sha256, updated_at = now()
        where public.agent_spec.owner = 'user' and public.agent_spec.user_id = excluded.user_id""",
        [spec.id, user_id, spec.name, spec.role, spec.description, spec.instructions, spec.policy_notes,
         json.dumps(spec.model.model_dump()), spec.tools, json.dumps(spec.outputs), json.dumps(spec.triggers), spec.action_kinds,
         json.dumps(spec.budgets), json.dumps(spec.autonomy), spec.status, spec.digest()])


def _view(spec) -> dict:
    from app.experts import custom
    policy = load_policy()
    return {"spec": spec.model_dump(), "problems": custom.problems(spec, policy), "preview": custom.preview(spec, policy),
            "dry_run_ok_at": (spec.autonomy or {}).get("dry_run_ok_at")}


@router.get("/custom/templates")
async def custom_templates(user: CurrentUser = Depends(get_current_user)):
    from app.experts import custom
    return {"templates": [{"id": k, **v} for k, v in custom.TEMPLATES.items()], "tools": custom.TOOL_WORDS}


class NewCustomIn(BaseModel):
    template: str | None = Field(default=None, max_length=40)
    name: str = Field(default="", max_length=60)


@router.post("/custom", status_code=201)
async def create_custom(body: NewCustomIn, user: CurrentUser = Depends(get_current_user)):
    from app.experts import custom
    if body.template and body.template not in custom.TEMPLATES:
        raise HTTPException(422, "Unknown template")
    base = custom.slug(body.name or custom.TEMPLATES.get(body.template or "", {}).get("name", "expert"))

    def make():
        taken = {r[0] for r in get_db(user.id).fetch("select id from public.agent_spec where id like %s", [base + "%"])}
        agent_id = next(f"{base}{'' if i == 0 else f'_{i}'}" for i in range(100) if f"{base}{'' if i == 0 else f'_{i}'}" not in taken)
        spec = custom.new_spec(agent_id, body.template, body.name)
        _save_custom(user.id, spec)
        return _view(spec)
    return await asyncio.to_thread(make)


@router.get("/custom/{agent_id}")
async def get_custom(agent_id: str, user: CurrentUser = Depends(get_current_user)):
    return _view(await asyncio.to_thread(_custom, user.id, agent_id))


class EditCustomIn(BaseModel):
    name: str = Field(max_length=60)
    role: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=600)
    instructions: str = Field(default="", max_length=4000)
    tools: list[str] = Field(default_factory=list, max_length=10)


@router.put("/custom/{agent_id}")
async def edit_custom(agent_id: str, body: EditCustomIn, user: CurrentUser = Depends(get_current_user)):
    """Any edit puts it back to draft: run it dry again before it can be used."""
    def work():
        spec = _custom(user.id, agent_id)
        spec = spec.model_copy(update={**body.model_dump(), "status": "draft",
                                       "autonomy": {k: v for k, v in (spec.autonomy or {}).items() if k != "dry_run_ok_at"}})
        _save_custom(user.id, spec)
        return _view(spec)
    return await asyncio.to_thread(work)


class DryRunIn(BaseModel):
    case_id: str = Field(min_length=36, max_length=36)


@router.post("/custom/{agent_id}/dry-run")
async def dry_run_custom(agent_id: str, body: DryRunIn, user: CurrentUser = Depends(get_current_user)):
    """Run it on a real case and show what it would write. Nothing is saved on the case."""
    from app.experts import custom
    from app.experts.runtime import ExpertContext
    from app.services.runs import PermanentRunError
    spec = await asyncio.to_thread(_custom, user.id, agent_id)
    ctx = ExpertContext(user.id, spec, body.case_id, {})
    try:
        result = await asyncio.wait_for(custom.run(ctx, dry_run=True), timeout=240)
    except PermanentRunError as exc:
        raise HTTPException(422, str(exc)) from None
    except asyncio.TimeoutError:
        raise HTTPException(504, "The dry run took too long; try again.") from None
    spec = spec.model_copy(update={"autonomy": {**(spec.autonomy or {}), "dry_run_ok_at": custom.now_iso()}})
    await asyncio.to_thread(_save_custom, user.id, spec)
    return {**result, **_view(spec)}


@router.post("/custom/{agent_id}/activate")
async def activate_custom(agent_id: str, user: CurrentUser = Depends(get_current_user)):
    from app.experts import custom

    def work():
        spec = _custom(user.id, agent_id)
        issues = custom.problems(spec, load_policy())
        if issues:
            raise HTTPException(422, " ".join(issues))
        if not custom.dry_run_recorded(spec):
            raise HTTPException(409, "Run it dry on a case first, so you've seen what it writes.")
        spec = spec.model_copy(update={"status": "active"})
        _save_custom(user.id, spec)
        return _view(spec)
    return await asyncio.to_thread(work)


@router.post("/custom/{agent_id}/pause")
async def pause_custom(agent_id: str, user: CurrentUser = Depends(get_current_user)):
    def work():
        spec = _custom(user.id, agent_id).model_copy(update={"status": "paused"})
        _save_custom(user.id, spec)
        return _view(spec)
    return await asyncio.to_thread(work)


@router.delete("/custom/{agent_id}", status_code=204)
async def delete_custom(agent_id: str, user: CurrentUser = Depends(get_current_user)):
    await asyncio.to_thread(_custom, user.id, agent_id)
    await asyncio.to_thread(get_db(user.id).fetch, "delete from public.agent_spec where id = %s and owner = 'user' and user_id = %s::uuid",
                            [agent_id, user.id])


@router.post("/cases/{case_id}/run/{agent_id}", status_code=202)
async def run_custom(case_id: str, agent_id: str, user: CurrentUser = Depends(get_current_user)):
    """Run an active custom expert on a case (its note lands on the case)."""
    _require_worker()
    spec = await asyncio.to_thread(_custom, user.id, agent_id)
    if spec.status != "active":
        raise HTTPException(409, f"{spec.name} is {spec.status}; activate it first.")
    run = await asyncio.to_thread(runtime.enqueue_expert, user.id, agent_id, case_id=case_id, trigger="manual")
    return {"run_id": run["id"]}
