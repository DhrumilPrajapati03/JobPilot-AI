"""Kill a real Worker after a synthetic DB commit, then resume after lease expiry.

Only used by check_database.py against its disposable, network-isolated Postgres.
External generation is replaced; Worker.run_once, checkpoints and SQL are real.
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


class SQLStore:
    def __init__(self,container): self.container=container

    def query(self,query):
        result=subprocess.run(['docker','exec','-i',self.container,'psql','-XqAt','-v','ON_ERROR_STOP=1','-U','postgres','-d','postgres'],input=query,text=True,encoding='utf-8',capture_output=True,timeout=30)
        if result.returncode:raise RuntimeError(result.stderr[-2000:])
        return result.stdout.strip()

    def rpc(self,name,**params):
        # Names are internal constants; values are SQL literals, never shell text.
        def literal(value):
            if value is None:return 'null'
            if isinstance(value,(dict,list)):return "'"+json.dumps(value).replace("'","''")+"'::jsonb"
            if isinstance(value,(int,float)):return str(value)
            return "'"+str(value).replace("'","''")+"'"
        args=','.join(k+'=>'+literal(v) for k,v in params.items())
        return json.loads(self.query(f'set role service_role; select to_jsonb(public.{name}({args}))::text;'))

    def claim(self,worker):return self.rpc('claim_agent_run',p_worker=worker,p_lease_seconds=30)
    def renew(self,run,token):return self.rpc('renew_agent_run',p_run_id=run,p_token=token,p_lease_seconds=30)
    def checkpoint(self,run,token,stage,value):return self.rpc('checkpoint_agent_run',p_run_id=run,p_token=token,p_stage=stage,p_value=value)
    def emit(self,run,token,event):return self.rpc('append_agent_run_event',p_run_id=run,p_token=token,p_event=event)
    def finish(self,run,token,status,*,result=None,error=None,delay=0):return self.rpc('finish_agent_run',p_run_id=run,p_token=token,p_status=status,p_result=result or {},p_error=error,p_delay=delay)


def child(container,marker,pause):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from pydantic_settings.sources import DotEnvSettingsSource
    with patch.dict(os.environ,{'APP_ENV':'test','DEBUG':'false','EXECUTION_MODE':'durable','RUN_LEASE_SECONDS':'30'}),patch.object(DotEnvSettingsSource,'__call__',return_value={}):
        from app.workers.runner import Worker
        class RecoveryWorker(Worker):
            async def execute(self,ctx):
                async def persist():
                    return await asyncio.to_thread(ctx.store.rpc,'save_run_application',p_run_id=ctx.run['id'],p_token=ctx.token,
                        p_application={'company':'Recovery Fixture','role':'Engineer','source':'manual','jd_analysis':{}},
                        p_tailored={'content':{'name':'Synthetic Person'},'keyword_match_score':80,'missing_keywords':[]},
                        p_emails=[{'subject':'Synthetic draft','body':'Never sent','sequence_number':1}])
                result=await ctx.stage('database_saving','Saving synthetic materials',persist)
                Path(marker).write_text('checkpoint restored' if ctx.run['attempts']>1 else 'committed',encoding='utf-8')
                if pause:await asyncio.Event().wait()
                return result
        asyncio.run(RecoveryWorker(SQLStore(container),heartbeat_factory=lambda:SQLStore(container)).run_once())


def check(container):
    store=SQLStore(container)
    uid=str(uuid.uuid4())
    store.query(f"insert into auth.users(id,email) values('{uid}','recovery@example.invalid');")
    run=store.rpc('enqueue_agent_run',p_user_id=uid,p_kind='application',p_inputs={'jd_text':'Synthetic Python role'},p_key='recovery-check')
    with TemporaryDirectory(prefix='jobpilot-worker-check-') as directory:
        marker=Path(directory)/'checkpoint'
        command=[sys.executable,str(Path(__file__).resolve()),'--container',container,'--marker',str(marker)]
        first=subprocess.Popen(command+['--pause'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            deadline=time.monotonic()+90
            while not marker.exists():
                if first.poll() is not None:raise RuntimeError('First worker exited: '+first.communicate()[1].decode(errors='replace')[-2500:])
                if time.monotonic()>deadline:raise RuntimeError('Worker did not reach checkpoint')
                time.sleep(.2)
            first.kill();first.wait(timeout=10)
        finally:
            if first.poll() is None:first.kill();first.wait(timeout=10)
        print('Worker process killed after committed checkpoint; waiting for real lease expiry.',flush=True)
        lease=json.loads(store.query(f"select jsonb_build_object('token',lease_token,'expires',extract(epoch from lease_expires_at))::text from public.agent_runs where id='{run['id']}';"))
        time.sleep(max(0,float(lease['expires'])-time.time()+.5))
        assert store.renew(run['id'],lease['token']) is False,'Expired worker could renew'
        marker.unlink()
        second=subprocess.run(command,capture_output=True,timeout=90)
        if second.returncode:raise RuntimeError('Replacement worker failed: '+second.stderr.decode(errors='replace')[-2500:])
        result=json.loads(store.query(f"select jsonb_build_object('status',status,'attempts',attempts,'apps',(select count(*) from public.job_applications where user_id='{uid}'),'versions',(select count(*) from public.tailored_resumes where user_id='{uid}'),'emails',(select count(*) from public.cold_emails where user_id='{uid}'))::text from public.agent_runs where id='{run['id']}';"))
        assert result=={'status':'succeeded','attempts':2,'apps':1,'versions':1,'emails':1},result
        assert marker.read_text()=='checkpoint restored','Completed stage was recomputed'
    print('PASS: replacement Worker restored checkpoint; one application/version/email, two attempts.',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container',required=True);parser.add_argument('--marker',required=True);parser.add_argument('--pause',action='store_true')
    args=parser.parse_args()
    if not args.container.startswith('jobpilot-release-check-'):raise SystemExit('Requires the isolated release-check container')
    child(args.container,args.marker,args.pause)
