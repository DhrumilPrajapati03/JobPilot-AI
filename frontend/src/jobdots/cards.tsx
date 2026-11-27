// ============================================================
// JobDots — typed cards (plan section 6: "the form of the answer is part of the answer")
// ============================================================
// Experts emit typed JSON; these render it. Approval cards are the same component in a case
// thread and in the Approvals inbox. Every state is a word; colour only reinforces it.

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink, FileText } from 'lucide-react';
import { ExpertAvatar } from '../components/experts/ExpertAvatar';
import { type Action, type Artifact, openArtifactFile, useActionMutations, useCaseMutations } from './api';

export const EXPERT_NAMES: Record<string, string> = {
  supervisor: 'Supervisor', scout: 'Scout', researcher: 'Researcher', comp_analyst: 'Comp Analyst', tailor: 'Tailor',
  answerer: 'Answerer', applicant: 'Applicant', recon: 'Recon', connector: 'Connector', email_outreach: 'Email Outreach',
  dm_outreach: 'DM Outreach', inbox: 'Inbox', interview_buddy: 'Interview Buddy', reviewer: 'Reviewer', courier: 'Courier',
};
export const expertName = (id: string) => EXPERT_NAMES[id] ?? id.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

export const STAGE_WORDS: Record<string, string> = {
  found: 'Found', researched: 'Researched', tailored: 'Tailored', ready: 'Ready to apply', applied: 'Applied',
  replied: 'Replied', interview: 'Interviewing', offer: 'Offer', closed: 'Closed',
};

const STATUS_WORDS: Record<string, [string, string]> = {
  proposed: ['Draft', 'draft'], reviewed: ['Needs your approval', 'waiting'], approved: ['Approved', 'ok'],
  executing: ['Sending', 'waiting'], provider_accepted: ['Sent', 'ok'], delivered: ['Delivered', 'ok'],
  send_unknown: ['Send result unknown', 'warn'], failed: ['Not sent', 'warn'], cancelled: ['Rejected', 'quiet'], blocked: ['Blocked', 'warn'],
};

export function Chip({ tone, children }: { tone: string; children: React.ReactNode }) {
  return <span className={`jd-chip jd-chip-${tone}`}>{children}</span>;
}

export function when(iso: string | null | undefined) {
  if (!iso) return '';
  const d = new Date(iso);
  const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  if (mins < 60 * 24) return `${Math.round(mins / 60)} h ago`;
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

// --- approvals -------------------------------------------------------------------------------

const KIND_WORDS: Record<string, string> = {
  send_email: 'Email', send_linkedin_invite: 'LinkedIn invitation', send_linkedin_dm: 'LinkedIn message',
  create_calendar_event: 'Calendar event',
};

function whenRange(start?: string, end?: string) {
  if (!start) return '';
  const s = new Date(start), e = end ? new Date(end) : null;
  const day = s.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'short' });
  const t = (d: Date) => d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  return `${day}, ${t(s)}${e ? ` to ${t(e)}` : ''}`;
}

