"""Run a local check with inherited provider credentials removed; retain raw output.

Usage: python docs/benchmarks/run_check.py NAME WORKDIR COMMAND [ARG ...]
Only use reviewed commands; this wrapper is not a subprocess network sandbox.
"""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[2]
name, cwd, *command = sys.argv[1:]
env = {k: v for k, v in os.environ.items() if not any(
    word in k.upper() for word in ('API_KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'SUPABASE', 'SENTRY_DSN'))}
env.update(APP_ENV='test', DEBUG='false', DISCOVERY_AUTO_SCAN='false',
           MAILBOX_ENABLED='false', MAIL_SEND_ENABLED='false', HF_HUB_OFFLINE='1',
           LANGCHAIN_TRACING_V2='false', LANGSMITH_TRACING='false', ANONYMIZED_TELEMETRY='false',
           PYTHONIOENCODING='utf-8')
started = time.perf_counter()
timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
with (root / 'docs/benchmarks/raw' / (name + '.log')).open('w', encoding='utf-8') as log:
    try:
        proc = subprocess.run(command, cwd=root / cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                              timeout=180)
        code = proc.returncode
        status = 'completed'
    except subprocess.TimeoutExpired:
        code, status = 124, 'timed_out; inspect and stop any remaining child fixture processes'
    except KeyboardInterrupt:
        code, status = 130, 'interrupted'
report = dict(command=command, cwd=cwd, started_utc=timestamp,
              wall_seconds=time.perf_counter() - started, exit_code=code, status=status,
              scope='offline/synthetic local check; not production latency')
(root / 'docs/benchmarks/raw' / (name + '-run.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report))
sys.exit(code)
