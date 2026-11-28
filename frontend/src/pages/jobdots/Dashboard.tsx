// JobDots — Pipeline and Live Ops on one page: how the search is going, and whether the
// machinery is healthy (queue, failures, spend, sends against caps, kill switch).
import { Link } from 'react-router-dom';
import { useDashboard, useHealth } from '../../jobdots/api';
import { Chip, expertName, when } from '../../jobdots/cards';

const STEPS: [string, string][] = [['found', 'Found'], ['tailored', 'Tailored'], ['applied', 'Applied'], ['replied', 'Replied'], ['interviews', 'Interviews']];

function Meter({ label, used, cap, unit = '' }: { label: string; used: number; cap: number | null; unit?: string }) {
  const share = cap ? Math.min(used / cap, 1) : 0;
  return <div className="jd-meter"><div><span>{label}</span><strong>{unit}{used}{cap != null ? ` of ${unit}${cap}` : ''}</strong></div>
    <span className="jd-meter-track" aria-hidden="true"><span style={{ width: `${share * 100}%` }} data-full={share >= 1 || undefined} /></span></div>;
}

export default function Dashboard() {
  const d = useDashboard();
  const health = useHealth();
  if (d.isLoading) return <div className="jd-page"><p className="jd-meta">Loading the numbers…</p></div>;
  if (!d.data) return <div className="jd-page"><p className="jd-empty">The dashboard couldn't load. Is the API running?</p></div>;
  const { pipeline, ops, approvals } = d.data;
  const runs = ops.runs_last_day;
  return (
    <div className="jd-page">
      <header className="jd-page-head"><h1>Dashboard</h1></header>

      <section aria-labelledby="pipe"><h2 id="pipe">Pipeline</h2>
        <table className="jd-table jd-funnel"><thead><tr><th></th>{STEPS.map(([, w]) => <th key={w}>{w}</th>)}</tr></thead><tbody>
          <tr><th scope="row">This week</th>{STEPS.map(([k]) => <td key={k}>{pipeline.week[k as keyof typeof pipeline.week]}</td>)}</tr>
          <tr><th scope="row">All time</th>{STEPS.map(([k]) => <td key={k}>{pipeline.all_time[k as keyof typeof pipeline.all_time]}</td>)}</tr>
        </tbody></table>
        <p className="jd-meta">All time includes {pipeline.all_time.imported} applications imported from JobPilot. Replies and interviews are counted from case stages until Inbox reads your mail.</p>
      </section>

      <section aria-labelledby="health"><h2 id="health">Health {health.data && <Chip tone={health.data.status === 'ok' ? 'ok' : 'warn'}>
        {health.data.status === 'ok' ? 'Everything works' : health.data.status === 'warn' ? 'Needs a look' : 'Something is down'}</Chip>}</h2>
        {health.data ? <ul className="jd-list">{health.data.checks.map(c => <li key={c.name}>
          <span><strong>{c.name}</strong> <span className="jd-meta">{c.detail}</span></span>
          <Chip tone={c.status === 'ok' ? 'ok' : 'warn'}>{c.status === 'ok' ? 'OK' : c.status === 'warn' ? 'Check' : 'Down'}</Chip></li>)}</ul>
          : <p className="jd-meta">Checking…</p>}
      </section>

      <section aria-labelledby="ops"><h2 id="ops">Live Ops</h2>
        <p>{ops.kill_switch ? <Chip tone="warn">Kill switch on: nothing is sent</Chip> : <Chip tone="ok">Sending allowed</Chip>}
          {ops.quiet_hours && <> <Chip tone="quiet">Quiet hours: sends wait until morning</Chip></>}
          {approvals.total > 0 && <> <Link to="/approvals"><Chip tone="waiting">{approvals.total} waiting for your approval</Chip></Link></>}</p>
        <div className="jd-meters">
          <Meter label="Emails sent today" used={ops.sent_today.emails[0]} cap={ops.sent_today.emails[1]} />
          <Meter label="LinkedIn invitations today" used={ops.sent_today.invites[0]} cap={ops.sent_today.invites[1]} />
          <Meter label="LinkedIn messages today" used={ops.sent_today.dms[0]} cap={ops.sent_today.dms[1]} />
          {ops.budget && <Meter label="Model spend this month" unit="$" used={Number(ops.budget.usd_used.toFixed(2))} cap={ops.budget.usd_limit} />}
        </div>
        <p className="jd-meta">Last 24 hours: {runs.succeeded ?? 0} runs finished, {runs.failed ?? 0} failed, {(runs.queued ?? 0) + (runs.running ?? 0) + (runs.retry_wait ?? 0)} waiting or running.</p>

        <h3>Working now</h3>
        {ops.active.length === 0 ? <p className="jd-empty">The worker is idle.</p> :
          <ul className="jd-list">{ops.active.map(r => <li key={r.id}><span>{expertName(r.agent)}{r.case_id && <> on <Link to={`/cases/${r.case_id}`}>a case</Link></>}</span>
            <Chip tone="waiting">{r.status === 'running' ? 'Working' : r.status === 'retry_wait' ? `Retrying (attempt ${r.attempts})` : 'Queued'}</Chip></li>)}</ul>}

        <h3>Failed in the last day</h3>
        {ops.failed.length === 0 ? <p className="jd-empty">Nothing failed.</p> :
          <ul className="jd-list jd-failures">{ops.failed.map(r => <li key={r.id}>
            <div><strong>{expertName(r.agent)}</strong>{r.company && <> on {r.case_id ? <Link to={`/cases/${r.case_id}`}>{r.company}</Link> : r.company}</>}<span className="jd-meta"> {when(r.updated_at)}</span>
              <p className="jd-note jd-warn">{r.error || 'No reason recorded.'}</p></div>
          </li>)}</ul>}
      </section>
    </div>
  );
}
