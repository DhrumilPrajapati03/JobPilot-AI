"""Tailor building blocks on a synthetic resume: parse/render, escaping, the fact-vault
validator, keyword coverage and page trimming. No model, no Tectonic."""
from pathlib import Path

import pytest

from app.tailor import plan as plan_mod
from app.tailor import validator, vault as vault_mod
from app.tailor.texdoc import Edits, parse, plain, render, to_latex

FIXTURES = Path(__file__).parent / "fixtures" / "resume"
SOURCE = (FIXTURES / "master.tex").read_text(encoding="utf-8")
JOB = "We need an ML engineer with RAG, pgvector, FastAPI and Kubernetes. Terraform is a plus."


@pytest.fixture()
def doc():
    return parse(SOURCE)


@pytest.fixture()
def vault():
    return vault_mod.load(FIXTURES / "fact_vault.yaml")


def test_parse_finds_entries_bullets_and_skills(doc):
    assert [(e.id, len(e.bullets)) for e in doc.entries] == [("exp1", 3), ("exp2", 1), ("proj1", 1), ("proj2", 1)]
    assert doc.entry("exp1").heading[:3] == ["Machine Learning Engineer", "Jan 2025 – Present", "Example Labs"]
    assert [s.category for s in doc.skills] == ["Languages", "ML & Retrieval", "Tools"]
    assert doc.bullets()["exp1.b2"].text == "Reduced model serving latency by 35% by batching requests in FastAPI"


def test_no_edits_is_byte_identical(doc):
    assert render(doc) == SOURCE
    assert render(doc, Edits(bullet_order={"exp1": ["exp1.b1", "exp1.b2", "exp1.b3"]})) == SOURCE


def test_edits_render_and_reparse(doc):
    out = render(doc, Edits(bullet_order={"exp1": ["exp1.b2", "exp1.b1"]}, rewrites={"exp1.b1": "Built a **RAG** service"},
                            entry_order={"projects": ["proj2", "proj1"]}, skills={"Tools": ["FastAPI", "Docker"]}))
    again = parse(out)
    assert [b.text for b in again.entry("exp1").bullets] == [
        "Reduced model serving latency by 35% by batching requests in FastAPI", "Built a RAG service"]
    assert [e.heading[0] for e in again.entries if e.section == "projects"] == ["Chess Bot | Weekend project",
                                                                               "Doc Search | Semantic search over manuals"]
    assert again.skills[2].items == ["FastAPI", "Docker"] and again.skills[0].items == ["Python", "SQL", "Go"]
    assert again.entry("exp1").heading == doc.entry("exp1").heading  # titles, employers and dates never change


def test_rewrites_cannot_inject_latex():
    assert to_latex(r"Owned \input{/etc/passwd} & 100% of $x_1$") == \
        r"Owned \textbackslash{}input\{/etc/passwd\} \& 100\% of \$x\_1\$"
    assert to_latex("Built **RAG** and **evals**") == r"Built \textbf{RAG} and \textbf{evals}"


def test_every_bullet_maps_to_its_confirmed_fact(doc, vault):
    mapping = {bid: vault_mod.match(b.text, vault)[0] for bid, b in doc.bullets().items()}
    assert mapping == {"exp1.b1": "exp.labs.rag", "exp1.b2": "exp.labs.latency", "exp1.b3": "exp.labs.evals",
                       "exp2.b1": "exp.sample.reports", "proj1.b1": "proj.docsearch.index", "proj2.b1": None}


@pytest.mark.parametrize("bullet,text,reason", [
    ("exp1.b2", "Cut FastAPI serving latency by 50% with request batching", "numbers not in the vault"),
    ("exp1.b1", "Built a RAG service on Kubernetes with pgvector for 40 teams", "kubernetes"),
    ("exp1.b3", "Wrote Pytest evaluation suites covering 120 labelled cases using Terraform", "terraform"),
    ("exp1.b1", "Built a RAG service with 5+ years of PostgreSQL experience", "years of experience"),
    ("exp1.b3", "Wrote Pytest suites for 120 cases with FAISS", "faiss"),          # FAISS is real, but from another fact
    ("proj2.b1", "Wrote a minimax chess engine in Python", None),                 # identical text: not a rewrite
    ("proj2.b1", "Built a minimax chess engine in Python", "no confirmed fact"),
])
def test_validator_refuses_claims_outside_the_bullets_fact(doc, vault, bullet, text, reason):
    reviewed = validator.review(doc, Edits(rewrites={bullet: text}), vault)
    if reason is None:
        assert not reviewed.rejected and bullet not in reviewed.edits.rewrites
        return
    assert bullet not in reviewed.edits.rewrites
    assert reason in " ".join(reviewed.rejected[0]["reasons"]).lower()


