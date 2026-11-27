"""Agent specs: every expert, built-in or custom, is data (plan section 3).

A spec is validated before it can run: tools must exist in the registry, action kinds must
exist in policy.yaml (custom agents can never add kinds or relax policy), budgets must stay
under the per-case caps, and routine-triggered (background) experts get read-only tools only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from app.core.policy import Policy, load_policy

BUILTIN = Path(__file__).with_name("builtin.yaml")
ARTIFACT_KINDS = {"resume_version", "company_brief", "comp_report", "contact_list", "draft", "answer_set", "invite_set", "dm_set",
                  "interview_prep", "case"}


class SpecError(ValueError):
    pass


class ModelChoice(BaseModel):
    provider: Literal["default", "groq", "ollama", "none"] = "default"
    model: str = ""
    fallback: str = ""
    task: Literal["quality", "light"] = "quality"


class AgentSpec(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,39}$")
    name: str = Field(min_length=1, max_length=60)
    role: str = Field(default="", max_length=120)
    description: str = ""
    instructions: str = ""
    policy_notes: str = ""
    model: ModelChoice = ModelChoice()
    tools: list[str] = []
    inputs: list[str] = []
    outputs: list[str] = []
    triggers: list[dict] = []
    action_kinds: list[str] = []
    budgets: dict[str, float] = {}
    autonomy: dict = {}
    status: Literal["active", "paused", "draft"] = "active"
    owner: Literal["builtin", "user"] = "builtin"

    @field_validator("budgets")
    @classmethod
    def _budget_units(cls, value):
        unknown = set(value) - {"steps", "tokens", "seconds"}
        if unknown or any(v <= 0 for v in value.values()):
            raise ValueError(f"budgets take positive steps/tokens/seconds only (got {sorted(value)})")
        return value

    @property
    def background(self) -> bool:
        return any(t.get("kind") == "routine" for t in self.triggers)

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True).encode()).hexdigest()


def validate(spec: AgentSpec, policy: Policy | None = None) -> AgentSpec:
    """Refuse a spec that could do more than the registry, policy and budgets allow."""
    from app.experts.tools import REGISTRY
    policy = policy or load_policy()
    unknown = [t for t in spec.tools if t not in REGISTRY]
    if unknown:
        raise SpecError(f"{spec.id}: unknown tools {unknown}")
    kinds = [k for k in spec.action_kinds if k not in policy.action_modes]
    if kinds:
        raise SpecError(f"{spec.id}: action kinds not in policy.yaml {kinds}")
    never = [k for k in spec.action_kinds if policy.action_modes[k] == "never"]
    if never:
        raise SpecError(f"{spec.id}: may not propose never-kinds {never}")
    outputs = [o for o in spec.outputs if o not in ARTIFACT_KINDS]
    if outputs:
        raise SpecError(f"{spec.id}: unknown outputs {outputs}")
    over = [u for u, v in spec.budgets.items() if v > policy.budgets["per_case"].get(u, v)]
    if over:
        raise SpecError(f"{spec.id}: budgets above the per-case caps in policy.yaml {over}")
    if spec.background:
        writers = [t for t in spec.tools if not REGISTRY[t].background_ok]
        if writers:
            raise SpecError(f"{spec.id}: background experts get read-only tools only; remove {writers}")
    return spec


def builtin_specs(policy: Policy | None = None) -> dict[str, AgentSpec]:
    raw = yaml.safe_load(BUILTIN.read_text(encoding="utf-8"))
    specs = {}
    for item in raw:
        spec = validate(AgentSpec.model_validate(item), policy)
        if spec.id in specs:
            raise SpecError(f"duplicate expert id {spec.id}")
        specs[spec.id] = spec
    return specs


def sync_builtins(db, policy: Policy | None = None) -> int:
    """Upsert built-in specs into agent_spec. A status set by the owner (paused) is kept."""
    count = 0
    for spec in builtin_specs(policy).values():
        data = spec.model_dump()
        db.fetch("""insert into public.agent_spec (id, owner, name, role, description, instructions, policy_notes, model,
                        tools, inputs, outputs, triggers, action_kinds, budgets, autonomy, status, spec_sha256)
                    values (%s, 'builtin', %s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s::jsonb, %s::jsonb, %s, %s)
                    on conflict (id) do update set name = excluded.name, role = excluded.role,
                        description = excluded.description, instructions = excluded.instructions,
                        policy_notes = excluded.policy_notes, model = excluded.model, tools = excluded.tools,
                        inputs = excluded.inputs, outputs = excluded.outputs, triggers = excluded.triggers,
                        action_kinds = excluded.action_kinds, budgets = excluded.budgets, autonomy = excluded.autonomy,
                        status = case when public.agent_spec.status = 'paused' and excluded.status = 'active'
                                      then 'paused' else excluded.status end,
                        version = public.agent_spec.version + (public.agent_spec.spec_sha256 <> excluded.spec_sha256)::int,
                        spec_sha256 = excluded.spec_sha256, updated_at = now()""",
                 [spec.id, spec.name, spec.role, spec.description, spec.instructions, spec.policy_notes,
                  json.dumps(data["model"]), spec.tools, json.dumps(spec.inputs), json.dumps(spec.outputs),
                  json.dumps(spec.triggers), spec.action_kinds, json.dumps(spec.budgets), json.dumps(spec.autonomy),
                  spec.status, spec.digest()])
        count += 1
    return count


def load_spec(db, agent_id: str) -> AgentSpec | None:
    """The live spec (database row, so a paused status applies), validated again on load."""
    rows = db.fetch("""select to_jsonb(s) from public.agent_spec s where id = %s""", [agent_id])
    if not rows:
        return None
    row = rows[0][0]
    fields = {k: row[k] for k in AgentSpec.model_fields if k in row}
    return validate(AgentSpec.model_validate(fields))
