// JobDots — case thread: one timeline that mixes system events and the experts' typed cards,
// with what needs you on this case pinned at the top.
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ExternalLink } from 'lucide-react';
import { ExpertAvatar } from '../../components/experts/ExpertAvatar';
import { type Artifact, type CaseEvent, useCase, useCaseMutations } from '../../jobdots/api';
import { ApprovalCard, ArtifactCard, STAGE_WORDS, expertName, when } from '../../jobdots/cards';

const STAGES = ['found', 'researched', 'tailored', 'ready', 'applied', 'replied', 'interview', 'offer', 'closed'];
const RERUN: [string, 'research' | 'recon' | 'tailor' | 'connect' | 'supervise'][] = [
  ['Research again', 'research'], ['Find people again', 'recon'], ['New resume version', 'tailor'],
  ['Propose LinkedIn invitations', 'connect'], ['Let Supervisor continue', 'supervise'],
];

type Item = { at: string; event?: CaseEvent; artifact?: Artifact };

export default function CaseThread() {
  const { id } = useParams();
  const q = useCase(id);
  const { stage, rerun, recipient } = useCaseMutations();
  const [to, setTo] = useState({ email: '', name: '' });
  const [showJd, setShowJd] = useState(false);
  if (q.isLoading) return <div className="jd-page"><p className="jd-meta">Opening the case…</p></div>;
  if (q.isError || !q.data) return <div className="jd-page"><p className="jd-empty">This case couldn't be opened. <Link to="/cases">Back to cases</Link></p></div>;
  const c = q.data;

  // Artifacts render as cards where they were made; the events that announce them fold into the card.
  const shown = new Set(c.artifacts.map(a => a.id));
  const items: Item[] = [
    ...c.artifacts.filter(a => !a.legacy).map(a => ({ at: a.created_at, artifact: a })),
    ...c.events.filter(e => !(e.kind === 'artifact' && shown.has(String(e.data?.artifact_id ?? '')))).map(e => ({ at: e.at, event: e })),
  ].sort((a, b) => a.at.localeCompare(b.at));
  const needsYou = c.actions.filter(a => ['reviewed', 'blocked', 'proposed'].includes(a.status) || (a.status === 'approved' && a.kind !== 'send_email'));
  const draft = c.artifacts.filter(a => a.kind === 'draft').at(-1);
  const noRecipient = draft && !draft.content?.to;

  return (
    <div className="jd-page jd-thread">
      <header className="jd-case-head">
        <div>
          <p className="jd-meta"><Link to="/cases">Cases</Link></p>
          <h1>{c.company}</h1>
          <p className="jd-lede">{c.role}{c.source_url && <> <a href={c.source_url} target="_blank" rel="noreferrer" className="jd-inline-link">posting <ExternalLink size={12} /></a></>}</p>
        </div>
        <label className="jd-stage">Stage
          <select value={c.stage} onChange={e => stage.mutate({ id: c.id, stage: e.target.value })} disabled={stage.isPending}>
            {STAGES.map(s => <option key={s} value={s}>{STAGE_WORDS[s]}</option>)}
          </select>
        </label>
      </header>

      <div className="jd-columns">
        <div>
          {needsYou.length > 0 && <section aria-labelledby="case-needs"><h2 id="case-needs">Needs you on this case</h2>
            {needsYou.map(a => <ApprovalCard key={a.id} action={a} company={c.company} />)}</section>}

          {noRecipient && <section className="jd-card jd-recipient" aria-labelledby="who">
            <h2 id="who">Who should the email go to?</h2>
            <p className="jd-meta">Recon found no address it could confirm. Add the recruiter's email and Email Outreach drafts it again for your approval.</p>
            <div className="jd-ask-row">
              <input className="jd-input" placeholder="Name" aria-label="Recipient name" value={to.name} onChange={e => setTo({ ...to, name: e.target.value })} />
              <input className="jd-input" placeholder="name@company.com" aria-label="Recipient email" type="email" value={to.email} onChange={e => setTo({ ...to, email: e.target.value })} />
              <button className="jd-btn jd-primary" disabled={!to.email.includes('@') || recipient.isPending}
                      onClick={() => recipient.mutate({ caseId: c.id, ...to })}>Add and redraft</button>
            </div>
            {recipient.error && <p className="jd-note jd-warn">{(recipient.error as Error).message}</p>}
          </section>}

          <section aria-labelledby="timeline"><h2 id="timeline">What happened</h2>
            <ol className="jd-timeline">{items.map((it, i) => <li key={i} className={it.artifact ? 'jd-tl-card' : 'jd-tl-event'}>
              {it.artifact ? <ArtifactCard a={it.artifact} caseId={c.id} /> : <EventLine e={it.event!} />}
            </li>)}</ol>
          </section>
        </div>

        <aside>
          <h2>Ask an expert again</h2>
          <div className="jd-stack">{RERUN.map(([label, expert]) =>
            <button key={expert} className="jd-btn" disabled={rerun.isPending} onClick={() => rerun.mutate({ caseId: c.id, expert })}>{label}</button>)}</div>
          {rerun.isSuccess && <p className="jd-meta">Queued. The expert's avatar shows when it starts.</p>}
          {rerun.error && <p className="jd-note jd-warn">{(rerun.error as Error).message}</p>}
          <h2>Job description</h2>
          <button className="jd-link" onClick={() => setShowJd(!showJd)}>{showJd ? 'Hide it' : 'Show it'}</button>
          {showJd && <p className="jd-body jd-jd">{c.jd_text}</p>}
          {c.applied_at && <p className="jd-meta">Applied {new Date(c.applied_at).toLocaleDateString()}</p>}
        </aside>
      </div>
    </div>
  );
}

function EventLine({ e }: { e: CaseEvent }) {
  const who = e.actor === 'user' ? 'You' : expertName(e.actor_name || e.actor);
  return (
    <div className="jd-event">
      {e.actor === 'agent' ? <ExpertAvatar expert={e.actor_name} name={who} size={20} /> : <span className="jd-dot" aria-hidden="true" />}
      <p>{e.kind === 'stage_changed' ? `${who === 'You' ? 'You moved' : 'Moved'} the case to ${(STAGE_WORDS[String(e.data?.to)] ?? String(e.data?.to ?? '')).toLowerCase()}`
          : e.summary || e.kind.replace(/_/g, ' ')}<span className="jd-meta"> {when(e.at)}</span></p>
    </div>
  );
}