def test_validator_accepts_a_faithful_rewording(doc, vault):
    text = "Cut FastAPI serving latency by 35% by **batching** model requests"
    reviewed = validator.review(doc, Edits(rewrites={"exp1.b2": text}), vault)
    assert reviewed.edits.rewrites == {"exp1.b2": text} and not reviewed.rejected


def test_structure_rules(doc, vault):
    reviewed = validator.review(doc, Edits(
        bullet_order={"exp1": ["exp1.b3", "exp2.b1", "exp1.b1"], "exp2": [], "nope": ["x"]},
        entry_order={"experience": ["exp2", "exp1"], "projects": ["proj1"]},
        skills={"Tools": ["Docker", "Kubernetes", "fastapi"], "Cooking": ["Pasta"]}), vault)
    assert reviewed.edits.bullet_order == {"exp1": ["exp1.b3", "exp1.b1"]}   # cross-entry bullet ignored
    assert "exp2" not in reviewed.edits.bullet_order                          # can't empty an entry
    assert "experience" not in reviewed.edits.entry_order                     # history is fixed
    assert reviewed.edits.entry_order == {"projects": ["proj1"]}
    assert reviewed.edits.skills == {"Tools": ["Docker", "FastAPI"]}
    assert any("Kubernetes" in r["text"] for r in reviewed.rejected)


def test_coverage_counts_vault_skills_and_lists_what_you_lack(doc, vault):
    cov = plan_mod.coverage(JOB, SOURCE, vault)
    assert set(cov.keywords) == {"RAG", "pgvector", "FastAPI"} and cov.score == 100.0
    assert {"Kubernetes", "Terraform"} <= set(cov.missing)
    smaller = render(doc, Edits(bullet_order={"exp1": ["exp1.b1"]}, skills={"Tools": ["Docker"]}))
    assert "FastAPI" not in plan_mod.coverage(JOB, smaller, vault).covered


def test_trim_drops_from_the_longest_entry_and_never_empties_one(doc):
    edits = plan_mod.trim_for_pages(doc, Edits())
    assert edits.bullet_order == {"exp1": ["exp1.b1", "exp1.b2"]}
    for _ in range(2):
        edits = plan_mod.trim_for_pages(doc, edits) or edits
    assert edits.bullet_order["exp1"] == ["exp1.b1"]
    assert plan_mod.trim_for_pages(doc, edits) is None


def test_plan_caps_rewrites():
    plan = plan_mod.Plan(rewrites=[{"id": f"b{i}", "text": "x"} for i in range(9)])
    assert len(plan.edits().rewrites) == plan_mod.MAX_REWRITES


def test_plain_text_of_latex():
    assert plain(r"Cut \textbf{latency} by 35\% \& more -- fast") == "Cut latency by 35% & more – fast"


def test_typographic_hyphens_and_tilde_match_the_vault(doc, vault):
    text = "Cut FastAPI serving latency by ~35% by batching requests‑wise"
    reviewed = validator.review(doc, Edits(rewrites={"exp1.b2": text}), vault)
    assert not reviewed.rejected and reviewed.edits.rewrites["exp1.b2"].endswith("requests-wise")


def test_missing_terms_skip_plain_words_boards_and_the_company(vault):
    job = "Originally posted on Himalayas. Acme needs Kubernetes; Acme ships Terraform. Exciting role."
    assert plan_mod.coverage(job, SOURCE, vault, "Acme").missing == ["Kubernetes", "Terraform"]


@pytest.mark.parametrize("original,new,ok", [
    ("reduced latency by approximately 40%", "cut latency by 40%", False),
    ("reduced latency by approximately 40%", "cut latency by ~40%", True),
    ("supporting 100+ articles a month", "supporting over 100 articles a month", True),
    ("supporting 100+ articles a month", "supporting 100 articles a month", False),
    ("reduced effort by 70%", "cut effort by 70%", True),
])
def test_approximate_numbers_stay_approximate(original, new, ok):
    keep = validator.hedged_numbers(original)
    lost = [n for n in validator._NUMBER.findall(new) if n in keep and n not in validator.hedged_numbers(new)]
    assert (not lost) == ok
