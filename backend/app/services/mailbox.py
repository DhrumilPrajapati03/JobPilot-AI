"""Approved immutable messages, at-most-once dispatch, and read-only reconciliation."""
import asyncio
import base64
import re
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr, format_datetime

from bs4 import BeautifulSoup
from fastapi import HTTPException

from app.config import settings
from app.services.gmail_broker import GmailBroker, BrokerError, configured, safe_id
from app.services.runs import RunStore, PermanentRunError, durable_enabled
from app.services.supabase import select_all

HISTORY_COLUMNS = ('id,user_id,application_id,cold_email_id,to_email,subject,body,revision,approved_revision,approved_at,'
                   'connection_id,from_email,state,run_id,sent_at,delivery_status,provider_message_id,provider_thread_id,last_error,created_at,updated_at,'
                   'attachment_name:attachment->>name,attachment_size:attachment->size,attachment_sha256:attachment->>sha256')


def valid_email(value: str) -> str:
    value = value.strip()
    if len(value) > 254 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}", value):
        raise ValueError("Enter a single email address without a display name")
    return value


def public_message(row):
    result = {k:v for k,v in row.items() if k not in {"attempt_id", "rfc_message_id", "request_key", "attachment", "attachment_name", "attachment_size", "attachment_sha256"}}
    attachment = row.get("attachment")
    result["attachment"] = ({k:v for k,v in attachment.items() if k != "data"} if attachment else
        {'name':row['attachment_name'],'size':row.get('attachment_size'),'sha256':row.get('attachment_sha256')} if row.get('attachment_name') else None)
    return result


def command(db, uid, action, data):
    try:
        return RunStore(db).rpc("mail_command", p_user_id=uid, p_action=action, p_data=data)
    except Exception as exc:
        text = str(exc)
        if "mail_not_found" in text: raise HTTPException(404, "Email or application not found") from exc
        if any(code in text for code in ("mail_revision_conflict", "mail_immutable", "mail_approval_required", "mail_incomplete", "mail_connection_required", "disconnect_existing_mailbox_first")):
            raise HTTPException(409, "Reload this email and review its current version and Gmail connection before continuing.") from exc
        raise HTTPException(503, "Email storage is temporarily unavailable") from exc


def mime_message(message, sender):
    mail = EmailMessage()
    mail['From'], mail['To'], mail['Subject'] = valid_email(sender), valid_email(message['to_email']), message['subject']
    mail['Message-ID'] = message['rfc_message_id']
    mail['Date'] = format_datetime(datetime.fromisoformat(message['attempt_started_at'].replace('Z','+00:00')))
    mail.set_content(message['body'])
    attachment = message.get('attachment')
    if attachment:
        raw = base64.b64decode(attachment['data'], validate=True)
        import hashlib
        if hashlib.sha256(raw).hexdigest() != attachment['sha256'] or not raw.startswith(b'%PDF-') or len(raw) > 2*1024*1024:
            raise PermanentRunError("The approved resume attachment is invalid")
        mail.add_attachment(raw, maintype='application', subtype='pdf', filename='tailored-resume.pdf')
    return base64.urlsafe_b64encode(mail.as_bytes()).decode()


def header_map(payload):
    return {h.get('name','').lower(): h.get('value','') for h in payload.get('headers',[]) if isinstance(h,dict)}


def body_text(payload):
    chunks = []
    def walk(part, depth=0):
        if depth > 10: return
        mime = part.get('mimeType','')
        data = part.get('body',{}).get('data','')
        if data and mime in {'text/plain','text/html'}:
            try:
                text = base64.urlsafe_b64decode(data[:180000]+'===').decode('utf-8',errors='replace')[:128000]
                if mime == 'text/html':
                    soup=BeautifulSoup(text,'html.parser')
                    for tag in soup(['script','style']): tag.decompose()
                    text=soup.get_text(' ',strip=True)
                chunks.append((mime,text))
            except (ValueError,TypeError): pass
        for child in part.get('parts',[])[:100]: walk(child,depth+1)
    walk(payload)
    plain=[text for mime,text in chunks if mime=='text/plain']
    result='\n'.join(plain or [text for _,text in chunks])
    result=re.split(r'\n(?:On .{0,200}wrote:|-{2,}\s*Original Message)',result,maxsplit=1,flags=re.I)[0]
    return '\n'.join(line for line in result.splitlines() if not line.lstrip().startswith('>'))[:4000]


