"""Read and rewrite the master resume .tex without letting anyone write LaTeX (plan Day 4).

The resume uses the common "Jake's resume" macros. This module finds the parts a tailoring
plan may touch, by exact character spans:

* Experience/Projects entries (`\\resumeSubheading{4 args}` / `\\resumeProjectHeading{2 args}`)
  and their bullets (`\\resumeItem{...}`). Entry headings (title, employer, dates) are read
  only; they are never edited.
* Technical Skills lines (`\\textbf{Category}: a, b, c\\\\`).

`render(doc, edits)` rebuilds only what changed: with no edits the output is byte-identical
to the input. Rewritten bullet text arrives as plain text (with optional **bold**) and is
LaTeX-escaped here, so a plan can't inject commands.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

ENTRY_MACROS = {"\\resumeSubheading": 4, "\\resumeProjectHeading": 2}
_SECTION = re.compile(r"\\section\{([^}]*)\}")
_SKILL_LINE = re.compile(r"\\textbf\{(?P<cat>[^}]*)\}\s*:\s*(?P<items>.*?)(?=\\\\|\Z)", re.S)


class TexError(ValueError):
    pass


def _balanced(text: str, start: int) -> int:
    """Index just after the brace group that opens at text[start] == '{'."""
    if text[start] != "{":
        raise TexError(f"expected '{{' at {start}")
    depth, i = 0, start
    while i < len(text):
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise TexError("unbalanced braces")


def _args(text: str, pos: int, count: int) -> tuple[list[str], int]:
    """Up to `count` brace groups (resumes often pass fewer, e.g. a project heading without dates)."""
    args = []
    for _ in range(count):
        probe = pos
        while probe < len(text) and text[probe].isspace():
            probe += 1
        if probe >= len(text) or text[probe] != "{":
            break
        pos = probe
        end = _balanced(text, pos)
        args.append(text[pos + 1:end - 1])
        pos = end
    return args, pos


def plain(latex: str) -> str:
    """Readable text of a LaTeX fragment (for matching, prompts and diffs)."""
    s = re.sub(r"\\(textbf|textit|underline|emph)\{", "{", latex)
    s = re.sub(r"\\href\{[^}]*\}", "", s)
    s = s.replace("\\%", "%").replace("\\&", "&").replace("\\$", "$").replace("\\#", "#").replace("\\_", "_")
    s = s.replace("--", "–").replace("$|$", "|").replace("~", " ")
    s = re.sub(r"\\[a-zA-Z]+\*?", "", s)
    s = s.replace("{", "").replace("}", "")
    return " ".join(s.split())


_ESCAPES = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
            "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


_DASHES = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "−": "-", " ": " ", " ": " "})


def normalize(text: str) -> str:
    """Model text uses typographic hyphens and spaces; compare and render the ASCII forms."""
    return " ".join(text.translate(_DASHES).split())


def to_latex(text: str) -> str:
    """Plain text (with optional **bold**) -> safe LaTeX. Nothing else is interpreted."""
    out = []
    for i, part in enumerate(re.split(r"\*\*", normalize(text))):
        escaped = "".join(_ESCAPES.get(c, c) for c in part)
        out.append(f"\\textbf{{{escaped}}}" if i % 2 and escaped else escaped)
    return "".join(out)


@dataclass
class Bullet:
    id: str
    latex: str            # inner text of \resumeItem{...}
    span: tuple[int, int]  # the whole \resumeItem{...} in the document

    @property
    def text(self) -> str:
        return plain(self.latex)


@dataclass
class Entry:
    id: str
    section: str          # 'experience' | 'projects'
    heading: list[str]    # plain text of the heading args (read only)
    span: tuple[int, int]  # macro start .. end of its item list (or heading)
    bullets: list[Bullet] = field(default_factory=list)
    list_span: tuple[int, int] | None = None  # between \resumeItemListStart and \resumeItemListEnd


@dataclass
class SkillLine:
    category: str
    items: list[str]
    span: tuple[int, int]  # the items text after "Category:"


@dataclass
class TexDoc:
    source: str
    entries: list[Entry]
    skills: list[SkillLine]

    def entry(self, entry_id: str) -> Entry:
        for e in self.entries:
            if e.id == entry_id:
                return e
        raise KeyError(entry_id)

    def bullets(self) -> dict[str, Bullet]:
        return {b.id: b for e in self.entries for b in e.bullets}


def _section_of(name: str) -> str | None:
    n = name.lower()
    if "experience" in n:
        return "experience"
    if "project" in n:
        return "projects"
    if "skill" in n:
        return "skills"
    return None


def parse(source: str) -> TexDoc:
    sections = [(m.start(), m.group(1)) for m in _SECTION.finditer(source)]
    end_doc = source.find("\\end{document}")
    entries, skills = [], []
    counters = {"experience": 0, "projects": 0}
    for i, (start, name) in enumerate(sections):
        stop = sections[i + 1][0] if i + 1 < len(sections) else (end_doc if end_doc != -1 else len(source))
        kind = _section_of(name)
        if kind in ("experience", "projects"):
            pattern = re.compile("|".join(re.escape(m) for m in ENTRY_MACROS) + r"(?![A-Za-z])")
            starts = [m for m in pattern.finditer(source, start, stop)]
            for j, m in enumerate(starts):
                limit = starts[j + 1].start() if j + 1 < len(starts) else stop
                args, after = _args(source, m.end(), ENTRY_MACROS[m.group(0)])
                counters[kind] += 1
                entry = Entry(f"{'exp' if kind == 'experience' else 'proj'}{counters[kind]}", kind,
                              [plain(a) for a in args], (m.start(), after))
                ls = source.find("\\resumeItemListStart", after, limit)
                le = source.find("\\resumeItemListEnd", after, limit)
                if ls != -1 and le != -1:
                    entry.list_span = (ls + len("\\resumeItemListStart"), le)
                    entry.span = (m.start(), le + len("\\resumeItemListEnd"))
                    pos, n = entry.list_span[0], 0
                    while (k := source.find("\\resumeItem{", pos, le)) != -1:
                        close = _balanced(source, k + len("\\resumeItem"))
                        n += 1
                        entry.bullets.append(Bullet(f"{entry.id}.b{n}", source[k + len("\\resumeItem{"):close - 1], (k, close)))
                        pos = close
                entries.append(entry)
        elif kind == "skills":
            body_start = source.find("\\item{", start, stop)
            if body_start == -1:
                continue
            body_end = _balanced(source, body_start + len("\\item")) - 1
            body = source[body_start + len("\\item{"):body_end]
            offset = body_start + len("\\item{")
            for m in _SKILL_LINE.finditer(body):
                raw = m.group("items")
                items = [" ".join(x.split()) for x in raw.split(",") if x.strip()]
                skills.append(SkillLine(plain(m.group("cat")), items, (offset + m.start("items"), offset + m.end("items"))))
    if not entries:
        raise TexError("No \\resumeSubheading or \\resumeProjectHeading entries found in Experience/Projects.")
    return TexDoc(source, entries, skills)


@dataclass
class Edits:
    """What a validated plan changes. Everything not mentioned stays exactly as it was."""
    bullet_order: dict[str, list[str]] = field(default_factory=dict)   # entry id -> bullet ids (missing = dropped)
    rewrites: dict[str, str] = field(default_factory=dict)             # bullet id -> plain text
    entry_order: dict[str, list[str]] = field(default_factory=dict)    # 'projects'/'experience' -> entry ids
    skills: dict[str, list[str]] = field(default_factory=dict)         # category -> items (subset, reordered)


def _indent_of(source: str, pos: int) -> str:
    line_start = source.rfind("\n", 0, pos) + 1
    return source[line_start:pos] if source[line_start:pos].strip() == "" else "      "


def _render_entry(doc: TexDoc, entry: Entry, edits: Edits) -> str:
    src = doc.source
    raw = src[entry.span[0]:entry.span[1]]
    if entry.list_span is None:
        return raw
    order = edits.bullet_order.get(entry.id)
    ids = [b.id for b in entry.bullets]
    rewritten = any(b in edits.rewrites for b in ids)
    if (order is None or order == ids) and not rewritten:
        return raw
    by_id = {b.id: b for b in entry.bullets}
    indent = _indent_of(src, entry.bullets[0].span[0]) if entry.bullets else "      "
    lines = []
    for bid in order if order is not None else ids:
        b = by_id[bid]
        if bid in edits.rewrites:
            lines.append(f"{indent}\\resumeItem{{{to_latex(edits.rewrites[bid])}}}")
        else:
            lines.append(indent + src[b.span[0]:b.span[1]])
    closing = _indent_of(src, entry.list_span[1])
    body = "\n" + "\n".join(lines) + "\n" + closing
    start = entry.list_span[0] - entry.span[0]
    end = entry.list_span[1] - entry.span[0]
    return raw[:start] + body + raw[end:]


def render(doc: TexDoc, edits: Edits | None = None) -> str:
    edits = edits or Edits()
    src = doc.source
    replacements: list[tuple[int, int, str]] = []
    for section in ("experience", "projects"):
        entries = [e for e in doc.entries if e.section == section]
        if not entries:
            continue
        order = edits.entry_order.get(section) or [e.id for e in entries]
        rendered = {e.id: _render_entry(doc, e, edits) for e in entries}
        if order == [e.id for e in entries]:
            replacements += [(e.span[0], e.span[1], rendered[e.id]) for e in entries
                             if rendered[e.id] != src[e.span[0]:e.span[1]]]
            continue
        # Reordered (or dropped) entries: keep the original separators between slots.
        seps = [src[a.span[1]:b.span[0]] for a, b in zip(entries, entries[1:])]
        sep = seps[0] if seps else "\n\n  "
        block = sep.join(rendered[eid] for eid in order)
        replacements.append((entries[0].span[0], entries[-1].span[1], block))
    for line in doc.skills:
        if line.category in edits.skills and edits.skills[line.category] != line.items:
            original = src[line.span[0]:line.span[1]]
            trailing = original[len(original.rstrip()):]
            replacements.append((line.span[0], line.span[1], ", ".join(edits.skills[line.category]) + trailing))
    out = src
    for start, end, text in sorted(replacements, reverse=True):
        out = out[:start] + text + out[end:]
    return out
