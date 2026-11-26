"""Profile facts for application forms, from the confirmed parts of your fact vault only.

Read straight from `private/fact_vault.yaml` (sections `person`, `contact`,
`application_facts`); entries not marked confirmed are ignored. These values go only to your
own extension, to fill your own forms, and never into a model prompt except name and links.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.config import settings


@dataclass
class Profile:
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    links: dict[str, str] = field(default_factory=dict)
    facts: dict[str, str] = field(default_factory=dict)    # application_facts, as text

    @property
    def first_name(self) -> str:
        return self.full_name.split()[0] if self.full_name else ""

    @property
    def last_name(self) -> str:
        return " ".join(self.full_name.split()[1:])


PLACEHOLDER = re.compile(r"^\s*(todo|tbd|tbc|xx+|\?+|-+|<[^>]*>|\[[^\]]*\]|fill ?me|fixme)\s*$", re.I)


def real(value) -> bool:
    """A filled-in value, not a template placeholder like TODO or <your salary>."""
    return value not in (None, "") and not PLACEHOLDER.match(str(value))


def _confirmed(item) -> bool:
    return isinstance(item, dict) and str(item.get("status", "confirmed")).lower() == "confirmed"


def load(path: Path | str | None = None) -> Profile:
    raw = yaml.safe_load(Path(path or settings.FACT_VAULT_PATH).read_text(encoding="utf-8")) or {}
    person, contact, facts = raw.get("person") or {}, raw.get("contact") or {}, raw.get("application_facts") or {}
    out = Profile()
    if _confirmed(person):
        out.full_name = str(person.get("full_name") or "").strip() if real(person.get("full_name")) else ""
        loc = person.get("location")
        if isinstance(loc, dict):
            out.location = ", ".join(str(loc[k]) for k in ("city", "state", "country") if loc.get(k))
        elif real(loc):
            out.location = str(loc)
    if _confirmed(contact):
        out.email = str(contact.get("email")).strip() if real(contact.get("email")) else ""
        out.phone = str(contact.get("phone")).strip() if real(contact.get("phone")) else ""
        out.links = {k: str(contact[k]).strip() for k in ("linkedin", "github", "portfolio")
                     if str(contact.get(k) or "").startswith("http")}
    if isinstance(facts, dict) and str(facts.get("status", "confirmed")).lower() == "confirmed":
        out.facts = {k: str(v).strip() for k, v in facts.items() if real(v) and k not in ("status", "source")}
    return out
