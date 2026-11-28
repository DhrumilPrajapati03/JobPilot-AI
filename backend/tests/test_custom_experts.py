"""Day 14 without a database: what a custom expert may be, and its policy preview."""
import pytest

from app.core.policy import load_policy
from app.experts import custom

POLICY = load_policy()


@pytest.mark.parametrize("template", list(custom.TEMPLATES))
def test_every_template_is_runnable_as_is(template):
    spec = custom.new_spec("my_test", template)
    assert spec.status == "draft" and spec.owner == "user" and spec.outputs == ["note"] and not spec.action_kinds
    assert custom.problems(spec, POLICY) == []


@pytest.mark.parametrize("change,problem", [
    ({"tools": ["read_case", "save_artifact", "propose_action"]}, "can't use propose_action"),
    ({"tools": ["read_case"]}, "needs save_artifact"),
    ({"action_kinds": ["send_email"]}, "can't send anything"),
    ({"outputs": ["draft"]}, "writes one note"),
    ({"budgets": {"steps": 500}}, "Budgets too high"),
    ({"triggers": [{"kind": "routine"}]}, "when you ask them to"),
    ({"instructions": "Do it."}, "Write its instructions"),
])
def test_what_a_custom_expert_can_never_be(change, problem):
    spec = custom.new_spec("my_test", "linkedin_post").model_copy(update=change)
    assert any(problem in p for p in custom.problems(spec, POLICY)), custom.problems(spec, POLICY)


def test_blank_needs_instructions_and_the_preview_says_it_never_sends():
    spec = custom.new_spec("my_blank", None, "Scratch")
    assert spec.name == "Scratch" and any("instructions" in p for p in custom.problems(spec, POLICY))
    preview = custom.preview(custom.new_spec("my_x", "referral_hunter"), POLICY)
    assert any("search the public web" in c for c in preview["can"])
    assert any("send email" in n for n in preview["never"]) and any("per run" in limit for limit in preview["limits"])


def test_ids_are_safe_slugs():
    assert custom.slug("LinkedIn Post Writer!") == "my_linkedin_post_writer"
    assert custom.slug("123 go") == "my_x123_go"


def test_list_numbers_and_citations_are_not_claims():
    import re
    body = "1. First [2]\n2. Second\n10. Tenth with 77 people"
    claims = re.sub(r"(?m)^\s*\d{1,2}[.)]\s", " ", re.sub(r"\[\d{1,2}\]", " ", body))
    from app.experts.answerer import check_numbers
    assert check_numbers(claims, "") == ["77"]
