"""Gmail connections and explicit review/approval/send endpoints."""
import asyncio
import base64
import hashlib
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.services.auth import CurrentUser, get_current_user
from app.services.supabase import get_supabase_admin_client
from app.services import mailbox
from app.services.gmail_broker import GmailBroker, BrokerError, configured
from app.services.runs import RunStore, durable_enabled
from app.resume_engine.builder import build_render_content
from app.resume_engine.renderer import render_resume_pdf

router = APIRouter()


def admin():
    try: return get_supabase_admin_client()
    except Exception as exc: raise HTTPException(503, "Email storage is unavailable") from exc


def owned(db, table, row_id, uid):
    rows=db.table(table).select('*').eq('id',str(row_id)).eq('user_id',uid).execute().data
    if not rows: raise HTTPException(404,'Email resource not found')
    return rows[0]


def active_connection(db, uid):
    rows=db.table('mail_connections').select('*').eq('user_id',uid).eq('status','active').execute().data
    if not rows: raise HTTPException(409,'Connect Gmail in Settings before continuing')
    return rows[0]


class CompleteConnection(BaseModel):
    session_uri: str = Field(min_length=1,max_length=2048)


class DraftBody(BaseModel):
    to_email: str = Field(max_length=254)
    subject: str = Field(min_length=1,max_length=300)
    body: str = Field(min_length=1,max_length=20000)
    attach_resume: bool = False

    @field_validator('to_email')
    @classmethod
    def address(cls, value): return mailbox.valid_email(value)

    @field_validator('subject')
    @classmethod
    def subject_header(cls,value):
        if '\r' in value or '\n' in value or not value.strip(): raise ValueError('Use a single subject line')
        return value


class CreateDraft(DraftBody):
    application_id: uuid.UUID
    cold_email_id: uuid.UUID | None = None


class EditDraft(DraftBody):
    revision: int = Field(ge=1)


class Revision(BaseModel):
    revision: int = Field(ge=1)


class ReplyReview(BaseModel):
    classification: Literal['positive','negative','interview','out_of_office','unsubscribe','bounce','other']


async def attachment(db, uid, app_id, email):
    rows=db.table('tailored_resumes').select('*').eq('application_id',str(app_id)).eq('user_id',uid).order('version',desc=True).limit(1).execute().data
    if not rows: raise HTTPException(409,'Prepare a tailored resume before attaching it')
    profiles=db.table('user_profiles').select('*').eq('id',uid).execute().data
    try:
        content=build_render_content(rows[0]['content'],profiles[0] if profiles else {},email=email)
        raw,_=await render_resume_pdf(content)
        if not raw.startswith(b'%PDF-') or len(raw)>2*1024*1024: raise ValueError('Invalid PDF')
    except Exception as exc:
        raise HTTPException(503,'The resume PDF could not be prepared. No email was approved or sent.') from exc
    return {'name':'tailored-resume.pdf','content_type':'application/pdf','size':len(raw),
            'sha256':hashlib.sha256(raw).hexdigest(),'data':base64.b64encode(raw).decode()}


@router.get('/connection')
async def connection_status(user: CurrentUser=Depends(get_current_user)):
    db=admin()
    rows=db.table('mail_connections').select('id,email,status,last_sync_at').eq('user_id',user.id).eq('status','active').execute().data
    return {'configured':configured(),'send_enabled':configured() and settings.MAIL_SEND_ENABLED and durable_enabled(),
            'connection':rows[0] if rows else None}


@router.post('/connection')
async def start_connection(user: CurrentUser=Depends(get_current_user)):
    try: return await GmailBroker().link(user.id)
    except BrokerError as exc: raise HTTPException(503,str(exc)) from exc


@router.post('/connection/complete')
async def complete_connection(body: CompleteConnection,user: CurrentUser=Depends(get_current_user)):
    try:
        account_id,email=await GmailBroker().complete(user.id,body.session_uri)
        mailbox.valid_email(email)
    except (BrokerError,ValueError) as exc:
        raise HTTPException(409,'Gmail identity verification did not complete. Start a new connection from Settings.') from exc
    row=await asyncio.to_thread(mailbox.command,admin(),user.id,'connect',{'provider_account_id':account_id,'email':email})
    return {k:row[k] for k in ('id','email','status')}


@router.delete('/connection')
async def disconnect_connection(user: CurrentUser=Depends(get_current_user)):
    db=admin(); connection=active_connection(db,user.id)
    # Stop local intake before attempting remote credential deletion. Failure to
    # revoke remotely never re-enables the local connection.
    await asyncio.to_thread(mailbox.command,db,user.id,'disconnect',{'id':connection['id']})
    revoked=True
    try: await GmailBroker().disconnect(user.id,connection['provider_account_id'])
    except BrokerError: revoked=False
    return {'disconnected':True,'provider_revoked':revoked}


