"""Bounded upload reads, archive inspection, and local storage of originals."""
import io
import re
import uuid
import zipfile
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import settings

MAX_RESUME_BYTES = 10 * 1024 * 1024


def save_upload(bucket: str, owner_id: str, filename: str, data: bytes) -> Path:
    """Store an uploaded original under FILE_STORAGE_DIR/<bucket>/<owner>/ and return its path.

    Path parts are sanitised so a crafted filename or id cannot leave the storage folder.
    """
    safe = lambda part: re.sub(r"[^A-Za-z0-9._-]", "_", part)[:120].lstrip(".") or "file"
    folder = Path(settings.FILE_STORAGE_DIR).resolve() / safe(bucket) / safe(owner_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4()}_{safe(filename)}"
    path.write_bytes(data)
    return path


async def read_resume(file: UploadFile) -> tuple[bytes, str]:
    filename = (file.filename or "").replace("\\", "/").split("/")[-1]
    suffix = filename.rsplit(".", 1)[-1].lower()
    if suffix not in {"pdf", "docx"}:
        raise HTTPException(400, "Please upload a PDF or DOCX file.")
    data = await file.read(MAX_RESUME_BYTES + 1)
    if len(data) > MAX_RESUME_BYTES:
        raise HTTPException(413, "Resume files must be at most 10 MiB.")
    if suffix == "pdf":
        if not data.startswith(b"%PDF-"):
            raise HTTPException(400, "The file does not have a valid PDF signature.")
    else:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = archive.infolist()
                if (len(entries) > 2000 or sum(e.file_size for e in entries) > 30 * 1024 * 1024
                        or any(e.flag_bits & 1 for e in entries)):
                    raise HTTPException(413, "The DOCX archive is encrypted or expands beyond supported limits.")
                if "word/document.xml" not in archive.namelist():
                    raise HTTPException(400, "The file is not a Word DOCX document.")
        except zipfile.BadZipFile as exc:
            raise HTTPException(400, "The DOCX archive is invalid.") from exc
    return data, filename
