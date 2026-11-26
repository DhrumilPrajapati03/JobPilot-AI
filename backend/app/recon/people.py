"""People from public search results: parse, check the company, classify, score (pure, no I/O).

A LinkedIn result becomes a person only with **evidence that they work at the company now**:
the result title names the company as a segment ("Name - Headline - Company | LinkedIn",
"Name - ML Engineer at Company") or the profile snippet says "Experience: Company". The
company must match exactly after legal and generic suffixes are dropped, so "Acme
Infotech" is not "Acme AI". Snippets from posts are only trusted in the first person
("I'm starting a new position as … at Company"), because posts often describe someone else.

LinkedIn pages are never opened: names and titles come from the search result only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from app.services.referrals import company_key

ROLE_CLASSES = ("recruiter", "hiring_manager", "ceo", "cto", "employee")
_GENERIC = {"ai", "labs", "lab", "technologies", "technology", "tech", "hq", "india", "io", "app", "software",
            "systems", "group", "global", "company", "co", "corp", "corporation", "inc", "ltd", "llc", "pvt",
            "private", "limited", "solutions", "services", "the"}
_SLUG = re.compile(r"^https://(?:[a-z]{2,3}\.|www\.)?linkedin\.com/in/([A-Za-z0-9\-_%]{3,100})/?(?:[?#].*)?$")
_NAME = re.compile(r"^[^\W\d_][^\W\d_'.\-]*(?:[ '.\-]+[^\W\d_][^\W\d_'.\-]*\.?){0,4}$")
_EXPERIENCE = re.compile(r"Experience:\s*([^·|]+?)\s*(?:·|$)")
_AT = re.compile(r"^(.+?)\s+(?:@|at)\s+(.+)$", re.I)
_FIRST_PERSON = re.compile(r"\bI(?:'m| am| have| will| was|’m)?\b[^.!?]{0,80}?\bas (?:an?|the|our) (.{3,70}?)\s+(?:at|@)\s+"
                           r"([A-Z0-9][\w&.\-]*(?:\s+[A-Z0-9][\w&.\-]*){0,3})")
_LEAD = re.compile(r"^(?:as an?|i am an?|i'm an?|i’m an?)\s+(.{3,60}?)\s+(?:at|@)\s+", re.I)
_LEAD_SHORT = re.compile(r"^(.{3,60}?)\s+(?:with|at|@|building|helping|focused|specializing|passionate)\b", re.I)
_TECH = re.compile(r"engineer|engineering|developer|scientist|science|machine learning|\bml\b|\bai\b|\bllms?\b|data|"
                   r"research|\bsde\b|\bfde\b|architect|software|platform|infrastructure|backend|frontend|full[- ]?stack|"
                   r"devops|\bmlops\b|inference|technical|technology|\bcto\b|programmer|deep learning|nlp|vision", re.I)
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]+")


def core_company(name: str) -> str:
    """Company identity for matching: lowercase, no legal or generic suffix words, no TLD."""
    text = re.sub(r"\b([a-z0-9-]+)\.(?:ai|io|com|co|in|app|dev|so|xyz|tech)\b", r"\1", (name or "").lower())
    words = company_key(text).split()
    core = [w for w in words if w not in _GENERIC]
    return " ".join(core or words)


def same_company(text: str, company: str) -> bool:
    a, b = core_company(text), core_company(company)
    return bool(a) and a == b


def classify_role(title: str) -> str:
    """role_class from a job title or headline (rules; checked by the Recon eval)."""
    t = f" {(title or '').lower()} "
    if re.search(r"recruit|talent acquisition|talent partner|\btalent\b|\bhr\b|human resources|people (partner|ops|operations|team|function)|sourcer|\bhrbp\b", t):
        return "recruiter"
    if re.search(r"\bcto\b|chief technology|chief technical", t):
        return "cto"
    if re.search(r"\bceo\b|chief executive|\bfounder\b|co-?founder", t):
        return "ceo"
    if re.search(r"engineering manager|head of|director|\bvp\b|vice president|hiring manager|engineering lead|"
                 r"engineering leader|tech lead|team lead|\blead\b|manager", t):
        return "hiring_manager"
    if t.strip():
        return "employee"
    return "unknown"


def technical(title: str) -> bool:
    return bool(_TECH.search(title or ""))


def linkedin_slug(url: str) -> str | None:
    match = _SLUG.match((url or "").strip())
    return match.group(1).lower() if match else None


def canonical_linkedin(url: str) -> str | None:
    slug = linkedin_slug(url)
    return f"https://www.linkedin.com/in/{slug}" if slug else None


def clean_name(text: str) -> str | None:
    name = " ".join(_EMOJI.sub(" ", text or "").replace(",", " ").split())
    name = re.sub(r"\s*\((?:he|she|they)[^)]*\)", "", name, flags=re.I).strip()
    if not name or len(name) > 60 or not _NAME.match(name):
        return None
    if len(name.replace(".", "").split()) < 2 and len(name) < 4:
        return None
    return name


@dataclass
class Person:
    name: str
    linkedin_url: str
    title: str
    role_class: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return linkedin_slug(self.linkedin_url) or ""


def _segments(title: str) -> list[str]:
    title = _EMOJI.sub(" ", title)
    parts = [p.strip(" !·") for p in re.split(r"\s+[-–—|]\s+", title)]
    return [p for p in parts if p and p.lower() not in ("linkedin", "linkedin india")]


def parse_result(url: str, title: str, snippets: list[str], company: str) -> Person | None:
    """One search result -> a Person working at `company`, or None without evidence."""
    profile = canonical_linkedin(url)
    if not profile:
        return None
    segments = _segments(title)
    if len(segments) < 2:
        return None
    name = clean_name(segments[0])
    if not name:
        return None
    company_evidence, headline, headline_at_company, evidence = False, "", False, []
    for seg in segments[1:]:
        if same_company(seg, company):
            company_evidence = True
            evidence.append(f'LinkedIn title lists {seg}')
            continue
        at = _AT.match(seg)
        if at and same_company(at.group(2), company):
            company_evidence = True
            if not headline_at_company:
                headline, headline_at_company = at.group(1).strip(), True
            evidence.append(f'LinkedIn title: "{seg[:120]}"')
        elif not headline and not seg.lower().startswith(("ex-", "ex ", "former")) and len(seg.split()) <= 10 \
                and not re.search(r"universit|college|institute|school|iit\b|nit\b", seg, re.I):
            headline = seg
    lead_title = ""
    for snippet in snippets:
        experience = _EXPERIENCE.search(snippet)
        if experience:
            if same_company(experience.group(1), company):
                line = f"Profile lists experience at {experience.group(1).strip()}"
                if line not in evidence:
                    evidence.append(line)
                company_evidence = True
                lead = snippet.split("·")[0].strip(" …")
                if lead and not lead.lower().startswith("experience"):
                    match = _LEAD.match(lead) or _LEAD_SHORT.match(lead)
                    if match and len(match.group(1).split()) <= 6:
                        lead_title = lead_title or match.group(1).strip()
            elif not company_evidence:
                return None   # the profile's current experience is another company
        for match in _FIRST_PERSON.finditer(snippet):
            if same_company(match.group(2), company) and len(match.group(1).split()) <= 6:
                lead_title = lead_title or match.group(1).strip()
                company_evidence = True
                evidence.append(f'Says: "…as {match.group(1).strip()} at {match.group(2).strip()}"')
    if not company_evidence:
        return None
    # A headline that is only the company, or an "at Other" headline, is not a title.
    if headline and (_AT.match(headline) and not same_company(_AT.match(headline).group(2), company)):
        return None
    # A headline that names the company wins; otherwise a title stated next to the company.
    title_text = headline if headline_at_company else (lead_title or headline)
    role = classify_role(title_text)
    if role == "unknown":
        return None
    confidence = 0.45 + (0.2 if headline else 0.1 if lead_title else 0) + (0.15 if len(evidence) > 1 else 0)
    return Person(name=name, linkedin_url=profile, title=title_text[:160], role_class=role,
                  confidence=round(min(confidence, 0.9), 2), evidence=evidence[:3], sources=[profile])


def area_words(role: str) -> str:
    """The specialty in a role title ("Senior ML Engineer II" -> "ML"), for search queries."""
    drop = {"senior", "sr", "junior", "jr", "staff", "principal", "lead", "intern", "i", "ii", "iii", "iv", "engineer",
            "engineering", "developer", "associate", "mid", "level", "full", "time", "remote", "hybrid", "the", "and", "of",
            "-", "/", "&"}
    words = [w for w in re.split(r"[\s,()/]+", role or "") if w and w.lower() not in drop]
    return " ".join(words[:4])


@dataclass(frozen=True)
class Query:
    role_class: str
    text: str


def queries(company: str, role: str) -> list[Query]:
    """The searches one Recon run makes, most useful first (the per-run cap cuts from the end)."""
    name = company.replace('"', "").strip()
    area = area_words(role)
    role_q = (role or "").replace('"', "").strip()
    out = [Query("recruiter", f'site:linkedin.com/in "{name}" (recruiter OR "talent acquisition" OR recruiting)'),
           Query("hiring_manager", f'site:linkedin.com/in "{name}" ("engineering manager" OR "head of" OR director OR lead) {area}'.strip()),
           Query("ceo", f'site:linkedin.com/in "{name}" (CTO OR CEO OR founder OR "co-founder")')]
    if role_q:
        out.append(Query("employee", f'site:linkedin.com/in "{name}" "{role_q}"'))
    if area:
        out.append(Query("employee", f'site:linkedin.com/in "{name}" {area} engineer'))
    return out


def merge(people: list[Person]) -> list[Person]:
    """One entry per LinkedIn profile: keep the best title, add up evidence."""
    best: dict[str, Person] = {}
    for p in people:
        current = best.get(p.slug)
        if current is None:
            best[p.slug] = p
            continue
        if p.confidence > current.confidence:
            p.evidence = list(dict.fromkeys(p.evidence + current.evidence))[:3]
            best[p.slug] = p
        else:
            current.evidence = list(dict.fromkeys(current.evidence + p.evidence))[:3]
    return list(best.values())


def relevant(p: Person) -> bool:
    """People worth contacting for an engineering role: recruiters, leaders, technical staff."""
    if p.role_class in ("recruiter", "ceo", "cto"):
        return True
    return technical(p.title)


PRIORITY = {"recruiter": 0, "hiring_manager": 1, "cto": 2, "ceo": 3, "employee": 4}
KEEP = {"recruiter": 3, "hiring_manager": 3, "cto": 1, "ceo": 1, "employee": 4}


def shortlist(people: list[Person]) -> list[Person]:
    """Best few per role class, in outreach order."""
    out = []
    for role in sorted(KEEP, key=PRIORITY.get):
        ranked = sorted((p for p in people if p.role_class == role), key=lambda p: -p.confidence)
        out += ranked[:KEEP[role]]
    return out


def host(url: str) -> str:
    return urlparse(url).netloc.lower()
