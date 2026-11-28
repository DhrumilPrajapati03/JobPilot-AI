"""Day 15: the end-to-end report's routing advice and table safety (no database)."""
from app.experts import e2e_report as r


def test_routing_advice_from_failures_and_call_sizes():
    data = {"llm": [("tailor", "big", 5, 40000, 0), ("researcher", "big", 4, 6000, 0)],
            "runs": {"tailor": {"failed": 3, "total": 6}, "researcher": {"failed": 0, "total": 4}}, "cases": []}
    advice = r.advice(data)
    assert any(a.startswith("tailor: 3 of 6 runs failed") for a in advice)
    assert any(a.startswith("researcher: calls average 1500 tokens") for a in advice)
    assert r.advice({"llm": [], "runs": {}, "cases": []})[0].startswith("No routing changes")


def test_table_cells_cannot_break_the_report():
    assert r.cell("Acme | Co\nLtd") == "Acme / Co Ltd"
    md = r.markdown({"cases": [{"company": "A|B", "role": "x", "stage": "ready", "artifacts": ["draft"], "waiting": 1, "blocked": 0, "failed": 0}],
                     "llm": [], "runs": {}})
    assert "| A/B | x | ready | draft | 1 | 0 | 0 |" in md
