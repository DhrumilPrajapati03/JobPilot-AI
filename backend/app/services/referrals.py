"""Referral first: the people you know at the companies you apply to.

Contacts come from LinkedIn's own data export (Settings → Data privacy → Get a
copy of your data → Connections), which is the user's data, or are added by
hand. Nothing here talks to LinkedIn. Company names are normalised so
"Bundl Technologies Pvt Ltd" finds Swiggy and "Sarvam" finds "Sarvam AI".

JobPilot drafts referral requests; the user sends them and records the result.
"""

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime

from app.services.job_matching import _title_words
from app.services.llm import get_default_llm
from app.services.supabase import select_all

MAX_IMPORT_ROWS = 50_000
MESSAGE_LIMIT = 900

_LEGAL = re.compile(
    r"\b(private limited|pvt\.? ltd\.?|pvt|ltd\.?|limited|inc\.?|incorporated|llc|llp|l\.l\.c\.|corp\.?|corporation|"
    r"co\.?|company|gmbh|plc|s\.a\.|b\.v\.|technologies|technology|tech|solutions|services|software|india)\b",
    re.IGNORECASE,
)
# Words too common to identify a company on their own.
_GENERIC = {"the", "and", "of", "group", "global", "systems", "digital", "labs", "lab", "ai", "app", "apps", "hq", "io", "co"}

# Parent companies, legal names and old names that should find each other.
COMPANY_ALIASES = [
    {"swiggy", "bundl"},
    {"zomato", "eternal", "blinkit", "grofers", "hyperpure", "district by zomato"},
    {"paytm", "one97 communications", "one 97 communications"},
    {"cred", "dreamplug"},
    {"fi money", "epifi"},
    {"google", "alphabet", "google deepmind", "deepmind"},
    {"meta", "facebook", "meta platforms"},
    {"amazon", "amazon web services", "aws"},
    {"microsoft", "linkedin", "github"},
    {"flipkart", "myntra", "cleartrip", "ekart"},
    {"phonepe"},
    {"tcs", "tata consultancy"},
]


