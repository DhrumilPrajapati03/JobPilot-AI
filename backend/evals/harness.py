"""Eval harness (plan section 8.1): JSONL/JSON golden datasets, deterministic checks, one
score per metric, optional recording to `eval_result` so the Experts page can show each
agent's last eval. Each agent lands with its suite; Day 2 seeds Scout's matching cases and
the Courier policy engine.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATASETS = Path(__file__).resolve().parent / "datasets"


@dataclass
class Metric:
    agent: str
    dataset: str
    metric: str
    score: float
    threshold: float
    higher_is_better: bool = True
    model: str = ""
    details: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.score >= self.threshold if self.higher_is_better else self.score <= self.threshold


def matching_suite(semantic: bool = False) -> list[Metric]:
    """Scout: the 37 labelled matching cases (eligibility, relevance, no false positives)."""
    from app.config import settings
    from app.services.matching_evaluation import evaluate_dataset
    previous = settings.MATCHING_SEMANTIC
    settings.MATCHING_SEMANTIC = semantic
    try:
        dataset = json.loads((ROOT / "evaluations" / "matching_cases.json").read_text(encoding="utf-8"))
        report = evaluate_dataset(dataset)
    finally:
        settings.MATCHING_SEMANTIC = previous
    name = f"matching_cases v{dataset['version']}"
    model = settings.OLLAMA_EMBED_MODEL if semantic and report.get("semantic_cases") else "lexical"
    failed = [o["id"] for o in report["outcomes"] if not o["passed"]]
    return [
        Metric("scout", name, "eligibility_accuracy", report["eligibility_accuracy"], 1.0, model=model),
        Metric("scout", name, "precision", report["precision"], 1.0, model=model),
        Metric("scout", name, "recall", report["recall"], 0.85, model=model, details={"failed_cases": failed}),
        Metric("scout", name, "false_positives", report["false_positives"], 0, higher_is_better=False, model=model),
    ]


def _usage(case: dict, now: datetime):
    from app.core.policy import Usage
    u = case.get("usage") or {}
    return Usage(executed_today=u.get("executed_today", 0), executed_this_week=u.get("executed_this_week", 0),
                 company_people=set(u.get("company_people") or []),
                 last_touch_at=now - timedelta(days=u["last_touch_days_ago"]) if "last_touch_days_ago" in u else None,
                 accepted_at=now - timedelta(hours=u["accepted_hours_ago"]) if "accepted_hours_ago" in u else None)


def policy_suite() -> list[Metric]:
    """Courier/policy engine: behavioural cases on a pinned policy, plus the real policy.yaml's structure."""
    from app.core.policy import OUTWARD, check_execution, load_policy
    fixture_text = (DATASETS / "policy_fixture.yaml").read_text(encoding="utf-8")
    cases = [json.loads(line) for line in (DATASETS / "policy_cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    wrong = []
    for case in cases:
        text = fixture_text.replace("kill_switch: false", "kill_switch: true") if case.get("kill_switch") else fixture_text
        policy = load_policy(text)
        hour, minute = (int(x) for x in case["local_time"].split(":"))
        now = datetime(2026, 11, 25, hour, minute, tzinfo=ZoneInfo("Asia/Kolkata")).astimezone(timezone.utc)
        verdict = check_execution(policy, case["kind"], case.get("payload") or {}, _usage(case, now), now)
        ok = verdict.allowed == (case["expect"] == "allow")
        if ok and case.get("reason"):
            ok = any(case["reason"].lower() in r.lower() for r in verdict.reasons)
        if not ok:
            wrong.append({"id": case["id"], "allowed": verdict.allowed, "reasons": verdict.reasons})
    real = load_policy()
    must_ask = sorted(k for k in OUTWARD if k in real.action_modes and real.action_modes[k] not in ("ask_first", "hand_off", "never"))
    missing = sorted(k for k in OUTWARD if k not in real.action_modes)
    never = sorted(k for k in ("bulk_send", "fake_identity", "scrape_behind_login") if real.action_modes.get(k) != "never")
    return [
        Metric("courier", "policy_cases", "accuracy", (len(cases) - len(wrong)) / len(cases), 1.0, details={"wrong": wrong}),
        Metric("courier", "config/policy.yaml", "outward_kinds_missing_a_mode", len(missing), 0, higher_is_better=False,
               details={"kinds": missing}),
        Metric("courier", "config/policy.yaml", "outward_kinds_not_ask_first", len(must_ask), 0, higher_is_better=False,
               details={"kinds": must_ask}),
        Metric("courier", "config/policy.yaml", "never_list_not_never", len(never), 0, higher_is_better=False,
               details={"kinds": never}),
    ]


SUITES = {"matching": matching_suite, "policy": policy_suite}


def run(names: list[str] | None = None, *, semantic: bool = False) -> list[Metric]:
    metrics: list[Metric] = []
    for name in names or list(SUITES):
        suite = SUITES[name]
        metrics += suite(semantic=semantic) if name == "matching" else suite()
    return metrics


def record(metrics: list[Metric]) -> None:
    """Save to eval_result (needs DATABASE_URL)."""
    from psycopg.types.json import Jsonb

    from app.db import get_db
    db = get_db()
    for m in metrics:
        db.fetch("""insert into public.eval_result (agent, dataset, metric, score, model, details)
                    values (%s, %s, %s, %s, %s, %s)""",
                 [m.agent, m.dataset, m.metric, float(m.score), m.model,
                  Jsonb({**m.details, "threshold": m.threshold, "passed": m.passed})])


def as_json(metrics: list[Metric]) -> str:
    return json.dumps([{**asdict(m), "passed": m.passed} for m in metrics], indent=2)
