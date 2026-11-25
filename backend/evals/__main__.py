"""Run the evals: python -m evals [matching|policy ...] [--semantic] [--record] [--json].

Exit code 1 when any metric misses its threshold. --semantic uses local Ollama embeddings;
--record saves the scores to eval_result (DATABASE_URL required).
"""
import argparse
import sys

from evals.harness import SUITES, as_json, record, run


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m evals", description=__doc__)
    parser.add_argument("suites", nargs="*", help=f"any of {', '.join(SUITES)} (default: all)")
    parser.add_argument("--semantic", action="store_true", help="matching with local embeddings (needs Ollama)")
    parser.add_argument("--record", action="store_true", help="save results to eval_result")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    unknown = set(args.suites) - set(SUITES)
    if unknown:
        parser.error(f"unknown suite(s): {', '.join(sorted(unknown))}")
    metrics = run(args.suites or None, semantic=args.semantic)
    if args.json:
        print(as_json(metrics))
    else:
        for m in metrics:
            sign = ">=" if m.higher_is_better else "<="
            print(f"{'PASS' if m.passed else 'FAIL'}  {m.agent:<8} {m.dataset:<22} {m.metric:<30} "
                  f"{m.score:>7.4g}  (need {sign} {m.threshold:g})")
            if not m.passed and m.details:
                print(f"      {m.details}")
    if args.record:
        record(metrics)
        print(f"Recorded {len(metrics)} results in eval_result.")
    return 0 if all(m.passed for m in metrics) else 1


if __name__ == "__main__":
    sys.exit(main())
