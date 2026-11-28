// JobDots — custom experts (Day 14): pick a template, write the instructions, see the policy
// preview, run it dry on a real case, then activate it. Edits put it back to draft.
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import api from '../../lib/api';
import { useCases } from '../../jobdots/api';
import { Chip } from '../../jobdots/cards';

interface View {
  spec: { id: string; name: string; role: string; description: string; instructions: string; tools: string[]; status: string };
  problems: string[];
  preview: { can: string[]; never: string[]; limits: string[] };
  dry_run_ok_at: string | null;
}
interface Templates { templates: { id: string; name: string; role: string; description: string }[]; tools: Record<string, string> }

export function NewExpert() {
  const navigate = useNavigate();
  const t = useQuery({ queryKey: ['jd', 'templates'], queryFn: () => api.get<Templates>('/experts/custom/templates') });
  const create = useMutation({ mutationFn: (template: string | null) => api.post<View>('/experts/custom', { template }),
                               onSuccess: v => navigate(`/experts/${v.spec.id}`) });
  return (
    <div className="jd-page">
      <header className="jd-page-head"><h1>Add an expert</h1>
        <p className="jd-lede">Start from a template or from blank. A custom expert reads the case and public pages and writes one note. It can never send anything.</p></header>
      <ul className="jd-list">
        {(t.data?.templates ?? []).map(x => <li key={x.id}>
          <div><strong>{x.name}</strong><span className="jd-meta">{x.description}</span></div>
          <button className="jd-btn" disabled={create.isPending} onClick={() => create.mutate(x.id)}>Use this</button>
        </li>)}
        <li><div><strong>Blank</strong><span className="jd-meta">Write it yourself.</span></div>
          <button className="jd-btn" disabled={create.isPending} onClick={() => create.mutate(null)}>Start blank</button></li>
      </ul>
      {create.error && <p className="jd-note jd-warn">{(create.error as Error).message}</p>}
    </div>
  );
}

