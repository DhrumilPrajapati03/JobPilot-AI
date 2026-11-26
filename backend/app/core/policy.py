"""Policy engine (plan sections 2.3 and 2.4): what each action kind may do, and when.

`config/policy.yaml` is the single source. Agents read it but never change it; custom
agents inherit it. Everything here is pure: callers gather usage counts from the
database (app.core.actions) and pass them in, so the rules are easy to test.

Two checks:

* `mode_for(kind)` when an action is proposed. Unknown kinds are rejected outright;
  `never` kinds are recorded as blocked.
* `check_execution(...)` right before Courier runs an approved action: kill switch,
  mode, quiet hours, daily/weekly caps, people per company, recent-touch cooldown and the
  delay between a LinkedIn acceptance and the first DM.
"""
from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

MODES = ("act", "act_with_preview", "ask_first", "hand_off", "never")
# Modes Courier may execute. hand_off goes to Dhrumil; never is never executed.
EXECUTABLE = ("act", "act_with_preview", "ask_first")
# Kinds that reach another person. Caps, quiet hours and cooldowns apply to these.
OUTWARD = {"send_email", "send_linkedin_invite", "send_linkedin_dm", "referral_request",
           "submit_application", "create_calendar_event"}
# Kinds that open a conversation with someone (the recent-touch cooldown applies).
OPENERS = {"send_email", "send_linkedin_invite", "referral_request"}
DAILY_CAPS = {"send_email": "emails_per_day", "send_linkedin_invite": "linkedin_invites_per_day",
              "send_linkedin_dm": "linkedin_dms_per_day"}
WEEKLY_CAPS = {"send_linkedin_invite": "linkedin_invites_per_week"}
PEOPLE_KINDS = {"send_email", "send_linkedin_invite", "send_linkedin_dm", "referral_request"}

# Caps added after the first policy.yaml; older files get these defaults.
OPTIONAL_CAPS = {"recon_searches_per_run": 6, "recon_searches_per_day": 40}

DEFAULT_BUDGETS = {
    "per_case": {"steps": 200, "tokens": 500_000, "seconds": 3600},
    "monthly_usd": 10.0,
    "refused_actions_circuit": {"max_blocked": 3, "window_hours": 24},
}
_KIND = re.compile(r"^[a-z][a-z0-9_]{1,59}$")
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class PolicyError(ValueError):
    """policy.yaml is missing or invalid. Nothing outward runs until it is fixed."""


class UnknownActionKind(ValueError):
    pass


@dataclass(frozen=True)
class Policy:
    version: int
    kill_switch: bool
    action_modes: dict[str, str]
    caps: dict[str, Any]
    autonomy: dict[str, dict[str, int]]
    budgets: dict[str, Any]
    timezone: ZoneInfo
    quiet_start: time | None
    quiet_end: time | None

    def mode_for(self, kind: str) -> str:
        if not isinstance(kind, str) or kind not in self.action_modes:
            raise UnknownActionKind(f"Action kind {kind!r} is not in policy.yaml, so it is rejected.")
        return self.action_modes[kind]

    def local(self, now: datetime) -> datetime:
        return now.astimezone(self.timezone)

    def day_start(self, now: datetime) -> datetime:
        local = self.local(now)
        return local.replace(hour=0, minute=0, second=0, microsecond=0)

    def week_start(self, now: datetime) -> datetime:
        start = self.day_start(now)
        return start - timedelta(days=start.weekday())  # Monday, local time

    def in_quiet_hours(self, now: datetime) -> bool:
        if self.quiet_start is None or self.quiet_end is None:
            return False
        t = self.local(now).time()
        if self.quiet_start <= self.quiet_end:
            return self.quiet_start <= t < self.quiet_end
        return t >= self.quiet_start or t < self.quiet_end

    def quiet_hours_end(self, now: datetime) -> datetime:
        local = self.local(now)
        end = local.replace(hour=self.quiet_end.hour, minute=self.quiet_end.minute, second=0, microsecond=0)
        return end if end > local else end + timedelta(days=1)


@dataclass
class Usage:
    """What has already happened, counted by the caller in the same transaction."""
    executed_today: int = 0           # this kind, since local midnight
    executed_this_week: int = 0       # this kind, since local Monday
    company_people: set[str] = field(default_factory=set)  # contacts already reached at the payload's company
    last_touch_at: datetime | None = None    # latest touch of the payload's contact, any channel
    accepted_at: datetime | None = None      # when the contact accepted the invite (DMs only)


@dataclass
class Verdict:
    allowed: bool
    mode: str
    reasons: list[str]
    retry_at: datetime | None = None  # set when waiting (quiet hours) would make it allowed


