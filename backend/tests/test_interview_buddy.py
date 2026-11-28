"""Day 13 without a database: the prep pack keeps only real stories, flags numbers that aren't
in your facts, drops gap advice that claims experience you don't have, and takes pay notes
from the research. Fictional data only."""
from pathlib import Path

from app.experts import comp_analyst, interview_buddy as ib
from app.experts.reviewer import vault_text
from app.tailor import vault as vault_mod

VAULT = vault_mod.load(Path(__file__).parent / "fixtures" / "resume" / "fact_vault.yaml")
JOB = "Acme is hiring an ML Engineer to build RAG on pgvector with FastAPI. Experience with Kubeflow and Terraform is a plus."
REAL = next(iter(VAULT.achievements))


def plan(**kw):
    base = dict(
        rounds=[ib.Round(name="Technical", focus="RAG systems", questions=[
            ib.Question(question="Walk us through a RAG system you built.", why="Core of the role", stories=[REAL, "made-up-id"],
                        outline="Describe the pgvector service and how you measured retrieval quality."),
            ib.Question(question="How did you cut latency?", stories=[REAL], outline="Explain how you cut latency by 73% in a week.")])],
        gaps=[ib.Gap(term="kubeflow", how="I have used Kubeflow in production."),
              ib.Gap(term="terraform", how="Say it's new to you; you've automated deployments with Docker and would ramp up fast.")],
        questions_to_ask=["How do you evaluate retrieval quality today?"], strategy=["Lead with the RAG story."])
    return ib.Prep(**{**base, **kw})


def test_gaps_are_terms_in_the_jd_that_the_vault_lacks():
    gaps = [g.lower() for g in ib.gap_terms(JOB, VAULT)]
    assert "kubeflow" in gaps and "terraform" in gaps and "pgvector" not in gaps and "experience" not in gaps
    banner = "We use cookies. Accept or Decline. Always choose wisely. Healthcare Culture matters. " + JOB
    assert [g.lower() for g in ib.gap_terms(banner, VAULT)] == gaps            # page chrome never counts


def test_pack_keeps_real_stories_flags_numbers_and_drops_false_claims():
    pack = ib.build(plan(), VAULT, ["kubeflow", "terraform"], " ".join([vault_text(VAULT), JOB]), None, comp_analyst.band_text)
    q1, q2 = pack["rounds"][0]["questions"]
    assert q1["stories"] == [REAL] and q1["check"] == ""
    assert "73" in q2["check"]                                               # not in the vault or the JD
    assert [s["id"] for s in pack["stories"]] == [REAL] and pack["stories"][0]["text"] == VAULT.achievements[REAL].text
    gaps = {g["term"]: g["how"] for g in pack["gaps"]}
    assert gaps["terraform"].startswith("Say it's new to you")
    assert gaps["kubeflow"].startswith("Not in your vault")                 # "I have used Kubeflow" was dropped
    assert pack["negotiation"][0].startswith("No pay research yet")


def test_negotiation_comes_from_the_pay_report():
    L = 100_000
    comp = {"jd_range": None, "market": {"low": 17 * L, "high": 25 * L, "currency": "INR", "n": 2},
            "suggested": {"low": 21 * L, "high": 25 * L, "currency": "INR"}, "yours": {"expected_floor": "20 LPA"}}
    lines = ib.negotiation(comp, comp_analyst.band_text)
    assert lines == ["Public data puts this role at 17–25 LPA (2 sources).",
                     "If asked for a number, a researched ask is 21–25 LPA; let them name a band first if you can.",
                     "Your floor from your vault: 20 LPA."]


def test_ids_handles_and_links_are_not_skills():
    from app.tailor.terms import job_terms
    assert job_terms("Signed in as someone1234 (x@y.example). Req R050976. Kubernetes, GPT-4, S3, RCM. https://x.example/Foo2") == \
        ["GPT-4", "Kubernetes", "RCM", "S3"]
