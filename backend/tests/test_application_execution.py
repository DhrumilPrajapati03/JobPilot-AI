import asyncio
import base64
import hashlib
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.api.v1 import extension as extension_api, applications
from app.services import application_execution as execution, form_answers
from app.services.auth import CurrentUser, get_current_user
from test_application_flow import FakeSupabase, FakeResult

UID = str(uuid.uuid4())
APP = str(uuid.uuid4())
SID = str(uuid.uuid4())
URL = 'https://job-boards.greenhouse.io/example/jobs/123'
PDF = b'%PDF-1.4\nsnapshot-test\n%%EOF'


@pytest.fixture
def evidence(monkeypatch):
    db = FakeSupabase()
    db.tables['job_applications'] = [{'id':APP,'user_id':UID,'company':'Example','role':'Engineer','jd_url':URL,'status':'saved'}]
    db.tables['application_execution_sessions'] = [{'id':SID,'user_id':UID,'application_id':APP,'page_url':URL,'document_id':'doc'}]
    db.tables['application_documents'] = [{'id':'doc','user_id':UID,'application_id':APP,'sha256':hashlib.sha256(PDF).hexdigest(),'name':'Resume.pdf','pdf_base64':base64.b64encode(PDF).decode(),'size_bytes':len(PDF)}]
    db.tables['tailored_resumes'] = [{'user_id':UID,'application_id':APP,'version':3,'content':{'name':'Ada'}}]
    calls = []
    def rpc(name,params):
        calls.append((name,params))
        if name == 'create_application_session':
            result={'id':params['p_id'],'user_id':UID,'application_id':APP,'page_url':params['p_page_url'],'document_id':None}
            db.tables.setdefault('application_execution_sessions',[]).append(result)
        else:
            result={'id':1,'kind':params['p_kind'],'details':params['p_details']}
        return SimpleNamespace(execute=lambda:FakeResult(result))
    db.rpc=rpc
    monkeypatch.setattr(execution,'build_render_content',lambda *a,**k:SimpleNamespace(name='Ada'))
    async def render(_content): return PDF,1
    monkeypatch.setattr(execution,'render_resume_pdf',render)
    return db,calls


@pytest.fixture
def api_client(evidence,monkeypatch):
    db,_=evidence
    previous=dict(app.dependency_overrides)
    app.dependency_overrides[extension_api.get_extension_user]=lambda:extension_api.ExtensionUser(UID,'ada@example.invalid',db)
    app.dependency_overrides[get_current_user]=lambda:CurrentUser(id=UID,email='ada@example.invalid',token='unit-test')
    monkeypatch.setattr(applications,'get_supabase_client',lambda **kw:db)
    with TestClient(app) as client: yield client
    app.dependency_overrides.clear();app.dependency_overrides.update(previous)


def test_url_identity_keeps_openings_and_rejects_host_spoofing():
    assert execution.page_key(URL)==execution.page_key(URL.replace('job-boards','boards')+'?utm_source=test')
    assert execution.page_key(URL)!=execution.page_key(URL.replace('/123','/124'))
    assert execution.page_key(URL)!=execution.page_key('https://evil.test/?gh_jid=123')
    assert execution.page_key('https://jobs.lever.co/example/ABC/apply')==execution.page_key('https://jobs.lever.co/example/ABC')
    assert execution.page_key('https://example.test/jobs?jobId=1')!=execution.page_key('https://example.test/jobs?jobId=2')
    redacted=execution.page_url(URL+'?token=secret#private')
    assert 'secret' not in redacted and 'private' not in redacted
    assert execution.page_url(redacted)==redacted
    assert execution.page_key('https://example.test/apply?opening=1')!=execution.page_key('https://example.test/apply?opening=2')


@pytest.mark.parametrize('url',['file:///tmp/a','javascript:alert(1)','http://employer.test/form','https://user:password@employer.test/form'])
def test_unsafe_form_urls_rejected(url):
    with pytest.raises(HTTPException): execution.page_url(url)


