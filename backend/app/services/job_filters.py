"""Skip-rule evaluation for job postings.

Used by the application pipeline (to warn about pasted jobs) and, in job
discovery, to drop postings before any LLM call is spent on them.
"""

import re

from app.models.user import WorkPreferences


def india_eligibility_flag(posting: dict) -> str | None:
    """Fail closed: remote alone is not evidence that hiring includes India.

    Location is the board's hiring scope; company offices and incidental mentions
    of India in the description must not override a restricted location list.
    """
    location = (posting.get("location") or "").lower().strip()
    description = (posting.get("description") or "").lower()
    exclusion = r"\b(?:excluding|except|not (?:available|open) (?:in|to)|cannot hire (?:in|from))\s+(?:candidates (?:in|from)\s+)?india\b|\bindia\s+(?:is\s+)?(?:excluded|not eligible)\b"
    if re.search(exclusion, location + "\n" + description):
        return "This role explicitly excludes applicants based in India"
    # Explicit foreign work authorization is incompatible even with a global label.
    if re.search(r"\b(?:must|only)\b[^.\n]{0,70}\b(?:authorized|authorised|eligible|right) to work in (?:the )?(?:us|usa|united states|uk|united kingdom|canada|europe|eu)\b", description):
        return "Requires work authorization outside India"
    foreign = r"(?:us|usa|united states|uk|united kingdom|canada|europe|eu|latin america|latam|brazil|argentina|colombia)"
    if re.search(rf"\b{foreign}[- ]only\b|\b(?:must be|only candidates)\s+(?:based|located|residing)\s+in (?:the )?{foreign}\b", description):
        return "Restricts applicants to locations outside India"
    scope = re.sub(r"^remote[\s,/:–—-]*", "", location).strip()
    if re.search(r"\bindia\b", scope) or scope in {"in", "ind"}:
        return None
    if re.search(r"\b(?:bengaluru|bangalore|hyderabad|pune|mumbai|chennai|delhi|noida|gurugram|gurgaon|ahmedabad|kolkata|kochi|indore|jaipur)\b", scope):
        return None
    if posting.get("remote") is not False and scope in {"worldwide", "anywhere", "global", "work from anywhere", "anywhere in the world"}:
        return None
    # An explicit location list is authoritative. APAC/Asia alone doesn't confirm
    # that the employer can hire in every country in the region.
    if scope:
        return "Hiring in India is not confirmed by this role's eligible locations"
    if posting.get("remote") is not False and re.search(r"\b(?:work from anywhere in the world|open to candidates (?:worldwide|in india)|hire (?:in|from) india|based (?:anywhere )?in india)\b", description):
        return None
    return "Hiring in India is not confirmed; remote alone does not establish eligibility"

# Phrases that mean the employer won't sponsor a work visa.
NO_SPONSORSHIP_PATTERNS = [
    r"\bno (visa )?sponsorship\b",
    r"\b(unable|not able|cannot|can't|will not|won't) (to )?(provide |offer )?(visa )?sponsor",
    r"\bsponsorship (is )?not (available|provided|offered)\b",
    r"\bwithout (the need for )?(current or future )?(visa )?sponsorship\b",
    r"\bmust (be|have) (authorized|authorised|eligible) to work\b.*\bwithout\b.*\bsponsorship\b",
]


def _contains_phrase(text: str, phrase: str) -> bool:
    phrase = phrase.strip().lower()
    if not phrase:
        return False
    return re.search(rf"(?<![\w]){re.escape(phrase)}(?![\w])", text) is not None


def evaluate_skip_rules(
    prefs: WorkPreferences | dict | None,
    company: str,
    jd_text: str = "",
    analysis: dict | None = None,
) -> list[str]:
    """Return human-readable reasons this job breaks the user's skip rules (empty = clean)."""
    if prefs is None:
        return []
    prefs = prefs if isinstance(prefs, WorkPreferences) else WorkPreferences.model_validate(prefs or {})
    analysis = analysis or {}
    text = " ".join([
        jd_text or "",
        " ".join(analysis.get("keywords") or []),
        " ".join(analysis.get("required_skills") or []),
    ]).lower()
    reasons: list[str] = []

    company_lower = (company or "").strip().lower()
    for blocked in prefs.blocked_companies:
        b = blocked.strip().lower()
        if b and company_lower and (b == company_lower or _contains_phrase(company_lower, b)):
            reasons.append(f"{company} is on your blocked companies list")
            break

    hits = [kw for kw in prefs.skip_keywords if _contains_phrase(text, kw)]
    if hits:
        reasons.append("Mentions " + ", ".join(f"“{h}”" for h in hits))

    if prefs.requires_sponsorship and any(re.search(p, text) for p in NO_SPONSORSHIP_PATTERNS):
        reasons.append("Says it doesn't sponsor visas, and you need sponsorship")

    if prefs.remote_only and analysis.get("remote") is False:
        reasons.append("Not a remote role, and you're looking for remote only")

    return reasons