export function CustomEditor({ id }: { id: string }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const view = useQuery({ queryKey: ['jd', 'custom', id], queryFn: () => api.get<View>(`/experts/custom/${id}`) });
  const tools = useQuery({ queryKey: ['jd', 'templates'], queryFn: () => api.get<Templates>('/experts/custom/templates') });
  const cases = useCases();
  const [form, setForm] = useState({ name: '', role: '', description: '', instructions: '', tools: [] as string[] });
  const [caseId, setCaseId] = useState('');
  const [dry, setDry] = useState<{ note: { title: string; body: string; checks: string[]; sources: { n: number; url: string; title: string }[] } } | null>(null);
  useEffect(() => { if (view.data) { const s = view.data.spec; setForm({ name: s.name, role: s.role, description: s.description, instructions: s.instructions, tools: s.tools }); } }, [view.data]);
  const refresh = () => qc.invalidateQueries({ queryKey: ['jd'] });
  const save = useMutation({ mutationFn: () => api.put<View>(`/experts/custom/${id}`, form), onSuccess: () => { setDry(null); refresh(); } });
  const run = useMutation({ mutationFn: () => api.post<any>(`/experts/custom/${id}/dry-run`, { case_id: caseId }), onSuccess: r => { setDry(r); refresh(); } });
  const activate = useMutation({ mutationFn: () => api.post(`/experts/custom/${id}/activate`), onSuccess: refresh });
  const pause = useMutation({ mutationFn: () => api.post(`/experts/custom/${id}/pause`), onSuccess: refresh });
  const remove = useMutation({ mutationFn: () => api.delete(`/experts/custom/${id}`), onSuccess: () => { refresh(); navigate('/'); } });
  if (!view.data) return <p className="jd-meta">Loading…</p>;
  const v = view.data;
  const changed = JSON.stringify(form) !== JSON.stringify({ name: v.spec.name, role: v.spec.role, description: v.spec.description, instructions: v.spec.instructions, tools: v.spec.tools });
  const open = (cases.data ?? []).filter(c => !c.legacy).slice(0, 30);
  const err = (save.error || run.error || activate.error || pause.error) as Error | null;
  return (
    <section className="jd-custom" aria-labelledby="edit-title">
      <h2 id="edit-title">Your expert <Chip tone={v.spec.status === 'active' ? 'ok' : v.spec.status === 'paused' ? 'quiet' : 'draft'}>
        {v.spec.status === 'active' ? 'Active' : v.spec.status === 'paused' ? 'Paused' : 'Draft'}</Chip></h2>
      <label className="jd-field">Name<input className="jd-input" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></label>
      <label className="jd-field">One line for the roster<input className="jd-input" value={form.role} onChange={e => setForm({ ...form, role: e.target.value })} /></label>
      <label className="jd-field">Instructions<textarea className="jd-textarea" rows={8} value={form.instructions} onChange={e => setForm({ ...form, instructions: e.target.value })} /></label>
      <fieldset className="jd-field"><legend>What it may use</legend>
        {Object.entries(tools.data?.tools ?? {}).map(([t, words]) => <label key={t} className="jd-check">
          <input type="checkbox" checked={form.tools.includes(t)} onChange={e => setForm({ ...form, tools: e.target.checked ? [...form.tools, t] : form.tools.filter(x => x !== t) })} /> {words}</label>)}
      </fieldset>
      {changed && <div className="jd-actions"><button className="jd-btn jd-primary" disabled={save.isPending} onClick={() => save.mutate()}>Save (back to draft)</button></div>}

      <h3>Policy preview</h3>
      <div className="jd-columns jd-preview">
        <div><p className="jd-meta">It can</p><ul className="jd-claims">{v.preview.can.map(x => <li key={x}>{x}</li>)}</ul></div>
        <div><p className="jd-meta">It can never</p><ul className="jd-claims">{v.preview.never.map(x => <li key={x}>{x}</li>)}</ul></div>
      </div>
      <p className="jd-meta">{v.preview.limits.join('. ')}.</p>
      {v.problems.length > 0 && <p className="jd-note jd-warn">Before it can run: {v.problems.join(' ')}</p>}

      <h3>Test run (dry)</h3>
      <p className="jd-meta">Runs it on a real case and shows what it would write. Nothing is saved on the case.</p>
      <div className="jd-ask-row">
        <select className="jd-input" value={caseId} onChange={e => setCaseId(e.target.value)} aria-label="Case for the dry run">
          <option value="">Choose a case</option>{open.map(c => <option key={c.id} value={c.id}>{c.company}: {c.role}</option>)}</select>
        <button className="jd-btn" disabled={!caseId || run.isPending || changed || v.problems.length > 0} onClick={() => run.mutate()}>
          {run.isPending ? 'Running it dry…' : 'Run it dry'}</button>
      </div>
      {dry && <article className="jd-card"><strong>{dry.note.title}</strong><p className="jd-body">{dry.note.body}</p>
        {dry.note.checks.map(c => <p key={c} className="jd-note jd-warn">{c}</p>)}
        {dry.note.sources.length > 0 && <ol className="jd-sources">{dry.note.sources.map(s => <li key={s.n}><a href={s.url} target="_blank" rel="noreferrer">{s.title || s.url}</a></li>)}</ol>}</article>}

      <div className="jd-actions">
        {v.spec.status !== 'active' && <button className="jd-btn jd-primary" disabled={!v.dry_run_ok_at || changed || v.problems.length > 0 || activate.isPending}
          onClick={() => activate.mutate()}>Activate</button>}
        {v.spec.status === 'active' && <button className="jd-btn" disabled={pause.isPending} onClick={() => pause.mutate()}>Pause</button>}
        <button className="jd-btn" disabled={remove.isPending} onClick={() => { if (confirm(`Delete ${v.spec.name}?`)) remove.mutate(); }}>Delete</button>
      </div>
      {!v.dry_run_ok_at && v.spec.status !== 'active' && <p className="jd-meta">Run it dry once before you activate it.</p>}
      {err && <p className="jd-note jd-warn" role="alert">{err.message}</p>}
    </section>
  );
}
