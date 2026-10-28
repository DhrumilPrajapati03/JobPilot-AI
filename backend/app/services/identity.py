"""Source-linked, user-confirmed resume facts. Never infer confirmation from AI."""
import hashlib
import json

from app.models.resume import Resume


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def source_content(resume: dict) -> dict:
    return Resume.model_validate(resume).model_dump(mode="json", exclude={"id", "user_id", "version", "created_at", "updated_at"})


def extract_facts(resume: dict) -> tuple[str, list[dict]]:
    source = source_content(resume)
    facts = []
    def add(kind, path, value):
        if value:
            facts.append({"id": digest([kind, path, value]), "kind": kind, "source_path": path, "value": value})
    add("identity", "name", source["name"])
    add("summary", "summary", source["summary"])
    add("headline", "headline", source["headline"])
    for group in ("primary", "secondary"):
        for i, skill in enumerate(source["skills"][group]):
            add("skill", f"skills.{group}.{i}", skill)
    for group, kind in (("experience", "experience"), ("projects", "project"), ("education", "education"), ("certifications", "certification")):
        for i, value in enumerate(source[group]):
            if any(value.values()):
                add(kind, f"{group}.{i}", value)
    return digest(source), facts


def load_vault(db, uid: str, resume: dict | None = None) -> dict:
    if resume is None:
        rows = db.table("resumes").select("*").eq("user_id", uid).eq("version", "base").execute().data
        resume = rows[0] if rows else {}
    source_digest, facts = extract_facts(resume)
    rows = db.table("identity_confirmations").select("fact_id,confirmed_at").eq("user_id", uid).eq("source_digest", source_digest).execute().data
    confirmed = {r["fact_id"]: r.get("confirmed_at") for r in rows}
    for fact in facts:
        fact["confirmed"] = fact["id"] in confirmed
        fact["confirmed_at"] = confirmed.get(fact["id"])
    count = sum(f["confirmed"] for f in facts)
    return {"source_digest": source_digest, "facts": facts, "confirmed_count": count, "total": len(facts),
            "complete": bool(facts) and count == len(facts), "verification": "user_confirmed"}


def attach_confirmation(profile, vault):
    profile.confirmation = {key: vault[key] for key in ("source_digest", "confirmed_count", "total", "complete")}
    profile.confirmed_evidence = " ".join(json.dumps(f["value"], ensure_ascii=False) for f in vault["facts"] if f["confirmed"])
    return profile