def test_new_session_freezes_owned_resume_bytes(evidence):
    db,calls=evidence
    result=asyncio.run(execution.start(db,UID,'ada@example.invalid',APP,uuid.uuid4(),URL))
    name,payload=calls[0]
    assert name=='create_application_session' and payload['p_application_id']==APP
    frozen=payload['p_document']
    assert frozen['resume_version']==3 and base64.b64decode(frozen['pdf_base64'])==PDF
    assert frozen['sha256']==hashlib.sha256(PDF).hexdigest()
    db.tables['tailored_resumes'][0]['content']={'name':'Changed'}
    assert base64.b64decode(frozen['pdf_base64'])==PDF
    assert 'pdf_base64' not in str(result)


def test_replayed_session_does_not_render_new_resume(evidence,monkeypatch):
    db,calls=evidence
    async def forbidden(*a): raise AssertionError('Cannot replace frozen document')
    monkeypatch.setattr(execution,'render_resume_pdf',forbidden)
    asyncio.run(execution.start(db,UID,'ada@example.invalid',APP,SID,URL))
    assert calls[0][1]['p_document'] is None


def test_pdf_failure_never_creates_partial_session(evidence,monkeypatch):
    db,calls=evidence
    async def broken(*a): raise RuntimeError('secret provider detail')
    monkeypatch.setattr(execution,'render_resume_pdf',broken)
    with pytest.raises(HTTPException) as err: asyncio.run(execution.start(db,UID,'a',APP,uuid.uuid4(),URL))
    assert err.value.status_code==503 and 'secret' not in err.value.detail and not calls


def test_cross_application_link_requires_explicit_confirmation(evidence):
    db,calls=evidence
    with pytest.raises(HTTPException) as err: asyncio.run(execution.start(db,UID,'a',APP,uuid.uuid4(),'https://example.test/form'))
    assert err.value.status_code==409 and not calls
    asyncio.run(execution.start(db,UID,'a',APP,uuid.uuid4(),'https://example.test/form',True))
    assert calls[0][1]['p_link_method']=='user_confirmed'


def test_summary_is_calculated_from_observations_without_answer_content(evidence):
    db,calls=evidence
    data={'url':URL,'fields':[{'key':'one','type':'email','required':True,'outcome':'invalid','source':'profile'},
                            {'key':'two','type':'text','required':True,'outcome':'review','source':'ai'}]}
    execution.append(db,UID,SID,'form_prepared',uuid.uuid4(),data)
    details=calls[0][1]['p_details']
    assert details['summary']['filled']==0 and details['summary']['invalid']==1 and details['summary']['review']==1
    assert details['summary']['required_missing']==1
    assert 'answer' not in details and db.tables['job_applications'][0]['status']=='saved'
    data['fields'][0]['value']='private answer'
    with pytest.raises(ValidationError): execution.append(db,UID,SID,'form_prepared',uuid.uuid4(),data)


def test_pdf_hash_must_match_frozen_session(evidence):
    db,calls=evidence
    with pytest.raises(HTTPException) as err:
        execution.append(db,UID,SID,'form_prepared',uuid.uuid4(),{'url':URL,'fields':[],'document_sha256':'0'*64})
    assert err.value.status_code==409 and not calls


def test_foreign_session_and_changed_opening_cannot_record_events(evidence):
    db,calls=evidence
    for uid,url,status in [(str(uuid.uuid4()),URL,404),(UID,URL.replace('/123','/999'),409),(UID,'https://evil.test/form',409)]:
        with pytest.raises(HTTPException) as err: execution.append(db,uid,SID,'submission_attempted',uuid.uuid4(),{'url':url})
        assert err.value.status_code==status
    assert not calls


