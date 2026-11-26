"""Answerer without a database: question kinds, option matching, profile facts from the vault,
and the answer_set artifact. Fictional profile only."""
import pytest

from app.answers import profile as profile_mod
from app.answers.bank import overlap
from app.answers.questions import company_specific, decline_option, kind_of, match_option, normalize
from app.experts import answerer, artifacts

VAULT = """
version: 1
person: {full_name: Ada Example, location: {city: Pune, state: Maharashtra, country: India}, status: confirmed}
contact: {email: ada@example.com, phone: "+91-90000-00000", linkedin: "https://www.linkedin.com/in/ada-example",
          github: "https://github.com/ada-example", status: confirmed}
application_facts:
  total_experience_years: 2
  work_authorization_india: Indian citizen
  needs_visa_sponsorship_abroad: "Yes"
  notice_period: 30 days
  expected_ctc_floor: 12 LPA
  current_ctc: 9 LPA
"""


@pytest.mark.parametrize("label,ftype,kind", [
    ("I agree to the privacy policy", "checkbox", "legal"), ("Gender", "select", "eeo"), ("Pronouns", "text", "eeo"),
    ("Resume/CV", "file", "file"), ("First Name", "text", "name"), ("Email", "email", "email"),
    ("LinkedIn Profile", "url", "link"), ("Expected CTC", "text", "pay"), ("Current salary (annual)", "text", "pay"),
    ("Will you now or in the future require visa sponsorship?", "radio", "sponsorship"),
    ("Are you legally authorized to work in India?", "radio", "work_auth"), ("Notice period", "select", "notice"),
    ("How many years of experience do you have with Python?", "select", "years"),
    ("Why do you want to work at Acme?", "textarea", "company_specific"),
    ("Describe a project where you used RAG", "textarea", "open"), ("Anything else we should know?", "textarea", "open"),
    ("Preferred team", "text", "short"), ("Which city are you based in?", "text", "location"),
    ("*First name", "text", "name"), ("Last name *", "text", "name"), ("✱ Email", "email", "email"),
    ("Phone (required)", "tel", "phone"),
])
def test_question_kinds(label, ftype, kind):
    assert kind_of(label, ftype, "Acme") == kind


def test_company_specific_needs_the_company_or_a_why_us_question():
    assert company_specific("What excites you about Acme's product?", "Acme")
    assert company_specific("Why this role?", "Other")
    assert not company_specific("Describe a project you led", "Acme")


@pytest.mark.parametrize("value,options,expected", [
    ("Yes", ["Yes", "No"], "Yes"), ("No, I don't need it", ["Yes", "No"], "No"), ("30 days", ["15 days", "30 days", "60 days"], "30 days"),
    ("2", ["0-1 years", "1-3 years", "3+ years"], "1-3 years"), ("5", ["Less than 2", "2-4", "5 or more"], "5 or more"),
    ("Indian citizen", ["Yes", "No"], None), ("Maybe", ["Yes", "No"], None), ("Man", ["Male", "Female"], "Male"),
    ("Woman", ["Man", "Woman"], "Woman"),
])
def test_option_matching_needs_one_clear_option(value, options, expected):
    assert match_option(value, options) == expected


def test_decline_option_and_normalize():
    assert decline_option(["Male", "Female", "I don't wish to answer"]) == "I don't wish to answer"
    assert normalize("  What's your Notice Period?* ") == "what s your notice period"
    assert overlap("notice period", "What is your notice period") > 0.5


@pytest.fixture()
def profile(tmp_path):
    path = tmp_path / "vault.yaml"
    path.write_text(VAULT, encoding="utf-8")
    return profile_mod.load(path)


def test_profile_values_come_from_confirmed_vault_facts(profile, tmp_path):
    assert profile_mod.load(tmp_path / "vault.yaml").location == "Pune, Maharashtra, India"
    assert answerer.profile_value("name", "First name", profile) == ("Ada", "")
    assert answerer.profile_value("name", "*First name", profile) == ("Ada", "")
    assert answerer.profile_value("name", "Last name", profile) == ("Example", "")
    assert answerer.profile_value("link", "GitHub", profile)[0] == "https://github.com/ada-example"
    assert answerer.profile_value("link", "Portfolio", profile)[0] == ""
    assert answerer.profile_value("years", "Total years of experience", profile)[0] == "2"
    assert answerer.profile_value("years", "Years of experience with Rust", profile)[0] == ""
    value, note = answerer.profile_value("pay", "Expected CTC", profile)
    assert value == "12 LPA" and "confirm" in note
    assert answerer.profile_value("pay", "Current CTC", profile)[0] == "9 LPA"


def test_unconfirmed_vault_sections_are_ignored(tmp_path):
    path = tmp_path / "v.yaml"
    path.write_text("version: 1\ncontact: {email: x@example.com, status: unconfirmed}\nperson: {full_name: Ada Example}\n", encoding="utf-8")
    p = profile_mod.load(path)
    assert p.email == "" and p.full_name == "Ada Example"


def test_fit_puts_text_into_choice_fields_or_says_why_not():
    assert answerer.fit({"type": "radio", "options": ["Yes", "No"]}, "yes") == ("Yes", "")
    assert answerer.fit({"type": "checkbox", "options": ["Python", "Go"]}, "Python") == (["Python"], "")
    value, problem = answerer.fit({"type": "select", "options": ["A", "B"]}, "Neither")
    assert value is None and "pick one" in problem
    assert answerer.fit({"type": "text"}, "anything") == ("anything", "")


def test_new_numbers_are_caught():
    assert answerer.check_numbers("Cut latency by 35% for 40 teams", "reduced latency 35%") == ["40"]


def test_answer_set_artifact_is_strict():
    one = answerer.item({"key": "q1", "label": "Gender", "type": "select", "options": ["Male", "Female"]}, "eeo", None, "needs_you")
    card = artifacts.AnswerSet(company="Acme", answers=[one], counts={"needs_you": 1})
    assert card.answers[0].flagged
    with pytest.raises(ValueError):
        artifacts.AnswerSet(company="Acme", answers=[{**one, "badge": "invented"}])
