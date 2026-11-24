"""Check the built Linux runtime without network, credentials or persistent data."""
import argparse
import subprocess

CHECK=r'''
import asyncio, os, resource, time
from pathlib import Path
assert os.getuid()==10001, 'Runtime must not run as root'
assert not any(Path(p).exists() for p in ['/app/.env','/app/.venv','/app/.venv-release','/app/tests'])
from app.services.matching_semantics import local_model,similarity
started=time.perf_counter()
assert local_model() is not None, 'Prepared offline model missing'
value,model=similarity('Python engineer building APIs','Build Python APIs','synthetic-image-check')
assert value is not None and model=='all-MiniLM-L6-v2'
from app.resume_engine.renderer import render_resume_pdf
from app.resume_engine.schemas import ResumeContentJSON,RendererType
pdf,_=asyncio.run(render_resume_pdf(ResumeContentJSON(name='Synthetic Person',headline='Engineer',summary='Builds Python tools.',renderer=RendererType.HTML)))
assert pdf.startswith(b'%PDF') and len(pdf)>1000
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as client:
 assert client.get('/health').status_code==200
 assert client.get('/ready').status_code==503, 'Unconfigured DB must not report ready'
from app.config import Settings
from app.services.production import validate_production
try:validate_production(Settings(_env_file=None,APP_ENV='production'))
except RuntimeError:pass
else:raise AssertionError('Unsafe production startup accepted')
print('PASS: non-root Linux runtime, read-only filesystem, network disabled, offline embeddings, PDF, liveness and fail-closed readiness.')
print('Synthetic smoke elapsed seconds:',round(time.perf_counter()-started,2),'peak RSS MiB:',round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1))
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('image');args=parser.parse_args()
    subprocess.run(['docker','run','--rm','--network','none','--memory','1g','--cpus','2','--pids-limit','256',
        '--read-only','--tmpfs','/tmp:rw,nosuid,size=256m',
        '-e','APP_ENV=test','-e','DEBUG=false','-e','EXECUTION_MODE=inline','-e','MATCHING_SEMANTIC=true',
        '-e','ANONYMIZED_TELEMETRY=false',args.image,'python','-c',CHECK],check=True,timeout=180)


if __name__=='__main__':main()
