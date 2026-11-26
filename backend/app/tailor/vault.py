"""The fact vault (private/fact_vault.yaml): the only source of truth about Dhrumil.

Only entries with `status: confirmed` count; drafts and TODOs are unknown. Each resume bullet
is matched to the vault achievement it came from, so a rewrite can be checked against
exactly that fact (and not borrow claims from another job).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9+#.\-/]*")
MATCH_THRESHOLD = 0.3


class VaultError(ValueError):
    pass


@dataclass
class Achievement:
    id: str
    text: str
    skills: list[str] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)   # values with their basis, flattened to text
    owner: str = ""                                    # employer or project name


@dataclass
class Vault:
    achievements: dict[str, Achievement]
    skills: dict[str, list[str]]
    total_years: float | None
    never_claim: list[str]
    employers: list[str]
    name: str = ""
    links: dict[str, str] = field(default_factory=dict)   # confirmed linkedin/github/portfolio URLs

    def all_skills(self) -> set[str]:
        return {s.lower() for items in self.skills.values() for s in items}


def words(text: str) -> set[str]:
    return {w.lower().strip(".-/") for w in _WORD.findall(text or "") if len(w) > 1}


def _confirmed(item: dict) -> bool:
    return isinstance(item, dict) and str(item.get("status", "confirmed")).lower() == "confirmed"


def load(path: Path | str) -> Vault:
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise VaultError(f"Fact vault not found at {path}") from None
    achievements: dict[str, Achievement] = {}
    employers = []
    for group, owner_key in (("experience", "employer"), ("projects", "name")):
        for item in raw.get(group) or []:
            if not _confirmed(item):
                continue
            if group == "experience" and item.get("employer"):
                employers.append(str(item["employer"]))
            for a in item.get("achievements") or []:
                if not a.get("id") or not a.get("text") or str(a.get("status", "confirmed")).lower() != "confirmed":
                    continue
                metrics = [" ".join(str(v) for v in m.values()) if isinstance(m, dict) else str(m) for m in a.get("metrics") or []]
                achievements[a["id"]] = Achievement(a["id"], str(a["text"]), [str(s) for s in a.get("skills") or []],
                                                    metrics, str(item.get(owner_key) or ""))
    skills_raw = raw.get("skills") or {}
    skills = {k: [str(s) for s in v] for k, v in skills_raw.items() if isinstance(v, list)} if _confirmed(skills_raw) else {}
    facts = raw.get("application_facts") or {}
    try:
        years = float(facts.get("total_experience_years"))
    except (TypeError, ValueError):
        years = None
    person = raw.get("person") or {}
    contact = raw.get("contact") or {}
    links = {}
    if _confirmed(contact):
        for key in ("linkedin", "github", "portfolio"):
            value = str(contact.get(key) or "").strip()
            if value.startswith("http"):
                links[key] = value
    return Vault(achievements, skills, years, [str(x) for x in raw.get("never_claim") or []], employers,
                 name=str(person.get("full_name") or "") if _confirmed(person) else "", links=links)


def match(bullet_text: str, vault: Vault) -> tuple[str | None, float]:
    """The vault achievement a bullet came from (Jaccard on words), or None below the threshold."""
    target = words(bullet_text)
    best, score = None, 0.0
    for a in vault.achievements.values():
        other = words(a.text)
        if not target or not other:
            continue
        s = len(target & other) / len(target | other)
        if s > score:
            best, score = a.id, s
    return (best, score) if score >= MATCH_THRESHOLD else (None, score)
