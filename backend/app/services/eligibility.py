"""Deterministic, evidence-carrying eligibility checks before ranking."""
import re

from app.models.user import WorkPreferences
from app.services.job_filters import india_eligibility_flag, NO_SPONSORSHIP_PATTERNS


def seniority(title: str) -> str:
    text = title.lower()
    if re.search(r"\b(senior|sr\.?|staff|principal|director|head|chief|vp)\b|\b(?:tech(?:nical)? |engineering )?lead\b(?! generation)", text):
        return "senior"
    if re.search(r"\b(intern(?:ship)?|trainee|apprentice)\b", text): return "intern"
    if re.search(r"\b(junior|jr\.?|entry[ -]level|graduate|fresher|new grad)\b|\b(?:engineer|sde|swe) (?:i|1)\b", text): return "entry"
    if re.search(r"\b(mid[ -]?(?:level)?|intermediate)\b|\b(?:engineer|sde|swe) (?:ii|2|iii|3)\b", text): return "mid"
    return "unknown"


def experience_requirement(description: str) -> tuple[float | None, str | None]:
    required = []
    for sentence in re.split(r"[\n.;]", description):
        if re.search(r"\b(preferred|nice to have|bonus|desirable|ideally)\b", sentence, re.I):
            continue
        if re.search(r"\b(?:our company|our team|we have|company has|team has)\b", sentence, re.I) and not re.search(r"\b(?:must|required|you have|you bring)\b", sentence, re.I):
            continue
        normalized = sentence.lower()
        for number, word in enumerate(("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty")):
            normalized = re.sub(rf"\b{word}\b", str(number), normalized)
        for match in re.finditer(r"\b(\d{1,2})(?:\s*(?:[-–—]|to)\s*\d{1,2})?\s*\+?\s*-?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:[a-z+#/-]+\s+){0,5}(?:experience|exp\b)", normalized, re.I):
            required.append((float(match[1]), sentence.strip()[:240]))
    return max(required, default=(None, None), key=lambda r: r[0] or 0)


def evaluate_eligibility(posting: dict, prefs: WorkPreferences) -> dict:
    checks = []
    def add(dimension, status, reason, evidence=""):
        checks.append(dict(dimension=dimension, status=status, reason=reason, evidence=evidence[:240]))
    description, title = posting.get("description") or "", posting.get("title") or ""
    location = posting.get("location") or ""
    flag = india_eligibility_flag(posting)
    add("location", "review" if flag and "not confirmed" in flag else "ineligible" if flag else "eligible",
        flag or "The posting's hiring locations include India", location)
    level = seniority(title)
    minimum, evidence = experience_requirement(description)
    if (prefs.career_level in {"entry", "intern"} and level in {"mid", "senior"}) or (prefs.career_level == "mid" and level == "senior"):
        add("seniority", "ineligible", f"This {level} role exceeds your {prefs.career_level} target", title)
    elif prefs.career_level in {"entry", "intern"} and minimum is not None and minimum > (prefs.experience_years if prefs.experience_years is not None else 2):
        add("seniority", "ineligible", f"Requires at least {minimum:g} years of experience; exceeds your early-career target", evidence or "")
    elif minimum is not None and prefs.experience_years is not None and minimum > prefs.experience_years:
        add("seniority", "ineligible", f"Requires {minimum:g} years; you reported {prefs.experience_years:g}", evidence or "")
    elif minimum is not None and prefs.experience_years is None:
        add("seniority", "review", "Set your experience in Preferences to check this requirement", evidence or "")
    elif level == "unknown" and minimum is None and prefs.career_level != "any":
        add("seniority", "review", "Seniority and experience requirements are not stated", title)
    else:
        add("seniority", "eligible", "No conflict with your declared career target", evidence or title)
    if prefs.requires_sponsorship and any(re.search(p, description, re.I) for p in NO_SPONSORSHIP_PATTERNS):
        add("authorization", "ineligible", "The employer excludes sponsorship you require", description)
    else:
        match = re.search(r"(?:must|only|require[sd]?)\b[^.\n]{0,70}(?:authorized|authorised|eligible|right) to work in (?:the )?(india|us|usa|united states|uk|united kingdom|canada)\b", description, re.I)
        if match:
            country = {"us": "united states", "usa": "united states", "uk": "united kingdom"}.get(match[1].lower(), match[1].lower())
            authorized = {c.strip().lower() for c in prefs.authorized_countries}
            add("authorization", "eligible" if country in authorized else "ineligible" if prefs.requires_sponsorship else "review",
                f"Requires work authorization in {country}; " + ("confirmed in Preferences" if country in authorized else "confirm your authorization in Preferences"), match[0])
        else:
            add("authorization", "eligible", "No explicit conflicting authorization requirement found")
    if prefs.remote_only and posting.get("remote") is not True:
        add("work_arrangement", "ineligible" if posting.get("remote") is False else "review", "Remote-only preference: " + ("this role is not remote" if posting.get("remote") is False else "remote work is not confirmed"), location)
    status = "ineligible" if any(c["status"] == "ineligible" for c in checks) else "review" if any(c["status"] == "review" for c in checks) else "eligible"
    return {"status": status, "checks": checks, "seniority": level, "minimum_experience_years": minimum, "policy": "india-v2"}
