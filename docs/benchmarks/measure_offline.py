"""Supplement existing synthetic regression with independently recomputed counts.

Run from backend through offline_entry.py. This is not a production benchmark.
"""
import collections
import json
import math
from pathlib import Path
import statistics
import sys
import time

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'backend'))
from app.config import settings
from app.services.matching_evaluation import evaluate_dataset
from app.services.matching_semantics import local_model, vector
from app.resume_engine.validator import validate_no_hallucinations

raw = root / 'docs/benchmarks/raw'
dataset = json.loads((root / 'backend/evaluations/matching_cases.json').read_text(encoding='utf-8'))
result = {'scope': '37 synthetic matching regression cases; one base profile with case-level preference overrides',
          'timing_scope': 'whole evaluate_dataset call, 37 cases, sequential local CPU, 1 cold batch + 10 warm batches per arm; excludes imports; warm runs reuse embedding cache; not workflow latency',
          'arms': {}}
for arm, enabled in [('lexical', False), ('semantic', True)]:
    settings.MATCHING_SEMANTIC = enabled
    local_model.cache_clear()
    vector.cache_clear()
    timings = []
    for repeat in range(11):
        start = time.perf_counter()
        report = evaluate_dataset(dataset)
        timings.append((time.perf_counter() - start) * 1000)
    rows = report['outcomes']
    tp = sum(r['expected_relevant'] and r['actual_relevant'] for r in rows)
    fp = sum(not r['expected_relevant'] and r['actual_relevant'] for r in rows)
    fn = sum(r['expected_relevant'] and not r['actual_relevant'] for r in rows)
    tn = len(rows) - tp - fp - fn
    confusion = collections.Counter((r['expected_eligibility'], r['actual_eligibility']) for r in rows)
    historical = json.loads((root / f'backend/evaluations/matching_{arm}_report.json').read_text(encoding='utf-8'))
    result['arms'][arm] = dict(n=len(rows), tp=tp, fp=fp, fn=fn, tn=tn,
        precision=tp/(tp+fp), recall=tp/(tp+fn), f1=2*tp/(2*tp+fp+fn),
        relevance_accuracy=(tp+tn)/len(rows), eligibility_accuracy=report['eligibility_accuracy'],
        eligibility_confusion=[dict(expected=a, predicted=b, count=c) for (a,b),c in sorted(confusion.items())],
        semantic_cases=report['semantic_cases'], exact_historical_report_match=report == historical,
        failing_ids=[r['id'] for r in rows if not r['passed']], batch_ms=timings,
        cold_batch_ms=timings[0], warm_batch_median_ms=statistics.median(timings[1:]),
        warm_batch_p95_ms=sorted(timings[1:])[math.ceil(.95*10)-1])
base = {'headline': 'Software Engineer', 'summary': 'Built a Python service.',
        'skills': {'primary': ['Python'], 'secondary': []}, 'experience': [], 'projects': [],
        'education': [], 'certifications': []}
probes = []
for name, summary in [('unsupported_skill', 'Built a Python and Kubernetes service.'),
                      ('invented_metric', 'Built a Python service improving speed by 90%.'),
                      ('unsupported_leadership', 'Led a company-wide engineering team building mission-critical Python services.')]:
    output = {**base, 'summary': summary}
    violations = validate_no_hallucinations(output, base, [])
    probes.append(dict(id=name, source=base, candidate=output, expected='flag unsupported claim',
                       violations=violations, flagged=bool(violations)))
result['validator_probes'] = {'scope': '3 deliberately constructed diagnostic probes; not an unsupported-claim rate estimate', 'cases': probes}
(raw / 'verified-metrics.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
