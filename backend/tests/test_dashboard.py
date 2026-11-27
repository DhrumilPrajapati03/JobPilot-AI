"""Live Ops shows failures in plain words and never a credential."""
import pytest

from app.api.v1.dashboard import clean_error


@pytest.mark.parametrize("raw,shown", [
    ("Groq said api_key=sk-secret-123 was rejected\nTraceback (most recent call last)", "Groq said api_key [hidden] was rejected"),
    ("Authorization: Bearer abc.def failed", "Authorization: Bearer [hidden] failed"),
    ("gsk_ABCDEFGHIJKLMN leaked into a log", "key [hidden] leaked into a log"),
    ("password: hunter22", "password [hidden]"),
    ("The model returned no JSON", "The model returned no JSON"),
    ("", ""), (None, ""), ("   \n  ", ""),
])
def test_errors_are_one_line_without_secrets(raw, shown):
    assert clean_error(raw) == shown
