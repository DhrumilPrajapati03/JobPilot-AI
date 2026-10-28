"""Fast, explainable fit scoring for discovered postings.

Discovery can see hundreds of postings per scan, far too many to send to an
LLM on a free-tier budget, so postings are scored locally:

    fallback = 40% role relevance + 60% smoothed skill coverage
    local MiniLM available = 85% fallback + 15% resume/job cosine similarity

Role relevance uses normalized title overlap with a conservative semantic
rescue for paraphrased titles. Structured eligibility is applied by discovery
after scoring: conflicts score zero and unknown requirements require review.

Title match is the word overlap (Dice) between the posting title and the
closest preferred role. Skill coverage is the share of tech skills the
posting mentions that the user's resume shows, smoothed so a posting that
names a single skill can't score 100%. Covering 75% of the skills a posting
names earns full skill marks: job ads list far more than any one hire has. The full ATS score is computed later, after tailoring,
only for postings the user (or auto-draft) picks.
"""

import re
from dataclasses import dataclass, field

from app.models.user import WorkPreferences
from app.resume_engine.validator import _normalise

TITLE_WEIGHT = 0.4
SKILL_WEIGHT = 0.6
# Postings whose title overlaps a preferred role less than this aren't stored.
MIN_TITLE_MATCH = 0.5
FULL_COVERAGE = 0.75

# Common skills recognised in job descriptions even when the resume doesn't list them,
# so they can count as "missing". The resume's own skills are always recognised too.
TECH_TERMS = [
    "python", "java", "javascript", "typescript", "go", "golang", "rust", "c++", "c#", "ruby", "php", "scala",
    "kotlin", "swift", "objective c", "r", "sql", "nosql", "bash", "elixir", "haskell", "dart",
    "react", "react native", "next.js", "vue", "angular", "svelte", "node.js", "express", "django", "flask",
    "fastapi", "spring", "rails", "laravel", ".net", "graphql", "rest", "grpc", "html", "css", "tailwind",
    "redux", "webpack", "vite", "flutter", "android", "ios",
    "aws", "gcp", "azure", "docker", "kubernetes", "terraform", "ansible", "helm", "linux", "ci/cd",
    "jenkins", "github actions", "serverless", "lambda", "cloudflare",
    "postgresql", "postgres", "mysql", "mongodb", "redis", "elasticsearch", "kafka", "rabbitmq", "dynamodb",
    "cassandra", "snowflake", "bigquery", "redshift", "spark", "hadoop", "airflow", "dbt", "databricks",
    "supabase", "firebase",
    "machine learning", "deep learning", "nlp", "computer vision", "llm", "llms", "rag", "langchain",
    "llamaindex", "pytorch", "tensorflow", "keras", "jax", "scikit learn", "pandas", "numpy", "hugging face",
    "transformers", "openai", "vector databases", "embeddings", "fine tuning", "mlops", "reinforcement learning",
    "statistics", "data science", "data engineering", "etl", "tableau", "power bi", "looker",
    "microservices", "distributed systems", "system design", "security", "oauth", "websockets",
    "figma", "agile", "scrum", "jira",
]

ALIASES = {
    "ml": "machine learning",
    "swe": "software engineer",
    "sde": "software engineer",
    "sre": "site reliability engineer",
    "frontend": "front end",
    "backend": "back end",
    "fullstack": "full stack",
    "golang": "go",
    "postgres": "postgresql",
    "k8s": "kubernetes",
    "js": "javascript",
    "ts": "typescript",
    "nodejs": "node.js",
    "node": "node.js",
    "llms": "llm",
}

