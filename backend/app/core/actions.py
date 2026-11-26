r"""Actions: agents propose, Dhrumil approves, Courier executes frozen payloads (plan section 4).

State machine (also enforced by a trigger in the database, migrations/0003):

    proposed -> reviewed -> approved -> executing -> provider_accepted -> delivered
                                                  \-> send_unknown / failed
    any pre-execution state -> cancelled; policy refusals -> blocked

* An approval is bound to the payload's sha256. Editing a payload sends it back to
  `proposed` and clears the approval, so an edited draft is never sent unapproved.
* `start_execution` is Courier's only door. It re-checks policy (kill switch, caps,
  quiet hours, cooldowns) under a per-kind lock so two workers cannot both slip under a cap.
* Every side effect carries the action's idempotency key; `send_unknown` is never retried
  blindly.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from psycopg.types.json import Jsonb

from app.core import policy as policy_mod
from app.core.policy import Policy, Usage, Verdict
from app.db import get_db

TERMINAL = {"delivered", "failed", "cancelled"}
CHANNELS = {"web", "telegram", "extension", "auto", "api"}
_COLUMNS = ("id, user_id, case_id, kind, mode, agent, payload, payload_sha256, revision, status, "
            "idempotency_key, review, block_reason, provider_ref, error, executing_at, created_at, updated_at")


class ActionError(ValueError):
    """A request that the state machine refuses. `code` is stable for the API."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class CircuitOpen(ActionError):
    pass


def payload_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class Gate:
    """Result of asking Courier's door: run it now, wait, or refuse."""
    action: dict
    verdict: Verdict

    @property
    def run(self) -> bool:
        return self.verdict.allowed


def _one(conn, query: str, params) -> dict | None:
    # A CTE, not a subquery, so INSERT/UPDATE ... RETURNING work too.
    row = conn.execute(f"with a as ({query}) select to_jsonb(a) from a", params).fetchone()
    return row[0] if row else None


def _locked(conn, user_id: str, action_id: str) -> dict:
    row = _one(conn, f"select {_COLUMNS} from public.action where id = %s::uuid and user_id = %s::uuid for update",
               [action_id, user_id])
    if row is None:
        raise ActionError("action_not_found", "Action not found.")
    return row


def _set_status(conn, action_id: str, status: str, **fields) -> dict:
    sets = ["status = %s"] + [f"{k} = %s" for k in fields]
    values = [status] + [Jsonb(v) if isinstance(v, (dict, list)) else v for v in fields.values()]
    return _one(conn, f"update public.action set {', '.join(sets)} where id = %s::uuid returning {_COLUMNS}",
                values + [action_id])


def blocked_recently(conn, user_id: str, case_id: str | None, policy: Policy, now: datetime) -> int:
    rule = policy.budgets["refused_actions_circuit"]
    since = now - timedelta(hours=rule["window_hours"])
    row = conn.execute("""select count(*) from public.action where user_id = %s::uuid and status = 'blocked'
                          and case_id is not distinct from %s::uuid and updated_at >= %s""",
                       [user_id, case_id, since]).fetchone()
    return row[0]


def propose(user_id: str, kind: str, payload: dict, *, agent: str, idempotency_key: str,
            case_id: str | None = None, policy: Policy | None = None, now: datetime | None = None) -> dict:
    """Record a proposal. Unknown kinds raise; `never` kinds are stored as blocked.

    Replaying the same key with the same payload returns the original action; a
    different payload under the same key is a conflict.
    """
    policy = policy or policy_mod.load_policy()
    now = now or datetime.now(timezone.utc)
    mode = policy.mode_for(kind)  # raises UnknownActionKind
    if not isinstance(payload, dict):
        raise ActionError("invalid_payload", "An action payload must be a JSON object.")
    digest = payload_hash(payload)

    def work(conn):
        existing = _one(conn, f"select {_COLUMNS} from public.action where user_id = %s::uuid and idempotency_key = %s",
                        [user_id, idempotency_key])
        if existing:
            if existing["payload_sha256"] != digest or existing["kind"] != kind:
                raise ActionError("idempotency_key_conflict", "This idempotency key was used for a different action.")
            return existing
        rule = policy.budgets["refused_actions_circuit"]
        if blocked_recently(conn, user_id, case_id, policy, now) >= rule["max_blocked"]:
            raise CircuitOpen("circuit_open", "Too many refused actions on this case recently; the task is stopped.")
        status, reason = ("blocked", f"{kind} is 'never' in policy.yaml.") if mode == "never" else ("proposed", None)
        return _one(conn, f"""insert into public.action (user_id, case_id, kind, mode, agent, payload, payload_sha256,
                                  status, idempotency_key, block_reason)
                              values (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s) returning {_COLUMNS}""",
                    [user_id, case_id, kind, mode, agent, Jsonb(payload), digest, status, idempotency_key, reason])

    return get_db(user_id).run(work)


