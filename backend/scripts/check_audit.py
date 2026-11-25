"""Fail on every known vulnerability in the locked backend dependencies (no exceptions)."""
import json
import sys
from pathlib import Path


def main():
    report=json.loads(Path(sys.argv[1]).read_text())
    dependencies=report.get('dependencies')
    if not isinstance(dependencies,list) or len(dependencies)<50 or any(p.get('skip_reason') for p in dependencies):
        raise SystemExit('Incomplete dependency audit; refusing a partial/empty success report')
    if not any(p['name'].lower()=='fastapi' for p in dependencies):
        raise SystemExit('Core dependency is missing from the audit')
    unexpected=[(package['name'],issue['id']) for package in dependencies for issue in package.get('vulns',[])]
    if unexpected:raise SystemExit('Unaccepted dependency findings: '+str(unexpected))
    print('No known dependency vulnerabilities.')
if __name__=='__main__':main()
