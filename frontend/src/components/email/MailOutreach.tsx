import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../../lib/api';
import { useDraft } from '../../hooks/use-draft';
import { useMailbox, useMailHistory, useMailAction, useMailReplies, useRecruiterLeads, useSyncMailbox, downloadMailAttachment,
  type OutreachMessage, type MailReply, type DraftFields } from '../../hooks/use-mailbox';
import type { ColdEmail } from '../../hooks/use-applications';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Textarea } from '../ui/textarea';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/card';

export const MAIL_STATE_LABEL: Record<OutreachMessage['state'],string> = {
  draft:'Draft — not sent',approved:'Approved — not sent',queued:'Queued — not confirmed sent',sending:'Awaiting Gmail confirmation',
  sent:'Gmail accepted',send_unknown:'Send outcome unknown — synchronize; no automatic resend',failed:'Request rejected — not confirmed sent',
};
const categories=['positive','negative','interview','out_of_office','unsubscribe','bounce','other'];

function ReplyRow({reply}:{reply:MailReply}) {
  const [category,setCategory]=useState(reply.classification);
  const update=useMailAction<void>(()=>api.patch(`/email/replies/${reply.id}`,{classification:category}));
  return <li className="space-y-2 rounded-md border p-3 text-sm"><p>{reply.from_email} · {new Date(reply.received_at).toLocaleString()}</p>
    <blockquote className="whitespace-pre-line border-l-2 pl-3">{reply.excerpt || '(No readable text)'}</blockquote>
    <label className="flex flex-wrap items-center gap-2">{reply.reviewed?'Reviewed category':'Suggested category'}
      <select aria-label="Reply category" value={category} onChange={e=>setCategory(e.target.value)} className="rounded border bg-background p-1">{categories.map(c=><option key={c} value={c}>{c.replaceAll('_',' ')}</option>)}</select>
      <Button size="sm" variant="outline" disabled={update.isPending} onClick={()=>update.mutate()}>Confirm category</Button>
    </label>{update.error && <p role="alert">{update.error.message}</p>}
  </li>;
}

