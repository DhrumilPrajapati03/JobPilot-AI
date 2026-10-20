"""Resume rendering engine service.

Implements LaTeX (Tectonic) and HTML (WeasyPrint) dual rendering pipelines.
Supports fallback rendering if LaTeX tools are not installed.
"""

import subprocess
import tempfile
import os
import shutil
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from app.resume_engine.schemas import ResumeContentJSON, RendererType

TEMPLATE_DIR = Path(__file__).parent / "templates"

# LaTeX special character escaping environment
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    block_start_string=r'\BLOCK{',
    block_end_string='}',
    variable_start_string=r'\VAR{',
    variable_end_string='}',
    comment_start_string=r'\#{',
    comment_end_string='}',
    trim_blocks=True,
    autoescape=False,
)

# Standard HTML environment
html_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=True,
)


def _escape_latex(text: str) -> str:
    """Escape special LaTeX characters in content strings."""
    replacements = {
        '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#',
        '_': r'\_', '{': r'\{', '}': r'\}',
        '~': r'\textasciitilde{}', '^': r'\^{}',
        '\\': r'\textbackslash{}',
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text


def _deep_escape_latex(obj):
    """Recursively escape LaTeX special chars in all string values."""
    if isinstance(obj, str):
        return _escape_latex(obj)
    elif isinstance(obj, list):
        return [_deep_escape_latex(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: _deep_escape_latex(v) for k, v in obj.items()}
    return obj


async def render_resume_pdf(content: ResumeContentJSON) -> tuple[bytes, RendererType]:
    """Unified entry point. Routes to correct renderer by template type.

    Returns:
        A tuple of (pdf_bytes, actual_renderer_used)
    """
    if content.renderer == RendererType.LATEX:
        # Check if tectonic exists in PATH
        if shutil.which("tectonic") is None:
            print("⚠️ Warning: Tectonic LaTeX engine not found in system path. Falling back to HTML/WeasyPrint.")
            return await _render_html(content), RendererType.HTML
        try:
            return await _render_latex(content), RendererType.LATEX
        except Exception as e:
            print(f"⚠️ Warning: Tectonic compile failed ({str(e)}). Falling back to HTML/WeasyPrint.")
            return await _render_html(content), RendererType.HTML
    else:
        return await _render_html(content), RendererType.HTML


async def _render_latex(content: ResumeContentJSON) -> bytes:
    """Renders LaTeX Jinja2 template and compiles using Tectonic."""
    template_path = f"latex/{content.template_id}.tex.j2"
    template = jinja_env.get_template(template_path)

    # Deep copy and escape fields for LaTeX compiler safety
    data = content.model_dump()
    data = _deep_escape_latex(data)

    filled_tex = template.render(**data)

    with tempfile.TemporaryDirectory() as tmpdir:
        tex_file = Path(tmpdir) / "resume.tex"
        tex_file.write_text(filled_tex, encoding="utf-8")

        result = subprocess.run(
            ["tectonic", str(tex_file)],
            capture_output=True,
            cwd=tmpdir,
            timeout=60,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Tectonic compile failed:\n{result.stderr.decode()}"
            )

        pdf_path = tex_file.with_suffix(".pdf")
        return pdf_path.read_bytes()


async def _render_html(content: ResumeContentJSON) -> bytes:
    """Renders HTML Jinja2 template and converts using WeasyPrint."""
    try:
        from weasyprint import HTML as WeasyprintHTML
    except (OSError, ImportError) as e:
        raise RuntimeError(
            "WeasyPrint external GTK libraries are missing or could not be loaded.\n"
            "To resolve this on Windows:\n"
            "1. Download and run the GTK3 installer for Windows (e.g. from MSYS2 or courtbouillon).\n"
            "2. Ensure the GTK bin folder is added to your System PATH environment variables.\n"
            "Alternatively, run the app inside the provided Docker container."
        ) from e

    template_path = f"html/{content.template_id}.html.j2"
    template = html_jinja_env.get_template(template_path)

    filled_html = template.render(**content.model_dump())

    pdf_bytes = WeasyprintHTML(string=filled_html).write_pdf()
    return pdf_bytes
