"""The end-to-end report (plan section 8, Day 15): how every case went, per expert, from the
database. Run it inside the api container (`python -m app.experts.e2e_report`); it writes
Markdown to FILE_STORAGE_DIR/reports/ (under data/, never committed) and prints the path.

Per case: the stage reached, which experts produced what, Reviewer blocks, failed runs.
Per expert and model: runs, failures, tokens and latency, and routing advice:
* an expert that failed on a model more than a quarter of the time should try the fallback
  first, or the 'light' task, for its structured calls;
* an expert whose calls are small (under ~3k tokens) can run on the light model to save quota.
`--run CASE_ID ...` first asks Supervisor to carry those cases as far as they go (it waits
for the queue to drain, up to --wait seconds).
"""
from __future__ import annotations

import argparse
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.db import get_db

GRAPH = ("company_brief", "comp_report", "contact_list", "resume_version", "draft", "invite_set", "dm_set")


def collect(user_id: str, case_ids: list[str] | None = None) -> dict:
    db = get_db(user_id)
    where = "and c.id = any(%s::uuid[])" if case_ids else "and not c.legacy"
    rows = db.fetch(f"""select c.id::text, c.company, c.role, c.stage,
                              coalesce((select array_agg(distinct a.kind) from public.artifact a where a.case_id = c.id and not a.legacy), '{{}}'),
                              (select count(*) from public.action x where x.case_id = c.id and x.status = 'blocked'),
                              (select count(*) from public.action x where x.case_id = c.id and x.status = 'reviewed'),
                              (select count(*) from public.agent_runs r where r.case_id = c.id and r.status = 'failed')
                       from public.job_case c where c.user_id = %s::uuid {where} order by c.created_at desc limit 50""",
                    [user_id, case_ids] if case_ids else [user_id])
    cases = [dict(zip(("id", "company", "role", "stage", "artifacts", "blocked", "waiting", "failed"), r)) for r in rows]
    llm = db.fetch("""select agent, coalesce(detail->>'model', ''), count(*), coalesce(sum(tokens), 0), coalesce(avg(duration_ms), 0)
                      from public.run_step where user_id = %s::uuid and kind = 'llm' group by 1, 2 order by 1, 2""", [user_id])
    fails = db.fetch("""select inputs->>'agent', count(*) filter (where status = 'failed'), count(*),
                               (array_agg(last_error order by updated_at desc) filter (where status = 'failed'))[1]
                        from public.agent_runs where user_id = %s::uuid and kind = 'agent' group by 1""", [user_id])
    return {"cases": cases, "llm": llm, "runs": {r[0]: {"failed": r[1], "total": r[2], "last_error": r[3]} for r in fails}}


def advice(data: dict) -> list[str]:
    out = []
    per_agent: dict[str, list] = defaultdict(list)
    for agent, model, calls, tokens, ms in data["llm"]:
        per_agent[agent].append((model, calls, tokens, ms))
    for agent, rows in sorted(per_agent.items()):
        calls = sum(r[1] for r in rows)
        tokens = sum(r[2] for r in rows)
        runs = data["runs"].get(agent, {"failed": 0, "total": 0})
        rate = runs["failed"] / runs["total"] if runs["total"] else 0
        if runs["total"] >= 4 and rate > 0.25:
            out.append(f"{agent}: {runs['failed']} of {runs['total']} runs failed; put the fallback model first or use task 'light'.")
        elif calls >= 3 and tokens / calls < 3000:
            out.append(f"{agent}: calls average {tokens // calls} tokens; the light model would do and save quota.")
    return out or ["No routing changes suggested yet: not enough runs, and no expert is failing often."]


def cell(text: str) -> str:
    """Safe inside a Markdown table cell."""
    return (text or "").replace("|", "/").replace("\n", " ")[:120]


def markdown(data: dict) -> str:
    lines = [f"# JobDots end-to-end report ({datetime.now(timezone.utc):%d %b %Y %H:%M} UTC)", "",
             "## Cases", "", "| Company | Role | Stage | Made | Waiting for you | Blocked | Failed runs |", "|---|---|---|---|---|---|---|"]
    for c in data["cases"]:
        made = ", ".join(k for k in GRAPH if k in c["artifacts"]) or "nothing yet"
        lines.append(f"| {cell(c['company'])} | {cell(c['role'])} | {c['stage']} | {made} | {c['waiting']} | {c['blocked']} | {c['failed']} |")
    lines += ["", "## Experts and models", "", "| Expert | Model | Calls | Tokens | Avg ms |", "|---|---|---|---|---|"]
    for agent, model, calls, tokens, ms in data["llm"]:
        lines.append(f"| {agent} | {model or 'not recorded'} | {calls} | {tokens} | {int(ms)} |")
    lines += ["", "## Failed runs by expert", ""]
    for agent, r in sorted(data["runs"].items()):
        if r["failed"]:
            lines.append(f"- {agent}: {r['failed']} of {r['total']} failed; last: {cell((r['last_error'] or '').splitlines()[0] if r['last_error'] else '')}")
    lines += ["", "## Model routing advice", "", *[f"- {a}" for a in advice(data)], ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run", nargs="*", default=None, help="case ids Supervisor should carry first")
    parser.add_argument("--wait", type=int, default=900)
    args = parser.parse_args()
    db = get_db()
    user_id = db.fetch("select id::text from auth.users order by created_at limit 1")[0][0]
    if args.run:
        from app.experts.runtime import enqueue_expert
        for case_id in args.run:
            enqueue_expert(user_id, "supervisor", case_id=case_id, trigger="manual")
        deadline = time.time() + args.wait
        while time.time() < deadline and db.fetch("""select count(*) from public.agent_runs where user_id = %s::uuid
                                                    and status in ('queued','running','retry_wait')""", [user_id])[0][0]:
            time.sleep(10)
    report = markdown(collect(user_id, args.run or None))
    from app.config import settings
    out = Path(settings.FILE_STORAGE_DIR) / "reports"        # under data/: yours, never committed
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"e2e-{datetime.now(timezone.utc):%Y%m%d-%H%M}.md"
    path.write_text(report, encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