export function MessageCard({message}:{message:OutreachMessage}) {
  const mailbox=useMailbox(); const sync=useSyncMailbox();
  const {draft,setDraft,dirty,reset}=useDraft<DraftFields>({to_email:message.to_email,subject:message.subject,body:message.body,attach_resume:!!message.attachment});
  const action=useMailAction<{type:string}>(async({type})=>type==='edit'?api.patch(`/email/messages/${message.id}`,{...draft,revision:message.revision}):api.post(`/email/messages/${message.id}/${type}`,{revision:message.revision}));
  const download=useMailAction<void>(()=>downloadMailAttachment(message.id));
  const replies=useMailReplies(message.id,message.state==='sent');
  const editable=['draft','approved','failed'].includes(message.state);
  const connectionMatches=!!mailbox.data?.connection && mailbox.data.connection.id===message.connection_id && (!message.from_email || message.from_email.toLowerCase()===mailbox.data.connection.email.toLowerCase());
  const busy=action.isPending;
  return <article className="space-y-3 rounded-lg border p-4">
    <p className="text-sm font-medium" role="status">{MAIL_STATE_LABEL[message.state]}</p>
    {message.state==='queued' && message.execution_status==='failed' && <p className="text-sm text-warning">The worker stopped before dispatch. Cancel this queued request, then review it again.</p>}
    <p className="text-sm">From: {message.from_email || mailbox.data?.connection?.email || 'Connect Gmail to choose the sending account'}</p>
    <label className="block space-y-1 text-xs">Recipient<Input type="email" value={draft.to_email} disabled={!editable} onChange={e=>setDraft({...draft,to_email:e.target.value})}/></label>
    <label className="block space-y-1 text-xs">Subject<Input value={draft.subject} disabled={!editable} onChange={e=>setDraft({...draft,subject:e.target.value})}/></label>
    <label className="block space-y-1 text-xs">Email text<Textarea value={draft.body} disabled={!editable} onChange={e=>setDraft({...draft,body:e.target.value})} className="min-h-40"/></label>
    {editable && <label className="flex gap-2 text-sm"><input type="checkbox" checked={draft.attach_resume} onChange={e=>setDraft({...draft,attach_resume:e.target.checked})}/>Attach tailored resume when saving this version</label>}
    {message.attachment ? <div className="text-sm"><Button variant="outline" size="sm" onClick={()=>download.mutate()} disabled={download.isPending}>Review saved resume PDF</Button><span className="ml-2">{Math.ceil(message.attachment.size/1024)} KB · saved snapshot</span></div> : <p className="text-xs text-muted-foreground">No attachment in this saved version.</p>}
    {message.state==='approved' && <p className="text-xs text-muted-foreground">Approved for {message.from_email || mailbox.data?.connection?.email || 'your connected Gmail account'}. Editing requires a fresh approval.</p>}
    <div className="flex flex-wrap gap-2">
      {editable && dirty && <><Button disabled={busy} onClick={()=>action.mutate({type:'edit'})}>Save new version</Button><Button variant="ghost" onClick={reset}>Reset edits</Button></>}
      {editable && message.attachment && !dirty && <Button variant="outline" disabled={busy} onClick={()=>action.mutate({type:'edit'})}>Refresh PDF from current resume</Button>}
      {message.state==='draft' && <Button disabled={busy || dirty || !mailbox.data?.connection} onClick={()=>action.mutate({type:'approve'})}>Approve this recipient, email and attachment</Button>}
      {message.state==='approved' && <><Button disabled={busy || dirty || !mailbox.data?.send_enabled || !connectionMatches} onClick={()=>action.mutate({type:'send'})}>Send approved email from Gmail</Button><Button variant="outline" disabled={busy} onClick={()=>action.mutate({type:'cancel'})}>Revoke approval</Button></>}
      {message.state==='queued' && <Button variant="outline" disabled={busy} onClick={()=>action.mutate({type:'cancel'})}>Cancel queued send</Button>}
      {message.state==='failed' && <Button variant="outline" disabled={busy || dirty} onClick={()=>action.mutate({type:'cancel'})}>Return to review</Button>}
      {['sent','sending','send_unknown'].includes(message.state) && <Button variant="outline" disabled={sync.isPending} onClick={()=>sync.mutate()}>Synchronize status and replies</Button>}
    </div>
    {message.state==='sent' && <p className="text-xs text-muted-foreground">Provider receipt: {message.provider_message_id}. {message.delivery_status==='bounce_observed'?'A bounce notice was observed.':'Recipient delivery and read status are unknown.'}</p>}
    {message.last_error && <p className="text-sm text-warning">{message.last_error}</p>}
    {(action.error || sync.error || download.error) && <p role="alert" className="text-sm text-destructive">{(action.error || sync.error || download.error)?.message}</p>}
    {sync.isSuccess && <p role="status" className="text-xs">{sync.data.errors?`${sync.data.errors} conversations could not be synchronized. Check the Gmail connection.`:sync.data.has_more?'This batch finished; remaining conversations continue in the background.':'Tracked conversation status checked.'}</p>}
    {replies.data && <div className="space-y-2"><p className="text-xs text-muted-foreground">{replies.data.replies.length ? 'Observed replies · category suggestions require your review':'No correlated reply observed yet. Unrelated mailbox messages are not imported.'}</p>
      <ul className="space-y-2">{replies.data.replies.map(r=><ReplyRow key={r.id} reply={r}/>)}</ul></div>}
    {replies.error && <p className="text-xs text-destructive">Replies could not be loaded.</p>}
  </article>;
}

