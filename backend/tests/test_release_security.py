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


@pytest.mark.asyncio
@pytest.mark.parametrize('active,status', [(True,200),(False,401),('unavailable',503)])
async def test_production_sessions_reject_revocation_and_fail_closed(monkeypatch,active,status):
    monkeypatch.setattr(settings,'APP_ENV','production')
    monkeypatch.setattr(settings,'SUPABASE_URL','https://example.supabase.co')
    monkeypatch.setattr(settings,'SUPABASE_JWT_SECRET','test-only-random-key-with-more-than-32-characters')
    def rpc(name,params):
        assert name=='jobpilot_session_active' and params['p_session_id']
        if active=='unavailable':raise RuntimeError('private database details')
        return SimpleNamespace(execute=lambda:SimpleNamespace(data=active))
    monkeypatch.setattr('app.services.supabase.get_supabase_admin_client',lambda:SimpleNamespace(rpc=rpc))
    payload={'sub':str(uuid.uuid4()),'session_id':str(uuid.uuid4()),'aud':'authenticated','iss':settings.SUPABASE_URL+'/auth/v1','exp':time.time()+60}
    token=jwt.encode(payload,settings.SUPABASE_JWT_SECRET,algorithm='HS256')
    if status==200:assert (await auth._verify_token(token))['sub']==payload['sub']
    else:
        with pytest.raises(HTTPException) as error:await auth._verify_token(token)
        assert error.value.status_code==status and 'private' not in error.value.detail
    del payload['session_id']
    with pytest.raises(HTTPException) as error:await auth._verify_token(jwt.encode(payload,settings.SUPABASE_JWT_SECRET,algorithm='HS256'))
    assert error.value.status_code==401


@pytest.mark.asyncio
@pytest.mark.parametrize('algorithm',['ES256','RS256'])
async def test_jwks_verifies_signature_and_required_claims(monkeypatch,algorithm):
    monkeypatch.setattr(settings,'APP_ENV','test')
    key=ec.generate_private_key(ec.SECP256R1()) if algorithm=='ES256' else rsa.generate_private_key(public_exponent=65537,key_size=2048)
    encoder=jwt.algorithms.ECAlgorithm if algorithm=='ES256' else jwt.algorithms.RSAAlgorithm
    jwk=json.loads(encoder.to_jwk(key.public_key()))
    async def lookup(kid):assert kid=='test-key';return jwk
    monkeypatch.setattr(auth,'_get_jwk_for_kid',lookup)
    payload={'sub':str(uuid.uuid4()),'aud':'authenticated','exp':time.time()+60}
    token=jwt.encode(payload,key,algorithm=algorithm,headers={'kid':'test-key'})
    assert (await auth._verify_token(token))['sub']==payload['sub']
    del payload['exp']
    with pytest.raises(HTTPException):await auth._verify_token(jwt.encode(payload,key,algorithm=algorithm,headers={'kid':'test-key'}))


def test_templates_are_owned_and_use_optimistic_concurrency(db,client,monkeypatch):
    from app.api.v1 import templates
    monkeypatch.setattr(templates,'get_supabase_client',lambda **_:db)
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
    monkeypatch.setattr(run_stream,'get_supabase_client',lambda **_:None)
    await run_stream.stream_run(Socket(),str(uuid.uuid4()),'owner','revoked-token')
    assert closed[0]['code']==4401 and not events
