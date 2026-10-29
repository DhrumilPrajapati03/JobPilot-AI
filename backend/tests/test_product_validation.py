import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import analytics, operations
from app.config import settings
from app.services import observability, identity
from app.workflows.context import ExecutionContext
from test_application_flow import USER_ID, db, client  # noqa: F401
from test_durable_execution import MemoryStore


def test_onboarding_requires_current_facts_and_roles_not_mailbox(db,client):
    initial=client.get('/api/v1/profile/onboarding').json()
    assert not initial['ready_for_matching'] and initial['next_step']=='facts'
    vault=client.get('/api/v1/profile/facts').json()
    assert client.post('/api/v1/profile/facts/confirm',json={'source_digest':vault['source_digest'],'fact_ids':[f['id'] for f in vault['facts']]}).status_code==200
    assert client.post('/api/v1/profile/update',json={'work_preferences':{'preferred_roles':['ML Engineer']}}).status_code==200
    ready=client.get('/api/v1/profile/onboarding').json()
    assert ready['ready_for_matching'] and ready['next_step']=='sources'
    assert all(step['id']!='gmail' for step in ready['steps'])
    db.tables['resumes'][0]['summary']='Changed saved source facts'
    assert not client.get('/api/v1/profile/onboarding').json()['ready_for_matching']
    db.tables['resumes']=[]
    assert client.get('/api/v1/profile/onboarding').json()['next_step']=='resume'


def test_onboarding_does_not_read_another_users_resume_or_sources(db,client):
    db.tables['resumes'][0]['user_id']='stranger'
    db.tables['job_sources']=[{'id':'foreign','user_id':'stranger','enabled':True}]
    result=client.get('/api/v1/profile/onboarding').json()
    assert not result['steps'][0]['done'] and not result['steps'][3]['done'] and result['total_facts']==0


def test_zero_denominators_are_unknown_not_zero_performance(db,client):
    metrics={'gmail':{'accepted_messages':0,'reviewed_human_replied_messages':0},'preparation':{'filled_fields':0,'preserved_fields':0,'inspected_fields':0}}
    db.rpc=lambda *args:SimpleNamespace(execute=lambda:SimpleNamespace(data=metrics))
    result=client.get('/api/v1/analytics/outcomes').json()
    assert result['gmail']['reviewed_human_reply_rate'] is None and result['preparation']['completion_rate'] is None
    metrics['gmail'].update(accepted_messages=4,reviewed_human_replied_messages=1)
    metrics['preparation'].update(filled_fields=1,preserved_fields=1,inspected_fields=4)
    result=client.get('/api/v1/analytics/outcomes').json()
    assert result['gmail']['reviewed_human_reply_rate']==25 and result['preparation']['completion_rate']==50


def test_metrics_failure_is_visible_without_database_error_contents(db,client):
    def broken(*args):raise RuntimeError('private SQL or credential details')
    db.rpc=broken
    result=client.get('/api/v1/analytics/outcomes')
    assert result.status_code==503 and 'private SQL' not in result.text


def test_request_metrics_use_route_templates_not_queries_or_user_data(monkeypatch):
    app=FastAPI();app.add_middleware(observability.RequestMetricsMiddleware)
    @app.get('/record/{record_id}')
    def read(record_id):return {'ok':True}
    logger=[];registry=observability.Metrics()
    monkeypatch.setattr(observability,'metrics',registry)
    monkeypatch.setattr(settings,'REQUEST_LOGS_ENABLED',True)
    monkeypatch.setattr(observability.log,'info',logger.append)
    response=TestClient(app).get('/record/private-user-id?token=private-query',headers={'Authorization':'Bearer private-token','X-Request-ID':'untrusted-user-value'})
    assert response.status_code==200 and response.headers['x-request-id']!='untrusted-user-value'
    assert response.headers['server-timing'].startswith('app;dur=')
    text=json.dumps(logger)+json.dumps(registry.snapshot())
    assert '/record/{record_id}' in text and 'private-user-id' not in text and 'private-query' not in text and 'private-token' not in text
    for i in range(150):registry.observe('GET',f'/test/{i}',200,100)
    assert len(registry.rows)<=129


def test_sentry_allowlist_drops_all_request_and_exception_payloads():
    error=RuntimeError('private-user-email private token private resume')
    raw={'request':{'data':'private resume','headers':{'Authorization':'private token'}},'user':{'email':'private-user-email'},'extra':{'anything':'private'},'breadcrumbs':['private']}
    event=observability.safe_sentry_event(raw,{'exc_info':(RuntimeError,error,None)})
    assert 'private' not in json.dumps(event) and event['exception']['values'][0]['type']=='RuntimeError'
    assert all(key not in event for key in ('request','user','extra','breadcrumbs','contexts','server_name'))


def test_private_ops_and_readiness_do_not_infer_an_idle_worker(client,monkeypatch):
    monkeypatch.setattr(settings,'OBSERVABILITY_TOKEN','test-ops-secret')
    monkeypatch.setattr(operations,'check_readiness',lambda:(False,{'healthy_workers':0,'expired_leases':1,'failed_24h':2,'oldest_ready_seconds':400}))
    monkeypatch.setattr(settings,'EXECUTION_MODE','durable')
    assert client.get('/health').status_code==200
    assert client.get('/ready').status_code==503 and client.get('/ready').json()['worker'] is False
    assert client.get('/ops/metrics').status_code==401
    good=client.get('/ops/metrics',headers={'X-Ops-Token':'test-ops-secret'})
    assert good.status_code==200 and all(good.json()['alerts'][k] for k in ('no_healthy_worker','expired_leases','failed_runs','queue_delay'))
    monkeypatch.setattr(operations,'check_readiness',lambda:(True,{'healthy_workers':1}))
    assert client.get('/ready').status_code==200
    assert client.get('/ops/metrics?token=test-ops-secret').status_code==401


def test_stage_duration_is_recorded_once_and_not_fabricated_on_recovery():
    store=MemoryStore();run=store.claim('fixture-worker');ctx=ExecutionContext(store,run)
    async def operation():return {'value':1}
    asyncio.run(ctx.stage('resume_tailoring','Fixture stage',operation))
    asyncio.run(ctx.stage('resume_tailoring','Fixture stage',operation))
    timings=[e['data']['duration_ms'] for e in store.events_log if 'duration_ms' in e.get('data',{})]
    assert len(timings)==1 and timings[0]>=0


def test_readiness_cache_bounds_database_probes_and_expires(monkeypatch):
    clock=[0.0];calls=[]
    monkeypatch.setattr(settings,'SUPABASE_URL','https://synthetic.example')
    monkeypatch.setattr(settings,'SUPABASE_SERVICE_KEY','synthetic-key')
    monkeypatch.setattr(settings,'EXECUTION_MODE','durable')
    monkeypatch.setattr(operations.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(operations,'_cache',{'until':0,'key':None,'health':None})
    def execute():calls.append(True);return SimpleNamespace(data={'healthy_workers':1})
    monkeypatch.setattr(operations,'get_supabase_admin_client',lambda:SimpleNamespace(rpc=lambda *a:SimpleNamespace(execute=execute)))
    assert operations.check_readiness()[0] and operations.check_readiness()[0] and len(calls)==1
    clock[0]=6
    assert operations.check_readiness()[0] and len(calls)==2
