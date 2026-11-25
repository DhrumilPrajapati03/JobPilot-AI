"""Compile a resume with Tectonic (in the image; plan Day 4) and count its pages.

Tectonic fetches TeX packages on first use and caches them (the Compose volume
`tectonic-cache` keeps that cache across restarts). Untrusted input never reaches here
unescaped: the .tex is the master plus validated, escaped edits. Shell escape stays off.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

TIMEOUT = 180


class CompileError(RuntimeError):
    pass


@dataclass
class Compiled:
    pdf: bytes
    pages: int
    sha256: str

    def __str__(self) -> str:  # what the step trace shows (never the PDF bytes)
        return f"PDF, {self.pages} page(s), sha256 {self.sha256[:12]}"


def available() -> bool:
    return shutil.which("tectonic") is not None


def pages(pdf: bytes) -> int:
    from io import BytesIO
    return len(PdfReader(BytesIO(pdf)).pages)


def compile_tex(tex: str, *, runner=subprocess.run) -> Compiled:
    if not available() and runner is subprocess.run:
        raise CompileError("Tectonic is not installed here; resumes compile inside the JobDots container.")
    with tempfile.TemporaryDirectory(prefix="jobdots-tex-") as tmp:
        src = Path(tmp) / "resume.tex"
        src.write_text(tex, encoding="utf-8")
        result = runner(["tectonic", "-X", "compile", "--untrusted", "--outdir", tmp, str(src)],
                        capture_output=True, text=True, timeout=TIMEOUT, cwd=tmp)
        pdf_path = Path(tmp) / "resume.pdf"
        if result.returncode or not pdf_path.exists():
            errors = [line for line in (result.stderr or "").splitlines() if "error" in line.lower()]
            raise CompileError("LaTeX did not compile: " + ("; ".join(errors[:3]) or (result.stderr or "")[-300:]))
        data = pdf_path.read_bytes()
    return Compiled(data, pages(data), hashlib.sha256(data).hexdigest())
