"""The eval harness (plan section 8.1) runs offline and every seeded metric meets its bar."""
from evals.harness import SUITES, run


def test_seeded_suites_pass_their_thresholds():
    metrics = run(list(SUITES))
    failed = [(m.agent, m.metric, m.score, m.details) for m in metrics if not m.passed]
    assert not failed, failed
    assert {m.agent for m in metrics} == {"scout", "courier", "tailor", "recon"}
    assert next(m for m in metrics if m.metric == "accuracy").details["wrong"] == []


def test_a_wrong_expectation_is_reported_not_hidden(monkeypatch):
    from evals import harness
    from app.core import policy
    real = policy.check_execution
    monkeypatch.setattr(policy, "check_execution", lambda *a, **k: policy.Verdict(True, "ask_first", []))
    try:
        accuracy = next(m for m in harness.policy_suite() if m.metric == "accuracy")
    finally:
        monkeypatch.setattr(policy, "check_execution", real)
    assert not accuracy.passed and accuracy.details["wrong"]
