"""Budgets (plan section 4): per-case caps on steps, tokens and seconds, and a monthly
LLM spend limit. Spending is recorded in budget_ledger; checks read the totals.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.core import policy as policy_mod
from app.core.policy import Policy
from app.db import get_db

UNITS = ("steps", "tokens", "seconds", "usd")


@dataclass
class BudgetStatus:
    used: dict[str, float]
    limits: dict[str, float]

    @property
    def exceeded(self) -> list[str]:
        return [u for u, limit in self.limits.items() if self.used.get(u, 0) >= limit]


def charge(user_id: str, unit: str, amount: float, *, case_id: str | None = None, run_id: str | None = None,
           agent: str = "") -> None:
    if unit not in UNITS or amount < 0:
        raise ValueError(f"invalid budget charge: {unit} {amount}")
    get_db(user_id).fetch("""insert into public.budget_ledger (user_id, case_id, run_id, agent, unit, amount)
                             values (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s)""",
                          [user_id, case_id, run_id, agent, unit, amount])


def case_status(user_id: str, case_id: str, *, policy: Policy | None = None) -> BudgetStatus:
    policy = policy or policy_mod.load_policy()
    rows = get_db(user_id).fetch("""select unit, coalesce(sum(amount), 0) from public.budget_ledger
                                    where user_id = %s::uuid and case_id = %s::uuid group by unit""", [user_id, case_id])
    return BudgetStatus({u: float(v) for u, v in rows}, dict(policy.budgets["per_case"]))


def month_status(user_id: str, *, policy: Policy | None = None, now: datetime | None = None) -> BudgetStatus:
    policy = policy or policy_mod.load_policy()
    now = now or datetime.now(timezone.utc)
    start = policy.day_start(now).replace(day=1)
    rows = get_db(user_id).fetch("""select coalesce(sum(amount), 0) from public.budget_ledger
                                    where user_id = %s::uuid and unit = 'usd' and at >= %s""", [user_id, start])
    return BudgetStatus({"usd": float(rows[0][0])}, {"usd": float(policy.budgets["monthly_usd"])})


def check(user_id: str, case_id: str | None = None, *, policy: Policy | None = None) -> list[str]:
    """Plain-language reasons why work must stop now; empty when within budget."""
    policy = policy or policy_mod.load_policy()
    reasons = []
    if case_id:
        status = case_status(user_id, case_id, policy=policy)
        reasons += [f"This case used its {u} budget ({status.used[u]:g} of {status.limits[u]:g})." for u in status.exceeded]
    month = month_status(user_id, policy=policy)
    if month.exceeded:
        reasons.append(f"Monthly LLM budget reached (${month.used['usd']:.2f} of ${month.limits['usd']:.2f}).")
    return reasons
