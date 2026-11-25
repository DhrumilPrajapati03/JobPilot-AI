"""Typed artifacts (plan sections 5 and 6): experts emit validated JSON, never HTML; the UI
renders each kind as a card. Saving validates content against the kind's model, so a
malformed or extra-field payload never reaches the case."""
from __future__ import annotations

from typing import Literal

from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.db import get_db


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(Strict):
    n: int = Field(ge=1, le=20)
    url: HttpUrl | None = None   # None for text stored on the case (the job description)
    title: str = Field(default="", max_length=300)
    fetched_at: str = ""


class Claim(Strict):
    text: str = Field(min_length=1, max_length=600)
    sources: list[int] = Field(min_length=1, max_length=8)   # numbers from `sources`


class CompanyBrief(Strict):
    company: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=1200)
    product: list[Claim] = Field(default_factory=list, max_length=8)
    stage: list[Claim] = Field(default_factory=list, max_length=4)      # funding, size, maturity
    recent_news: list[Claim] = Field(default_factory=list, max_length=8)
    tech_stack: list[Claim] = Field(default_factory=list, max_length=12)
    fit_notes: list[Claim] = Field(default_factory=list, max_length=8)  # why the role fits (or not)
    open_questions: list[str] = Field(default_factory=list, max_length=8)
    sources: list[Source] = Field(min_length=1, max_length=20)
    confidence: Literal["low", "medium", "high"] = "low"


KINDS: dict[str, type[BaseModel]] = {"company_brief": CompanyBrief}


class ArtifactError(ValueError):
    pass


def check_citations(brief: CompanyBrief) -> list[str]:
    """Every claim must cite sources that exist in the brief."""
    known = {s.n for s in brief.sources}
    problems = []
    for field in ("product", "stage", "recent_news", "tech_stack", "fit_notes"):
        for claim in getattr(brief, field):
            missing = sorted(set(claim.sources) - known)
            if missing:
                problems.append(f"{field}: '{claim.text[:60]}' cites missing source(s) {missing}")
    return problems


def save(user_id: str, case_id: str | None, kind: str, content: dict, *, agent: str, title: str = "") -> dict:
    model = KINDS.get(kind)
    if model is None:
        raise ArtifactError(f"No schema for artifact kind {kind!r} yet")
    value = model.model_validate(content)
    if isinstance(value, CompanyBrief) and (problems := check_citations(value)):
        raise ArtifactError("; ".join(problems))
    data = value.model_dump(mode="json")

    def work(conn):
        version = conn.execute("""select coalesce(max(version), 0) + 1 from public.artifact
                                  where case_id is not distinct from %s::uuid and kind = %s""", [case_id, kind]).fetchone()[0]
        row = conn.execute("""insert into public.artifact (user_id, case_id, kind, version, title, content, created_by)
                              values (%s::uuid, %s::uuid, %s, %s, %s, %s, %s) returning id, version""",
                           [user_id, case_id, kind, version, title or kind.replace("_", " ").capitalize(), Jsonb(data), agent]).fetchone()
        return {"id": str(row[0]), "kind": kind, "version": row[1]}

    return get_db(user_id).run(work)


def latest(user_id: str, case_id: str, kind: str) -> dict | None:
    rows = get_db(user_id).fetch("""select id, version, content, created_at from public.artifact
                                    where case_id = %s::uuid and kind = %s and not legacy
                                    order by version desc limit 1""", [case_id, kind])
    if not rows:
        return None
    return {"id": str(rows[0][0]), "version": rows[0][1], "content": rows[0][2], "created_at": rows[0][3]}
