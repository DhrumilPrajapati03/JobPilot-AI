"""Tailor: a job-specific version of your master resume (plan section 2.1, Day 4).

1. Read the case (job description, company brief) and your master .tex + fact vault.
2. The model proposes a plan in JSON: bullet order, drops, project order, skill order and a
   few rewordings. It never writes LaTeX.
3. The validator keeps only what your vault supports; refused parts are listed on the card.
4. Code renders the .tex, Tectonic compiles it; if it runs longer than your master, the
   least relevant bullets are trimmed (up to three times).
5. A `resume_version` artifact (the diff card) and the .tex/.pdf files are saved for review.
"""
from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.core import cases
from app.experts import artifacts
from app.services import llm
from app.services.runs import PermanentRunError
from app.tailor import compile as tex_compile
from app.tailor import plan as plan_mod
from app.tailor import validator, vault as vault_mod
from app.tailor.texdoc import Edits, TexDoc, parse, plain, render

MAX_TRIMS = 3
_master_pages: dict[str, int] = {}


def _resolve(configured: str) -> Path:
    path = Path(configured)
    if path.is_absolute() or path.exists():
        return path
    repo = Path(__file__).resolve().parents[3] / configured  # repo root when running from backend/
    return repo if repo.exists() else path


def load_inputs() -> tuple[str, TexDoc, vault_mod.Vault, str, str]:
    master_path, vault_path = _resolve(settings.RESUME_MASTER_PATH), _resolve(settings.FACT_VAULT_PATH)
    if not master_path.exists():
        raise PermanentRunError(f"Master resume not found ({settings.RESUME_MASTER_PATH}). Put it in private/resume/master.tex.")
    source = master_path.read_text(encoding="utf-8")
    try:
        vault = vault_mod.load(vault_path)
    except Exception as exc:
        raise PermanentRunError(f"The fact vault could not be read: {exc}") from None
    return (source, parse(source), vault, hashlib.sha256(source.encode()).hexdigest(),
            hashlib.sha256(vault_path.read_bytes()).hexdigest())


def changes(doc: TexDoc, edits: Edits, mapping: dict) -> list[dict]:
    out = []
    for entry in doc.entries:
        where = ", ".join(h for h in entry.heading[:3] if h)[:120]
        original = [b.id for b in entry.bullets]
        order = edits.bullet_order.get(entry.id, original)
        by_id = {b.id: b for b in entry.bullets}
        for bid in original:
            if bid not in order:
                out.append({"kind": "removed", "target": bid, "where": where, "before": by_id[bid].text})
        for bid in order:
            if bid in edits.rewrites:
                out.append({"kind": "reworded", "target": bid, "where": where, "before": by_id[bid].text,
                            "after": plain(edits.rewrites[bid]), "fact": mapping.get(bid)})
        kept = [b for b in original if b in order]
        if order != kept:
            def label(bid):
                text = plain(edits.rewrites[bid]) if bid in edits.rewrites else by_id[bid].text
                return " ".join(text.split()[:6]) + "…"
            out.append({"kind": "moved", "target": entry.id, "where": where,
                        "before": " | ".join(label(b) for b in kept), "after": " | ".join(label(b) for b in order)})
    projects = [e.id for e in doc.entries if e.section == "projects"]
    if edits.entry_order.get("projects") and edits.entry_order["projects"] != projects:
        names = {e.id: e.heading[0] if e.heading else e.id for e in doc.entries}
        out.append({"kind": "moved", "target": "projects", "where": "Projects",
                    "before": " → ".join(names[p] for p in projects),
                    "after": " → ".join(names[p] for p in edits.entry_order["projects"])})
    for line in doc.skills:
        after = edits.skills.get(line.category)
        if after and after != line.items:
            out.append({"kind": "skills", "target": line.category, "where": "Technical Skills",
                        "before": ", ".join(plain(i) for i in line.items), "after": ", ".join(plain(i) for i in after)})
    return out


def chat_model(spec):
    from app.experts.researcher import chat_model as pick
    return pick(spec)


async def _compile(ctx, tex: str, summary: str):
    try:
        return await ctx.tools.call("compile_resume", summary, tex=tex), None
    except tex_compile.CompileError as exc:
        return None, str(exc)


def _store(case_id: str, stamp: str, name: str, data: bytes) -> dict:
    rel = Path("resumes") / case_id / f"{stamp}-{name}"
    path = Path(settings.FILE_STORAGE_DIR) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"path": rel.as_posix(), "sha256": hashlib.sha256(data).hexdigest()}


