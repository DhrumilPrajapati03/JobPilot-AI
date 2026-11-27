// JobDots — every case, newest first; imported JobPilot applications behind a toggle.
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useCases } from '../../jobdots/api';
import { Chip, STAGE_WORDS, when } from '../../jobdots/cards';

const FILTERS: [string, string, (stage: string, status: string) => boolean][] = [
  ['open', 'Open', (_s, status) => status === 'open'],
  ['applied', 'Applied and after', s => ['applied', 'replied', 'interview', 'offer'].includes(s)],
  ['all', 'All', () => true],
];

export default function Cases() {
  const cases = useCases();
  const [filter, setFilter] = useState('open');
  const [imported, setImported] = useState(false);
  const test = FILTERS.find(f => f[0] === filter)![2];
  const rows = (cases.data ?? []).filter(c => (imported || !c.legacy) && test(c.stage, c.status));
  return (
    <div className="jd-page">
      <header className="jd-page-head"><h1>Cases</h1>
        <div className="jd-filters" role="group" aria-label="Show">
          {FILTERS.map(([id, label]) => <button key={id} className={`jd-btn${filter === id ? ' jd-on' : ''}`} aria-pressed={filter === id} onClick={() => setFilter(id)}>{label}</button>)}
          <label className="jd-check"><input type="checkbox" checked={imported} onChange={e => setImported(e.target.checked)} /> Imported from JobPilot</label>
        </div>
      </header>
      {cases.isLoading ? <p className="jd-meta">Loading cases…</p> : rows.length === 0 ? <p className="jd-empty">No cases here.</p> :
        <table className="jd-table jd-cases"><thead><tr><th>Company</th><th>Role</th><th>Stage</th><th>Updated</th></tr></thead><tbody>
          {rows.map(c => <tr key={c.id}>
            <td><Link to={`/cases/${c.id}`}>{c.company || 'Unknown company'}</Link>{c.legacy && <span className="jd-meta"> imported</span>}</td>
            <td>{c.role}</td>
            <td><Chip tone={['applied', 'replied', 'interview', 'offer'].includes(c.stage) ? 'ok' : c.stage === 'closed' ? 'quiet' : 'waiting'}>{STAGE_WORDS[c.stage] ?? c.stage}</Chip></td>
            <td>{when(c.updated_at)}</td>
          </tr>)}</tbody></table>}
    </div>
  );
}