export function ApprovalCard({ action, showCase = false, company }: { action: Action; showCase?: boolean; company?: string }) {
  const { approve, reject, edit } = useActionMutations();
  const p = action.payload;
  const calendar = action.kind === 'create_calendar_event';
  const linkedin = action.kind === 'send_linkedin_invite' || action.kind === 'send_linkedin_dm';
  const textKey = action.kind === 'send_linkedin_invite' ? 'note' : 'body';
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string>(p[textKey] ?? '');
  const [subject, setSubject] = useState<string>(p.subject ?? '');
  const [status, label] = STATUS_WORDS[action.status] ?? [action.status, 'quiet'];
  const busy = approve.isPending || reject.isPending || edit.isPending;
  const error = (approve.error || reject.error || edit.error) as Error | null;
  const notes = action.review?.notes ?? [];
  const actionable = ['reviewed', 'proposed', 'approved', 'blocked'].includes(action.status);
  const over = action.kind === 'send_linkedin_invite' && draft.length > 200;

  const save = () => edit.mutate({ a: action, payload: { ...p, [textKey]: draft, ...(linkedin ? {} : { subject }) } },
                                  { onSuccess: () => setEditing(false) });
  return (
    <article className="jd-card jd-approval" data-status={action.status}>
      <header className="jd-card-head">
        <ExpertAvatar expert={action.agent} name={expertName(action.agent)} size={28} />
        <div className="jd-card-title">
          <strong>{KIND_WORDS[action.kind] ?? action.kind}{p.company ? ` to ${p.company}` : company ? ` to ${company}` : ''}</strong>
          <span>by {expertName(action.agent)}{showCase && action.case_id ? <>, <Link to={`/cases/${action.case_id}`}>open the case</Link></> : null}</span>
        </div>
        <Chip tone={label}>{status}</Chip>
      </header>
      <dl className="jd-fields">
        {calendar ? <>
          <dt>What</dt><dd>{p.summary}</dd>
          <dt>When</dt><dd>{whenRange(p.start, p.end)}</dd>
          {p.location && <><dt>Where</dt><dd>{p.location}</dd></>}
        </> : linkedin ? <>
          <dt>To</dt><dd>{p.name}{p.title ? `, ${p.title}` : ''} {p.profile_url && <a href={p.profile_url} target="_blank" rel="noreferrer" className="jd-inline-link">profile <ExternalLink size={12} /></a>}</dd>
        </> : <>
          <dt>From</dt><dd>{p.from_name || 'You'}</dd>
          <dt>To</dt><dd>{p.to ? `${p.to_name ? p.to_name + ' ' : ''}<${p.to}>` : <em>No recipient yet</em>}</dd>
          <dt>Subject</dt><dd>{editing ? <input className="jd-input" value={subject} onChange={e => setSubject(e.target.value)} aria-label="Subject" /> : p.subject}</dd>
        </>}
      </dl>
      {calendar ? <p className="jd-note">Goes on your own Google Calendar only; nobody else is invited.</p> : editing
        ? <><textarea className="jd-textarea" rows={linkedin ? 4 : 10} value={draft} onChange={e => setDraft(e.target.value)} aria-label="Message" />
            {action.kind === 'send_linkedin_invite' && <p className={`jd-count${over ? ' jd-over' : ''}`}>{draft.length} of 200 characters</p>}</>
        : <p className="jd-body">{p[textKey] || <em>No note</em>}</p>}
      {p.attachment && !linkedin && !calendar && <p className="jd-attach"><FileText size={14} />{p.attachment.filename}</p>}
      {action.block_reason && <p className="jd-note jd-warn">Reviewer: {action.block_reason}</p>}
      {!action.block_reason && notes.length > 0 && <p className="jd-note">Reviewer: {notes.join(' ')}</p>}
      {action.status === 'approved' && linkedin && <p className="jd-note">Waiting in the LinkedIn queue in the side panel. You send it yourself.</p>}
      {error && <p className="jd-note jd-warn" role="alert">{error.message}</p>}
      {actionable && <footer className="jd-actions">
        {editing ? <>
          <button className="jd-btn jd-primary" disabled={busy || over} onClick={save}>Save and check again</button>
          <button className="jd-btn" disabled={busy} onClick={() => { setEditing(false); setDraft(p[textKey] ?? ''); setSubject(p.subject ?? ''); }}>Cancel</button>
        </> : <>
          {action.status === 'reviewed' && <button className="jd-btn jd-primary" disabled={busy} onClick={() => approve.mutate(action)}>
            {calendar ? 'Approve and add' : linkedin ? 'Approve and queue' : 'Approve and send'}</button>}
          {action.status !== 'blocked' && !calendar && <button className="jd-btn" disabled={busy} onClick={() => setEditing(true)}>Edit</button>}
          <button className="jd-btn" disabled={busy} onClick={() => reject.mutate(action)}>{action.status === 'blocked' ? 'Discard' : 'Reject'}</button>
        </>}
      </footer>}
    </article>
  );
}

/** Several drafts of one kind stack as a deck: the top card acts, the count shows behind it. */
export function ApprovalDeck({ actions, showCase = false }: { actions: Action[]; showCase?: boolean }) {
  if (!actions.length) return null;
  const [top, ...rest] = actions;
  return (
    <div className="jd-deck" data-depth={Math.min(rest.length, 2)}>
      <ApprovalCard action={top} showCase={showCase} />
      {rest.length > 0 && <p className="jd-deck-count">{rest.length} more {rest.length === 1 ? 'draft' : 'drafts'} like this behind it</p>}
    </div>
  );
}

// --- artifacts -------------------------------------------------------------------------------

