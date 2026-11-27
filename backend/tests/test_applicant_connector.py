"""Day 8 without a database: which file field takes the resume, Reviewer's LinkedIn checks,
and who Connector invites. Fictional people and companies only."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.answers.questions import kind_of
from app.experts import applicant, connector, reviewer
from app.tailor import vault as vault_mod

VAULT = vault_mod.load(Path(__file__).parent / "fixtures" / "resume" / "fact_vault.yaml")
JOB = "Acme is hiring an ML Engineer to build RAG on pgvector with FastAPI."
BRIEF = {"summary": "Acme builds retrieval tools for support teams.", "tech_stack": [{"text": "pgvector", "sources": [1]}]}
URL = "https://www.linkedin.com/in/jane-example/"


@pytest.mark.parametrize("label,others,expected", [
    ("Resume/CV", ["Resume/CV", "Cover letter"], (True, False)),
    ("CV", ["CV"], (True, False)),
    ("Cover letter", ["Resume/CV", "Cover letter"], (False, False)),
    # A provider's upload widget with a useless label: the only file field takes it, as a guess.
    ("SVGs not supported by this browser. Choose file", ["SVGs not supported by this browser. Choose file"], (True, True)),
    ("Attachment", ["Attachment", "Portfolio"], (True, True)),
    ("Portfolio", ["Attachment", "Portfolio"], (False, False)),
    ("Attachment", ["Resume", "Attachment"], (False, False)),     # another field says resume
])
def test_which_file_field_takes_the_resume(label, others, expected):
    assert applicant.is_resume_field(label, others) == expected


@pytest.mark.parametrize("label", ["First Name *", "Full name ✱", "Name *"])
def test_provider_name_labels_are_name_questions(label):
    assert kind_of(label, "text", "Acme") == "name"


def linkedin(note, kind="send_linkedin_invite", url=URL, **kw):
    payload = {"contact_id": "c1", "name": "Jane Example", "title": "Recruiter", "profile_url": url, "company": "Acme",
               "role": "ML Engineer", "note": note, "body": note}
    return reviewer.check_linkedin(payload, kind=kind, company="Acme", role="ML Engineer", job=JOB, brief=BRIEF, vault=VAULT, **kw)


GOOD_NOTE = "Hi Jane, I applied for the ML Engineer role at Acme. I built a RAG service on PostgreSQL and pgvector at Example Labs."


def test_a_short_true_note_passes():
    review = linkedin(GOOD_NOTE)
    assert review.ok, review.blocks


@pytest.mark.parametrize("note,url,reason", [
    (GOOD_NOTE + " " + "x" * 120, URL, "characters"),
    (GOOD_NOTE.replace("RAG service", "RAG service for 70 teams"), URL, "Numbers"),
    ("Hi Jane, I have 9 years of experience with pgvector at Acme.", URL, "years"),
    ("Hi Jane, I shipped Kubernetes operators at Example Labs.", URL, "kubernetes"),
    (GOOD_NOTE, "https://www.linkedin.com/company/acme/", "not a LinkedIn profile"),
    (GOOD_NOTE, "", "No LinkedIn profile link"),
])
def test_linkedin_blocks(note, url, reason):
    review = linkedin(note, url=url)
    assert not review.ok and any(reason.lower() in b.lower() for b in review.blocks), review.blocks


def test_cooldown_and_empty_notes():
    recent = datetime.now(timezone.utc) - timedelta(days=3)
    assert any("contacted this person" in b for b in linkedin(GOOD_NOTE, last_touch=recent).blocks)
    empty_invite = linkedin("")
    assert empty_invite.ok and any("No note" in n for n in empty_invite.notes)      # LinkedIn allows it
    assert not linkedin("", kind="send_linkedin_dm").ok                              # a DM needs words


def person(cid, **kw):
    return {"contact_id": cid, "name": cid.title(), "linkedin_url": f"https://www.linkedin.com/in/{cid}/", "suggested": True,
            "channel": "linkedin", "connected": False, "blocked": "", "email": "", **kw}


def test_connector_invites_suggested_linkedin_people_within_the_company_limit():
    people = [person("ann"), person("bo", channel="email", email="bo@acme.example"), person("cy", connected=True),
              person("di", suggested=False), person("ed", blocked="Do not contact"), person("fay", linkedin_url=None),
              person("gus"), person("hal"), person("ivy")]
    picked, notes = connector.candidates(people, invited={"gus"}, reached=set(), slots=2)
    assert [p["contact_id"] for p in picked] == ["ann", "hal"]
    assert any("Do not contact" in n for n in notes) and any("over your limit" in n for n in notes)
    picked, _ = connector.candidates(people, invited=set(), reached={"ann"}, slots=0)
    assert picked == []


class Thinker:
    """A reasoning model that returns nothing until asked to reason less."""
    provider, model = "groq", "openai/gpt-oss-120b"

    def __init__(self):
        self.calls = []

    async def ainvoke(self, messages, **extra):
        from app.services.llm import AIMessage
        self.calls.append(extra)
        low = extra.get("extra_body", {}).get("reasoning_effort") == "low"
        return AIMessage(content='{"notes": [{"contact_id": "c1", "note": "Hi"}]}' if low else "")


def test_structured_output_retries_once_with_less_reasoning_when_the_model_returns_nothing():
    import asyncio

    from app.services import llm
    model = Thinker()
    out = asyncio.run(llm.Structured(model, connector.InviteNotes).ainvoke([llm.HumanMessage("x")]))
    assert out.notes[0].note == "Hi" and len(model.calls) == 2
    other = Thinker()
    other.model = "qwen/qwen3.8-27b"                    # not a gpt-oss model: no retry, the error stands
    with pytest.raises(llm.OutputParserException):
        asyncio.run(llm.Structured(other, connector.InviteNotes).ainvoke([llm.HumanMessage("x")]))


def test_trim_drops_trailing_sentences_never_mid_word():
    long = "Hi Jane, I applied for the ML Engineer role at Acme. " + "I built RAG on pgvector at Example Labs. " * 5
    out = connector.trim(long)
    assert len(out) <= 200 and out.endswith(".") and out.startswith("Hi Jane")
    assert connector.trim("x" * 250) == ""                      # one huge sentence: nothing safe to keep
    assert connector.trim("Hi Jane, short.") == "Hi Jane, short."
