"""Applicant: fills the form in your Chrome through the side panel (plan section 2.1, Day 8).

The filling itself runs in the extension (content/form-engine.js, exact options only, never
submits, never ticks consents). This module is the server side:

* `resume_file` / `document`: the case's latest tailored resume PDF that you haven't
  rejected, with its sha256 so the extension can prove the file it attaches is that one;
* `is_resume_field`: which file field takes the resume;
* `record_fill`: one timeline event per fill (what was filled, what to check).
"""
from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

from app.config import settings
from app.core import cases
from app.db import get_db

MAX_BYTES = 2 * 1024 * 1024          # the form engine's limit for an attachment
RESUME_LABEL = re.compile(r"\b(resume|résumé|cv|curriculum vitae)\b", re.I)
OTHER_FILE = re.compile(r"\b(cover|letter|portfolio|transcript|certificate|photo|picture|passport|sample|writing)\b", re.I)


def resume_file(user_id: str, case_id: str) -> dict | None:
    """The tailored PDF Applicant would attach: newest version you haven't rejected."""
    rows = get_db(user_id).fetch("""select id::text, content from public.artifact where case_id = %s::uuid and user_id = %s::uuid
                                    and kind = 'resume_version' and not legacy and coalesce(content->>'status', '') <> 'rejected'
                                    and content->'pdf' is not null and content->'pdf' <> 'null'::jsonb
                                    order by version desc limit 1""", [case_id, user_id])
    if not rows:
        return None
    artifact_id, content = rows[0]
    from app.answers import profile
    try:
        name = profile.load().full_name or "Resume"
    except Exception:
        name = "Resume"
    safe = "".join(c for c in name if c.isalnum() or c in " -").strip().replace(" ", "_") or "Resume"
    return {"artifact_id": artifact_id, "filename": f"{safe}_Resume.pdf", "path": content["pdf"]["path"],
            "sha256": content["pdf"]["sha256"], "approved": content.get("status") == "approved"}


def document(user_id: str, case_id: str) -> dict | None:
    """The PDF itself, checked against the hash Tailor recorded. None when missing or changed."""
    meta = resume_file(user_id, case_id)
    if meta is None:
        return None
    root = Path(settings.FILE_STORAGE_DIR).resolve()
    path = (root / meta["path"]).resolve()
    if root not in path.parents or not path.is_file():
        return None
    data = path.read_bytes()
    if len(data) > MAX_BYTES or not data.startswith(b"%PDF-") or hashlib.sha256(data).hexdigest() != meta["sha256"]:
        return None
    return {"name": meta["filename"], "sha256": meta["sha256"], "size_bytes": len(data),
            "pdf_base64": base64.b64encode(data).decode("ascii"), "artifact_id": meta["artifact_id"],
            "approved": meta["approved"]}


def is_resume_field(label: str, file_labels: list[str]) -> tuple[bool, bool]:
    """(takes the resume, only a guess). A field that says resume/CV takes it; otherwise the
    first file field takes it when no field says resume and it isn't a cover letter etc."""
    if RESUME_LABEL.search(label or ""):
        return True, False
    if OTHER_FILE.search(label or "") or any(RESUME_LABEL.search(other or "") for other in file_labels):
        return False, False
    unnamed = [other for other in file_labels if not OTHER_FILE.search(other or "")]
    return bool(unnamed) and unnamed[0] == label, True


WORDS = {"filled": "filled", "review": "to check", "preserved": "already filled", "missing": "still empty",
         "invalid": "rejected by the form", "skipped": "not filled"}


def record_fill(user_id: str, case_id: str, url: str, results: list[dict], attached: bool) -> dict:
    """One timeline event for a fill, in plain words."""
    counts: dict[str, int] = {}
    for r in results:
        counts[r.get("outcome", "skipped")] = counts.get(r.get("outcome", "skipped"), 0) + 1
    parts = [f"{n} {WORDS.get(o, o)}" for o, n in sorted(counts.items(), key=lambda x: list(WORDS).index(x[0]) if x[0] in WORDS else 99)]
    host = re.sub(r"^https?://([^/]+).*$", r"\1", url or "")[:100]
    summary = f"Applicant filled the form{' on ' + host if host else ''}: {', '.join(parts) or 'nothing to fill'}" + \
              ("; attached your tailored resume" if attached else "")
    check = [r.get("label", "")[:120] for r in results if r.get("outcome") in ("review", "missing", "invalid")][:10]
    return cases.add_event(user_id, case_id, "form_filled", actor="agent", actor_name="applicant", summary=summary[:300],
                           data={"url": url[:500], "counts": counts, "attached_resume": attached, "check": check})
