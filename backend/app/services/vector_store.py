"""Resume section embeddings in Postgres (pgvector), from local Ollama embeddings.

Replaces the local Chroma store (plan Day 1). Rows are keyed by owner and embedding
model and carry a digest of the base resume they came from, so a changed resume or
model is re-indexed on the next search. Every query filters by owner.
"""
import json

from app.db import get_db
from app.models.resume import Resume
from app.services.identity import digest, source_content
from app.services.llm import get_embeddings


def _sections(resume: Resume) -> list[tuple[str, str, dict]]:
    """(section_type, text, metadata) chunks. Bullets are separate for granular matches."""
    out: list[tuple[str, str, dict]] = []
    if resume.summary:
        out.append(("summary", resume.summary, {}))
    for exp_idx, exp in enumerate(resume.experience):
        for bullet_idx, bullet in enumerate(exp.bullets):
            out.append(("experience", bullet, {"company": exp.company, "role": exp.role,
                                               "experience_index": exp_idx, "bullet_index": bullet_idx}))
    for proj_idx, proj in enumerate(resume.projects):
        text = f"Project: {proj.name}. Description: {proj.description}. Tech: {', '.join(proj.tech)}"
        out.append(("project", text, {"project_name": proj.name, "project_index": proj_idx}))
    if resume.skills.primary:
        out.append(("skills_primary", "Primary Skills: " + ", ".join(resume.skills.primary), {}))
    if resume.skills.secondary:
        out.append(("skills_secondary", "Secondary Skills: " + ", ".join(resume.skills.secondary), {}))
    return out


def _vector(values) -> str:
    return "[" + ",".join(repr(float(v)) for v in values) + "]"


def embed_resume(user_id: str, resume: Resume) -> None:
    """Replace the owner's section embeddings for the current model in one statement."""
    model_id, embeddings = get_embeddings()
    sections = _sections(resume)
    source = digest(source_content(resume.model_dump()))
    vectors = embeddings.embed_documents([text for _, text, _ in sections]) if sections else []
    rows, params = [], [user_id, model_id]
    for (section_type, text, metadata), vec in zip(sections, vectors):
        rows.append("(%s::uuid, %s, %s, %s, %s, %s::jsonb, %s::vector)")
        params += [user_id, model_id, source, section_type, text, json.dumps(metadata), _vector(vec)]
    query = "with gone as (delete from public.resume_sections where user_id = %s::uuid and model = %s) "
    if rows:
        query += ("insert into public.resume_sections (user_id, model, source_digest, section_type, content, metadata, embedding) "
                  "values " + ", ".join(rows))
    else:
        query += "select 1"
    get_db().fetch(query, params)


def search_relevant(query: str, user_id: str, top_k: int = 5) -> list[dict]:
    """Resume chunks closest to ``query`` (cosine distance), for this owner only.

    Re-indexes first when the base resume or the embedding model changed.
    """
    db = get_db()
    model_id, embeddings = get_embeddings()
    rows = db.table("resumes").select("*").eq("user_id", user_id).eq("version", "base").execute().data
    if not rows:
        db.fetch("delete from public.resume_sections where user_id = %s::uuid", [user_id])
        return []
    source = digest(source_content(rows[0]))
    indexed = db.fetch("select 1 from public.resume_sections where user_id = %s::uuid and model = %s and source_digest = %s limit 1",
                       [user_id, model_id, source])
    if not indexed:
        embed_resume(user_id, Resume.model_validate(rows[0]))
    found = db.fetch(
        """select content, section_type, metadata, embedding <=> %s::vector as distance
           from public.resume_sections where user_id = %s::uuid and model = %s
           order by distance limit %s""",
        [_vector(embeddings.embed_query(query)), user_id, model_id, int(top_k)],
    )
    return [{"text": text, "metadata": {**(metadata or {}), "user_id": user_id, "section_type": section_type},
             "distance": float(distance)} for text, section_type, metadata, distance in found]
