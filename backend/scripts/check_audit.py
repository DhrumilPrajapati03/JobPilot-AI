"""Fail on every vulnerability except reviewed unreachable Chroma server paths."""
import json
import sys
from datetime import date
from pathlib import Path

EXCEPTIONS={'PYSEC-2026-311','PYSEC-2026-3814','PYSEC-2026-3815','PYSEC-2026-3813'}
def main():
    report=json.loads(Path(sys.argv[1]).read_text())
    dependencies=report.get('dependencies')
    if not isinstance(dependencies,list) or len(dependencies)<100 or any(p.get('skip_reason') for p in dependencies):
        raise SystemExit('Incomplete dependency audit; refusing a partial/empty success report')
    if not any(p['name'].lower()=='pyjwt' for p in dependencies):
        raise SystemExit('Release JWT dependency is missing from the audit')
    unexpected=[];accepted=set()
    for package in report['dependencies']:
        for issue in package.get('vulns',[]):
            if package['name']=='chromadb' and package['version']=='1.5.9' and issue['id'] in EXCEPTIONS and date.today()<=date(2026,12,7):
                accepted.add(issue['id'])
            else:unexpected.append((package['name'],issue['id']))
    if unexpected:raise SystemExit('Unaccepted dependency findings: '+str(unexpected))
    print('No unaccepted dependency vulnerabilities. Reviewed Chroma server-only exceptions:',sorted(accepted))
if __name__=='__main__':main()
