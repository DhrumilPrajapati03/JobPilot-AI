import asyncio
import base64
import copy
import hashlib
import uuid
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser

import httpx
import pytest

from app.api.v1 import email as email_api
from app.config import settings
from app.services import mailbox, gmail_broker, recruiters
from app.services.gmail_broker import GmailBroker, BrokerError
from app.workers.runner import Worker
from app.workflows.context import ExecutionContext
from test_application_flow import FakeSupabase, USER_ID, client  # noqa: F401
from test_durable_execution import MemoryStore


@pytest.fixture
def enabled(monkeypatch):
    for key,value in {'MAILBOX_ENABLED':True,'MAIL_SEND_ENABLED':True,'COMPOSIO_API_KEY':'unit-test-key','COMPOSIO_GMAIL_AUTH_CONFIG_ID':'ac_test'}.items():
        monkeypatch.setattr(settings,key,value)


class MailStore(MemoryStore):
    def __init__(self):
        super().__init__(FakeSupabase(),kind='mail_send')
        self.message={'id':str(uuid.uuid4()),'user_id':USER_ID,'state':'queued','revision':1,'approved_revision':1,
                      'to_email':'recruiter@example.invalid','subject':'Application review','body':'A reviewed draft','attachment':None,
                      'rfc_message_id':None,'provider_message_id':None,'provider_thread_id':None}
        self.connection={'id':str(uuid.uuid4()),'user_id':USER_ID,'provider_account_id':'ca_owner','email':'owner@example.invalid','status':'active'}
        self.row['inputs']={'message_id':self.message['id']}
        self.result_fault=None

    def rpc(self,name,**params):
        if name=='begin_mail_send':
            dispatch=self.message['state']=='queued'
            if dispatch:
                self.message.update(state='sending',attempt_started_at='2026-10-28T00:00:00+00:00',rfc_message_id='<unit-test@example.invalid>')
            return {'dispatch':dispatch,'message':copy.deepcopy(self.message),'connection':self.connection}
        if name=='mail_worker_result':
            if params['p_state']=='sent' and self.result_fault=='before':
                self.result_fault=None; raise RuntimeError('Database acknowledgement lost')
            if params['p_state']!='replies':
                self.message.update(state=params['p_state'],**params['p_data'])
            if params['p_state']=='sent' and self.result_fault=='after':
                self.result_fault=None; raise RuntimeError('Committed but acknowledgement lost')
            return copy.deepcopy(self.message)
        raise AssertionError(name)


class Provider:
    def __init__(self,store,error=None): self.store,self.error,self.sends=store,error,0
    async def gmail(self,uid,account,method,path,body=None,query=None):
        assert uid==USER_ID and account=='ca_owner'
        if method=='POST':
            self.sends+=1
            if self.error: raise self.error
            return {'id':'gmail_receipt','threadId':'thread_one'}
        if path=='messages': return {'messages':[{'id':'gmail_receipt'}]}
        if path.startswith('messages/'):
            return {'id':'gmail_receipt','threadId':'thread_one','labelIds':['SENT'],'payload':{'headers':[
                {'name':'Message-ID','value':self.store.message['rfc_message_id']},
                {'name':'From','value':'owner@example.invalid'},{'name':'To','value':'recruiter@example.invalid'}]}}
        if path.startswith('threads/'): return {'messages':[]}
        raise AssertionError(path)


@pytest.mark.parametrize('fault',['before','after'])
def test_worker_recovery_after_gmail_acceptance_never_sends_twice(enabled,monkeypatch,fault):
    store=MailStore(); store.result_fault=fault; provider=Provider(store)
    monkeypatch.setattr(mailbox,'GmailBroker',lambda:provider)
    asyncio.run(Worker(store,heartbeat_factory=lambda:store).run_once())
    assert store.row['status']=='retry_wait'
    asyncio.run(Worker(store,heartbeat_factory=lambda:store).run_once())
    assert store.row['status']=='succeeded' and store.message['state']=='sent'
    assert provider.sends==1 and store.message['provider_message_id']=='gmail_receipt'


