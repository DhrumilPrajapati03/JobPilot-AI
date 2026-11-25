import json
import time
import uuid
from types import SimpleNamespace
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import HTTPException
from app.config import settings
from app.services import auth
from test_application_flow import db, client, USER_ID  # noqa: F401


OWNER_TOKEN='owner-test-token-'+'z'*32


@pytest.mark.asyncio
async def test_owner_token_maps_to_the_owner_and_fails_closed(monkeypatch):
    owner=str(uuid.uuid4())
    monkeypatch.setattr(settings,'OWNER_API_TOKEN',OWNER_TOKEN)
    monkeypatch.setattr(auth,'owner_identity',lambda:(owner,'owner@example.invalid'))
    assert await auth._verify_token(OWNER_TOKEN)=={'sub':owner,'email':'owner@example.invalid'}
    with pytest.raises(HTTPException) as error:await auth._verify_token(OWNER_TOKEN[:-1])
    assert error.value.status_code==401
    def broken():raise RuntimeError('private database details')
    monkeypatch.setattr(auth,'owner_identity',broken)
    with pytest.raises(HTTPException) as error:await auth._verify_token(OWNER_TOKEN)
    assert error.value.status_code==503 and 'private' not in error.value.detail
    monkeypatch.setattr(settings,'OWNER_API_TOKEN','')
    with pytest.raises(HTTPException) as error:await auth._verify_token('')
    assert error.value.status_code==503


def test_owner_identity_is_cached_and_normalised(monkeypatch):
    pinned=str(uuid.uuid4());calls=[]
    def fetch(query,params=None):calls.append(query);return [(params[0],)]
    monkeypatch.setattr('app.db.get_db',lambda *a,**k:SimpleNamespace(fetch=fetch))
    monkeypatch.setattr(settings,'OWNER_EMAIL',' Owner@Example.invalid ')
    monkeypatch.setattr(settings,'OWNER_ID',pinned.upper())
    auth.reset_owner_cache()
    try:
        assert auth.owner_identity()==(pinned,'owner@example.invalid')
        assert auth.owner_identity()==(pinned,'owner@example.invalid') and len(calls)==1
    finally:
        auth.reset_owner_cache()



def test_templates_are_owned_and_use_optimistic_concurrency(db,client,monkeypatch):
    from app.api.v1 import templates
    monkeypatch.setattr(templates,'get_db',lambda *a, **k:db)
    saved=client.put('/api/v1/templates/email',json={'content':'Use a concise tone.'})
    assert saved.status_code==200,saved.text
    timestamp=saved.json()['template']['updated_at']
    assert client.put('/api/v1/templates/email',json={'content':'Overwrite without revision'}).status_code==409
    assert client.put('/api/v1/templates/email',json={'content':'Changed','expected_updated_at':'old'}).status_code==409
    response=client.put('/api/v1/templates/email',json={'content':'Changed','expected_updated_at':timestamp})
    assert response.status_code==200
    db.tables['writing_templates'].append({'user_id':'stranger','kind':'dm','content':'Private'})
    result=client.get('/api/v1/templates').json()['templates']
    assert len(result)==1 and result[0]['user_id']==USER_ID


def test_recent_runs_hide_inputs_and_surface_uncertain_email_outcome(client,monkeypatch):
    from app.services.runs import RunStore
    monkeypatch.setattr(settings,'EXECUTION_MODE','durable')
    monkeypatch.setattr(RunStore,'__init__',lambda self:None)
    monkeypatch.setattr(RunStore,'recent',lambda self,uid:[{'id':'fixture','kind':'mail_send','status':'succeeded','inputs':{'private':'secret'},'checkpoints':{'private':'secret'},'result':{'state':'send_unknown','private':'secret'}}])
    response=client.get('/api/v1/runs')
    assert response.status_code==200 and response.json()['runs'][0]['mail_outcome']=='send_unknown'
    assert 'secret' not in response.text and 'inputs' not in response.text


@pytest.mark.asyncio
async def test_chat_tool_rechecks_revoked_sessions_before_any_action(monkeypatch):
    from app.agents import assistant
    from app.services.auth import CurrentUser
    called=[]
    async def executor(*_):called.append(True);return {}
    async def revoked(*_):raise HTTPException(401,'This session has ended.')
    monkeypatch.setitem(assistant.EXECUTORS,'release-test',executor)
    monkeypatch.setattr(settings,'APP_ENV','production')
    monkeypatch.setattr(auth,'_verify_token',revoked)
    result=await assistant.execute_tool('release-test',{},CurrentUser('owner','old-token'))
    assert 'session has ended' in result['error'] and not called


@pytest.mark.asyncio
async def test_chat_tool_never_exposes_provider_diagnostics(monkeypatch):
    from app.agents import assistant
    from app.services.auth import CurrentUser
    async def broken(*_):raise RuntimeError('sensitive provider body with private resume text')
    monkeypatch.setitem(assistant.EXECUTORS,'release-test',broken)
    result=await assistant.execute_tool('release-test',{},CurrentUser('owner','token'))
    assert 'temporarily unavailable' in result['error'] and 'private' not in str(result)


@pytest.mark.asyncio
async def test_progress_socket_stops_before_replay_when_session_revoked(monkeypatch):
    from app.services import run_stream
    events=[];closed=[]
    async def revoked(*_):raise HTTPException(401,'Session ended')
    class Store:
        def get(self,*_):return {'status':'running'}
        def replay_cursor(self,*_):return 0
        def events(self,*_):events.append(True);return []
    class Socket:
        async def close(self,**kwargs):closed.append(kwargs)
    monkeypatch.setattr(settings,'APP_ENV','production')
    monkeypatch.setattr(auth,'_verify_token',revoked)
    monkeypatch.setattr(run_stream,'RunStore',lambda *_:Store())
    monkeypatch.setattr(run_stream,'get_db',lambda *a, **k:None)
    await run_stream.stream_run(Socket(),str(uuid.uuid4()),'owner','revoked-token')
    assert closed[0]['code']==4401 and not events
