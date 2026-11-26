"""Reviewer: checks every outward draft before Dhrumil sees it (plan section 2.1).

Deterministic checks (no model), so a prompt-injected draft can't talk its way past them:

Blocking (the action becomes `blocked`, with the reason):
* the recipient address is missing, malformed or a no-reply mailbox;
* a number about him that isn't in the fact vault (or the JD/brief, for company facts);
* a tool, product or name that isn't in the vault, the company brief, the JD or the
  recipient's details;
* a years-of-experience claim above the vault's total, or an approximate number stated as exact;
* it doesn't name the company, or reads like a template (two or more stock phrases);
* the person was contacted within the policy cooldown.

Notes (passed on, shown on the approval card): one stock phrase, long body, no specific
company detail, no attachment.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.tailor.validator import _NUMBER, _YEARS, hedged_numbers, notable_terms
from app.tailor.vault import Vault, words

EMAIL = re.compile(r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
NO_REPLY = re.compile(r"^(no-?reply|do-?not-?reply|mailer-daemon|postmaster|bounce)", re.I)
STOCK = ("i hope this email finds you well", "i am writing to express", "i came across your", "to whom it may concern",
         "i am excited to apply", "i would love the opportunity", "please find attached my resume", "dear hiring manager",
         "i believe i would be a great fit", "thank you for your time and consideration", "i am reaching out to",
         "perfect fit", "synergy", "passionate about leveraging", "i'm excited by", "i am excited by",
         "i'm thrilled", "i am thrilled")
MAX_WORDS = 180
ALWAYS_OK = {"linkedin", "github", "gmail", "pdf", "resume", "cv", "ai", "ml", "llm", "llms", "api", "apis", "ps"}


@dataclass
class EmailReview:
    blocks: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.blocks


def vault_text(vault: Vault) -> str:
    parts = []
    for a in vault.achievements.values():
        parts += [a.text, " ".join(a.skills), " ".join(a.metrics), a.owner]
    parts += [" ".join(items) for items in vault.skills.values()]
    parts += vault.employers
    return " ".join(parts)


def check_email(payload: dict, *, company: str, role: str, job: str, brief: dict | None, vault: Vault,
                sender_name: str = "", sender_links: str = "", last_touch: datetime | None = None,
                cooldown_days: int = 14, now: datetime | None = None) -> EmailReview:
    review = EmailReview()
    now = now or datetime.now(timezone.utc)
    to = (payload.get("to") or "").strip()
    if not to:
        review.blocks.append("No recipient yet. Add the recruiter's email to send this.")
    elif not EMAIL.match(to):
        review.blocks.append(f"'{to}' is not a valid email address.")
    elif NO_REPLY.match(to.split("@")[0]):
        review.blocks.append(f"{to} is a no-reply mailbox; nobody will read it.")
    body, subject = payload.get("body") or "", payload.get("subject") or ""
    text = f"{subject}\n{body}"
    brief_text = " ".join(c.get("text", "") for key in ("product", "stage", "recent_news", "tech_stack", "fit_notes")
                          for c in ((brief or {}).get(key) or [])) + " " + ((brief or {}).get("summary") or "")
    context = " ".join([vault_text(vault), job, brief_text, company, role, payload.get("to_name") or "", sender_name, sender_links])
    numbers = set(_NUMBER.findall(text)) - set(_NUMBER.findall(context))
    if numbers:
        review.blocks.append(f"Numbers that aren't in your vault, the JD or the brief: {', '.join(sorted(numbers))}.")
    # A number the vault states as approximate ("approximately 40%", "~40%", "100+") must stay
    # approximate wherever it appears, subject included.
    vault_hedged = hedged_numbers(vault_text(vault))
    exact = sorted(n for n in set(_NUMBER.findall(text)) & vault_hedged
                   if n not in hedged_numbers(subject) | hedged_numbers(body) or
                   (n in _NUMBER.findall(subject) and n not in hedged_numbers(subject)))
    if exact:
        review.blocks.append(f"States {', '.join(exact)} as exact; your vault says it is approximate "
                             "(keep \"approximately\" or \"~\").")
    known = words(context) | ALWAYS_OK
    unknown = sorted(t for t in notable_terms(body) if t not in known and t.rstrip("s") not in known)
    if unknown:
        review.blocks.append(f"Names or tools not in your vault, the JD or the brief: {', '.join(unknown[:8])}.")
    for years in _YEARS.findall(text):
        if vault.total_years is None or float(years) > vault.total_years:
            review.blocks.append(f"Claims {years} years of experience; your vault says {vault.total_years}.")
    if company and company.lower() not in text.lower():
        review.blocks.append(f"It never names {company}.")
    stock = [p for p in STOCK if p in text.lower()]
    if len(stock) >= 2:
        review.blocks.append("Reads like a template: " + "; ".join(f'"{p}"' for p in stock[:3]) + ".")
    elif stock:
        review.notes.append(f'Stock phrase: "{stock[0]}".')
    specific = words(body) & (words(brief_text) | words(job)) - words(company) - words(role) - ALWAYS_OK
    if len(specific) < 2:
        review.notes.append("Nothing specific about the company or the role; consider adding one detail from the brief.")
    if len(body.split()) > MAX_WORDS:
        review.notes.append(f"{len(body.split())} words; recruiters skim, under {MAX_WORDS} reads better.")
    if not payload.get("attachment"):
        review.notes.append("No resume attached.")
    if last_touch and now - last_touch < timedelta(days=cooldown_days):
        review.blocks.append(f"You emailed this person on {last_touch:%d %b}; wait {cooldown_days} days between contacts.")
    return review
