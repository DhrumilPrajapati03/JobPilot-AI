"""Reviewer checks and the Gmail executor, without a database or network."""
from datetime import datetime, timedelta, timezone
from email import message_from_bytes
from pathlib import Path

import httpx
import pytest

from app.courier import gmail
from app.experts import reviewer
from app.tailor import vault as vault_mod

FIXTURES = Path(__file__).parent / "fixtures" / "resume"
VAULT = vault_mod.load(FIXTURES / "fact_vault.yaml")
JOB = "Acme is hiring an ML Engineer to build RAG on pgvector with FastAPI. Acme ships Kubeflow pipelines."
BRIEF = {"summary": "Acme builds retrieval tools for support teams.",
         "product": [{"text": "Support search for 300 companies", "sources": [1]}], "tech_stack": [{"text": "pgvector", "sources": [1]}]}
GOOD = ("Hi Jane,\n\nI saw Acme is building RAG on pgvector for support search. At Example Labs I built a RAG service on "
        "PostgreSQL and pgvector that answers support questions for 40 teams, and reduced serving latency by 35% by batching "
        "requests in FastAPI.\n\nWould you consider my application for the ML Engineer role? My resume is attached.\n\nAda Example")


def check(body=GOOD, to="jane@acme.example", **kw):
    payload = {"to": to, "to_name": "Jane", "subject": "ML Engineer: RAG on pgvector", "body": body,
               "attachment": {"path": "x.pdf", "sha256": "a" * 64}}
    return reviewer.check_email(payload, company="Acme", role="ML Engineer", job=JOB, brief=BRIEF, vault=VAULT,
                                sender_name="Ada Example", **kw)


def test_a_specific_true_email_passes():
    review = check()
    assert review.ok, review.blocks
    assert not any("specific" in n for n in review.notes)


@pytest.mark.parametrize("body,reason", [
    (GOOD.replace("35%", "60%"), "Numbers"),
    (GOOD.replace("in FastAPI", "in FastAPI and Kubernetes"), "kubernetes"),
    (GOOD + "\nI have 5 years of experience.", "years"),
    (GOOD.replace("Acme", "your company"), "never names"),
    ("I hope this email finds you well. I am writing to express interest in Acme. " + GOOD, "template"),
])
def test_reviewer_blocks(body, reason):
    review = check(body)
    assert not review.ok and reason.lower() in " ".join(review.blocks).lower()


@pytest.mark.parametrize("to,reason", [("", "No recipient"), ("not-an-email", "not a valid"),
                                       ("noreply@acme.example", "no-reply")])
def test_reviewer_checks_the_recipient(to, reason):
    assert reason in " ".join(check(to=to).blocks)


def test_company_numbers_from_the_brief_are_allowed_and_cooldown_blocks():
    assert check(GOOD.replace("Hi Jane,", "Hi Jane, Acme already serves 300 companies.")).ok
    recent = datetime.now(timezone.utc) - timedelta(days=3)
    assert "wait 14 days" in " ".join(check(last_touch=recent).blocks)


def test_message_is_built_with_fixed_id_and_attachment():
    payload = {"to": "jane@acme.example", "to_name": "Jane", "subject": "Hello", "body": "Body text"}
    msg = gmail.build(payload, "me@gmail.com", "Ada Example", "a1b2", ("Ada_Resume.pdf", b"%PDF-1.4"))
    parsed = message_from_bytes(msg.as_bytes())
    assert parsed["Message-ID"] == "<jobdots.a1b2@gmail.com>" and "Jane" in parsed["To"] and "Ada Example" in parsed["From"]
    assert [p.get_filename() for p in parsed.walk() if p.get_filename()] == ["Ada_Resume.pdf"]


def transport(sent_exists=False, send_status=200, timeout=False):
    calls = []

    def respond(request):
        calls.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json={"messages": [{"id": "old-1"}]} if sent_exists else {})
        if timeout:
            raise httpx.ReadTimeout("slow", request=request)
        if send_status == 200:
            return httpx.Response(200, json={"id": "gm-1"})
        return httpx.Response(send_status, json={"error": {"message": "Recipient address rejected"}})
    return httpx.Client(transport=httpx.MockTransport(respond)), calls


@pytest.mark.parametrize("kwargs,status,ref", [
    ({}, "provider_accepted", "gm-1"),
    ({"sent_exists": True}, "provider_accepted", "old-1"),
    ({"send_status": 400}, "failed", None),
    ({"send_status": 503}, "send_unknown", None),
    ({"timeout": True}, "send_unknown", None),
])
def test_send_outcomes(kwargs, status, ref):
    client, calls = transport(**kwargs)
    msg = gmail.build({"to": "a@b.example", "subject": "s", "body": "b"}, "me@gmail.com", "", "id1", None)
    result = gmail.send(client, "token", msg)
    assert result.status == status and result.provider_ref == ref
    if kwargs.get("sent_exists"):
        assert ("POST", "/gmail/v1/users/me/messages/send") not in calls   # never sent twice


def test_attachment_must_match_the_approved_hash(tmp_path):
    import hashlib
    (tmp_path / "r.pdf").write_bytes(b"%PDF approved")
    att = {"path": "r.pdf", "sha256": hashlib.sha256(b"%PDF approved").hexdigest(), "filename": "R.pdf"}
    assert gmail.attachment_for({"attachment": att}, str(tmp_path)) == ("R.pdf", b"%PDF approved")
    (tmp_path / "r.pdf").write_bytes(b"%PDF changed")
    with pytest.raises(ValueError):
        gmail.attachment_for({"attachment": att}, str(tmp_path))
    with pytest.raises(FileNotFoundError):
        gmail.attachment_for({"attachment": {**att, "path": "../../etc/passwd"}}, str(tmp_path))


def test_approximate_vault_numbers_stay_approximate_in_subject_and_body():
    import dataclasses
    hedged = dataclasses.replace(VAULT, achievements={**VAULT.achievements, "exp.labs.latency": dataclasses.replace(
        VAULT.achievements["exp.labs.latency"], text="Reduced model serving latency by approximately 35% by batching requests in FastAPI")})
    def run(subject, body):
        payload = {"to": "jane@acme.example", "to_name": "Jane", "subject": subject, "body": body, "attachment": {"path": "x"}}
        return reviewer.check_email(payload, company="Acme", role="ML Engineer", job=JOB, brief=BRIEF, vault=hedged)
    ok_body = GOOD.replace("by 35%", "by approximately 35%")
    assert run("ML Engineer: RAG on pgvector", ok_body).ok
    assert run("ML Engineer: ~35% faster serving", ok_body).ok
    subject_exact = run("ML Engineer: 35% latency cut", ok_body)
    assert not subject_exact.ok and "approximate" in subject_exact.blocks[0]
    assert not run("ML Engineer: RAG on pgvector", GOOD).ok   # body drops the qualifier


def test_excited_opener_counts_as_stock():
    assert any("excited" in n for n in check("Hi Jane,\n\nI'm excited by Acme. " + GOOD).notes)
