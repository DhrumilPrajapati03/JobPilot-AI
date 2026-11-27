// JobDots — one expert: who it is, what it may do, its routines and its recent steps.
import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import api from '../../lib/api';
import { ExpertAvatar } from '../../components/experts/ExpertAvatar';
import { useRoster } from '../../jobdots/api';
import { Chip, when } from '../../jobdots/cards';

interface Detail {
  spec: { id: string; name: string; role: string; description: string; policy_notes: string; status: string; tools: string[]; action_kinds: string[] };
  routines: { key: string; name: string; schedule: { kind: string; hour?: number; minute?: number; weekday?: number }; enabled: boolean; last_run_at: string | null }[];
  steps: { id: number; kind: string; summary: string; case_id: string | null; at: string }[];
}

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
function schedule(s: Detail['routines'][number]['schedule']) {
  const at = `${String(s.hour ?? 0).padStart(2, '0')}:${String(s.minute ?? 0).padStart(2, '0')}`;
  return s.kind === 'daily' ? `every day at ${at}` : s.kind === 'weekly' ? `every ${DAYS[s.weekday ?? 0]} at ${at}` : s.kind;
}

export default function ExpertPage() {
  const { id = '' } = useParams();
  const detail = useQuery({ queryKey: ['jd', 'expert', id], queryFn: () => api.get<Detail>(`/experts/${id}`), refetchInterval: 5000 });
  const live = (useRoster().data ?? []).find(e => e.id === id);
  if (detail.isLoading) return <div className="jd-page"><p className="jd-meta">Loading…</p></div>;
  if (!detail.data) return <div className="jd-page"><p className="jd-empty">Unknown expert.</p></div>;
  const { spec, routines, steps } = detail.data;
  return (
    <div className="jd-page">
      <header className="jd-expert-head">
        <ExpertAvatar expert={spec.id} name={spec.name} state={live?.state} step={live?.step} approvals={live?.approvals} size={72} interactive />
        <div><h1>{spec.name}</h1><p className="jd-lede">{spec.role}</p>
          {spec.status !== 'active' && <Chip tone="quiet">{spec.status === 'draft' ? 'Not built yet' : 'Paused'}</Chip>}</div>
      </header>
      {spec.description && <p>{spec.description}</p>}
      {spec.policy_notes && <p className="jd-meta">{spec.policy_notes}</p>}
      {routines.length > 0 && <section><h2>Routines</h2><ul className="jd-list">{routines.map(r => <li key={r.key}>
        <span>{r.name} <span className="jd-meta">{schedule(r.schedule)}</span></span>
        <Chip tone={r.enabled ? 'ok' : 'quiet'}>{!r.enabled ? 'Paused' : r.last_run_at ? `Ran ${when(r.last_run_at)}` : 'Scheduled'}</Chip></li>)}</ul></section>}
      <section><h2>Recent steps</h2>
        {steps.length === 0 ? <p className="jd-empty">Nothing yet.</p> :
          <ol className="jd-timeline">{steps.map(s => <li key={s.id} className="jd-tl-event"><div className="jd-event">
            <span className="jd-dot" data-kind={s.kind} aria-hidden="true" />
            <p>{s.summary}{s.case_id && <> <Link to={`/cases/${s.case_id}`} className="jd-link">case</Link></>}<span className="jd-meta"> {when(s.at)}</span></p>
          </div></li>)}</ol>}
      </section>
    </div>
  );
}