def review(user_id: str, action_id: str, *, ok: bool, notes: list[str] | None = None, reviewer: str = "reviewer") -> dict:
    """Reviewer's verdict: annotate and pass on, or block."""
    def work(conn):
        action = _locked(conn, user_id, action_id)
        if action["status"] != "proposed":
            raise ActionError("invalid_transition", f"Only proposed actions can be reviewed (this one is {action['status']}).")
        verdict = {"by": reviewer, "ok": ok, "notes": list(notes or []), "payload_sha256": action["payload_sha256"]}
        if ok:
            return _set_status(conn, action_id, "reviewed", review=verdict)
        return _set_status(conn, action_id, "blocked", review=verdict, block_reason="; ".join(notes or []) or "Reviewer blocked it.")

    return get_db(user_id).run(work)


def approve(user_id: str, action_id: str, *, payload_sha256: str, channel: str = "web", note: str = "") -> dict:
    """Approve exactly the payload Dhrumil saw. A stale hash (edited since) is refused."""
    if channel not in CHANNELS:
        raise ActionError("invalid_channel", "Unknown approval channel.")

    def work(conn):
        action = _locked(conn, user_id, action_id)
        if action["status"] == "approved" and action["payload_sha256"] == payload_sha256:
            return action
        if action["status"] != "reviewed":
            raise ActionError("invalid_transition", f"Only reviewed actions can be approved (this one is {action['status']}).")
        if action["mode"] not in policy_mod.EXECUTABLE:
            raise ActionError("not_approvable", f"{action['kind']} is '{action['mode']}' and cannot be approved.")
        if payload_sha256 != action["payload_sha256"]:
            raise ActionError("stale_payload", "The draft changed after you opened it. Review it again.")
        conn.execute("""insert into public.approval (action_id, user_id, decision, payload_sha256, channel, note)
                        values (%s::uuid, %s::uuid, 'approved', %s, %s, %s)""",
                     [action_id, user_id, payload_sha256, channel, note])
        return _set_status(conn, action_id, "approved")

    return get_db(user_id).run(work)


def reject(user_id: str, action_id: str, *, channel: str = "web", note: str = "") -> dict:
    if channel not in CHANNELS:
        raise ActionError("invalid_channel", "Unknown approval channel.")

    def work(conn):
        action = _locked(conn, user_id, action_id)
        if action["status"] not in ("proposed", "reviewed", "approved", "blocked"):
            raise ActionError("invalid_transition", f"A {action['status']} action can't be rejected.")
        conn.execute("""insert into public.approval (action_id, user_id, decision, payload_sha256, channel, note)
                        values (%s::uuid, %s::uuid, 'rejected', %s, %s, %s)""",
                     [action_id, user_id, action["payload_sha256"], channel, note])
        return _set_status(conn, action_id, "cancelled")

    return get_db(user_id).run(work)


def edit(user_id: str, action_id: str, payload: dict) -> dict:
    """Change a draft before it runs. The approval is cleared; it goes back through review."""
    if not isinstance(payload, dict):
        raise ActionError("invalid_payload", "An action payload must be a JSON object.")
    digest = payload_hash(payload)

    def work(conn):
        action = _locked(conn, user_id, action_id)
        if action["status"] not in ("proposed", "reviewed", "approved"):
            raise ActionError("payload_frozen", f"A {action['status']} action can't be edited.")
        if digest == action["payload_sha256"]:
            return action
        return _one(conn, f"""update public.action set payload = %s, payload_sha256 = %s, revision = revision + 1,
                                  status = 'proposed', review = '{{}}'::jsonb where id = %s::uuid returning {_COLUMNS}""",
                    [Jsonb(payload), digest, action_id])

    return get_db(user_id).run(work)


def _usage(conn, user_id: str, action: dict, policy: Policy, now: datetime) -> Usage:
    kind, payload = action["kind"], action["payload"]
    today, week = policy.day_start(now), policy.week_start(now)
    counts = conn.execute("""select count(*) filter (where executing_at >= %s), count(*) filter (where executing_at >= %s)
                             from public.action where user_id = %s::uuid and kind = %s and executing_at is not null
                             and id <> %s::uuid""", [today, week, user_id, kind, action["id"]]).fetchone()
    usage = Usage(executed_today=counts[0], executed_this_week=counts[1])
    company = str(payload.get("company") or "").strip().lower()
    if company:
        rows = conn.execute("""select distinct payload->>'contact_id' from public.action where user_id = %s::uuid
                               and executing_at is not null and lower(trim(payload->>'company')) = %s
                               and payload->>'contact_id' is not null and kind = any(%s)""",
                            [user_id, company, sorted(policy_mod.PEOPLE_KINDS)]).fetchall()
        usage.company_people = {r[0] for r in rows}
    contact = payload.get("contact_id")
    if contact:
        row = conn.execute("""select greatest(
                                (select max(executing_at) from public.action where user_id = %s::uuid and id <> %s::uuid
                                   and payload->>'contact_id' = %s and executing_at is not null),
                                (select max(sent_at) from public.contact_touch where user_id = %s::uuid
                                   and contact_id::text = %s))""",
                           [user_id, action["id"], str(contact), user_id, str(contact)]).fetchone()
        usage.last_touch_at = row[0]
    accepted = payload.get("accepted_at")
    if accepted:
        try:
            usage.accepted_at = datetime.fromisoformat(str(accepted).replace("Z", "+00:00"))
        except ValueError:
            usage.accepted_at = None
    return usage


