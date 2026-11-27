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


def tailor_suite() -> list[Metric]:
    """Tailor: the fact-vault validator on labelled rewrites, and lossless rendering of the .tex."""
    from app.tailor import validator, vault as vault_mod
    from app.tailor.texdoc import Edits, parse, render
    fixtures = ROOT / "tests" / "fixtures" / "resume"
    source = (fixtures / "master.tex").read_text(encoding="utf-8")
    doc, vault = parse(source), vault_mod.load(fixtures / "fact_vault.yaml")
    cases = [json.loads(line) for line in (DATASETS / "tailor_cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    wrong = []
    for case in cases:
        reviewed = validator.review(doc, Edits(rewrites={case["bullet"]: case["text"]}), vault)
        accepted = case["bullet"] in reviewed.edits.rewrites
        if accepted != (case["expect"] == "accept"):
            wrong.append({"id": case["id"], "accepted": accepted, "rejected": reviewed.rejected})
    refused = [c for c in cases if c["expect"] == "reject"]
    leaked = [w for w in wrong if w["accepted"]]
    return [
        Metric("tailor", "tailor_cases", "validator_accuracy", (len(cases) - len(wrong)) / len(cases), 1.0, details={"wrong": wrong}),
        Metric("tailor", "tailor_cases", "invented_claims_accepted", len(leaked), 0, higher_is_better=False,
               details={"of": len(refused)}),
        Metric("tailor", "fixture master.tex", "render_without_edits_identical", float(render(doc) == source), 1.0),
    ]


def recon_suite() -> list[Metric]:
    """Recon: labelled LinkedIn search results (fictional people). A wrong-company person is
    the costly mistake (an email to a stranger), so it must be zero."""
    from app.recon.people import parse_result
    cases = [json.loads(line) for line in (DATASETS / "recon_cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    wrong, accepted_bad, role_ok, role_total = [], [], 0, 0
    for case in cases:
        person = parse_result(case["url"], case["title"], case["snippets"], case["company"])
        expect = case["expect"]
        if expect is None:
            if person is not None:
                accepted_bad.append({"id": case["id"], "got": person.title})
            continue
        role_total += 1
        if person is None:
            wrong.append({"id": case["id"], "got": None})
        elif person.role_class == expect["role_class"] and person.title == expect.get("title", person.title):
            role_ok += 1
        else:
            wrong.append({"id": case["id"], "got": [person.role_class, person.title]})
    return [
        Metric("recon", "recon_cases", "wrong_people_accepted", len(accepted_bad), 0, higher_is_better=False,
               details={"accepted": accepted_bad}),
        Metric("recon", "recon_cases", "role_and_title_accuracy", role_ok / role_total, 0.9, details={"wrong": wrong}),
    ]


def answerer_suite() -> list[Metric]:
    """Answerer: question kinds decide who may answer. A legal or self-identification question
    classified as anything else could be auto-answered, so those misses must be zero."""
    from app.answers.questions import kind_of
    cases = [json.loads(line) for line in (DATASETS / "answerer_cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    wrong = [{"label": c["label"], "expected": c["kind"], "got": kind_of(c["label"], c["type"], "Acme")} for c in cases
             if kind_of(c["label"], c["type"], "Acme") != c["kind"]]
    guarded = [w for w in wrong if w["expected"] in ("legal", "eeo")]
    return [
        Metric("answerer", "answerer_cases", "legal_or_eeo_missed", len(guarded), 0, higher_is_better=False, details={"missed": guarded}),
        Metric("answerer", "answerer_cases", "kind_accuracy", (len(cases) - len(wrong)) / len(cases), 0.9, details={"wrong": wrong}),
    ]


def connector_suite() -> list[Metric]:
    """Connector: the Reviewer's LinkedIn checks on labelled notes. A note with a claim the vault
    doesn't support, over LinkedIn's limit, or to something that isn't a person's profile must
    never pass; true, specific notes must not be blocked."""
    from app.experts import reviewer
    from app.tailor import vault as vault_mod
    vault = vault_mod.load(ROOT / "tests" / "fixtures" / "resume" / "fact_vault.yaml")
    job = "Acme is hiring an ML Engineer to build RAG on pgvector with FastAPI."
    brief = {"summary": "Acme builds support search for support teams.", "product": [{"text": "Support search on pgvector", "sources": [1]}]}
    cases = [json.loads(line) for line in (DATASETS / "connector_notes.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    wrong = []
    for c in cases:
        payload = {"contact_id": "c1", "name": "Jane Example", "title": "Recruiter", "company": "Acme", "role": "ML Engineer",
                   "profile_url": c.get("url", "https://www.linkedin.com/in/jane-example/"), "note": c["note"], "body": c["note"]}
        review = reviewer.check_linkedin(payload, kind=c.get("kind", "send_linkedin_invite"), company="Acme", role="ML Engineer", job=job,
                                         brief=brief, vault=vault)
        if review.ok != (c["expect"] == "pass"):
            wrong.append({"note": c["note"][:80], "expected": c["expect"], "blocks": review.blocks})
    leaked = [w for w in wrong if w["expected"] == "block"]
    return [
        Metric("connector", "connector_notes", "bad_notes_passed", len(leaked), 0, higher_is_better=False,
               details={"of": sum(c["expect"] == "block" for c in cases), "passed": leaked}),
        Metric("connector", "connector_notes", "review_accuracy", (len(cases) - len(wrong)) / len(cases), 1.0, details={"wrong": wrong}),
    ]


SUITES = {"matching": matching_suite, "policy": policy_suite, "tailor": tailor_suite, "recon": recon_suite,
          "answerer": answerer_suite, "connector": connector_suite}


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
