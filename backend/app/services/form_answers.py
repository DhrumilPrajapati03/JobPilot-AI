"""Answers for job application form fields.

Given a form's fields (from the Greenhouse questions API overnight, or read
from the page by the Chrome extension), decide what goes in each one:

1. Profile and resume facts: name, email, phone, links, current role.
2. Saved answers from the answer bank, matched by question wording.
3. The tailored cover letter for cover-letter fields.
4. EEO / demographic questions: the user's saved answer, else "decline to answer".
5. Open questions ("Why us?"): a short AI draft from the resume and JD, always flagged.

Legal agreements, consents and certifications are never answered: the user
reads and accepts them. Nothing here submits anything.
"""

import json
import re
from dataclasses import asdict, dataclass, field

from app.services.llm import get_default_llm

RESUME_FILE = "__resume__"
MAX_AI_QUESTIONS = 6

_STOP = {
    "a", "an", "the", "you", "your", "are", "do", "does", "have", "has", "is", "of", "to", "in", "for", "with", "and",
    "or", "what", "please", "any", "this", "at", "on", "be", "will", "would", "if", "we", "our", "us", "it", "as", "can",
}
_OPEN_ENDED = re.compile(r"\b(why|describe|tell us|explain|what (excites|interests|motivates)|share|how (would|do|have) you|walk us|example|elaborate)\b", re.I)
_LEGAL = re.compile(
    r"\b(agree|agreement|consent|acknowledg\w*|arbitrat\w*|terms|privacy|certif(y|ication that)|attest|policy|gdpr|"
    r"data (processing|retention)|truthful|accurate and complete|signature|sign)\b",
    re.I,
)
_EEO = re.compile(r"\b(gender|sex\b|race|ethnic\w*|hispanic|latin[oax]|veteran|disabilit\w*|sexual orientation|transgender|pronouns?)\b", re.I)
_DECLINE = re.compile(r"(decline|don.?t wish|do not wish|prefer not|not to (say|answer|disclose)|rather not)", re.I)


@dataclass
class FormField:
    key: str
    label: str
    type: str = "text"  # text | textarea | select | multiselect | radio | checkbox | file | email | tel | url | number | date
    required: bool = False
    options: list[str] = field(default_factory=list)


@dataclass
class FieldAnswer:
    key: str
    label: str
    type: str
    required: bool
    value: str | list[str] | None
    source: str  # profile | answer_bank | cover_letter | resume | default | ai | none
    flagged: bool
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ApplicantContext:
    email: str = ""
    full_name: str = ""
    first_name: str = ""
    last_name: str = ""
    location: str = ""
    linkedin: str = ""
    salary: str = ""
    current_company: str = ""
    current_title: str = ""
    requires_sponsorship: bool | None = None
    answers: list[dict] = field(default_factory=list)  # {question, answer, sensitive}
    cover_letter: str = ""
    company: str = ""
    role: str = ""
    jd_text: str = ""
    resume: dict = field(default_factory=dict)


def build_context(*, email: str, profile: dict, resume: dict, answers: list[dict], application: dict | None,
                  prefs: dict | None = None) -> ApplicantContext:
    name = (profile.get("name") or resume.get("name") or "").strip()
    parts = name.split()
    latest = next(iter(resume.get("experience") or []), {})
    prefs = prefs or {}
    app = application or {}
    return ApplicantContext(
        email=email or "",
        full_name=name,
        first_name=parts[0] if parts else "",
        last_name=" ".join(parts[1:]) if len(parts) > 1 else "",
        location=profile.get("location") or "",
        linkedin=profile.get("linkedin_url") or "",
        salary=profile.get("salary_range") or "",
        current_company=latest.get("company") or "",
        current_title=latest.get("role") or "",
        requires_sponsorship=prefs.get("requires_sponsorship"),
        answers=[a for a in answers if (a.get("answer") or "").strip()],
        cover_letter=app.get("cover_letter") or "",
        company=app.get("company") or "",
        role=app.get("role") or "",
        jd_text=(app.get("jd_text") or "")[:4000],
        resume=resume,
    )


# --- Matching helpers -----------------------------------------------------------------

def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9+#]+", (text or "").lower()) if w not in _STOP and len(w) > 1}


