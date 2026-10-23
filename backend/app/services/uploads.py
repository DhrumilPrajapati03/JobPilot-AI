"""Bounded upload reads and archive inspection before document parsers run."""
import io
import zipfile

from fastapi import HTTPException, UploadFile

MAX_RESUME_BYTES = 10 * 1024 * 1024


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