_SENIORITY = {"senior", "sr", "junior", "jr", "staff", "principal", "lead", "head", "intern", "i", "ii", "iii", "iv", "mid", "level"}
# Stems of words every role shares ("engineer"); a title must also match something specific.
_GENERIC = {"engine", "develo", "specia", "associ", "profes", "techni", "member", "staff"}
# Stems of people-management words; a title with one only fits roles that have one.
_MANAGEMENT = {"manage", "direct", "vp", "vice", "presid", "chief"}
_TITLE_STOP = {"and", "or", "of", "the", "a", "an", "in", "for", "to", "with", "at", "remote", "hybrid"}
# Short, ambiguous terms that only count when written exactly (not as part of prose).
_CASE_SENSITIVE = {"go": r"\bGo\b|\bGolang\b", "r": r"\bR\b(?![&'])", "rest": r"\bREST(?:ful)?\b", "rag": r"\bRAG\b"}


@dataclass
class CandidateProfile:
    role_terms: list[set[str]]
    roles: list[str]
    skills: set[str]
    resume_text: str
    vocabulary: list[str] = field(default_factory=list)
    owner: str = ""
    confirmation: dict = field(default_factory=dict)
    confirmed_evidence: str = ""


@dataclass
class Fit:
    score: float
    title_match: float
    matched: list[str]
    missing: list[str]
    details: dict = field(default_factory=dict)


def _norm(text: str) -> str:
    text = (text or "").lower()
    for short, full in ALIASES.items():
        text = re.sub(rf"(?<![\w.]){re.escape(short)}(?![\w]|\.\w)", full, text)
    return _normalise(text)


def _stem(word: str) -> str:
    return word[:6] if len(word) > 6 else word


def _title_words(text: str) -> set[str]:
    return {_stem(w) for w in _norm(text).split() if w not in _SENIORITY and w not in _TITLE_STOP and len(w) > 1 or w in {"ai", "ui", "ux", "qa"}}


def build_profile(base_resume: dict, prefs: WorkPreferences) -> CandidateProfile:
    roles = [r for r in prefs.preferred_roles if r.strip()]
    if not roles:
        # Fall back to what the resume says the user does.
        headline = base_resume.get("headline") or ""
        roles = [part for part in re.split(r"[|,•·]", headline) if part.strip()][:1]
        latest = next(iter(base_resume.get("experience") or []), {})
        if latest.get("role"):
            roles.append(latest["role"])
    role_terms = [words for words in (_title_words(r) for r in roles) if words]

    skills_block = base_resume.get("skills") or {}
    listed = [s for key in ("primary", "secondary") for s in skills_block.get(key) or [] if isinstance(s, str)]
    skills = {_norm(s) for s in listed if _norm(s)}
    resume_text = " ".join([
        base_resume.get("headline") or "",
        base_resume.get("summary") or "",
        " ".join(listed),
        " ".join(b for e in base_resume.get("experience") or [] for b in e.get("bullets") or []),
        " ".join(f"{p.get('name', '')} {p.get('description', '')} {' '.join(p.get('tech') or [])}" for p in base_resume.get("projects") or []),
    ])
    vocabulary = sorted({_norm(t) for t in TECH_TERMS} | skills)
    return CandidateProfile(role_terms=role_terms, roles=[r.strip() for r in roles], skills=skills, resume_text=f" {_norm(resume_text)} ", vocabulary=vocabulary, owner=base_resume.get("user_id") or "")


def _mentions(term: str, normalised_text: str, raw_text: str) -> bool:
    if term in _CASE_SENSITIVE:
        return re.search(_CASE_SENSITIVE[term], raw_text) is not None
    return f" {term} " in normalised_text


def title_match(title: str, profile: CandidateProfile) -> float:
    if not profile.role_terms:
        return 0.5  # nothing to compare against: neutral
    words = _title_words(title)
    if not words:
        return 0.0
    best = 0.0
    for role in profile.role_terms:
        specific = role - _GENERIC
        if specific and not specific & words:
            continue  # only "engineer" in common
        match = 2 * len(role & words) / (len(role) + len(words))
        if words & _MANAGEMENT and not role & _MANAGEMENT:
            match *= 0.5
        best = max(best, match)
    if best < MIN_TITLE_MATCH and not (words & _MANAGEMENT and not any(r & _MANAGEMENT for r in profile.role_terms)):
        from app.services.matching_semantics import similarity
        semantic, _ = similarity("; ".join(profile.roles), title, profile.owner)
        if semantic is not None and semantic >= 0.58:
            best = max(best, semantic)
    return best