function Claims({ title, items }: { title: string; items?: { text: string; sources: number[] }[] }) {
  if (!items?.length) return null;
  return <><h4>{title}</h4><ul className="jd-claims">{items.map((c, i) => <li key={i}>{c.text} <sup>{c.sources.join(',')}</sup></li>)}</ul></>;
}

function BriefCard({ a }: { a: Artifact }) {
  const c = a.content;
  const [open, setOpen] = useState(false);
  return <>
    <p>{c.summary}</p>
    <button className="jd-link" onClick={() => setOpen(!open)}>{open ? 'Hide the details' : 'Product, stack, news and sources'}</button>
    {open && <div className="jd-detail">
      <Claims title="Product" items={c.product} /><Claims title="Stage" items={c.stage} /><Claims title="Recent news" items={c.recent_news} />
      <Claims title="Tech stack" items={c.tech_stack} /><Claims title="Why it fits" items={c.fit_notes} />
      <h4>Sources</h4><ol className="jd-sources">{(c.sources ?? []).map((s: any) => <li key={s.n}>{s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.title || s.url}</a> : s.title || 'The job description'}</li>)}</ol>
    </div>}
    <p className="jd-meta">Confidence: {c.confidence}</p>
  </>;
}

function ResumeCard({ a, caseId }: { a: Artifact; caseId: string }) {
  const c = a.content;
  const { reviewResume } = useCaseMutations();
  const [open, setOpen] = useState(false);
  const status: Record<string, [string, string]> = { awaiting_review: ['Needs your review', 'waiting'], approved: ['Approved', 'ok'], rejected: ['Rejected', 'quiet'] };
  const [word, tone] = status[c.status] ?? [c.status, 'quiet'];
  return <>
    <p><Chip tone={tone}>{word}</Chip> {c.changes?.length ?? 0} changes, {c.rejected?.length ?? 0} refused by the validator{c.pdf?.pages ? `, ${c.pdf.pages} page${c.pdf.pages > 1 ? 's' : ''}` : ''}.</p>
    {c.missing?.length > 0 && <p className="jd-meta">Not in your vault, so never added: {c.missing.slice(0, 8).join(', ')}</p>}
    <button className="jd-link" onClick={() => setOpen(!open)}>{open ? 'Hide the changes' : 'See every change'}</button>
    {open && <ol className="jd-diff">{(c.changes ?? []).map((ch: any, i: number) => <li key={i}>
      <span className="jd-meta">{ch.where || ch.target} ({ch.kind})</span>
      {ch.before && <del>{ch.before}</del>}{ch.after && <ins>{ch.after}</ins>}
    </li>)}{(c.rejected ?? []).map((r: any, i: number) => <li key={`r${i}`} className="jd-refused"><span className="jd-meta">Refused: {r.reasons.join('; ')}</span><del>{r.text}</del></li>)}</ol>}
    <footer className="jd-actions">
      {c.pdf && <button className="jd-btn" onClick={() => openArtifactFile(caseId, a.id)}><FileText size={14} />Open the PDF</button>}
      {c.status === 'awaiting_review' && <>
        <button className="jd-btn jd-primary" disabled={reviewResume.isPending} onClick={() => reviewResume.mutate({ caseId, artifactId: a.id, decision: 'approved' })}>Approve this resume</button>
        <button className="jd-btn" disabled={reviewResume.isPending} onClick={() => reviewResume.mutate({ caseId, artifactId: a.id, decision: 'rejected' })}>Reject</button>
      </>}
    </footer>
  </>;
}

const ROLE_WORDS: Record<string, string> = { recruiter: 'Recruiter', hiring_manager: 'Hiring manager', ceo: 'CEO', cto: 'CTO', employee: 'Engineer', unknown: 'Someone' };

function PeopleCard({ a }: { a: Artifact }) {
  const people: any[] = a.content.people ?? [];
  if (!people.length) return <p>Nobody found it could confirm{a.content.notes?.[0] ? `: ${a.content.notes[0]}` : '.'}</p>;
  return <table className="jd-table"><thead><tr><th>Person</th><th>Role</th><th>How to reach</th><th></th></tr></thead><tbody>
    {people.map(p => <tr key={p.contact_id}>
      <td>{p.linkedin_url ? <a href={p.linkedin_url} target="_blank" rel="noreferrer">{p.name}</a> : p.name}<span className="jd-meta">{p.title}</span></td>
      <td>{ROLE_WORDS[p.role_class] ?? p.role_class}</td>
      <td>{p.blocked ? <Chip tone="warn">{p.blocked}</Chip> : p.channel === 'email' ? `Email ${p.email}` : p.channel === 'referral' ? 'Ask for a referral (connection)' : 'LinkedIn'}</td>
      <td>{p.suggested && <Chip tone="ok">Suggested</Chip>}</td>
    </tr>)}</tbody></table>;
}

