// JobDots — answer bank: your approved form answers, their versions, and delete.
import { useState } from 'react';
import { useAnswerBank, useAnswerHistory, useBankMutations } from '../../jobdots/api';
import { Chip, when } from '../../jobdots/cards';

const SOURCE: Record<string, string> = { legacy: 'Imported', vault: 'From your vault', reused: 'Reused', adapted: 'Adapted', generated: 'Drafted', user: 'Yours' };

export default function AnswerBank() {
  const [q, setQ] = useState('');
  const [open, setOpen] = useState<string | null>(null);
  const bank = useAnswerBank(q);
  const history = useAnswerHistory(open);
  const { remove } = useBankMutations();
  return (
    <div className="jd-page">
      <header className="jd-page-head"><h1>Answer bank</h1>
        <p className="jd-lede">Answers you approved in the side panel. The Answerer reuses one when a new form asks the same thing, and adapts it when the question is close.</p>
        <input className="jd-input" placeholder="Search questions and answers" aria-label="Search the answer bank" value={q} onChange={e => setQ(e.target.value)} />
      </header>
      {bank.isLoading ? <p className="jd-meta">Loading answers…</p> : !bank.data?.length ? <p className="jd-empty">No saved answers yet. Fill a form from the side panel and your answers land here.</p> :
        <ul className="jd-bank">{bank.data.map(a => <li key={a.id}>
          <div className="jd-bank-q"><strong>{a.question}</strong>
            <span><Chip tone={a.source === 'user' ? 'ok' : 'quiet'}>{SOURCE[a.source] ?? a.source}</Chip>{a.company_scope && <Chip tone="draft">Only for {a.company_scope}</Chip>}{a.sensitive && <Chip tone="warn">Sensitive</Chip>}</span></div>
          <p className="jd-body">{a.answer}</p>
          <div className="jd-actions">
            {a.version > 1 && <button className="jd-btn" onClick={() => setOpen(open === a.id ? null : a.id)}>{open === a.id ? 'Hide versions' : `${a.version} versions`}</button>}
            <button className="jd-btn" disabled={remove.isPending} onClick={() => { if (confirm('Delete this answer and all its versions?')) remove.mutate(a.id); }}>Delete</button>
          </div>
          {open === a.id && <ol className="jd-versions">{(history.data ?? []).map(v => <li key={v.id}><span className="jd-meta">Version {v.version}, {SOURCE[v.source] ?? v.source}, {when(v.created_at)}</span><p>{v.answer}</p></li>)}</ol>}
        </li>)}</ul>}
    </div>
  );
}