def score_posting(title: str, description: str, profile: CandidateProfile) -> Fit:
    t_match = title_match(title, profile)
    raw = f"{title}\n{description}"
    text = f" {_norm(raw)} "
    mentioned = [term for term in profile.vocabulary if _mentions(term, text, raw)]
    matched = [term for term in mentioned if term in profile.skills or f" {term} " in profile.resume_text]
    missing = [term for term in mentioned if term not in matched]
    coverage = min(1.0, (len(matched) + 1) / (len(mentioned) + 2) / FULL_COVERAGE)
    lexical = 100 * (TITLE_WEIGHT * t_match + SKILL_WEIGHT * coverage)
    from app.services.matching_semantics import similarity
    semantic, model = similarity(profile.resume_text, raw, profile.owner)
    score = round(0.85 * lexical + 0.15 * semantic * 100 if semantic is not None else lexical, 1)
    evidence = f" {_norm(profile.confirmed_evidence)} "
    confirmed = [s for s in matched if f" {s} " in evidence]
    details = {"version": "matching-v2", "components": {"title": round(t_match*100, 1), "skills": round(coverage*100, 1),
               "semantic": round(semantic*100, 1) if semantic is not None else None},
               "weights": {"title": 0.34, "skills": 0.51, "semantic": 0.15} if semantic is not None else {"title": 0.4, "skills": 0.6, "semantic": 0},
               "semantic_model": model, "identity": profile.confirmation,
               "confirmed_matched_skills": confirmed,
               "reasons": [f"{len(matched)} of {len(mentioned)} recognized job skills appear in your base resume",
                           f"{len(confirmed)} matched skills have user-confirmed source evidence"]}
    return Fit(score=score, title_match=round(t_match, 2), matched=matched, missing=missing, details=details)


# Regions a remote job may name that include candidates in a given country.
REGION_ALIASES = {
    "india": ["apac", "asia", "south asia"],
    "united kingdom": ["uk", "europe", "emea"],
    "united states": ["us", "usa", "americas", "north america"],
    "canada": ["americas", "north america"],
    "germany": ["europe", "emea", "eu"],
    "singapore": ["apac", "asia"],
    "australia": ["apac"],
}
_ANYWHERE = ("worldwide", "anywhere", "global")


def user_country(location: str) -> str | None:
    """The country at the end of a profile location such as "Ahmedabad, Gujarat, India"."""
    parts = [p.strip() for p in re.split(r"[,/|]", location or "") if p.strip()]
    return parts[-1] if parts else None


def region_flag(location: str, country: str | None) -> str | None:
    """A skip reason when a remote job is restricted to regions that exclude the user."""
    if not country:
        return None
    where = re.sub(r"^remote,?\s*", "", location or "", flags=re.IGNORECASE).strip()
    text = where.lower()
    if not text or any(word in text for word in _ANYWHERE):
        return None
    c = country.lower()
    terms = [c] + REGION_ALIASES.get(c, []) + [k for k, v in REGION_ALIASES.items() if c in v]
    if any(re.search(rf"(?<![a-z]){re.escape(t)}(?![a-z])", text) for t in terms):
        return None
    return f"Remote, but only open to candidates in {where}"


def location_flag(prefs: WorkPreferences, location: str, remote: bool | None) -> str | None:
    """A skip reason when an on-site posting is outside every preferred location."""
    places = [p.strip().lower() for p in prefs.preferred_locations if p.strip()]
    if remote or not places or not location:
        return None
    if any(p in location.lower() for p in places):
        return None
    return f"Located in {location}, outside your preferred locations"
