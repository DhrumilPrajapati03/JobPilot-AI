"""Answer bank (plan section 5): your approved answers, searched by meaning with pgvector.

* Questions are embedded with the local Ollama model (OLLAMA_EMBED_MODEL); vectors from a
  different model are never compared. If Ollama is down, search falls back to word overlap
  so the Answerer still works (it says so).
* Each save is a new version of the question (same normalized wording and company scope);
  search reads the latest version only. Deleting removes every version.
* Retrieval thresholds (plan): similarity >= 0.9 reuse, 0.75-0.9 adapt, below that generate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.answers.questions import normalize
from app.config import settings
from app.db import get_db

REUSE, ADAPT = 0.9, 0.75
SOURCES = ("legacy", "vault", "reused", "adapted", "generated", "user")
_STOP = {"a", "an", "the", "you", "your", "are", "do", "does", "have", "has", "is", "of", "to", "in", "for", "with", "and",
         "or", "what", "please", "any", "this", "at", "on", "be", "will", "would", "if", "we", "our", "us", "it", "as", "can"}


@dataclass
class Hit:
    id: str
    question: str
    answer: str
    type: str
    source: str
    company_scope: str
    sensitive: bool
    version: int
    similarity: float


def model_ids() -> list[str]:
    base = settings.OLLAMA_EMBED_MODEL.split(":")[0]
    return [base, f"ollama-{base}", settings.OLLAMA_EMBED_MODEL]


def embed(text: str) -> list[float] | None:
    try:
        from app.services.llm import get_embeddings_client
        return get_embeddings_client().embed_query(text)
    except Exception:
        return None


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9+#]+", (text or "").lower()) if w not in _STOP and len(w) > 1}


def overlap(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


_LATEST = """select distinct on (normalized_question, company_scope) id::text, question_text, answer, type, source,
                    company_scope, sensitive, version, embedding, embedding_model
             from public.answer_bank where user_id = %s::uuid and answer <> ''
             order by normalized_question, company_scope, version desc, created_at desc"""


def search(user_id: str, question: str, *, k: int = 3, vector: list[float] | None = None) -> tuple[list[Hit], bool]:
    """Closest saved answers (latest versions). Returns (hits, used_vectors)."""
    vector = vector if vector is not None else embed(question)
    db = get_db(user_id)
    exact = normalize(question)
    if vector is not None:
        rows = db.fetch(f"""with latest as ({_LATEST})
                            select id, question_text, answer, type, source, company_scope, sensitive, version,
                                   1 - (embedding <=> %s::vector) as similarity
                            from latest where embedding is not null and embedding_model = any(%s)
                            order by embedding <=> %s::vector limit %s""",
                        [user_id, str(vector), model_ids(), str(vector), k])
        hits = [Hit(*r[:8], similarity=round(float(r[8]), 4)) for r in rows]
        used = True
    else:
        rows = db.fetch(f"select * from ({_LATEST}) latest", [user_id])
        scored = sorted(((overlap(question, r[1]), r) for r in rows), key=lambda x: -x[0])[:k]
        hits = [Hit(*r[:8], similarity=round(s, 4)) for s, r in scored]
        used = False
    for h in hits:                       # identical wording is a reuse whatever the vectors say
        if normalize(h.question) == exact:
            h.similarity = max(h.similarity, 0.99)
    return sorted(hits, key=lambda h: -h.similarity), used


def save(user_id: str, question: str, answer: str, *, source: str, type_: str = "text", company_scope: str = "",
         sensitive: bool = False, approved: bool = True) -> dict:
    """Store a new version of this question's answer."""
    if source not in SOURCES:
        raise ValueError(f"unknown source {source!r}")
    norm = normalize(question)
    vector = embed(question)
    model = settings.OLLAMA_EMBED_MODEL.split(":")[0] if vector is not None else None
    rows = get_db(user_id).fetch("""
        insert into public.answer_bank (user_id, question_text, normalized_question, answer, type, embedding, embedding_model,
                                        source, version, approved_at, company_scope, sensitive)
        values (%s::uuid, %s, %s, %s, %s, %s::vector, %s, %s,
                coalesce((select max(version) from public.answer_bank where user_id = %s::uuid and normalized_question = %s
                          and company_scope = %s), 0) + 1,
                case when %s then now() end, %s, %s)
        returning id::text, version""",
        [user_id, question.strip()[:1000], norm, answer.strip()[:4000], type_, str(vector) if vector is not None else None, model,
         source, user_id, norm, company_scope, approved, company_scope, sensitive])
    return {"id": rows[0][0], "version": rows[0][1], "embedded": vector is not None}


def history(user_id: str, answer_id: str) -> list[dict]:
    rows = get_db(user_id).fetch("""select b.id::text, b.version, b.answer, b.source, b.approved_at, b.created_at
                                    from public.answer_bank b join public.answer_bank a on a.id = %s::uuid
                                    and a.user_id = b.user_id and a.normalized_question = b.normalized_question
                                    and a.company_scope = b.company_scope
                                    where b.user_id = %s::uuid order by b.version desc""", [answer_id, user_id])
    return [dict(zip(("id", "version", "answer", "source", "approved_at", "created_at"), r)) for r in rows]


def list_latest(user_id: str, q: str = "") -> list[dict]:
    rows = get_db(user_id).fetch(f"""select id, question_text, answer, type, source, company_scope, sensitive, version
                                     from ({_LATEST}) latest where %s = '' or question_text ilike %s or answer ilike %s
                                     order by question_text""", [user_id, q, f"%{q}%", f"%{q}%"])
    keys = ("id", "question", "answer", "type", "source", "company_scope", "sensitive", "version")
    return [dict(zip(keys, r)) for r in rows]


def delete(user_id: str, answer_id: str) -> int:
    """Delete this answer and all its versions."""
    rows = get_db(user_id).fetch("""delete from public.answer_bank b using public.answer_bank a
                                    where a.id = %s::uuid and a.user_id = %s::uuid and b.user_id = a.user_id
                                    and b.normalized_question = a.normalized_question and b.company_scope = a.company_scope
                                    returning b.id""", [answer_id, user_id])
    return len(rows)