def test_confirmation_rules_are_provider_bound_and_explicitly_unverified(evidence):
    db,calls=evidence
    data={'url':URL,'attempt_key':str(uuid.uuid4()),'rule':'lever_confirmation'}
    with pytest.raises(HTTPException): execution.append(db,UID,SID,'submission_confirmation_observed',uuid.uuid4(),data)
    data['rule']='greenhouse_confirmation'
    execution.append(db,UID,SID,'submission_confirmation_observed',uuid.uuid4(),data)
    assert calls[0][1]['p_details']['verification']=='browser_observation_not_independently_verified'
    assert db.tables['job_applications'][0]['status']=='saved'


def test_manual_report_is_owner_scoped_and_idempotently_identified(evidence):
    db,calls=evidence
    execution.report(db,UID,APP,SID)
    execution.report(db,UID,APP,SID)
    assert calls[0][1]['p_key']==calls[1][1]['p_key']
    assert calls[0][1]['p_kind']=='user_reported_submitted'
    with pytest.raises(HTTPException): execution.report(db,'other',APP,SID)


def test_session_download_is_private_and_owner_scoped(api_client,evidence):
    db,_=evidence
    response=api_client.post('/api/v1/extension/document',json={'session_id':SID})
    assert response.status_code==200 and response.headers['cache-control']=='private, no-store'
    assert base64.b64decode(response.json()['pdf_base64'])==PDF
    db.tables['application_execution_sessions'][0]['user_id']='another-owner'
    assert api_client.post('/api/v1/extension/document',json={'session_id':SID}).status_code==404


def test_api_rejects_raw_answer_storage_and_fabricated_confirmation_kind(api_client):
    body={'session_id':SID,'request_key':str(uuid.uuid4()),'kind':'form_prepared','details':{'url':URL,'fields':[],'raw_answers':'private'}}
    assert api_client.post('/api/v1/extension/events',json=body).status_code==422
    body['kind']='submission_confirmed'
    assert api_client.post('/api/v1/extension/events',json=body).status_code==422


def test_history_and_delete_preserve_owned_audit(api_client,evidence):
    response=api_client.get(f'/api/v1/applications/{APP}/execution')
    assert response.status_code==200 and len(response.json()['sessions'])==1
    # Real PostgREST applies the projection; the fake query intentionally returns
    # entire rows, so test the explicit safe projection separately.
    assert 'pdf_base64' not in execution.DOCUMENT_FIELDS
    assert api_client.delete(f'/api/v1/applications/{APP}').status_code==409


def test_web_report_uses_an_owned_session_and_explicit_user_provenance(api_client,evidence,monkeypatch):
    from app.services import supabase
    db,calls=evidence
    monkeypatch.setattr(supabase,'get_supabase_admin_client',lambda:db)
    key=str(uuid.uuid4())
    response=api_client.post(f'/api/v1/applications/{APP}/report-submission',json={'request_key':key})
    assert response.status_code==200 and response.json()['evidence']=='user_reported_not_independently_verified'
    assert calls[0][1]['p_link_method']=='manual_report' and calls[0][1]['p_document'] is None
    assert calls[1][1]['p_user_id']==UID and calls[1][1]['p_kind']=='user_reported_submitted'
    assert api_client.post(f'/api/v1/applications/{uuid.uuid4()}/report-submission',json={'request_key':key}).status_code==404


@pytest.mark.parametrize('value,options',[('male',['female']),('India',['Indiana','India - remote']),('Yes',['Yes, full-time','Yes, part-time']),('3',['0-3','3-5'])])
def test_ambiguous_or_partial_options_require_review(value,options):
    assert form_answers.match_option(value,options) is None


def test_sponsorship_does_not_bypass_legal_attestation_review():
    context=form_answers.ApplicantContext(requires_sponsorship=False)
    field=form_answers.FormField('legal','I certify that I do not require sponsorship','checkbox',True,['I certify that I do not require sponsorship'])
    answer=asyncio.run(form_answers.answer_fields([field],context,use_ai=False))[0]
    assert answer.value is None and answer.flagged and 'Legal' in answer.note