def test_ambiguous_send_can_only_reconcile_not_resend(enabled):
    store=MailStore(); provider=Provider(store,BrokerError('Timeout after request'))
    ctx=ExecutionContext(store,store.claim('worker'))
    assert asyncio.run(mailbox.execute_send(ctx,provider))['state']=='send_unknown'
    provider.error=None
    assert asyncio.run(mailbox.execute_send(ctx,provider))['state']=='sent'
    assert provider.sends==1


def test_missing_provider_receipt_remains_unknown_even_with_http_success(enabled):
    store=MailStore()
    class MissingReceipt(Provider):
        async def gmail(self,*a,**kw): self.sends+=1; return {}
    provider=MissingReceipt(store); ctx=ExecutionContext(store,store.claim('worker'))
    assert asyncio.run(mailbox.execute_send(ctx,provider))['state']=='send_unknown'
    assert store.message['state']=='send_unknown'


def test_known_rejection_is_not_marked_sent(enabled):
    store=MailStore(); provider=Provider(store,BrokerError('Rejected',rejected=True))
    result=asyncio.run(mailbox.execute_send(ExecutionContext(store,store.claim('worker')),provider))
    assert result['state']=='failed' and not store.message.get('provider_message_id') and provider.sends==1


def test_frozen_attachment_and_headers_are_encoded_in_the_approved_message():
    store=MailStore(); message=store.rpc('begin_mail_send')['message']; pdf=b'%PDF-1.7\n%%EOF'
    message['attachment']={'data':base64.b64encode(pdf).decode(),'sha256':hashlib.sha256(pdf).hexdigest()}
    parsed=BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(mailbox.mime_message(message,'owner@example.invalid')))
    assert parsed['To']=='recruiter@example.invalid' and parsed['From']=='owner@example.invalid'
    assert parsed['Message-ID']=='<unit-test@example.invalid>'
    assert list(parsed.iter_attachments())[0].get_payload(decode=True)==pdf
    message['attachment']['data']=base64.b64encode(b'changed').decode()
    with pytest.raises(ValueError): mailbox.valid_email('a@example.invalid,b@example.invalid')
    with pytest.raises(mailbox.PermanentRunError): mailbox.mime_message(message,'owner@example.invalid')


@pytest.mark.parametrize('field,value', [('user_id','stranger'),('status','EXPIRED'),('toolkit',{'slug':'outlook'}),('auth_config',{'id':'wrong'}),('experimental',{'account_type':'SHARED'}),('is_disabled',True),('auth_config',{'id':'ac_test','is_disabled':True})])
def test_foreign_or_shared_connections_cannot_reach_the_gmail_proxy(enabled,field,value):
    class Broker(GmailBroker):
        async def request(self,method,path,body=None):
            assert method=='GET', 'Proxy reached before private-owner validation'
            return {'user_id':USER_ID,'status':'ACTIVE','toolkit':{'slug':'gmail'},'auth_config':{'id':'ac_test'},field:value}
    with pytest.raises(BrokerError): asyncio.run(Broker().gmail(USER_ID,'ca_owner','POST','messages/send',body={'raw':'never-send'}))


def test_proxy_explicitly_scopes_user_account_and_fixed_google_endpoint(enabled):
    calls=[]
    class Broker(GmailBroker):
        async def request(self,method,path,body=None):
            calls.append((method,path,body))
            if method=='GET': return {'user_id':USER_ID,'status':'ACTIVE','toolkit':{'slug':'gmail'},'auth_config':{'id':'ac_test'}}
            return {'status':200,'data':{'emailAddress':'owner@example.invalid'}}
    assert asyncio.run(Broker().gmail(USER_ID,'ca_owner','GET','profile'))['emailAddress']=='owner@example.invalid'
    request=calls[-1][2]
    assert request['user_id']==USER_ID and request['connected_account_id']=='ca_owner'
    assert request['endpoint']=='https://gmail.googleapis.com/gmail/v1/users/me/profile'
    with pytest.raises(BrokerError): asyncio.run(Broker().gmail(USER_ID,'ca_owner','GET','https://evil.invalid'))