async def run(ctx) -> dict:
    if not ctx.case_id:
        raise PermanentRunError("Tailor needs a case.")
    case = await ctx.tools.call("read_case", "Reading the case", case_id=ctx.case_id)
    job = (case or {}).get("jd_text") or ""
    if not job.strip():
        raise PermanentRunError("This case has no job description to tailor against.")
    source, doc, vault, master_sha, vault_sha = await asyncio.to_thread(load_inputs)
    mapping = {bid: vault_mod.match(b.text, vault)[0] for bid, b in doc.bullets().items()}
    brief = await asyncio.to_thread(artifacts.latest, ctx.user_id, ctx.case_id, "company_brief")
    company, role = case.get("company") or "the company", case.get("role") or "the role"

    prompt = [llm.SystemMessage(plan_mod.INSTRUCTIONS),
              llm.HumanMessage(plan_mod.prompt_context(doc, mapping, job, company, role, brief and brief["content"]))]
    with llm.usage_meter() as usage:
        proposed = await llm.with_structured(chat_model(ctx.spec), plan_mod.Plan).ainvoke(prompt)
    await ctx.log.add("llm", "plan", f"Planned the {company} version", {"rationale": proposed.rationale,
                      "model": usage[-1]["model"] if usage else ""}, tokens=sum(u["tokens"] for u in usage))

    reviewed = validator.review(doc, proposed.edits(), vault)
    rejected = [{"target": r["bullet"], "text": r["text"], "reasons": r["reasons"]} for r in reviewed.rejected]
    if rejected or reviewed.structure:
        await ctx.log.add("note", "validator", f"Refused {len(rejected)} change{'s' if len(rejected) != 1 else ''} "
                          "not supported by your fact vault", {"rejected": rejected, "structure": reviewed.structure})
    edits = reviewed.edits

    master_pages = _master_pages.get(master_sha)
    compile_error = None
    if master_pages is None:
        master, compile_error = await _compile(ctx, source, "Compiling your master resume (page count)")
        if master:
            master_pages = _master_pages[master_sha] = master.pages
    tex = render(doc, edits)
    compiled, error = await _compile(ctx, tex, f"Compiling the {company} version")
    compile_error = error or compile_error
    trimmed = 0
    while compiled and master_pages and compiled.pages > master_pages and trimmed < MAX_TRIMS:
        smaller = plan_mod.trim_for_pages(doc, edits)
        if smaller is None:
            break
        edits, trimmed = smaller, trimmed + 1
        tex = render(doc, edits)
        compiled, error = await _compile(ctx, tex, f"Trimming to {master_pages} page{'s' if master_pages > 1 else ''}")
        compile_error = error

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    tex_file = await asyncio.to_thread(_store, ctx.case_id, stamp, "resume.tex", tex.encode("utf-8"))
    pdf_file = None
    if compiled:
        pdf_file = {**await asyncio.to_thread(_store, ctx.case_id, stamp, "resume.pdf", compiled.pdf), "pages": compiled.pages}
    before, after = plan_mod.coverage(job, source, vault, company), plan_mod.coverage(job, tex, vault, company)
    card = {"company": company, "role": role, "master_sha256": master_sha, "vault_sha256": vault_sha,
            "rationale": proposed.rationale[:800], "changes": changes(doc, edits, mapping), "rejected": rejected,
            "keywords": after.keywords, "covered_before": before.covered, "covered_after": after.covered,
            "missing": after.missing, "master_pages": master_pages, "trimmed": trimmed, "tex": tex_file,
            "pdf": pdf_file, "compile_error": compile_error}
    saved = await ctx.tools.call("save_artifact", "Saved the resume version for your review", kind="resume_version",
                                 content=card, title=f"Resume for {role} at {company}")
    summary = (f"Tailor made a resume version for {company}: {len(card['changes'])} change{'s' if len(card['changes']) != 1 else ''}"
               + (f", {len(rejected)} refused" if rejected else "")
               + ("" if compiled else " (PDF not compiled)"))
    await asyncio.to_thread(cases.add_event, ctx.user_id, ctx.case_id, "artifact", actor="agent", actor_name="tailor",
                            summary=summary, data={"artifact_id": saved["id"], "kind": "resume_version"})
    return {"artifact_id": saved["id"], "changes": len(card["changes"]), "rejected": len(rejected),
            "pages": compiled.pages if compiled else None, "trimmed": trimmed, "compile_error": compile_error}