@router.post('/messages',status_code=201)
async def create_message(body: CreateDraft,user: CurrentUser=Depends(get_current_user),idempotency_key: str|None=Header(default=None,max_length=128)):
    db=admin(); owned(db,'job_applications',body.application_id,user.id)
    data=body.model_dump(mode='json',exclude={'attach_resume'})
    data['request_key']=('cold-email:'+str(body.cold_email_id)) if body.cold_email_id else (idempotency_key or str(uuid.uuid4()))
    data['attachment']=await attachment(db,user.id,body.application_id,user.email) if body.attach_resume else None
    return mailbox.public_message(await asyncio.to_thread(mailbox.command,db,user.id,'create',data))


@router.get('/history')
async def history(application_id: uuid.UUID|None=None,user: CurrentUser=Depends(get_current_user)):
    db=admin()
    query=db.table('outreach_messages').select(mailbox.HISTORY_COLUMNS).eq('user_id',user.id).order('created_at',desc=True).limit(100)
    if application_id: query=query.eq('application_id',str(application_id))
    rows=query.execute().data
    run_ids=[r['run_id'] for r in rows if r.get('run_id') and r.get('state')=='queued']
    if run_ids:
        states={r['id']:r['status'] for r in db.table('agent_runs').select('id,status').eq('user_id',user.id).in_('id',run_ids).execute().data}
        for row in rows: row['execution_status']=states.get(row.get('run_id'))
    return {'emails':[mailbox.public_message(r) for r in rows],'total':len(rows)}


@router.patch('/messages/{message_id}')
async def edit_message(message_id: uuid.UUID,body: EditDraft,user: CurrentUser=Depends(get_current_user)):
    db=admin(); message=owned(db,'outreach_messages',message_id,user.id)
    data=body.model_dump(mode='json',exclude={'attach_resume'})
    data.update(id=str(message_id),attachment=await attachment(db,user.id,message['application_id'],user.email) if body.attach_resume else None)
    return mailbox.public_message(await asyncio.to_thread(mailbox.command,db,user.id,'edit',data))


@router.post('/messages/{message_id}/approve')
async def approve(message_id: uuid.UUID,body: Revision,user: CurrentUser=Depends(get_current_user)):
    return mailbox.public_message(await asyncio.to_thread(mailbox.command,admin(),user.id,'approve',{'id':str(message_id),'revision':body.revision}))


@router.post('/messages/{message_id}/send',status_code=202)
async def send(message_id: uuid.UUID,body: Revision,user: CurrentUser=Depends(get_current_user)):
    if not configured() or not settings.MAIL_SEND_ENABLED or not durable_enabled():
        raise HTTPException(503,'Gmail sending is not available yet')
    return mailbox.public_message(await asyncio.to_thread(mailbox.command,admin(),user.id,'queue',{'id':str(message_id),'revision':body.revision}))


@router.post('/messages/{message_id}/cancel')
async def cancel(message_id: uuid.UUID,body: Revision,user: CurrentUser=Depends(get_current_user)):
    return mailbox.public_message(await asyncio.to_thread(mailbox.command,admin(),user.id,'cancel',{'id':str(message_id),'revision':body.revision}))


@router.post('/send')
async def deprecated_send(user: CurrentUser=Depends(get_current_user)):
    raise HTTPException(409,'Create an email draft, approve its current version, then send through the reviewed-message endpoint')


@router.post('/sync',status_code=202)
async def sync(user: CurrentUser=Depends(get_current_user)):
    if not configured() or not durable_enabled(): raise HTTPException(503,'Gmail synchronization is not available yet')
    db=admin(); connection=active_connection(db,user.id); cycle=str(uuid.uuid4())
    run=await asyncio.to_thread(RunStore(db).enqueue,user.id,'mail_sync',{'connection_id':connection['id'],'cycle':cycle},'mail-sync:'+connection['id']+':'+cycle)
    return {'status':'queued','run_id':run['id']}


@router.get('/messages/{message_id}/attachment')
async def download_attachment(message_id: uuid.UUID,user: CurrentUser=Depends(get_current_user)):
    row=owned(admin(),'outreach_messages',message_id,user.id)
    if not row.get('attachment'): raise HTTPException(404,'No attachment')
    raw=base64.b64decode(row['attachment']['data'],validate=True)
    return Response(raw,media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="tailored-resume.pdf"','Cache-Control':'private, no-store'})


@router.get('/messages/{message_id}/replies')
async def replies(message_id: uuid.UUID,user: CurrentUser=Depends(get_current_user)):
    db=admin(); owned(db,'outreach_messages',message_id,user.id)
    return {'replies':db.table('mail_replies').select('*').eq('message_id',str(message_id)).eq('user_id',user.id).order('received_at',desc=True).limit(100).execute().data}


@router.patch('/replies/{reply_id}')
async def review_reply(reply_id: uuid.UUID,body: ReplyReview,user: CurrentUser=Depends(get_current_user)):
    db=admin(); owned(db,'mail_replies',reply_id,user.id)
    return db.table('mail_replies').update({'classification':body.classification,'classification_source':'user','reviewed':True}).eq('id',str(reply_id)).eq('user_id',user.id).execute().data[0]