def test_oauth_identity_verifier_is_used_instead_of_trusting_callback_account_ids(enabled):
    calls=[]
    class Broker(GmailBroker):
        async def request(self,method,path,body=None):
            calls.append((method,path,body))
            if path.endswith('complete_auth'): return {'connected_account_id':'ca_owner','toolkit_slug':'gmail'}
            if method=='GET': return {'user_id':USER_ID,'status':'ACTIVE','toolkit':{'slug':'gmail'},'auth_config':{'id':'ac_test'}}
            return {'status':200,'data':{'emailAddress':'owner@example.invalid'}}
    assert asyncio.run(Broker().complete(USER_ID,'opaque-single-use-session'))==('ca_owner','owner@example.invalid')
    assert calls[0]==('POST','/api/v3.1/connected_accounts/complete_auth',{'user_id':USER_ID,'session_uri':'opaque-single-use-session'})


def test_broker_timeout_is_not_retried_and_does_not_expose_auth_material(enabled,monkeypatch):
    count=[]; original=httpx.AsyncClient
    def handler(request): count.append(1); raise httpx.ReadTimeout('secret response',request=request)
    monkeypatch.setattr(gmail_broker.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    with pytest.raises(BrokerError) as exc: asyncio.run(GmailBroker().request('POST','/api/v3/tools/execute/proxy',{}))
    assert not exc.value.rejected and len(count)==1 and 'secret' not in str(exc.value)


def test_correlated_replies_exclude_outgoing_unrelated_and_quoted_text():
    store=MailStore(); m=store.rpc('begin_mail_send')['message']
    text='Thank you for reaching out.\n> We can schedule an interview\nOn Monday someone wrote:\ninterview'
    def item(id_,references,labels=None):
        return {'id':id_,'internalDate':'1793145660000','labelIds':labels or [],'payload':{'mimeType':'text/plain',
            'body':{'data':base64.urlsafe_b64encode(text.encode()).decode()},'headers':[
                {'name':'From','value':'Recruiter <recruiter@example.invalid>'},{'name':'References','value':references}]}}
    thread={'messages':[item('reply1',m['rfc_message_id']),item('unrelated','<someone-else@example.invalid>'),item('outgoing',m['rfc_message_id'],['SENT'])]}
    replies=mailbox.observed_replies(thread,m,'owner@example.invalid')
    assert len(replies)==1 and replies[0]['classification']=='other'
    assert 'interview' not in replies[0]['excerpt']
    assert mailbox.classify_reply({'auto-submitted':'auto-replied'},'Schedule an interview')=='out_of_office'
    assert mailbox.classify_reply({'auto-submitted':'auto-generated','from':'mailer-daemon@example.invalid'},'Delivery failed: address not found')=='bounce'
    assert mailbox.classify_reply({},'Please remove me from your contact list')=='unsubscribe'


def test_new_email_endpoints_require_owned_resources_and_reject_header_injection(client,monkeypatch):
    db=FakeSupabase(); app_id=str(uuid.uuid4()); message_id=str(uuid.uuid4())
    db.tables['job_applications']=[{'id':app_id,'user_id':USER_ID,'company':'Co'}]
    db.tables['outreach_messages']=[{'id':message_id,'user_id':'stranger','application_id':app_id}]
    monkeypatch.setattr(email_api,'admin',lambda:db)
    assert client.get('/api/v1/email/history').json()['emails']==[]
    assert client.get(f'/api/v1/email/messages/{message_id}/replies').status_code==404
    assert client.get(f'/api/v1/email/messages/{message_id}/attachment').status_code==404
    response=client.post('/api/v1/email/messages',json={'application_id':app_id,'to_email':'r@example.invalid','subject':'Hi\r\nBcc: bad@example.invalid','body':'Hello'})
    assert response.status_code==422
    assert client.post('/api/v1/email/send',json={}).status_code==409


def test_attachment_download_returns_the_saved_private_copy(client,monkeypatch):
    db=FakeSupabase(); id_=str(uuid.uuid4()); pdf=b'%PDF-1.7\n%%EOF'
    db.tables['outreach_messages']=[{'id':id_,'user_id':USER_ID,'attachment':{'data':base64.b64encode(pdf).decode()}}]
    monkeypatch.setattr(email_api,'admin',lambda:db)
    response=client.get(f'/api/v1/email/messages/{id_}/attachment')
    assert response.status_code==200 and response.content==pdf and response.headers['cache-control']=='private, no-store'


def test_recruiter_research_excludes_guesses_and_unverified_addresses(monkeypatch):
    db=FakeSupabase(); application={'id':str(uuid.uuid4()),'company':'Globex'}
    async def hunter(path,params):
        if path=='email-verifier': return {'email':params['email'],'status':'valid','accept_all':False,'verification':{'date':datetime.now(timezone.utc).date().isoformat()}}
        base={'value':'verified@globex.com','first_name':'Ada','last_name':'Recruiter','position':'Talent Recruiter','provenance':'found',
              'sources':[{'uri':'https://globex.com/team','last_seen_on':'2026-10-28'}]}
        return {'organization':'Globex','emails':[base,{**base,'value':'guessed@globex.com','provenance':'guessed'},{**base,'value':'engineering@globex.com','position':'Software Engineer'}]}
    monkeypatch.setattr(recruiters,'hunter',hunter)
    result=asyncio.run(recruiters.research(db,USER_ID,application,'globex.com'))
    assert [r['email'] for r in result['contacts']]==['verified@globex.com']
    assert db.tables['recruiter_leads'][0]['user_id']==USER_ID


def test_plain_public_projection_never_returns_pdf_bytes():
    row={'id':'m','attachment':{'name':'cv.pdf','data':'PRIVATE_PDF','sha256':'digest'},'attempt_id':'private'}
    output=mailbox.public_message(row)
    assert output['attachment']=={'name':'cv.pdf','sha256':'digest'} and 'attempt_id' not in output


def test_resume_attachment_is_built_from_owned_content_and_failure_does_not_silently_drop_it(monkeypatch):
    from test_application_flow import BASE_RESUME
    db=FakeSupabase(); app_id=str(uuid.uuid4()); pdf=b'%PDF-1.7\n%%EOF'
    db.tables['tailored_resumes']=[{'id':'resume','user_id':USER_ID,'application_id':app_id,'version':1,'content':BASE_RESUME}]
    async def render(*a): return pdf,'test'
    monkeypatch.setattr(email_api,'render_resume_pdf',render)
    attachment=asyncio.run(email_api.attachment(db,USER_ID,app_id,'owner@example.invalid'))
    assert base64.b64decode(attachment['data'])==pdf and attachment['sha256']==hashlib.sha256(pdf).hexdigest()
    async def fail(*a): raise RuntimeError('Renderer unavailable')
    monkeypatch.setattr(email_api,'render_resume_pdf',fail)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc: asyncio.run(email_api.attachment(db,USER_ID,app_id,'owner@example.invalid'))
    assert exc.value.status_code==503 and 'No email was approved or sent' in exc.value.detail


def test_invalid_settings_do_not_print_secret_inputs():
    from app.config import Settings
    with pytest.raises(ValueError) as exc: Settings(_env_file=None,RUN_LEASE_SECONDS='secret-input-must-not-print')
    assert 'secret-input-must-not-print' not in str(exc.value)
