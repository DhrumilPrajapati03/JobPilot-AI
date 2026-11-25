"""Researcher: a cited company brief for each case (plan section 2.1, wave 1).

1. Sources: the job description stored on the case (source 1), the posting page, any URLs
   you gave, and public links found in the JD; at most MAX_SOURCES. Pages are fetched with
   the SSRF-safe public fetcher (no logins, no private hosts).
2. The model writes the brief from the numbered sources only. The sources list is attached
   by code, never by the model, so URLs can't be invented. Source text is untrusted data.
3. Claims citing sources that don't exist are dropped (and noted); the brief is saved as a
   typed `company_brief` artifact.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.experts.artifacts import CompanyBrief
from app.services import llm
from app.services.runs import PermanentRunError

MAX_SOURCES = 5
SOURCE_CHARS = 3500
_LINK = re.compile(r"https?://[^\s)<>\"']+")
_SKIP_HOSTS = ("linkedin.com", "facebook.com", "twitter.com", "x.com", "instagram.com", "youtube.com",
               "glassdoor.", "indeed.", "mailto:")


class DraftClaim(BaseModel):
    """Lenient on input (models add fields or run long); the saved brief is strict."""
    text: str = ""
    sources: list[int] = Field(default_factory=list)


class BriefDraft(BaseModel):
    """What the model fills in; sources are attached by code."""
    summary: str = ""
    product: list[DraftClaim] = Field(default_factory=list)
    stage: list[DraftClaim] = Field(default_factory=list)
    recent_news: list[DraftClaim] = Field(default_factory=list)
    tech_stack: list[DraftClaim] = Field(default_factory=list)
    fit_notes: list[DraftClaim] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    confidence: str = "low"


def source_urls(case: dict, extra: list[str]) -> list[str]:
    urls = []
    for url in [case.get("source_url") or "", *extra, *_LINK.findall(case.get("jd_text") or "")]:
        url = url.rstrip(".,;")
        host = urlparse(url).netloc.lower()
        if not url.startswith(("http://", "https://")) or not host or any(s in host for s in _SKIP_HOSTS):
            continue
        if url not in urls:
            urls.append(url)
    return urls[:MAX_SOURCES - 1]


def chat_model(spec):
    provider = spec.model.provider
    if provider in ("default", "none"):
        return llm.get_default_llm(task=spec.model.task)
    return llm.get_chat_llm(provider, model=spec.model.model or None, task=spec.model.task)


def cap_confidence(stated: str, source_count: int) -> str:
    """Confidence can't exceed the evidence: JD only -> low, two sources -> at most medium."""
    ceiling = "low" if source_count <= 1 else "medium" if source_count == 2 else "high"
    order = ("low", "medium", "high")
    return min(stated if stated in order else "low", ceiling, key=order.index)


LIMITS = {"product": 8, "stage": 4, "recent_news": 8, "tech_stack": 12, "fit_notes": 8}


def keep_cited(draft: BriefDraft, known: set[int]) -> tuple[dict, int]:
    """Brief fields with only claims that cite real sources, trimmed to the artifact's limits."""
    dropped = 0
    data = {"summary": draft.summary[:1200], "open_questions": [q[:300] for q in draft.open_questions if q.strip()][:8],
            "confidence": draft.confidence if draft.confidence in ("low", "medium", "high") else "low"}
    for field, limit in LIMITS.items():
        kept = []
        for claim in getattr(draft, field):
            valid = sorted({n for n in claim.sources if n in known})[:8]
            if valid and claim.text.strip():
                kept.append({"text": claim.text.strip()[:600], "sources": valid})
            else:
                dropped += 1
        data[field] = kept[:limit]
    return data, dropped


async def run(ctx) -> dict:
    if not ctx.case_id:
        raise PermanentRunError("Researcher needs a case.")
    case = await ctx.tools.call("read_case", "Reading the case", case_id=ctx.case_id)
    if case is None:
        raise PermanentRunError("The case was removed.")
    company = case.get("company") or "the company"
    sources, texts = [], []
    if (case.get("jd_text") or "").strip():
        sources.append({"n": 1, "url": case.get("source_url") or None, "title": "Job description",
                        "fetched_at": datetime.now(timezone.utc).isoformat()})
        texts.append(case["jd_text"][:SOURCE_CHARS])
    for url in source_urls(case, list(ctx.inputs.get("urls") or [])):
        if sources and url == case.get("source_url"):
            continue  # the JD text already covers the posting page
        page = await ctx.tools.call("fetch_public_page", f"Reading {urlparse(url).netloc}", url=url)
        if page.get("excerpt"):
            sources.append({"n": len(sources) + 1, "url": page["url"], "title": page.get("title", "")[:300],
                            "fetched_at": page.get("fetched_at", "")})
            texts.append(page["excerpt"][:SOURCE_CHARS])
    if not sources:
        raise PermanentRunError("No readable sources: the case has no job description and no public page could be read.")

    numbered = "\n\n".join(f"[{s['n']}] {s['title']} ({s['url'] or 'stored text'})\n{t}" for s, t in zip(sources, texts))
    prompt = [llm.SystemMessage(ctx.spec.instructions),
              llm.HumanMessage(f"Company: {company}\nRole: {case.get('role') or ''}\n\nSources:\n{numbered}")]
    with llm.usage_meter() as usage:
        draft = await llm.with_structured(chat_model(ctx.spec), BriefDraft).ainvoke(prompt)
    tokens = sum(u["tokens"] for u in usage)
    model = usage[-1]["model"] if usage else ""
    await ctx.log.add("llm", "write_brief", f"Wrote the {company} brief from {len(sources)} source{'s' if len(sources) > 1 else ''}",
                      {"model": model, "sources": [s["url"] for s in sources]}, tokens=tokens)
    draft, dropped = keep_cited(draft, {s["n"] for s in sources})
    if dropped:
        await ctx.log.add("note", "citations", f"Dropped {dropped} claim{'s' if dropped > 1 else ''} without a valid source")
    draft["confidence"] = cap_confidence(draft["confidence"], len(sources))
    brief = CompanyBrief(company=company, sources=sources, **draft)
    saved = await ctx.tools.call("save_artifact", "Saved the company brief", kind="company_brief",
                                 content=brief.model_dump(mode="json"), title=f"{company} brief")
    from app.core import cases
    await asyncio.to_thread(cases.add_event, ctx.user_id, ctx.case_id, "artifact", actor="agent", actor_name="researcher",
                            summary=f"Researcher wrote a brief on {company} ({len(sources)} sources)",
                            data={"artifact_id": saved["id"], "kind": "company_brief"})
    return {"artifact_id": saved["id"], "sources": len(sources), "dropped_claims": dropped, "model": model}