export function MailOutreach({applicationId,emails}:{applicationId:string;emails:ColdEmail[]}) {
  const mailbox=useMailbox(); const history=useMailHistory(applicationId); const leads=useRecruiterLeads(applicationId);
  const [source,setSource]=useState(emails[0]?.id || ''); const [to,setTo]=useState(''); const [subject,setSubject]=useState(emails[0]?.subject || '');
  const [body,setBody]=useState(emails[0]?.body || ''); const [attach,setAttach]=useState(true); const [domain,setDomain]=useState('');
  const attempt=useRef<{payload:string;key:string}|null>(null);
  const create=useMailAction<void>(async()=>{
    const data={application_id:applicationId,cold_email_id:source || null,to_email:to,subject,body,attach_resume:attach};
    const payload=JSON.stringify(data);
    if(attempt.current?.payload!==payload) attempt.current={payload,key:crypto.randomUUID()};
    const result=await api.post('/email/messages',data,{headers:{'Idempotency-Key':attempt.current.key}});
    attempt.current=null; return result;
  });
  const research=useMailAction<void>(()=>api.post('/contacts/research',{application_id:applicationId,company_domain:domain}));
  return <Card><CardHeader><CardTitle>Reviewed Gmail outreach</CardTitle><p className="text-sm text-muted-foreground">Drafts stay in JobPilot until you approve and send. Review the saved PDF, sending account and recipient. Generated templates and manual logs below do not confirm a Gmail send.</p></CardHeader>
    <CardContent className="space-y-4">
      {history.data?.emails.some(m=>m.state==='send_unknown') && <p className="text-sm text-warning">An earlier send has an unresolved outcome. Check Gmail Sent before creating another message for the same recipient.</p>}
      {!mailbox.data?.connection && <p className="text-sm"><Link className="underline" to="/settings">Connect Gmail in Settings</Link> to approve and send. You can prepare drafts first.</p>}
      <details className="rounded-lg border p-3 text-sm"><summary className="cursor-pointer">Find recruiter contacts with source evidence</summary>
        <div className="mt-3 flex flex-wrap gap-2"><Input aria-label="Company domain" placeholder="company.com" value={domain} onChange={e=>setDomain(e.target.value)} className="max-w-xs"/>
        <Button variant="outline" disabled={!domain || research.isPending} onClick={()=>research.mutate()}>{research.isPending?'Checking sources…':'Research and verify'}</Button></div>
        <p className="mt-2 text-xs text-muted-foreground">Uses the configured research provider. Guessed addresses and catch-all results are excluded. Review employer, role and source dates.</p>
        {research.isSuccess && !leads.data?.contacts.length && <p>No verified recruiter contacts found.</p>}
        {research.error && <p role="alert" className="text-destructive">{research.error.message}</p>}
        {leads.data?.contacts.map(lead=><div key={lead.email} className="mt-3 space-y-1 border-t pt-2"><p>{lead.full_name} · {lead.position} · {lead.email}</p><p className="text-xs">Provider-valid email · checked {new Date(lead.verified_at).toLocaleDateString()}</p>
          {lead.sources.filter(s=>s.url).map(s=><a className="mr-3 inline-block text-xs underline" key={s.url} href={s.url} target="_blank" rel="noreferrer">Source{s.last_seen_on?` · last seen ${s.last_seen_on}`:''}</a>)}
          <Button size="sm" variant="outline" onClick={()=>setTo(lead.email)}>Use recipient in draft</Button></div>)}
      </details>
      <details className="rounded-lg border p-3 text-sm"><summary className="cursor-pointer">Create a Gmail review draft</summary><div className="mt-3 space-y-3">
        {!!emails.length && <label className="block space-y-1">Saved generated template<select aria-label="Generated email template" value={source} className="ml-2 rounded border bg-background p-1" onChange={e=>{setSource(e.target.value);const email=emails.find(m=>m.id===e.target.value);if(email){setSubject(email.subject);setBody(email.body);}}}><option value="">New independent draft</option>{emails.map(e=><option key={e.id} value={e.id}>{e.sequence_number===1?'Initial email':`Follow-up ${e.sequence_number-1}`}</option>)}</select></label>}
        <label className="block space-y-1">Recipient<Input type="email" value={to} onChange={e=>setTo(e.target.value)} placeholder="recruiter@company.com"/></label>
        <label className="block space-y-1">Subject<Input value={subject} onChange={e=>setSubject(e.target.value)}/></label>
        <label className="block space-y-1">Email text<Textarea value={body} onChange={e=>setBody(e.target.value)} className="min-h-40"/></label>
        <label className="flex gap-2"><input type="checkbox" checked={attach} onChange={e=>setAttach(e.target.checked)}/>Save a tailored resume PDF snapshot with this draft</label>
        <Button disabled={create.isPending || !to || !subject || !body} onClick={()=>create.mutate()}>{create.isPending?'Preparing saved copy…':'Save draft for review — do not send'}</Button>
        {create.error && <p role="alert" className="text-destructive">{create.error.message}</p>}
      </div></details>
      {history.error && <p role="alert" className="text-sm text-destructive">Email history could not be loaded.</p>}
      {history.data?.emails.map(message=><MessageCard key={message.id} message={message}/>)}
    </CardContent></Card>;
}