def _similarity(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _saved(ctx: ApplicantContext, *phrases: str) -> str:
    """A saved answer whose question contains any of ``phrases``."""
    for phrase in phrases:
        for a in ctx.answers:
            if phrase.lower() in a["question"].lower():
                return a["answer"].strip()
    return ""


def _best_saved(ctx: ApplicantContext, label: str, *, allow_sensitive: bool = False) -> tuple[str, float, str]:
    best = ("", 0.0, "")
    for a in ctx.answers:
        if a.get("sensitive") and not allow_sensitive:
            continue
        score = _similarity(label, a["question"])
        if a["question"].lower() in label.lower():
            score = max(score, 0.9)
        if score > best[1]:
            best = (a["answer"].strip(), score, a["question"])
    return best


_YES = {"yes", "y", "true", "i am", "i do", "i will"}
_NO = {"no", "n", "false", "i am not", "i do not", "i will not"}


def match_option(value: str, options: list[str]) -> str | None:
    """The option that best represents ``value`` (exact, yes/no, contains, numeric range)."""
    if not options or not value:
        return None
    v = value.strip().lower()
    exact = [o for o in options if o.strip().lower() == v]
    if len(exact) == 1:
        return exact[0]
    if exact:
        return None
    first = v.split()[0].strip(",.") if v.split() else v
    if first in _YES or first in _NO:
        want = "yes" if first in _YES else "no"
        candidates = [o for o in options if o.strip().lower().split()[0].strip(",.") == want]
        return candidates[0] if len(candidates) == 1 else None
    if (num := re.fullmatch(r"\d+(?:\.\d+)?(?:\s+years?)?", v)) is not None:
        n = float(re.match(r"\d+(?:\.\d+)?", num.group()).group())
        candidates = []
        for o in options:
            bounds = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", o)]
            if len(bounds) == 2 and bounds[0] <= n <= bounds[1]:
                candidates.append(o)
            if len(bounds) == 1 and ((re.search(r"\+|or more", o, re.I) and n >= bounds[0]) or (re.search(r"more than|above", o, re.I) and n > bounds[0])):
                candidates.append(o)
            if len(bounds) == 1 and re.search(r"less than|under|below|fewer", o, re.I) and n < bounds[0]:
                candidates.append(o)
        return candidates[0] if len(candidates) == 1 else None
    return None


def _choice(f: FormField, value: str, source: str, note: str = "") -> FieldAnswer:
    """Fit a text answer to a choice field, or flag it."""
    if f.type in ("select", "radio", "multiselect", "checkbox") and f.options:
        option = match_option(value, f.options)
        if option is None:
            return FieldAnswer(f.key, f.label, f.type, f.required, None, "none", True,
                               f"Your saved answer “{value[:60]}” doesn't match an option here. Pick one.")
        return FieldAnswer(f.key, f.label, f.type, f.required, [option] if f.type in ("multiselect", "checkbox") else option, source, False, note)
    return FieldAnswer(f.key, f.label, f.type, f.required, value, source, False, note)


# --- Rules -------------------------------------------------------------------------------

def _years_with(label: str, ctx: ApplicantContext) -> str:
    m = re.search(r"experience (?:with|in|using)\s+(.+?)(\?|$)", label, re.I)
    if not m:
        return ""
    skill = m.group(1).strip().lower()
    for a in ctx.answers:
        q = a["question"].lower()
        if q.startswith("years of experience with") and q.removeprefix("years of experience with").strip() in skill:
            return a["answer"]
    return ""


def _rule_answer(f: FormField, ctx: ApplicantContext) -> FieldAnswer | None:
    label = f.label.strip()
    l = label.lower()

    def give(value: str, source: str = "profile", note: str = "") -> FieldAnswer | None:
        return _choice(f, value, source, note) if value else None

    if f.type == "file":
        if re.search(r"resume|\bcv\b|curriculum", l):
            return FieldAnswer(f.key, label, f.type, f.required, RESUME_FILE, "resume", False, "Your tailored resume PDF")
        if "cover" in l:
            return FieldAnswer(f.key, label, f.type, f.required, None, "none", f.required, "Attach a cover letter file if you want one; the text is in JobPilot.")
        return FieldAnswer(f.key, label, f.type, f.required, None, "none", f.required, "Attach this file yourself.")

    if _LEGAL.search(l):
        return FieldAnswer(f.key, label, f.type, f.required, None, "none", True, "Legal agreement or consent: read it and answer it yourself.")

    if _EEO.search(l):
        saved, score, _ = _best_saved(ctx, label, allow_sensitive=True)
        if saved and score >= 0.3:
            return _choice(f, saved, "answer_bank", "Your saved answer")
        decline = next((o for o in f.options if _DECLINE.search(o)), None)
        if decline:
            return FieldAnswer(f.key, label, f.type, f.required, decline, "default", False, "Declined to self-identify (change it in your answer bank)")
        return FieldAnswer(f.key, label, f.type, f.required, None, "none", f.required, "Voluntary self-identification: answer it yourself.")

    if re.search(r"\b(first|given) name\b", l) or l == "first":
        return give(ctx.first_name)
    if re.search(r"\b(last|family|sur) ?name\b", l) or l == "last":
        return give(ctx.last_name)
    if re.search(r"preferred (first )?name", l):
        return give(ctx.first_name)
    if re.fullmatch(r"(full |your |legal )?name\*?", l):
        return give(ctx.full_name)
    if "email" in l or f.type == "email":
        return give(ctx.email)
    if re.search(r"\b(phone|mobile|telephone|contact number)\b", l) or f.type == "tel":
        return give(_saved(ctx, "phone"), "answer_bank")
    if "linkedin" in l:
        return give(ctx.linkedin or _saved(ctx, "linkedin"))
    if "github" in l:
        return give(_saved(ctx, "github"), "answer_bank")
    if re.search(r"\b(website|portfolio|personal site|blog)\b", l):
        return give(_saved(ctx, "portfolio", "website"), "answer_bank")
    if re.search(r"(current|present|most recent) (company|employer)", l):
        return give(ctx.current_company, "resume")
    if re.search(r"(current|present|most recent) (job )?(title|role|position)", l):
        return give(ctx.current_title, "resume")
    if re.search(r"sponsor", l):
        saved = _saved(ctx, "sponsorship")
        if saved:
            return _choice(f, saved, "answer_bank")
        if ctx.requires_sponsorship is not None:
            return _choice(f, "Yes" if ctx.requires_sponsorship else "No", "profile", "From your preferences")
        return None
    if re.search(r"(legally )?(authori[sz]ed|eligible|right) to work", l):
        return give(_saved(ctx, "legally authorized", "authorized to work"), "answer_bank")
    if re.search(r"(salary|compensation|pay) (expectation|requirement|range)|expected (salary|compensation|ctc)|desired (salary|pay)", l):
        return give(_saved(ctx, "expected salary", "salary") or ctx.salary, "answer_bank")
    if "notice period" in l:
        return give(_saved(ctx, "notice period"), "answer_bank")
    if re.search(r"(earliest|available|availability).*(start|join)|start date|when (can|could) you (start|join)", l):
        return give(_saved(ctx, "earliest start", "start date"), "answer_bank")
    if "relocat" in l:
        return give(_saved(ctx, "relocate"), "answer_bank")
    if re.search(r"years of (professional |relevant |total )?experience", l) and not re.search(r"experience (with|in|using)", l):
        return give(_saved(ctx, "total years"), "answer_bank")
    if (years := _years_with(label, ctx)):
        return _choice(f, years, "answer_bank")
    if re.search(r"\b(city|location|where (are you|do you) (located|based|live)|current location|country of residence)\b", l):
        return give(_saved(ctx, "city and country", "residence") or ctx.location, "answer_bank")
    if "cover letter" in l and f.type in ("textarea", "text"):
        if ctx.cover_letter:
            return FieldAnswer(f.key, label, f.type, f.required, ctx.cover_letter, "cover_letter", False, "Your tailored cover letter")
        return None
    return None


def _from_bank(f: FormField, ctx: ApplicantContext) -> FieldAnswer | None:
    saved, score, question = _best_saved(ctx, f.label)
    if not saved or score < 0.5:
        return None
    answer = _choice(f, saved, "answer_bank")
    if score < 0.75 and answer.value is not None:
        answer.flagged, answer.note = True, f"Matched your saved answer to “{question[:70]}”. Check it fits."
    return answer


# --- AI drafts for open questions ----------------------------------------------------------

def _resume_brief(resume: dict) -> str:
    lines = [f"Headline: {resume.get('headline', '')}", f"Summary: {resume.get('summary', '')}"]
    for e in (resume.get("experience") or [])[:3]:
        lines.append(f"- {e.get('role')} at {e.get('company')} ({e.get('duration', '')}): " + "; ".join((e.get("bullets") or [])[:3]))
    skills = resume.get("skills") or {}
    lines.append("Skills: " + ", ".join((skills.get("primary") or []) + (skills.get("secondary") or [])))
    for p in (resume.get("projects") or [])[:2]:
        lines.append(f"Project: {p.get('name')}: {p.get('description', '')}")
    return "\n".join(lines)


async def _ai_drafts(questions: list[FormField], ctx: ApplicantContext) -> dict[str, str]:
    if not questions:
        return {}
    numbered = "\n".join(f"{i + 1}. {q.label}" for i, q in enumerate(questions))
    prompt = (
        f"You are helping a candidate answer application questions for the {ctx.role} role at {ctx.company}.\n"
        f"Candidate's resume:\n{_resume_brief(ctx.resume)}\n\nJob description excerpt:\n{ctx.jd_text[:2500]}\n\n"
        f"Questions:\n{numbered}\n\n"
        "Rules: answer each in the first person, 40-120 words, specific and warm. Use ONLY facts from the resume; never invent "
        "employers, numbers, tools or experience. If the resume doesn't support a question, say so honestly and briefly "
        "(e.g. what related experience they do have). Output JSON only: {\"1\": \"answer\", \"2\": \"answer\", ...}."
    )
    try:
        res = await get_default_llm(temperature=0.3, task="light").ainvoke(prompt)
        text = res.content if isinstance(res.content, str) else str(res.content)
        data = json.loads(re.search(r"\{.*\}", text, re.S).group())
    except Exception as e:
        print(f"AI drafts for form questions failed: {e}")
        return {}
    return {questions[int(k) - 1].key: str(v).strip() for k, v in data.items() if str(k).isdigit() and 0 < int(k) <= len(questions) and str(v).strip()}


async def answer_fields(fields: list[FormField], ctx: ApplicantContext, *, use_ai: bool = True,
                        reuse: dict[str, str] | None = None) -> list[FieldAnswer]:
    """An answer (or a flag) for every field. ``reuse`` maps labels to earlier AI drafts."""
    answers: list[FieldAnswer | None] = []
    open_questions: list[FormField] = []
    reuse = {k.strip().lower(): v for k, v in (reuse or {}).items()}
    for f in fields:
        a = _rule_answer(f, ctx) or _from_bank(f, ctx)
        if a is None and f.type in ("text", "textarea") and f.label.strip().lower() in reuse:
            a = FieldAnswer(f.key, f.label, f.type, f.required, reuse[f.label.strip().lower()], "ai", True, "AI draft: review and personalise")
        if a is None and f.type in ("text", "textarea") and (f.type == "textarea" or _OPEN_ENDED.search(f.label)) and (f.required or f.type == "textarea"):
            open_questions.append(f)
        answers.append(a)

    drafts = await _ai_drafts(open_questions[:MAX_AI_QUESTIONS], ctx) if use_ai else {}
    result = []
    for f, a in zip(fields, answers):
        if a is None and f.key in drafts:
            a = FieldAnswer(f.key, f.label, f.type, f.required, drafts[f.key], "ai", True, "AI draft: review and personalise")
        if a is None:
            if f.required:
                note = "Pick an option" if f.options else "No saved answer: fill this in (and save it to your answer bank)"
                a = FieldAnswer(f.key, f.label, f.type, f.required, None, "none", True, note)
            else:
                a = FieldAnswer(f.key, f.label, f.type, f.required, None, "none", False, "Optional")
        result.append(a)
    return result


def summarise(answers: list[FieldAnswer]) -> dict:
    return {
        "total": len(answers),
        "filled": sum(1 for a in answers if a.value not in (None, "", [])),
        "flagged": sum(1 for a in answers if a.flagged),
        "required_missing": sum(1 for a in answers if a.required and a.value in (None, "", [])),
    }


# --- Greenhouse: questions are public, so forms can be prepared overnight -----------------

_GH_TYPES = {
    "input_text": "text", "textarea": "textarea", "input_file": "file",
    "multi_value_single_select": "select", "multi_value_multi_select": "multiselect", "input_hidden": None,
}


def greenhouse_fields(job: dict) -> list[FormField]:
    """Form fields from ``GET /v1/boards/{board}/jobs/{id}?questions=true``."""
    fields: list[FormField] = []
    groups = list(job.get("questions") or []) + list(job.get("location_questions") or [])
    for block in job.get("compliance") or []:
        groups += block.get("questions") or []
    for block in job.get("demographic_questions") or [] if isinstance(job.get("demographic_questions"), list) else []:
        groups += block.get("questions") or []
    labels = {"VeteranStatus": "Veteran status", "DisabilityStatus": "Disability status", "Gender": "Gender", "Race": "Race", "Hispanic/Latino": "Are you Hispanic/Latino?"}
    for q in groups:
        for fdef in (q.get("fields") or [])[:1]:
            kind = _GH_TYPES.get(fdef.get("type"), "text")
            if kind is None:
                continue
            label = labels.get(q.get("label"), q.get("label") or fdef.get("name") or "")
            fields.append(FormField(
                key=fdef.get("name") or label,
                label=re.sub(r"\s+", " ", label).strip(),
                type=kind,
                required=bool(q.get("required")),
                options=[v.get("label") for v in fdef.get("values") or [] if v.get("label")],
            ))
    return fields
