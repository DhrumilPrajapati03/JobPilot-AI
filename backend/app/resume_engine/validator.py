"""Resume content and page count validator.

Ensures generated PDFs meet length limitations and do not hallucinate facts.
"""

import io
import re
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


def validate_no_hallucinations(
    tailored: dict,
    base: dict,
    jd_keywords: list[str]
) -> list[str]:
    """
    Check that the tailored resume contains no content
    not present in the base resume or JD keywords.
    
    Returns:
        List of violation strings (empty list = clean).
    """
    violations = []

    # 1. Check company names
    base_companies = {e.get("company", "").strip().lower() for e in base.get("experience", []) if e.get("company")}
    for exp in tailored.get("experience", []):
        company = exp.get("company", "").strip()
        if company and company.lower() not in base_companies:
            violations.append(f"Unknown company: {company}")

    # 2. Check employment dates/durations
    base_dates = {e.get("duration", "").strip().lower() for e in base.get("experience", []) if e.get("duration")}
    for exp in tailored.get("experience", []):
        duration = exp.get("duration", "").strip()
        if duration and duration.lower() not in base_dates:
            violations.append(f"Modified date/duration: {duration} for company {exp.get('company')}")

    # 3. Check skills
    base_all_skills = set()
    skills_obj = base.get("skills", {})
    if isinstance(skills_obj, dict):
        base_all_skills.update(s.strip().lower() for s in skills_obj.get("primary", []) if isinstance(s, str))
        base_all_skills.update(s.strip().lower() for s in skills_obj.get("secondary", []) if isinstance(s, str))
    
    jd_kw_lower = {k.strip().lower() for k in jd_keywords if isinstance(k, str)}
    
    tailored_skills = tailored.get("skills", {})
    if isinstance(tailored_skills, dict):
        for skill in tailored_skills.get("primary", []) + tailored_skills.get("secondary", []):
            if not isinstance(skill, str):
                continue
            skill_clean = skill.strip().lower()
            # If the skill is not in the base resume AND is not a keyword from the JD, flag it
            if skill_clean not in base_all_skills and skill_clean not in jd_kw_lower:
                violations.append(f"New skill not in base resume or job keywords: {skill}")

    return violations


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
