"""What kind of question a form field asks (rules only, so it is fast and testable).

The kind decides who may answer it:

* `legal` (agreements, consents, attestations, signatures): never answered; handed to you.
* `eeo` (gender, race, veteran, disability, pronouns): your saved answer, else the form's
  "decline" option, else handed to you. Never generated.
* `file`: the resume upload (Applicant handles files on Day 8).
* `pay` (current/expected salary or CTC): your confirmed number, always marked to confirm
  before it is filled (the Comp Analyst adds a researched range on Day 12).
* Profile facts (`name`, `email`, `phone`, `link`, `location`, `work_auth`, `sponsorship`,
  `notice`, `start_date`, `relocation`, `years`, `dob`): from your fact vault or answer bank.
* `company_specific` ("Why Acme?", "Why this role?"): never reused verbatim; a stored answer
  is only an angle for a new one.
* `open` (describe, tell us, explain…): reuse, adapt or generate from the answer bank.
* `short`: anything else; reuse a close bank match or hand it to you.
"""
from __future__ import annotations

import re

LEGAL = re.compile(r"\b(agree|agreement|consent|acknowledg\w*|arbitrat\w*|terms|privacy|certif(y|ication that)|attest|"
                   r"policy|gdpr|data (processing|retention)|truthful|accurate and complete|signature|sign here|e-?sign)\b", re.I)
EEO = re.compile(r"\b(gender|sex\b|race|ethnic\w*|hispanic|latin[oax]|veteran|disabilit\w*|sexual orientation|transgender|"
                 r"pronouns?|caste|religion|marital)\b", re.I)
DECLINE = re.compile(r"(decline|don.?t wish|do not wish|prefer not|not to (say|answer|disclose)|rather not)", re.I)
OPEN = re.compile(r"\b(why|describe|tell us|explain|what (excites|interests|motivates|draws)|share|how (would|do|have|did) you|"
                  r"walk us|example|elaborate|anything else|cover letter|additional information|summary)\b", re.I)
PERSONAL_LINE = re.compile(r"\b(you|your)\b", re.I)

RULES: tuple[tuple[str, re.Pattern], ...] = (
    ("name", re.compile(r"^(full |your |legal |preferred )?(first |given |last |family |sur)?\s?name\b|^(first|last)$", re.I)),
    ("email", re.compile(r"\be-?mail\b", re.I)),
    ("phone", re.compile(r"\b(phone|mobile|telephone|contact number|whatsapp)\b", re.I)),
    ("link", re.compile(r"\b(linkedin|github|portfolio|website|personal site|blog|url)\b", re.I)),
    ("pay", re.compile(r"\b(salary|compensation|ctc|pay (expectation|range)|expected (pay|package)|current package|remuneration)\b", re.I)),
    ("sponsorship", re.compile(r"\b(sponsor\w*|visa)\b", re.I)),
    ("work_auth", re.compile(r"(authori[sz]ed|eligible|right|permit\w*) to work|work authori[sz]ation|citizenship", re.I)),
    ("notice", re.compile(r"\bnotice period\b|\bserving notice\b", re.I)),
    ("start_date", re.compile(r"(earliest|available|availability).*(start|join)|start date|joining date|when (can|could) you (start|join)", re.I)),
    ("relocation", re.compile(r"\brelocat\w*|\bopen to (moving|working from)\b|\bwork from (the )?office\b|\bonsite\b|\bhybrid\b", re.I)),
    ("years", re.compile(r"\byears? of (\w+ )*experience\b|\bhow many years\b|\bexperience (with|in|using)\b", re.I)),
    ("location", re.compile(r"\b(city|current location|where (are you|do you) (located|based|live)|country of residence|"
                            r"based in|located in|address)\b", re.I)),
    ("dob", re.compile(r"\b(date of birth|birth ?date|\bdob\b|age)\b", re.I)),
)


def normalize(text: str) -> str:
    """Lowercase words only: the key for exact matches and version history."""
    text = re.sub(r"[*✱]+\s*$", "", text or "")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower())).strip()


def company_specific(label: str, company: str) -> bool:
    l = (label or "").lower()
    if company and re.search(rf"\b{re.escape(company.lower().split()[0])}\b", l):
        return True
    return bool(re.search(r"\bwhy (do you want to |would you like to )?(work|join|apply)\b|\bwhy (us|this (company|role|team|position))\b|"
                          r"\b(our|this) (company|mission|product|team|role)\b", l))


def kind_of(label: str, field_type: str = "text", company: str = "") -> str:
    label = (label or "").strip()
    if field_type == "file":
        return "file"
    if LEGAL.search(label):
        return "legal"
    if EEO.search(label):
        return "eeo"
    if field_type in ("textarea", "text") and OPEN.search(label) and len(label.split()) >= 3:
        return "company_specific" if company_specific(label, company) else "open"
    for kind, pattern in RULES:
        if pattern.search(label):
            return kind
    if company_specific(label, company):
        return "company_specific"
    if field_type == "textarea":
        return "open"
    return "short"


_YES = {"yes", "y", "true", "i am", "i do", "i will"}
# Same meaning, different wording across forms (only for exact whole answers).
SYNONYMS = {"man": "male", "woman": "female", "male": "man", "female": "woman", "immediately": "immediate",
            "immediate": "immediately", "prefer not to say": "decline", "decline": "prefer not to say"}
_NO = {"no", "n", "false", "i am not", "i do not", "i will not", "not required"}


def match_option(value: str, options: list[str]) -> str | None:
    """The one option that represents `value` (exact, yes/no, numeric range), else None."""
    if not options or not value:
        return None
    v = value.strip().lower()
    exact = [o for o in options if o.strip().lower() == v]
    if len(exact) == 1:
        return exact[0]
    if exact:
        return None
    if v in SYNONYMS:
        alias = [o for o in options if o.strip().lower() == SYNONYMS[v]]
        if len(alias) == 1:
            return alias[0]
    first = v.split()[0].strip(",.") if v.split() else v
    if first in _YES or first in _NO or v in _NO:
        want = "no" if (first in _NO or v in _NO) else "yes"
        candidates = [o for o in options if o.strip().lower().split()[0].strip(",.") == want]
        return candidates[0] if len(candidates) == 1 else None
    if (num := re.fullmatch(r"(\d+(?:\.\d+)?)(?:\s*\+)?(?:\s+(?:years?|months?|days?|weeks?))?", v)) is not None:
        n = float(num.group(1))
        candidates = []
        for o in options:
            bounds = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", o)]
            if len(bounds) == 2 and bounds[0] <= n <= bounds[1]:
                candidates.append(o)
            elif len(bounds) == 1 and re.search(r"\+|or more|more than|above", o, re.I) and n >= bounds[0]:
                candidates.append(o)
            elif len(bounds) == 1 and re.search(r"less than|under|below|fewer|up to", o, re.I) and n < bounds[0]:
                candidates.append(o)
            elif len(bounds) == 1 and bounds[0] == n:
                candidates.append(o)
        return candidates[0] if len(candidates) == 1 else None
    contains = [o for o in options if v in o.lower() or o.lower() in v]
    return contains[0] if len(contains) == 1 else None


def decline_option(options: list[str]) -> str | None:
    return next((o for o in options if DECLINE.search(o)), None)
