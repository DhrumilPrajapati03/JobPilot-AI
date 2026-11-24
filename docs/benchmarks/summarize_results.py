"""Build machine-readable result/status summary from retained run artifacts."""
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

raw = Path(__file__).resolve().parent / 'raw'
def readlog(name):
    data = (raw / name).read_bytes()
    return data.decode('utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8', errors='replace')

suite = ET.parse(raw / 'backend-junit.xml').getroot().find('testsuite')
backend = {key: int(suite.attrib[key]) for key in ('tests', 'failures', 'errors', 'skipped')}
backend.update(status='PASS', seconds=float(suite.attrib['time']), scope='offline test suite with mocked external boundaries')
front = readlog('frontend-tests.log')
browser = readlog('frontend-e2e.log')
extension = readlog('extension-tests.log')
ext_browser = readlog('extension-browser.log')
verified = json.loads((raw / 'verified-metrics.json').read_text(encoding='utf-8'))
summary = {
    'audit_date': '2026-11-12', 'timezone': 'Asia/Calcutta',
    'head': 'eb8c6d09a5bdfa472af8ed8ae619e952339d963a',
    'source_scope': 'dirty working tree; see source-manifest.json',
    'backend': backend,
    'frontend_node': {'status': 'PASS', 'tests': int(re.search(r'tests (\d+)', front).group(1)), 'scope': 'offline'},
    'frontend_build': {'status': 'PASS', 'exit_code': 0, 'scope': 'TypeScript/Vite build'},
    'frontend_browser': {'status': 'BLOCKED', 'individual_ok_results': len(re.findall(r'\bok\s+\d+\s+e2e', browser)),
                         'successful_suite_completion': False, 'interrupted_exit_code': 1,
                         'reason': 'No terminal suite summary; stalled after 14 individual ok results and was interrupted. Shutdown/teardown is suspected; root cause not determined.',
                         'scope': 'synthetic local server and intercepted provider boundaries'},
    'extension_node': {'status': 'PASS', 'tests': int(re.search(r'tests (\d+)', extension).group(1)), 'scope': 'offline'},
    'extension_browser': {'status': 'PASS', 'tests': int(re.search(r'(\d+) passed', ext_browser).group(1)), 'scope': 'local Chromium fixtures'},
    'matching': {'status': 'MEASURED_SYNTHETIC', 'cases': 37, 'independent_real_postings': 0, 'arms': verified['arms']},
    'coverage': {'backend': 'NOT MEASURED: coverage/pytest-cov absent',
                 'frontend': 'NOT MEASURED: native report has zero attributable source rows; aggregate rejected',
                 'extension': 'NOT MEASURED'},
    'database': {'status': 'BLOCKED', 'command': "docker image inspect postgres:17 --format '{{.Id}}'", 'exit_code': 1,
                 'reason': 'Docker engine named pipe not found; Docker config access warning also present; no SQL suites executed'},
    'unmeasured': {name: {'value': None, 'status': 'NOT MEASURED', 'reason': reason} for name, reason in {
        'independent_posting_accuracy': 'No independently adjudicated real-posting corpus',
        'precision_at_5': 'No ranked independently labeled dataset',
        'recall_at_5': 'No ranked independently labeled retrieval universe',
        'ndcg_at_10_or_mrr': 'No ranked independently labeled dataset',
        'generated_resume_factual_consistency': 'No approved provider generations with claim-level human labels',
        'unsupported_claim_rate': 'Only three constructed validator probes; no representative generation sample',
        'workflow_completion_rate': 'Test assertions are not a task-level evaluation denominator',
        'workflow_recovery_rate': 'Fake-store recovery tests are not an independent task-rate experiment',
        'median_and_p95_end_to_end_latency': 'Only local scoring batch timings measured',
        'llm_tokens_and_average_api_cost': 'No provider calls or token ledger',
        'manual_vs_ai_preparation_time': 'No comparable human timing study'}.items()}}
(raw / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k in ('backend','frontend_node','frontend_browser','extension_node','extension_browser')}, indent=2))
