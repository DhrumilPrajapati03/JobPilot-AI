// JobDots — command center: tell Supervisor what you want, see what needs you, and what the
// experts are doing. The primary action is delegation, not "new chat".
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ExpertAvatar } from '../../components/experts/ExpertAvatar';
import { useCaseMutations, useCases, usePending, useRoster } from '../../jobdots/api';
import { ApprovalDeck, Chip, STAGE_WORDS, when } from '../../jobdots/cards';

const KIND_ORDER = ['create_calendar_event', 'send_email', 'send_linkedin_invite', 'send_linkedin_dm', 'referral_request'];

export default function Command() {
  const navigate = useNavigate();
  const roster = useRoster();
  const pending = usePending();
  const cases = useCases();
  const { quick } = useCaseMutations();
  const [jd, setJd] = useState('');
  const [url, setUrl] = useState('');

  const waiting = (pending.data ?? []).filter(a => a.status === 'reviewed' || a.status === 'blocked');
  const byKind = KIND_ORDER.map(k => waiting.filter(a => a.kind === k)).filter(list => list.length);
  const open = (cases.data ?? []).filter(c => !c.legacy && c.status === 'open').slice(0, 8);
  const busy = (roster.data ?? []).filter(e => e.step && e.status === 'active')
    .sort((a, b) => (b.step_at ?? '').localeCompare(a.step_at ?? '')).slice(0, 8);

  const start = () => quick.mutate({ jd_text: jd.trim(), ...(url.trim() ? { source_url: url.trim() } : {}) },
    { onSuccess: r => navigate(`/cases/${r.case_id}`) });

  return (
    <div className="jd-page">
      <section className="jd-ask" aria-labelledby="ask-title">
        <h1 id="ask-title">What should Supervisor work on?</h1>
        <p className="jd-lede">Paste a job description. Supervisor opens a case and runs the experts: company brief, people, tailored resume, then drafts for your approval.</p>
        <textarea className="jd-textarea" rows={5} value={jd} onChange={e => setJd(e.target.value)} placeholder="Paste the job description here" aria-label="Job description" />
        <div className="jd-ask-row">
          <input className="jd-input" value={url} onChange={e => setUrl(e.target.value)} placeholder="Link to the posting (optional)" aria-label="Link to the posting" />
          <button className="jd-btn jd-primary" disabled={jd.trim().length < 200 || quick.isPending} onClick={start}>
            {quick.isPending ? 'Opening the case…' : 'Hand it to Supervisor'}</button>
        </div>
        {jd.trim().length > 0 && jd.trim().length < 200 && <p className="jd-meta">Paste the whole description; it needs at least 200 characters.</p>}
        {quick.error && <p className="jd-note jd-warn" role="alert">{(quick.error as Error).message}</p>}
      </section>

      <div className="jd-columns">
        <section aria-labelledby="needs-title">
          <h2 id="needs-title">Needs you {waiting.length > 0 && <Chip tone="waiting">{waiting.length}</Chip>}</h2>
          {pending.isLoading ? <p className="jd-meta">Checking for drafts…</p>
            : byKind.length === 0 ? <p className="jd-empty">Nothing to approve. Drafts from the experts land here and in Telegram.</p>
            : byKind.map(list => <ApprovalDeck key={list[0].kind} actions={list} showCase />)}
        </section>

        <aside>
          <h2>Cases in motion</h2>
          {open.length === 0 ? <p className="jd-empty">No open cases. Paste a job description above, or capture one with the side panel.</p> :
            <ul className="jd-list">{open.map(c => <li key={c.id}>
              <Link to={`/cases/${c.id}`}><strong>{c.company}</strong><span>{c.role}</span></Link>
              <Chip tone={c.stage === 'applied' ? 'ok' : 'quiet'}>{STAGE_WORDS[c.stage] ?? c.stage}</Chip>
            </li>)}</ul>}
          <p><Link to="/cases" className="jd-link">All cases</Link></p>

          <h2>What the experts did last</h2>
          <ul className="jd-activity">{busy.map(e => <li key={e.id}>
            <ExpertAvatar expert={e.id} name={e.name} state={e.state} step={e.step} size={24} />
            <p><Link to={`/experts/${e.id}`}><strong>{e.name}</strong></Link> {e.step}<span className="jd-meta"> {when(e.step_at)}</span></p>
          </li>)}</ul>
        </aside>
      </div>
    </div>
  );
}