def classify_reply(headers, text):
    if re.search(r'\b(delivery (?:has )?failed|undeliverable|address not found)\b',text,re.I) and re.search(r'mailer-daemon|postmaster',headers.get('from',''),re.I): return 'bounce'
    if headers.get('auto-submitted','no').lower() != 'no' or headers.get('x-autoreply'):
        return 'out_of_office'
    lower=text.lower()
    if re.search(r'\b(unsubscribe|remove me|do not contact|stop emailing)\b',lower): return 'unsubscribe'
    if re.search(r'\b(not interested|not moving forward|unfortunately|position (?:is )?filled|reject(?:ed|ion))\b',lower): return 'negative'
    if re.search(r'\b(interview|schedule a (?:call|chat)|availability|meet with)\b',lower): return 'interview'
    if re.search(r'\b(interested|like to discuss|send (?:your |a )?resume|next steps)\b',lower): return 'positive'
    return 'other'


def observed_replies(thread, message, sender):
    replies=[]
    for item in sorted(thread.get('messages',[]),key=lambda m:int(m.get('internalDate') or 0))[-100:]:
        if set(item.get('labelIds',[])) & {'SENT','DRAFT'}: continue
        payload=item.get('payload',{})
        headers=header_map(payload)
        from_email=parseaddr(headers.get('from',''))[1].lower()
        references=headers.get('references','')+' '+headers.get('in-reply-to','')
        if (not from_email or from_email==sender.lower() or message['rfc_message_id'] not in references): continue
        try:
            received=datetime.fromtimestamp(int(item['internalDate'])/1000,timezone.utc)
            if received < datetime.fromisoformat(message['attempt_started_at'].replace('Z','+00:00')): continue
        except (ValueError,KeyError,OverflowError): continue
        text=body_text(payload)
        replies.append({'provider_message_id':safe_id(item['id']),'from_email':from_email,'excerpt':text,
                        'received_at':received.isoformat(),'classification':classify_reply(headers,text)})
    return replies


async def result(ctx, message_id, state, data):
    return await asyncio.to_thread(ctx.store.rpc,'mail_worker_result',p_run_id=ctx.run['id'],p_token=ctx.token,
                                   p_message_id=message_id,p_state=state,p_data=data)


async def reconcile(ctx, message, connection, broker):
    uid, account = ctx.run['user_id'],connection['provider_account_id']
    if not message.get('rfc_message_id'): return message['state']
    if message['state'] in {'sending','send_unknown'}:
        matches=await broker.gmail(uid,account,'GET','messages',query={'q':'in:sent rfc822msgid:'+message['rfc_message_id'], 'maxResults':10,'includeSpamTrash':'true'})
        confirmed=None
        for candidate in matches.get('messages',[]):
            item=await broker.gmail(uid,account,'GET','messages/'+safe_id(candidate['id']),query={'format':'metadata'})
            headers=header_map(item.get('payload',{}))
            if ('SENT' in item.get('labelIds',[]) and headers.get('message-id')==message['rfc_message_id']
                and parseaddr(headers.get('from',''))[1].lower()==(message.get('from_email') or connection['email']).lower()
                and parseaddr(headers.get('to',''))[1].lower()==message['to_email'].lower()):
                confirmed=item; break
        if not confirmed:
            await result(ctx,message['id'],'send_unknown',{'error':'Gmail acceptance is not confirmed. This email will not be automatically sent again.'})
            return 'send_unknown'
        message=await result(ctx,message['id'],'sent',{'provider_message_id':confirmed['id'],'provider_thread_id':confirmed.get('threadId')})
    thread_id=message.get('provider_thread_id')
    if message['state']=='sent' and thread_id:
        thread=await broker.gmail(uid,account,'GET','threads/'+safe_id(thread_id),query={'format':'full'})
        replies=observed_replies(thread,message,message.get('from_email') or connection['email'])
        await result(ctx,message['id'],'replies',{'replies':replies})
    return message['state']