def _parse(raw: dict) -> Policy:
    if not isinstance(raw, dict) or raw.get("version") != 1:
        raise PolicyError("policy.yaml must be a mapping with version: 1")
    modes = raw.get("action_modes")
    if not isinstance(modes, dict) or not modes:
        raise PolicyError("policy.yaml needs action_modes")
    for kind, mode in modes.items():
        if not _KIND.match(str(kind)) or mode not in MODES:
            raise PolicyError(f"Invalid action mode for {kind!r}: {mode!r}")
    caps = dict(raw.get("caps") or {})
    for name in ("emails_per_day", "linkedin_invites_per_day", "linkedin_invites_per_week",
                 "linkedin_dms_per_day", "max_people_per_company", "min_hours_accept_to_dm",
                 "no_contact_if_touched_within_days"):
        value = caps.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise PolicyError(f"caps.{name} must be a whole number >= 0")
    for name, default in OPTIONAL_CAPS.items():
        value = caps.setdefault(name, default)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise PolicyError(f"caps.{name} must be a whole number >= 0")
    try:
        tz = ZoneInfo(str(caps.get("timezone") or "UTC"))
    except Exception:
        raise PolicyError("caps.timezone is not a valid time zone") from None
    quiet_start = quiet_end = None
    if caps.get("quiet_hours"):
        parts = str(caps["quiet_hours"]).split("-")
        if len(parts) != 2 or not all(_HHMM.match(p.strip()) for p in parts):
            raise PolicyError('caps.quiet_hours must look like "22:00-08:00"')
        quiet_start, quiet_end = (time.fromisoformat(p.strip()) for p in parts)
    autonomy = {}
    for kind, rule in (raw.get("autonomy") or {}).items():
        if kind not in modes or not isinstance(rule, dict):
            raise PolicyError(f"autonomy.{kind} must name an action kind from action_modes")
        n, cap = rule.get("auto_after_clean_approvals"), rule.get("daily_cap")
        if not all(isinstance(v, int) and not isinstance(v, bool) and v >= 1 for v in (n, cap)):
            raise PolicyError(f"autonomy.{kind} needs auto_after_clean_approvals and daily_cap >= 1")
        autonomy[kind] = {"auto_after_clean_approvals": n, "daily_cap": min(cap, caps.get(DAILY_CAPS.get(kind, ""), cap))}
    budgets = {**DEFAULT_BUDGETS, **(raw.get("budgets") or {})}
    budgets["per_case"] = {**DEFAULT_BUDGETS["per_case"], **(budgets.get("per_case") or {})}
    budgets["refused_actions_circuit"] = {**DEFAULT_BUDGETS["refused_actions_circuit"],
                                          **(budgets.get("refused_actions_circuit") or {})}
    for unit, value in budgets["per_case"].items():
        if unit not in ("steps", "tokens", "seconds") or not isinstance(value, (int, float)) or value <= 0:
            raise PolicyError(f"budgets.per_case.{unit} must be a positive number")
    if not isinstance(budgets["monthly_usd"], (int, float)) or budgets["monthly_usd"] < 0:
        raise PolicyError("budgets.monthly_usd must be >= 0")
    return Policy(version=1, kill_switch=bool(raw.get("kill_switch", False)), action_modes=dict(modes),
                  caps=caps, autonomy=autonomy, budgets=budgets, timezone=tz,
                  quiet_start=quiet_start, quiet_end=quiet_end)


def policy_path() -> Path:
    configured = os.environ.get("POLICY_FILE")
    if configured:
        return Path(configured)
    here = Path(__file__).resolve()
    for candidate in (Path.cwd() / "config" / "policy.yaml", here.parents[3] / "config" / "policy.yaml",
                      here.parents[2] / "config" / "policy.yaml"):
        if candidate.is_file():
            return candidate
    return here.parents[3] / "config" / "policy.yaml"


_cache: tuple[Path, float, Policy] | None = None
_lock = threading.Lock()


def load_policy(text: str | None = None) -> Policy:
    """Parse policy text, or load config/policy.yaml (re-read when the file changes)."""
    global _cache
    if text is not None:
        return _parse(yaml.safe_load(text))
    path = policy_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        raise PolicyError(f"policy.yaml not found at {path}") from None
    with _lock:
        if _cache and _cache[0] == path and _cache[1] == mtime:
            return _cache[2]
        policy = _parse(yaml.safe_load(path.read_text(encoding="utf-8")))
        _cache = (path, mtime, policy)
        return policy


def check_execution(policy: Policy, kind: str, payload: dict, usage: Usage, now: datetime) -> Verdict:
    """May Courier run this approved action now? Every failed rule is listed."""
    try:
        mode = policy.mode_for(kind)
    except UnknownActionKind as exc:
        return Verdict(False, "never", [str(exc)])
    reasons: list[str] = []
    retry_at = None
    if mode not in EXECUTABLE:
        reasons.append(f"{kind} is '{mode}' in policy.yaml, so it is never executed automatically.")
    if kind in OUTWARD:
        if policy.kill_switch:
            reasons.append("The kill switch is on; all sending is paused.")
        cap = DAILY_CAPS.get(kind)
        if cap and usage.executed_today >= policy.caps[cap]:
            reasons.append(f"Daily cap reached: {cap} = {policy.caps[cap]}.")
        cap = WEEKLY_CAPS.get(kind)
        if cap and usage.executed_this_week >= policy.caps[cap]:
            reasons.append(f"Weekly cap reached: {cap} = {policy.caps[cap]}.")
        contact = str(payload.get("contact_id") or "")
        if kind in PEOPLE_KINDS and contact and contact not in usage.company_people \
                and len(usage.company_people) >= policy.caps["max_people_per_company"]:
            reasons.append(f"Already reached {len(usage.company_people)} people at this company "
                           f"(max_people_per_company = {policy.caps['max_people_per_company']}).")
        days = policy.caps["no_contact_if_touched_within_days"]
        if kind in OPENERS and usage.last_touch_at and now - usage.last_touch_at < timedelta(days=days):
            reasons.append(f"This person was contacted in the last {days} days.")
        if kind == "send_linkedin_dm":
            hours = policy.caps["min_hours_accept_to_dm"]
            if usage.accepted_at is None:
                reasons.append("No recorded invite acceptance for this person yet.")
            elif now - usage.accepted_at < timedelta(hours=hours):
                reasons.append(f"Wait {hours} hours after the invite was accepted before a DM.")
        if policy.in_quiet_hours(now):
            reasons.append("Quiet hours; it will be sent when they end.")
            if len(reasons) == 1:
                retry_at = policy.quiet_hours_end(now)
    return Verdict(not reasons, mode, reasons, retry_at)