function InvitesCard({ a }: { a: Artifact }) {
  const invites: any[] = a.content.invites ?? [];
  return <>
    {invites.length === 0 && <p>{a.content.notes?.[0] ?? 'Nobody to invite.'}</p>}
    <ul className="jd-invites">{invites.map(i => <li key={i.contact_id}>
      <strong>{i.name}</strong> <span className="jd-meta">{i.title}</span>
      <p>{i.note}</p>
      {i.status === 'blocked' ? <p className="jd-note jd-warn">Reviewer blocked it: {i.review?.blocks?.join(' ')}</p> : <p className="jd-meta">Approve it in the approval card on this case.</p>}
    </li>)}</ul>
    {invites.length > 0 && a.content.notes?.length > 0 && <p className="jd-meta">{a.content.notes.join(' ')}</p>}
  </>;
}

const BADGE_WORDS: Record<string, string> = { vault: 'From your vault', reused: 'Reused', adapted: 'Adapted', generated: 'Drafted', needs_you: 'Needs you' };

function AnswersCard({ a }: { a: Artifact }) {
  const [open, setOpen] = useState(false);
  const answers: any[] = a.content.answers ?? [];
  const counts = Object.entries(a.content.counts ?? {}).filter(([, n]) => n).map(([b, n]) => `${n} ${(BADGE_WORDS[b] ?? b).toLowerCase()}`).join(', ');
  return <>
    <p>{answers.length} questions: {counts}. Review and fill them from the side panel on the form.</p>
    <button className="jd-link" onClick={() => setOpen(!open)}>{open ? 'Hide the answers' : 'See the answers'}</button>
    {open && <dl className="jd-answers">{answers.map(x => <div key={x.key}><dt>{x.label}</dt><dd><Chip tone={x.badge === 'needs_you' ? 'warn' : x.badge === 'generated' || x.badge === 'adapted' ? 'draft' : 'ok'}>{BADGE_WORDS[x.badge]}</Chip> {Array.isArray(x.value) ? x.value.join(', ') : x.value === '__resume__' ? 'Your tailored resume' : x.value || '—'}</dd></div>)}</dl>}
  </>;
}

function DraftCard({ a }: { a: Artifact }) {
  const c = a.content;
  return <><p><strong>{c.subject}</strong></p><p className="jd-body">{c.body}</p>
    {!c.to && <p className="jd-note jd-warn">No recipient yet. Add one on this case to send it.</p>}</>;
}

const ARTIFACT_WORDS: Record<string, string> = {
  company_brief: 'Company brief', resume_version: 'Tailored resume', draft: 'Email draft', contact_list: 'People at the company',
  answer_set: 'Application answers', invite_set: 'LinkedIn invitations', comp_report: 'Pay research', interview_prep: 'Interview prep',
};

export function ArtifactCard({ a, caseId }: { a: Artifact; caseId: string }) {
  const body = a.kind === 'company_brief' ? <BriefCard a={a} /> : a.kind === 'resume_version' ? <ResumeCard a={a} caseId={caseId} />
    : a.kind === 'contact_list' ? <PeopleCard a={a} /> : a.kind === 'invite_set' ? <InvitesCard a={a} />
    : a.kind === 'answer_set' ? <AnswersCard a={a} /> : a.kind === 'draft' ? <DraftCard a={a} /> : <pre className="jd-json">{JSON.stringify(a.content, null, 2).slice(0, 2000)}</pre>;
  return (
    <article className="jd-card" data-kind={a.kind}>
      <header className="jd-card-head">
        <ExpertAvatar expert={a.created_by} name={expertName(a.created_by)} size={28} />
        <div className="jd-card-title"><strong>{a.title || ARTIFACT_WORDS[a.kind] || a.kind}</strong>
          <span>{ARTIFACT_WORDS[a.kind] ?? a.kind}{a.version > 1 ? `, version ${a.version}` : ''} by {expertName(a.created_by)}, {when(a.created_at)}</span></div>
      </header>
      <div className="jd-card-body">{body}</div>
    </article>
  );
}