async def execute_send(ctx, broker=None):
    if not configured() or not settings.MAIL_SEND_ENABLED:
        raise PermanentRunError('Gmail sending is disabled. Cancel the queued send or enable the configured worker.')
    broker=broker or GmailBroker()
    try:
        reservation=await asyncio.to_thread(ctx.store.rpc,'begin_mail_send',p_run_id=ctx.run['id'],p_token=ctx.token,p_message_id=ctx.run['inputs']['message_id'])
    except Exception as exc:
        if any(code in str(exc) for code in ('mail_not_found','mail_connection_required','mail_approval_required')):
            raise PermanentRunError('The queued email or Gmail connection changed. Cancel the request and review the current version.') from exc
        raise
    message,connection=reservation['message'],reservation['connection']
    if not reservation['dispatch']:
        state=await reconcile(ctx,message,connection,broker)
        return {'message_id':message['id'],'state':state}
    try:
        raw=mime_message(message,message.get('from_email') or connection['email'])
    except (ValueError,PermanentRunError):
        await result(ctx,message['id'],'failed',{'error':'The approved message could not be encoded. Edit and approve a new version.'})
        return {'message_id':message['id'],'state':'failed'}
    try:
        response=await broker.gmail(ctx.run['user_id'],connection['provider_account_id'],'POST','messages/send',body={'raw':raw})
    except BrokerError as exc:
        state='failed' if exc.rejected else 'send_unknown'
        await result(ctx,message['id'],state,{'error':'Gmail rejected this request. Review before retrying.' if exc.rejected else 'Gmail response was not confirmed. Synchronize status; automatic resending is blocked.'})
        return {'message_id':message['id'],'state':state}
    try:
        provider_id=safe_id(response.get('id'))
    except BrokerError:
        await result(ctx,message['id'],'send_unknown',{'error':'Gmail returned no usable receipt. Synchronize status before taking further action.'})
        return {'message_id':message['id'],'state':'send_unknown'}
    # If this commit fails after Gmail accepted, a replacement worker sees
    # 'sending' and can only search/reconcile. It cannot call send a second time.
    await result(ctx,message['id'],'sent',{'provider_message_id':provider_id,'provider_thread_id':response.get('threadId')})
    return {'message_id':message['id'],'state':'sent'}


async def execute_sync(ctx, broker=None):
    if not configured(): raise PermanentRunError('Gmail synchronization is disabled')
    broker=broker or GmailBroker()
    uid=ctx.run['user_id']; inputs=ctx.run['inputs']
    rows=ctx.store.client.table('mail_connections').select('*').eq('id',inputs['connection_id']).eq('user_id',uid).eq('status','active').execute().data
    if not rows: raise PermanentRunError('Gmail connection is no longer active')
    connection=rows[0]
    await broker.verify(uid,connection['provider_account_id'])
    query=ctx.store.client.table('outreach_messages').select('id,user_id,state,connection_id,from_email,rfc_message_id,provider_message_id,provider_thread_id,to_email,attempt_started_at').eq('user_id',uid).eq('connection_id',connection['id']).in_('state',['sent','sending','send_unknown']).order('id').limit(50)
    if inputs.get('after_id'): query=query.gt('id',inputs['after_id'])
    messages=await asyncio.to_thread(lambda:query.execute().data)
    errors=0; processed=0
    for message in messages:
        ctx.check()
        processed+=1
        try: await reconcile(ctx,message,connection,broker)
        except BrokerError:
            errors+=1
            if errors>=3: break
    more=len(messages)==50 and processed==len(messages) and errors<3
    if more:
        next_inputs={'connection_id':connection['id'],'cycle':inputs['cycle'],'after_id':messages[-1]['id']}
        await asyncio.to_thread(ctx.store.enqueue,uid,'mail_sync',next_inputs,f"mail-sync:{connection['id']}:{inputs['cycle']}:{messages[-1]['id']}")
    return {'processed':processed,'errors':errors,'has_more':more}


async def schedule_sync(db):
    if not configured() or not settings.MAIL_SYNC_ENABLED: return
    connections=await asyncio.to_thread(select_all,lambda:db.table('mail_connections').select('id,user_id').eq('status','active').order('id'))
    cycle=str(int(time.time()//600))
    for connection in connections:
        await asyncio.to_thread(RunStore(db).enqueue,connection['user_id'],'mail_sync',{'connection_id':connection['id'],'cycle':cycle},f"mail-sync:{connection['id']}:{cycle}")
