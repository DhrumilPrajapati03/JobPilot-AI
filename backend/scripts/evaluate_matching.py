"""Offline matching evaluation: python scripts/evaluate_matching.py [--semantic]."""
import argparse
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

from pydantic_settings.sources import DotEnvSettingsSource

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--semantic", action="store_true", help="Use cached local MiniLM; never download or call a provider")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    with patch.dict(os.environ, {"DEBUG": "false", "MATCHING_SEMANTIC": str(args.semantic).lower()}), patch.object(DotEnvSettingsSource, "__call__", return_value={}):
        from app.services.matching_evaluation import evaluate_dataset
        report = evaluate_dataset(json.loads((root / "evaluations/matching_cases.json").read_text(encoding="utf-8")))
    report_text = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(report_text+"\n", encoding="utf-8")
    print(json.dumps({k: v for k,v in report.items() if k != "outcomes"}, indent=2))
    print("Mismatches:", json.dumps([r for r in report["outcomes"] if not r["passed"]]))
