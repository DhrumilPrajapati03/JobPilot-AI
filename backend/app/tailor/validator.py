"""Tailoring plan validation: nothing reaches the resume unless the fact vault supports it.

Structure rules (always enforced):
* Experience entries keep their order and are never dropped (no gaps, no reshuffled history).
* Bullets can be reordered or dropped within their own entry; each entry keeps at least one.
* Projects can be reordered or dropped; at least one stays.
* Skills can be reordered or dropped within their category; none can be added.

Rewrite rules (a failing rewrite falls back to the original bullet and is reported):
* The bullet must map to a confirmed vault achievement.
* No number that isn't in that achievement (text or metric basis) or the original bullet, and an
  approximate number stays approximate ("~40%" can't become "40%").
* No tool, product or proper name that isn't in that achievement, its skills or the original.
* No years-of-experience claim above total_experience_years.
* Plain text only: no LaTeX or markup characters.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.tailor.texdoc import Edits, TexDoc, normalize, plain
from app.tailor.vault import Vault, match, words

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-/]*")
# Rewrites are plain text (with **bold**); LaTeX or markup characters are refused, not escaped into the PDF.
_MARKUP = re.compile(r"[\\{}$^<>]")  # "~" is allowed: vault metrics use it ("~40%"); it is escaped when rendered
_YEARS = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", re.I)


@dataclass
class Review:
    edits: Edits
    rejected: list[dict] = field(default_factory=list)   # {bullet, text, reasons}
    structure: list[str] = field(default_factory=list)   # structural problems that were ignored
    mapping: dict[str, str | None] = field(default_factory=dict)


def notable_terms(text: str) -> set[str]:
    """Names, tools and products: tokens with digits or inner capitals, or capitalised mid-sentence."""
    terms = set()
    for sentence in re.split(r"(?<=[.;:!?])\s+", text.replace("**", "")):
        for i, token in enumerate(_TOKEN.findall(sentence)):
            t = token.strip(".-/")
            if len(t) < 2:
                continue
            if any(c.isdigit() for c in t) or any(c.isupper() for c in t[1:]) or (i > 0 and t[0].isupper()):
                terms.add(t.lower())
    return terms


_HEDGE = re.compile(r"(?:~|\b(?:approximately|approx\.?|about|around|roughly|nearly|almost|over|more than|up to|under|"
                    r"less than|at least)\s*)$", re.I)


def hedged_numbers(text: str) -> set[str]:
    """Numbers stated as approximate or bounded ("~40%", "approximately 40%", "100+", "over 100")."""
    found = set()
    for m in _NUMBER.finditer(text):
        before, after = text[max(0, m.start() - 20):m.start()], text[m.end():m.end() + 1]
        if _HEDGE.search(before) or after == "+":
            found.add(m.group(0))
    return found


def check_rewrite(original: str, new: str, achievement, vault: Vault) -> list[str]:
    new = normalize(new)
    if achievement is None:
        return ["this bullet has no confirmed fact in the vault, so it can't be reworded"]
    reasons = []
    markup = sorted(set(_MARKUP.findall(new)))
    if markup:
        reasons.append(f"plain text only; remove {' '.join(markup)}")
    allowed_text = " ".join([achievement.text, original, " ".join(achievement.skills), " ".join(achievement.metrics)])
    allowed_numbers = set(_NUMBER.findall(allowed_text))
    new_numbers = set(_NUMBER.findall(new)) - allowed_numbers
    if new_numbers:
        reasons.append(f"numbers not in the vault fact: {', '.join(sorted(new_numbers))}")
    for number in sorted(set(_NUMBER.findall(new)) & hedged_numbers(original)):
        if number not in hedged_numbers(new):
            reasons.append(f"keep the qualifier on {number} (the original says it is approximate)")
    allowed_words = words(allowed_text) | {s.lower() for s in achievement.skills}
    unknown = sorted(t for t in notable_terms(new) if t not in allowed_words and t.rstrip("s") not in allowed_words)
    if unknown:
        reasons.append(f"names or tools not in the vault fact: {', '.join(unknown)}")
    for years in _YEARS.findall(new):
        if vault.total_years is None or float(years) > vault.total_years:
            reasons.append(f"claims {years} years of experience")
    if len(new) > max(320, int(len(original) * 1.5)):
        reasons.append("much longer than the original bullet")
    return reasons


def review(doc: TexDoc, proposed: Edits, vault: Vault) -> Review:
    """Keep only the parts of a plan that pass; everything else is reported, not applied."""
    out = Review(Edits())
    bullets = doc.bullets()
    out.mapping = {bid: match(b.text, vault)[0] for bid, b in bullets.items()}

    for entry_id, order in proposed.bullet_order.items():
        try:
            entry = doc.entry(entry_id)
        except KeyError:
            out.structure.append(f"unknown entry {entry_id}")
            continue
        own = [b.id for b in entry.bullets]
        clean = [b for b in dict.fromkeys(order) if b in own]
        if not clean:
            out.structure.append(f"{entry_id}: a plan can't remove every bullet")
            continue
        if len(clean) != len(order):
            out.structure.append(f"{entry_id}: ignored bullets from other entries")
        out.edits.bullet_order[entry_id] = clean

    for section, order in proposed.entry_order.items():
        current = [e.id for e in doc.entries if e.section == section]
        if section == "experience":
            if order != current:
                out.structure.append("experience order and entries are fixed")
            continue
        clean = [e for e in dict.fromkeys(order) if e in current]
        if section == "projects" and clean:
            out.edits.entry_order[section] = clean

    lines = {s.category: s.items for s in doc.skills}
    for category, items in proposed.skills.items():
        if category not in lines:
            out.structure.append(f"unknown skills category {category}")
            continue
        known = {i.lower(): i for i in lines[category]}
        clean = [known[i.lower()] for i in dict.fromkeys(items) if i.lower() in known]
        added = [i for i in items if i.lower() not in known]
        if added:
            out.rejected.append({"bullet": f"skills:{category}", "text": ", ".join(added),
                                 "reasons": ["skills can't be added, only reordered or removed"]})
        if clean:
            out.edits.skills[category] = clean

    for bullet_id, text in proposed.rewrites.items():
        bullet = bullets.get(bullet_id)
        if bullet is None or not text.strip():
            continue
        if plain(text) == bullet.text:
            continue
        achievement = vault.achievements.get(out.mapping.get(bullet_id) or "")
        reasons = check_rewrite(bullet.text, text, achievement, vault)
        if reasons:
            out.rejected.append({"bullet": bullet_id, "text": text, "reasons": reasons})
        else:
            out.edits.rewrites[bullet_id] = normalize(text)
    return out