def company_key(name: str) -> str:
    """Lowercase company name without legal suffixes or punctuation."""
    text = re.sub(r"\([^)]*\)", " ", (name or "").lower())
    text = _LEGAL.sub(" ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _aliases(key: str) -> set[str]:
    keys = {key}
    for group in COMPANY_ALIASES:
        if key in group or any(_contains(key, g) for g in group):
            keys |= group
    return {k for k in keys if k}


def _tokens(key: str) -> set[str]:
    return {t for t in key.split() if t not in _GENERIC and len(t) >= 2}


def _contains(longer: str, shorter: str) -> bool:
    """Every distinctive word of ``shorter`` appears in ``longer``."""
    short = _tokens(shorter)
    return bool(short) and short <= set(longer.split())


def companies_match(a: str, b: str) -> bool:
    """Whether two company keys name the same company (or parent / alias)."""
    if not a or not b:
        return False
    for x in _aliases(a):
        for y in _aliases(b):
            if x == y or _contains(x, y) or _contains(y, x):
                return True
    return False


class NetworkIndex:
    """Contacts indexed by company, for fast "who do I know at X?" lookups."""

    def __init__(self, contacts: list[dict]):
        self.by_key: dict[str, list[dict]] = {}
        self.by_token: dict[str, set[str]] = {}
        for c in contacts:
            key = c.get("company_key") or company_key(c.get("company") or "")
            if not key:
                continue
            self.by_key.setdefault(key, []).append(c)
            for token in _tokens(key):
                self.by_token.setdefault(token, set()).add(key)

    def find(self, company: str) -> list[dict]:
        target = company_key(company)
        if not target:
            return []
        candidates: set[str] = set()
        for alias in _aliases(target):
            if alias in self.by_key:
                candidates.add(alias)
            for token in _tokens(alias):
                candidates |= self.by_token.get(token, set())
        matched = [k for k in candidates if companies_match(target, k)]
        return [c for k in sorted(matched) for c in self.by_key[k]]

    def count(self, company: str) -> int:
        return len(self.find(company))


def load_index(supabase, user_id: str) -> NetworkIndex:
    rows = select_all(lambda: supabase.table("network_contacts").select(
        "id, full_name, first_name, company, company_key, position, linkedin_url, email"
    ).eq("user_id", user_id).order("id"))
    return NetworkIndex(rows)


def contact_counts(supabase, user_id: str, companies: list[str]) -> dict[str, int]:
    """How many contacts you have at each company (empty if the network isn't set up)."""
    try:
        index = load_index(supabase, user_id)
    except Exception:
        return {}
    return {c: index.count(c) for c in set(companies) if c}


def is_table_missing(error: Exception) -> bool:
    message = str(error)
    return "PGRST205" in message or (("network_contacts" in message or "referral_requests" in message) and "does not exist" in message)


# --- Import ---------------------------------------------------------------------------

def dedupe_key(contact: dict) -> str:
    url = (contact.get("linkedin_url") or "").strip().lower().rstrip("/")
    if url:
        return "url:" + re.sub(r"^https?://(www\.)?", "", url)
    if contact.get("email"):
        return "email:" + contact["email"].strip().lower()
    return f"name:{(contact.get('full_name') or '').strip().lower()}|{company_key(contact.get('company') or '')}"


def _parse_date(value: str) -> str | None:
    value = (value or "").strip()
    for fmt in ("%d %b %Y", "%d %B %Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def contact_row(user_id: str, *, first_name="", last_name="", full_name="", email="", linkedin_url="", company="",
                position="", connected_on=None, source="manual", notes="") -> dict:
    full = (full_name or f"{first_name} {last_name}").strip()
    if not first_name and full:
        first_name = full.split()[0]
    row = {
        "user_id": user_id,
        "full_name": full,
        "first_name": first_name.strip(),
        "last_name": last_name.strip(),
        "email": email.strip(),
        "linkedin_url": linkedin_url.strip(),
        "company": company.strip(),
        "company_key": company_key(company),
        "position": position.strip(),
        "connected_on": connected_on,
        "source": source,
        "notes": notes,
    }
    row["dedupe_key"] = dedupe_key(row)
    return row


class ImportError_(ValueError):
    """The uploaded file isn't a LinkedIn connections export; the message is safe to show."""


MAX_ZIP_MEMBER_BYTES = 20 * 1024 * 1024


def _connections_from_zip(raw: bytes) -> bytes:
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as e:
        raise ImportError_("That zip file couldn't be opened. Try unzipping it and uploading Connections.csv.") from e
    member = next((m for m in archive.infolist() if m.filename.lower().rsplit("/", 1)[-1] == "connections.csv"), None)
    if member is None:
        raise ImportError_(
            "This LinkedIn archive has no Connections.csv yet. LinkedIn sometimes sends connections in a later email; "
            "upload that archive when it arrives."
        )
    if member.file_size > MAX_ZIP_MEMBER_BYTES:
        raise ImportError_("Connections.csv in that archive is too large to import.")
    return archive.read(member)


def parse_linkedin_connections(raw: bytes, user_id: str) -> tuple[list[dict], int]:
    """Parse LinkedIn's Connections.csv. Returns ``(rows, skipped)``.

    The export starts with a few lines of notes before the header row
    ``First Name,Last Name,URL,Email Address,Company,Position,Connected On``.
    The whole LinkedIn archive (.zip) works too: Connections.csv is read from it.
    """
    if raw[:2] == b"PK":
        raw = _connections_from_zip(raw)
    text = raw.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    header_at = next((i for i, line in enumerate(lines[:30]) if line.lower().startswith("first name,")), None)
    if header_at is None:
        raise ImportError_(
            "This doesn't look like LinkedIn's Connections.csv. Export it from LinkedIn: Settings → Data privacy → "
            "Get a copy of your data → Connections."
        )
    reader = csv.DictReader(io.StringIO("\n".join(lines[header_at:])))
    rows, skipped, seen = [], 0, set()
    for record in reader:
        if len(rows) >= MAX_IMPORT_ROWS:
            break
        get = lambda k: (record.get(k) or "").strip()  # noqa: E731
        if not (get("First Name") or get("Last Name")):
            skipped += 1
            continue
        row = contact_row(
            user_id,
            first_name=get("First Name"),
            last_name=get("Last Name"),
            linkedin_url=get("URL"),
            email=get("Email Address"),
            company=get("Company"),
            position=get("Position"),
            connected_on=_parse_date(get("Connected On")),
            source="linkedin",
        )
        if row["dedupe_key"] in seen:
            continue
        seen.add(row["dedupe_key"])
        rows.append(row)
    return rows, skipped


# --- Ranking and drafting ----------------------------------------------------------------

_RECRUITING = re.compile(r"\b(recruit\w*|talent|hr|human resources|people (partner|ops|operations)|hiring)\b", re.IGNORECASE)
_SENIOR = re.compile(r"\b(senior|sr|lead|staff|principal|manager|head|director|vp|founder|cto|ceo)\b", re.IGNORECASE)


@dataclass
class RankedContact:
    contact: dict
    score: float
    reason: str


def rank_contacts(contacts: list[dict], role: str) -> list[RankedContact]:
    """Best people to ask first: same kind of work, then recruiters, then senior people."""
    role_words = _title_words(role)
    ranked = []
    for c in contacts:
        position = c.get("position") or ""
        words = _title_words(position)
        overlap = 2 * len(role_words & words) / (len(role_words) + len(words)) if role_words and words else 0.0
        recruiter = bool(_RECRUITING.search(position))
        senior = bool(_SENIOR.search(position))
        score = overlap * 2 + (1.0 if recruiter else 0) + (0.5 if senior else 0)
        if overlap >= 0.4:
            reason = f"Works in a similar role ({position})"
        elif recruiter:
            reason = f"Recruits at {c.get('company')}"
        elif position:
            reason = position
        else:
            reason = f"Works at {c.get('company')}"
        ranked.append(RankedContact(c, round(score, 2), reason))
    ranked.sort(key=lambda r: (-r.score, r.contact.get("full_name") or ""))
    return ranked


def fallback_message(contact: dict, application: dict, sender: str) -> str:
    first = contact.get("first_name") or (contact.get("full_name") or "there").split()[0]
    link = f" ({application['jd_url']})" if application.get("jd_url") else ""
    sign = f"\n\nThanks,\n{sender}" if sender else "\n\nThanks!"
    return (
        f"Hi {first}, hope you're doing well! I'm applying for the {application['role']} role at {application['company']}{link} "
        f"and noticed you work there. Would you be open to referring me, or telling me a bit about the team? "
        f"I'm happy to send my resume and a short summary to make it easy. No worries at all if it's not a good time.{sign}"
    )


async def draft_referral_message(contact: dict, application: dict, profile: dict, resume: dict) -> tuple[str, bool]:
    """A short, honest referral request. Returns ``(message, used_fallback)``."""
    sender = (profile.get("name") or resume.get("name") or "").strip()
    first = contact.get("first_name") or (contact.get("full_name") or "").split(" ")[0]
    skills = ", ".join(((resume.get("skills") or {}).get("primary") or [])[:6])
    latest = next(iter(resume.get("experience") or []), {})
    prompt = (
        "Write a LinkedIn message asking a first-degree connection for a job referral.\n"
        f"- Recipient: {first}, {contact.get('position') or 'works'} at {application['company']}.\n"
        f"- Role: {application['role']} at {application['company']}. Job link: {application.get('jd_url') or 'none'}.\n"
        f"- Sender: {sender or 'the candidate'}. Headline: {resume.get('headline') or ''}. "
        f"Current role: {latest.get('role', '')} at {latest.get('company', '')}. Key skills: {skills}.\n"
        "Rules: under 120 words; warm and direct; one or two specific, true reasons the sender fits, using ONLY the facts "
        "above (never invent numbers, employers or experience); offer to send a resume; give an easy way to say no; "
        "no subject line, no placeholders, no hashtags. Output only the message."
    )
    try:
        res = await get_default_llm(temperature=0.4, task="light").ainvoke(prompt)
        message = (res.content if isinstance(res.content, str) else str(res.content)).strip().strip('"')
        if not message or "[" in message:
            raise ValueError("empty or templated message")
        return message[:MESSAGE_LIMIT], False
    except Exception as e:
        print(f"Referral message fell back to a template: {e}")
        return fallback_message(contact, application, sender), True