def start_execution(user_id: str, action_id: str, *, policy: Policy | None = None, now: datetime | None = None) -> Gate:
    """Courier's door. Approved + policy allows it -> `executing` and the frozen payload is returned.

    When policy says no, the action stays approved (for quiet hours, with `retry_at`) or is
    blocked (caps, cooldowns, kill switch leave it approved so it can run later).
    """
    policy = policy or policy_mod.load_policy()
    now = now or datetime.now(timezone.utc)

    def work(conn):
        action = _locked(conn, user_id, action_id)
        if action["status"] != "approved":
            raise ActionError("not_approved", f"Only approved actions can run (this one is {action['status']}).")
        approved = conn.execute("""select 1 from public.approval where action_id = %s::uuid and decision = 'approved'
                                   and payload_sha256 = %s""", [action_id, action["payload_sha256"]]).fetchone()
        if not approved:
            raise ActionError("approval_required", "This payload has no approval.")
        # Serialise executions of one kind so concurrent workers can't both pass a cap.
        conn.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))", [f"action-kind:{user_id}:{action['kind']}"])
        verdict = policy_mod.check_execution(policy, action["kind"], action["payload"],
                                             _usage(conn, user_id, action, policy, now), now)
        if not verdict.allowed:
            return Gate(action, verdict)
        return Gate(_set_status(conn, action_id, "executing"), verdict)

    return get_db(user_id).run(work)


def record_outcome(user_id: str, action_id: str, status: str, *, provider_ref: str | None = None,
                   error: str | None = None) -> dict:
    """Courier reports what the provider said. provider_accepted is not delivered."""
    if status not in ("provider_accepted", "delivered", "failed", "send_unknown"):
        raise ActionError("invalid_transition", f"Unknown outcome {status!r}.")

    def work(conn):
        action = _locked(conn, user_id, action_id)
        if action["status"] == status:
            return action
        fields = {}
        if provider_ref:
            fields["provider_ref"] = provider_ref
        if error:
            fields["error"] = error[:500]
        try:
            return _set_status(conn, action_id, status, **fields)
        except Exception as exc:
            raise ActionError("invalid_transition", f"{action['status']} -> {status} is not allowed.") from exc

    return get_db(user_id).run(work)


def cancel(user_id: str, action_id: str) -> dict:
    def work(conn):
        action = _locked(conn, user_id, action_id)
        if action["status"] == "cancelled":
            return action
        if action["status"] not in ("proposed", "reviewed", "approved", "blocked", "failed"):
            raise ActionError("invalid_transition", f"A {action['status']} action can't be cancelled.")
        return _set_status(conn, action_id, "cancelled")

    return get_db(user_id).run(work)


def auto_approval_allowed(user_id: str, kind: str, *, policy: Policy | None = None, now: datetime | None = None) -> bool:
    """Autonomy is earned per kind: the last N approvals were unedited, and today's auto cap has room."""
    policy = policy or policy_mod.load_policy()
    rule = policy.autonomy.get(kind)
    if not rule or policy.kill_switch:
        return False
    now = now or datetime.now(timezone.utc)

    def work(conn):
        rows = conn.execute("""select a.revision from public.approval p join public.action a on a.id = p.action_id
                               where p.user_id = %s::uuid and a.kind = %s and p.channel <> 'auto'
                               order by p.seq desc limit %s""",
                            [user_id, kind, rule["auto_after_clean_approvals"]]).fetchall()
        rejected = conn.execute("""select count(*) from (select p.decision from public.approval p
                                     join public.action a on a.id = p.action_id where p.user_id = %s::uuid and a.kind = %s
                                     and p.channel <> 'auto' order by p.seq desc limit %s) recent
                                   where decision = 'rejected'""",
                                [user_id, kind, rule["auto_after_clean_approvals"]]).fetchone()[0]
        if len(rows) < rule["auto_after_clean_approvals"] or rejected or any(r[0] != 1 for r in rows):
            return False
        used = conn.execute("""select count(*) from public.approval p join public.action a on a.id = p.action_id
                               where p.user_id = %s::uuid and a.kind = %s and p.channel = 'auto' and p.decided_at >= %s""",
                            [user_id, kind, policy.day_start(now)]).fetchone()[0]
        return used < rule["daily_cap"]

    return get_db(user_id).run(work)


def pending(user_id: str, *, case_id: str | None = None, limit: int = 100) -> list[dict]:
    """Actions waiting for Dhrumil: reviewed (ready to approve) or blocked/send_unknown (needs a look)."""
    def work(conn):
        rows = conn.execute(f"""select to_jsonb(a) from (select {_COLUMNS} from public.action
                                where user_id = %s::uuid and status in ('proposed','reviewed','send_unknown','blocked')
                                and (%s::uuid is null or case_id = %s::uuid) order by created_at limit %s) a""",
                            [user_id, case_id, case_id, limit]).fetchall()
        return [r[0] for r in rows]

    return get_db(user_id).run(work)
