"""Storage helpers for generated application materials.

The cover letter and LinkedIn DM drafts live in the ``cover_letter`` and
``linkedin_dm`` columns of ``job_applications`` (see
``supabase/migrations/20261006_application_materials.sql``). Databases that
have not run that migration yet keep working: the drafts are packed into the
``notes`` column behind section markers, which is how v1 stored them.
"""

from typing import Any

COVER_MARKER = "=== COVER LETTER ==="
CONNECTION_MARKER = "=== LINKEDIN CONNECTION REQUEST ==="
FOLLOW_UP_MARKER = "=== LINKEDIN DM FOLLOW-UP ==="
NOTES_MARKER = "=== NOTES ==="

_MARKERS = {
    COVER_MARKER: "cover_letter",
    CONNECTION_MARKER: "connection_request",
    FOLLOW_UP_MARKER: "follow_up",
    NOTES_MARKER: "notes",
}

MATERIAL_FIELDS = ("cover_letter", "linkedin_dm", "notes")


def unpack_notes(notes: str | None) -> dict[str, str]:
    """Split a packed ``notes`` value into its sections.

    Notes without any marker are treated as plain user notes.
    """
    sections = {"cover_letter": "", "connection_request": "", "follow_up": "", "notes": ""}
    text = notes or ""
    if not any(marker in text for marker in _MARKERS):
        sections["notes"] = text.strip()
        return sections

    current = "notes"
    buffer: list[str] = []
    for line in text.splitlines():
        if line.strip() in _MARKERS:
            sections[current] = "\n".join(buffer).strip()
            current, buffer = _MARKERS[line.strip()], []
        else:
            buffer.append(line)
    sections[current] = "\n".join(buffer).strip()
    return sections


def pack_notes(notes: str, cover_letter: str, linkedin_dm: dict[str, str]) -> str:
    """Inverse of :func:`unpack_notes`, used when the dedicated columns are missing."""
    parts = [
        f"{COVER_MARKER}\n{cover_letter or ''}",
        f"{CONNECTION_MARKER}\n{linkedin_dm.get('connection_request', '')}",
        f"{FOLLOW_UP_MARKER}\n{linkedin_dm.get('follow_up', '')}",
    ]
    if notes:
        parts.append(f"{NOTES_MARKER}\n{notes}")
    return "\n\n".join(parts)


def normalize_application(row: dict[str, Any]) -> dict[str, Any]:
    """Return the row with ``cover_letter``, ``linkedin_dm`` and plain ``notes``."""
    packed = unpack_notes(row.get("notes"))
    dm = row.get("linkedin_dm") or {}
    return {
        **row,
        "notes": packed["notes"],
        "cover_letter": row.get("cover_letter") or packed["cover_letter"],
        "linkedin_dm": {
            "connection_request": dm.get("connection_request") or packed["connection_request"],
            "follow_up": dm.get("follow_up") or packed["follow_up"],
        },
    }


def is_missing_column_error(error: Exception) -> bool:
    """True when PostgREST rejected a write because a column does not exist."""
    message = str(error)
    return "PGRST204" in message or ("column" in message and "does not exist" in message)


def _to_packed_payload(payload: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    merged = {**normalize_application(current), **payload}
    fallback = {k: v for k, v in payload.items() if k not in MATERIAL_FIELDS}
    fallback["notes"] = pack_notes(
        merged.get("notes") or "",
        merged.get("cover_letter") or "",
        merged.get("linkedin_dm") or {},
    )
    return fallback


def insert_application(supabase, payload: dict[str, Any]) -> dict[str, Any]:
    """Insert a job application, packing materials into notes if needed."""
    try:
        res = supabase.table("job_applications").insert(payload).execute()
    except Exception as e:
        if not is_missing_column_error(e):
            raise
        res = supabase.table("job_applications").insert(_to_packed_payload(payload, {})).execute()
    if not res.data:
        raise RuntimeError("Failed to insert job application.")
    return normalize_application(res.data[0])


def update_application(
    supabase,
    application_id: str,
    user_id: str,
    payload: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    """Update a job application, packing materials into notes if needed.

    ``current`` is the existing row; it supplies the untouched sections when
    the materials have to be re-packed into ``notes``.
    """
    # Writing any material field rewrites notes so legacy packed notes are cleaned up.
    if any(field in payload for field in MATERIAL_FIELDS):
        merged = normalize_application(current)
        payload = {
            "notes": merged["notes"],
            "cover_letter": merged["cover_letter"],
            "linkedin_dm": merged["linkedin_dm"],
            **payload,
        }

    def _write(data: dict[str, Any]):
        return (
            supabase.table("job_applications")
            .update(data)
            .eq("id", application_id)
            .eq("user_id", user_id)
            .execute()
        )

    try:
        res = _write(payload)
    except Exception as e:
        if not is_missing_column_error(e):
            raise
        res = _write(_to_packed_payload(payload, current))
    if not res.data:
        raise LookupError("Job application not found or unauthorized")
    return normalize_application(res.data[0])
