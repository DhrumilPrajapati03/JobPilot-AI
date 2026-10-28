"""Resume content and page count validator.

Ensures generated PDFs meet length limitations and do not hallucinate facts.
"""

import io
import re
from pypdf import PdfReader

def validate_page_count(pdf_bytes: bytes) -> int:
    """Return the number of pages in the rendered PDF."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return len(reader.pages)
    except Exception as e:
        print(f"Warning: Failed to parse PDF page count: {str(e)}")
        return 1


def validate_no_hallucinations(tailored: dict, base: dict, jd_keywords: list[str]) -> list[str]:
    """Check fixed facts and unsupported skill/numeric claims against the base.

    Job keywords describe an employer's needs; they never authorize a claim.
    Prose still requires human review; this is not a proof of semantic truth.
    """
    import json
    from collections import Counter
    from app.services.job_matching import _norm, TECH_TERMS, _mentions
    violations = []
    canonical = lambda value: json.dumps(value, sort_keys=True, ensure_ascii=False)
    numbers = lambda text: set(re.findall(r"(?<![\w])\d+(?:[.,]\d+)?(?:%|x|\+)?", text))
    text = lambda value: json.dumps(value, ensure_ascii=False)
    def check_numbers(value, original, label):
        if numbers(text(value)) - numbers(text(original)):
            violations.append(f"Unsupported numeric claim in {label}")
    base_skill_values = [s for group in ('primary', 'secondary') for s in (base.get('skills') or {}).get(group, [])]
    # A skill can also be evidenced in a source bullet/project, not only a tag.
    source_text = text(base)
    source_norm = f" {_norm(source_text)} "
    allowed = {_norm(s) for s in base_skill_values}
    for term in TECH_TERMS:
        normalized = _norm(term)
        if _mentions(normalized, source_norm, source_text): allowed.add(normalized)
    for group in ('primary', 'secondary'):
        for skill in (tailored.get('skills') or {}).get(group, []):
            if _norm(skill) not in allowed:
                violations.append(f"New skill not supported by base resume: {skill}")
    # Employment identities are paired, so swapping dates between employers fails.
    originals = {(e.get('company','').strip().lower(), e.get('role','').strip().lower(), e.get('duration','').strip().lower()): e for e in base.get('experience', [])}
    for e in tailored.get('experience', []):
        key = (e.get('company','').strip().lower(), e.get('role','').strip().lower(), e.get('duration','').strip().lower())
        if key not in originals:
            violations.append('Modified employment company, role or duration')
        else:
            check_numbers(e.get('bullets', []), originals[key].get('bullets', []), 'experience bullets')
    if len(tailored.get('experience', [])) > len(base.get('experience', [])):
        violations.append('Added employment entry')
    for group in ('education', 'certifications'):
        allowed_entries = Counter(canonical(e) for e in base.get(group, []))
        output_entries = Counter(canonical(e) for e in tailored.get(group, []))
        if output_entries - allowed_entries:
            violations.append(f'Added or modified {group} credential')
    projects = {p.get('name','').strip().lower(): p for p in base.get('projects', [])}
    for project in tailored.get('projects', []):
        original = projects.get(project.get('name','').strip().lower())
        if original is None:
            violations.append('Added or renamed project')
        else:
            check_numbers(project, original, 'project')
            if {_norm(t) for t in project.get('tech', [])} - {_norm(t) for t in original.get('tech', [])}:
                violations.append('Added project technology')
    check_numbers([tailored.get('summary',''), tailored.get('headline','')], base, 'summary/headline')
    output_text = text(tailored)
    output_norm = f" {_norm(output_text)} "
    for term in TECH_TERMS:
        normalized = _norm(term)
        if _mentions(normalized, output_norm, output_text) and normalized not in allowed:
            violations.append(f'Unsupported technology claim: {term}')
    return list(dict.fromkeys(violations))


def calculate_ats_score(tailored: dict, jd_analysis: dict) -> tuple[float, list[str]]:
    """Calculate keyword match score between tailored resume and JD.

    Returns:
        A tuple of (score_out_of_100, list_of_missing_keywords)
    """
    # Compile text representation of resume
    tailored_text_parts = [
        tailored.get("summary", ""),
        tailored.get("headline", ""),
    ]
    
    for exp in tailored.get("experience", []):
        tailored_text_parts.append(exp.get("role", ""))
        tailored_text_parts.extend(exp.get("bullets", []))
        
    for proj in tailored.get("projects", []):
        tailored_text_parts.append(proj.get("name", ""))
        tailored_text_parts.append(proj.get("description", ""))
        tailored_text_parts.extend(proj.get("tech", []))
        
    skills = tailored.get("skills", {})
    if isinstance(skills, dict):
        tailored_text_parts.extend(skills.get("primary", []))
        tailored_text_parts.extend(skills.get("secondary", []))
        
    resume_text = _normalise(" ".join(t for t in tailored_text_parts if isinstance(t, str)))
    resume_words = set(resume_text.split())

    # Merge keywords and required_skills for a broader list
    jd_keywords: set[str] = set()
    for field in ("keywords", "required_skills"):
        for kw in jd_analysis.get(field) or []:
            if isinstance(kw, str) and (term := _normalise(kw)) and term not in NON_RESUME_TERMS:
                jd_keywords.add(term)

    if not jd_keywords:
        return 100.0, []

    missing = sorted(kw for kw in jd_keywords if not _keyword_present(kw, resume_text, resume_words))
    score = (len(jd_keywords) - len(missing)) / len(jd_keywords) * 100.0
    return round(score, 1), missing


# Work arrangement and similar terms describe the job, not the candidate, so a resume
# can't (and shouldn't) "contain" them.
NON_RESUME_TERMS = {
    "remote", "hybrid", "onsite", "on site", "in office", "full time", "part time",
    "contract", "freelance", "internship", "immediate joiner",
}
_STOPWORDS = {"and", "or", "of", "the", "a", "an", "in", "with", "for", "to", "on", "at", "based", "experience", "years", "year"}
_DASHES = re.compile(r"[\u2010-\u2015\u2212\-_/]")


def _normalise(text: str) -> str:
    """Lowercase, drop parentheticals like "(2-4 years)", unify unicode dashes, collapse spaces."""
    text = re.sub(r"\([^)]*\)", " ", text.lower())
    text = _DASHES.sub(" ", text)
    text = re.sub(r"[^\w+#.\s]", " ", text)
    return " ".join(w.strip(".") for w in text.split() if w.strip("."))


def _keyword_present(keyword: str, resume_text: str, resume_words: set[str]) -> bool:
    """A keyword counts if the phrase appears, or every meaningful word in it does."""
    if f" {keyword} " in f" {resume_text} ":
        return True
    words = [w for w in keyword.split() if w not in _STOPWORDS and len(w) > 1]
    return bool(words) and all(w in resume_words for w in words)
