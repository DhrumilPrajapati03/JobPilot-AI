// ============================================================
// JobPilot — Agent activity: tool steps + result cards
// ============================================================

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  Circle,
  ExternalLink,
  FileText,
  FolderKanban,
  Loader2,
  PanelRight,
  Search,
  Sparkles,
  X,
} from 'lucide-react';
import api from '../../lib/api';
import { cn } from '@/lib/utils';
import { Button } from '../ui/button';
import { ScoreRing, StatusBadge, formatDate, scoreColor } from '../applications/shared';
import { PIPELINE_STEPS, useAgentStream } from '../../hooks/use-agent-stream';
import { useChatStore, type StageView, type ToolPart } from '../../agent/store';
import type { ApplicationStatus } from '../../hooks/use-applications';
import type { SkillGaps } from '../../hooks/use-analytics';
import { SkillGapsView } from '../applications/SkillGaps';

type Result = Record<string, any>;

export const VIEW_LABEL: Record<StageView, string> = {
  applications: 'Applications',
  detail: 'Application',
  analytics: 'Analytics',
  new: 'New application',
  profile: 'Profile',
  feed: 'Job feed',
  network: 'Network',
  queue: 'Apply queue',
};

function useOpen() {
  return useChatStore((s) => s.openStage);
}

// --- Step rows -----------------------------------------------------------------------

function stepLabel(part: ToolPart): string {
  const r = (part.result ?? {}) as Result;
  const running = part.status === 'running';
  switch (part.name) {
    case 'get_overview':
      return running ? 'Checking your overview' : 'Checked your overview';
    case 'list_applications':
      return running ? 'Reading your applications' : `Read ${r.applications?.length ?? 0} application${r.applications?.length === 1 ? '' : 's'}`;
    case 'get_application':
      return running ? 'Reading the application' : `Read ${r.role ?? 'application'}${r.company ? ` at ${r.company}` : ''}`;
    case 'get_base_resume':
      return running ? 'Reading your base resume' : r.exists === false ? 'No base resume found' : 'Read your base resume';
    case 'create_application':
      return running ? 'Starting the application pipeline' : 'Started the application pipeline';
    case 'get_skill_gaps':
      return running ? 'Analysing skill gaps' : `Analysed skill gaps across ${r.applications_analyzed ?? 0} applications`;
    case 'get_job_preferences':
      return running ? 'Reading your job preferences' : 'Read your job preferences';
    case 'get_saved_answers':
      return running ? 'Reading your saved answers' : `Read ${r.answers?.length ?? 0} saved answers`;
    case 'propose_status_change':
    case 'propose_email_draft':
    case 'propose_cover_letter':
      return running ? 'Preparing a change' : 'Prepared a change for your approval';
    case 'propose_resume_edit':
      return running ? 'Drafting resume edits' : 'Drafted resume edits for your approval';
    case 'get_briefing':
      return running ? 'Preparing your briefing' : 'Prepared your briefing';
    case 'get_job_feed':
      return running ? 'Reading your job feed' : `Found ${r.total ?? 0} open match${r.total === 1 ? '' : 'es'} in your feed`;
    case 'draft_job':
      return running ? 'Starting a draft' : 'Started drafting the application';
    case 'find_referrals':
      return running ? 'Checking who you know' : `Found ${r.total ?? 0} ${r.total === 1 ? 'person' : 'people'} you know at ${r.company ?? 'the company'}`;
    case 'propose_referral_request':
      return running ? 'Drafting a referral request' : 'Drafted a referral request for your approval';
    case 'scan_jobs':
      return running ? 'Scanning your job boards' : `Scanned ${r.sources ?? 0} board${r.sources === 1 ? '' : 's'}: ${r.new ?? 0} new match${r.new === 1 ? '' : 'es'}`;
    case 'open_view':
      return running ? 'Opening the workspace' : `Opened ${VIEW_LABEL[r.opened as StageView] ?? 'a view'} in the workspace`;
    default:
      return part.name;
  }
}

function StepIcon({ part }: { part: ToolPart }) {
  const r = part.result as Result | undefined;
  if (part.status === 'running') return <Loader2 size={14} className="animate-spin text-muted-foreground" />;
  if (r?.error) return <AlertCircle size={14} className="text-destructive" />;
  if (part.name === 'open_view') return <PanelRight size={14} className="text-muted-foreground" />;
  if (part.name === 'create_application' || part.name === 'draft_job') return <Sparkles size={14} className="text-accent" />;
  if (part.name.startsWith('propose_')) return <FileText size={14} className="text-muted-foreground" />;
  return <Search size={14} className="text-muted-foreground" />;
}

function StepRow({ part }: { part: ToolPart }) {
  const r = part.result as Result | undefined;
  const open = useOpen();
  return (
    <li className="flex items-start gap-2.5 py-1">
      <span className="mt-0.5 shrink-0">
        <StepIcon part={part} />
      </span>
      <span className="min-w-0 flex-1 text-[13px] text-muted-foreground">
        {r?.error ? <span className="text-destructive">{String(r.error)}</span> : stepLabel(part)}
      </span>
      {part.name === 'open_view' && r?.opened && (
        <button
          type="button"
          onClick={() => open({ view: r.opened, applicationId: r.application_id || undefined, tab: r.tab || undefined })}
          className="shrink-0 text-xs font-medium text-foreground underline-offset-2 hover:underline"
        >
          Show
        </button>
      )}
    </li>
  );
}

/** A run of consecutive tool calls, collapsible once finished. */
export function ActivityGroup({ parts }: { parts: ToolPart[] }) {
  const running = parts.some((p) => p.status === 'running');
  const failed = parts.filter((p) => (p.result as Result | undefined)?.error).length;
  const [expanded, setExpanded] = useState(false);
  const isOpen = running || expanded;

  return (
    <div className="rounded-lg border bg-card/60">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px]"
        aria-expanded={isOpen}
      >
        {running ? (
          <Loader2 size={14} className="animate-spin text-muted-foreground" />
        ) : failed ? (
          <AlertCircle size={14} className="text-destructive" />
        ) : (
          <CheckCircle2 size={14} className="text-accent" />
        )}
        <span className="flex-1 font-medium">
          {running ? stepLabel(parts.find((p) => p.status === 'running')!) + '…' : `Used ${parts.length} tool${parts.length > 1 ? 's' : ''}`}
          {failed > 0 && !running && <span className="font-normal text-destructive"> · {failed} failed</span>}
        </span>
        {!running && <ChevronDown size={14} className={cn('text-muted-foreground transition-transform', isOpen && 'rotate-180')} />}
      </button>
      {isOpen && (
        <ul className="border-t px-3 py-1.5">
          {parts.map((p) => (
            <StepRow key={p.id} part={p} />
          ))}
        </ul>
      )}
    </div>
  );
}

// --- Result cards -----------------------------------------------------------------------

function Shell({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('rounded-lg border bg-card', className)}>{children}</div>;
}

function OverviewCard({ r }: { r: Result }) {
  const tiles: [string, string][] = [
    ['Applications', String(r.total_applications ?? 0)],
    ['Response rate', r.submitted ? `${r.response_rate}%` : '—'],
    ['Avg match', r.avg_keyword_score === null || r.avg_keyword_score === undefined ? '—' : `${r.avg_keyword_score}%`],
    ['Follow-ups due', String(r.pending_follow_ups ?? 0)],
  ];
  return (
    <Shell className="grid grid-cols-2 divide-x divide-y sm:grid-cols-4 sm:divide-y-0">
      {tiles.map(([label, value]) => (
        <div key={label} className="px-3 py-2.5">
          <p className="text-[11px] text-muted-foreground">{label}</p>
          <p className="text-lg font-semibold tabular-nums">{value}</p>
        </div>
      ))}
    </Shell>
  );
}

function ApplicationsCard({ r }: { r: Result }) {
  const open = useOpen();
  const apps = (r.applications ?? []) as Result[];
  if (!apps.length) return null;
  return (
    <Shell className="overflow-hidden">
      <ul className="divide-y">
        {apps.slice(0, 6).map((a) => (
          <li key={a.id}>
            <button
              type="button"
              onClick={() => open({ view: 'detail', applicationId: a.id })}
              className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-secondary/60"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{a.role}</span>
                <span className="block truncate text-xs text-muted-foreground">
                  {a.company}
                  {a.follow_up_at && a.status === 'applied' ? ` · follow up ${formatDate(a.follow_up_at)}` : ''}
                </span>
              </span>
              {a.status && <StatusBadge status={a.status as ApplicationStatus} className="shrink-0" />}
              <span className="w-10 shrink-0 text-right text-sm font-semibold tabular-nums" style={{ color: scoreColor(a.match_score) }}>
                {a.match_score === null || a.match_score === undefined ? '—' : `${Math.round(a.match_score)}%`}
              </span>
            </button>
          </li>
        ))}
      </ul>
      <div className="flex items-center justify-between border-t bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground">
        <span>
          {Math.min(apps.length, 6)} of {r.total ?? apps.length}
        </span>
        <button type="button" onClick={() => open({ view: 'applications' })} className="inline-flex items-center gap-1 font-medium text-foreground hover:underline">
          <FolderKanban size={12} />
          Open all
        </button>
      </div>
    </Shell>
  );
}

function PostingsCard({ postings, total }: { postings: Result[]; total?: number }) {
  const open = useOpen();
  if (!postings.length) return null;
  return (
    <Shell className="overflow-hidden">
      <ul className="divide-y">
        {postings.slice(0, 6).map((p) => (
          <li key={p.id} className="flex items-center gap-3 px-3 py-2.5">
            <span className="min-w-0 flex-1">
              <a href={p.url} target="_blank" rel="noreferrer" className="block truncate text-sm font-medium hover:underline">
                {p.title}
              </a>
              <span className="block truncate text-xs text-muted-foreground">
                {p.company}
                {p.remote ? ' · Remote' : p.location ? ` · ${p.location}` : ''}
                {(p.ats === 'himalayas' || p.ats === 'remotive') && ` · via ${p.ats === 'himalayas' ? 'Himalayas' : 'Remotive'}`}
              </span>
            </span>
            <span className="w-10 shrink-0 text-right text-sm font-semibold tabular-nums" style={{ color: scoreColor(p.fit_score) }} title="Fit score">
              {Math.round(Number(p.fit_score ?? 0))}%
            </span>
          </li>
        ))}
      </ul>
      <div className="flex items-center justify-between border-t bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground">
        <span>{total !== undefined ? `${Math.min(postings.length, 6)} of ${total}` : 'Top matches'}</span>
        <button type="button" onClick={() => open({ view: 'feed' })} className="inline-flex items-center gap-1 font-medium text-foreground hover:underline">
          <Search size={12} />
          Open job feed
        </button>
      </div>
    </Shell>
  );
}

function ReferralsCard({ r }: { r: Result }) {
  const open = useOpen();
  const people = (r.contacts ?? []) as Result[];
  if (!people.length) return null;
  return (
    <Shell className="overflow-hidden">
      <ul className="divide-y">
        {people.slice(0, 5).map((p) => (
          <li key={p.id} className="flex items-center gap-3 px-3 py-2.5">
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-secondary text-xs font-semibold">{String(p.full_name ?? '?').charAt(0)}</span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">{p.full_name}</span>
              <span className="block truncate text-xs text-muted-foreground">{p.why ?? [p.position, p.company].filter(Boolean).join(' · ')}</span>
            </span>
            {p.request_status && <span className="shrink-0 rounded-full bg-secondary px-2 py-0.5 text-[11px]">{p.request_status}</span>}
          </li>
        ))}
      </ul>
      <div className="flex items-center justify-between border-t bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground">
        <span>
          {Math.min(people.length, 5)} of {r.total ?? people.length}
        </span>
        <button type="button" onClick={() => open({ view: 'network' })} className="font-medium text-foreground hover:underline">
          Open network
        </button>
      </div>
    </Shell>
  );
}

function ApplicationCard({ r }: { r: Result }) {
  const open = useOpen();
  const missing = (r.missing_keywords ?? []) as string[];
  return (
    <Shell className="flex items-center gap-3 p-3">
      <ScoreRing score={r.match_score} size={52} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{r.role}</p>
        <p className="truncate text-xs text-muted-foreground">
          {r.company}
          {missing.length > 0 && ` · missing ${missing.slice(0, 3).join(', ')}`}
        </p>
      </div>
      <Button size="sm" variant="outline" onClick={() => open({ view: 'detail', applicationId: r.id })}>
        Open
      </Button>
    </Shell>
  );
}

/** Live progress of one application pipeline run. `onReview` overrides opening the result in the workspace. */
export function PipelineCard({ runId, onReview, onFinish }: { runId: string; onReview?: (applicationId: string) => void; onFinish?: () => void }) {
  const stream = useAgentStream({ persist: false, runId });
  const open = useOpen();
  const finished = stream.phase === 'success' || stream.phase === 'error';
  const notified = useRef(false);
  useEffect(() => {
    if (finished && !notified.current) {
      notified.current = true;
      onFinish?.();
    }
  }, [finished, onFinish]);
  const done = PIPELINE_STEPS.filter((s) => ['done', 'warning'].includes(stream.steps[s.id].state)).length;
  const result = stream.result as { score?: number; role?: string; company?: string } | null;
  // What each step reported, in pipeline order: the "terminal" view of the run.
  const log = PIPELINE_STEPS.flatMap((s) => {
    const step = stream.steps[s.id];
    return step.state !== 'idle' && step.message ? [{ id: s.id, state: step.state, message: step.message }] : [];
  });

  if (stream.phase === 'idle') {
    return <p className="text-xs text-muted-foreground">This run finished earlier — it's in your applications.</p>;
  }

  return (
    <Shell className="p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="flex items-center gap-2 text-sm font-medium">
          {stream.phase === 'running' && <Loader2 size={14} className="animate-spin text-muted-foreground" />}
          {stream.phase === 'success' && <CheckCircle2 size={14} className="text-accent" />}
          {stream.phase === 'error' && <AlertCircle size={14} className="text-destructive" />}
          {stream.phase === 'success' ? 'Application ready' : stream.phase === 'error' ? 'Pipeline failed' : 'Creating application'}
        </p>
        <span className="text-xs tabular-nums text-muted-foreground">
          {done}/{PIPELINE_STEPS.length}
        </span>
      </div>
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-secondary">
        <div className="h-full rounded-full bg-accent transition-all duration-500" style={{ width: `${(done / PIPELINE_STEPS.length) * 100}%` }} />
      </div>
      <ul className="mt-2.5 grid gap-1 sm:grid-cols-2">
        {PIPELINE_STEPS.map((step) => {
          const s = stream.steps[step.id].state;
          return (
            <li key={step.id} className="flex items-center gap-1.5 text-xs">
              {s === 'done' && <CheckCircle2 size={12} className="shrink-0 text-accent" />}
              {s === 'running' && <Loader2 size={12} className="shrink-0 animate-spin text-muted-foreground" />}
              {s === 'warning' && <AlertTriangle size={12} className="shrink-0 text-warning" />}
              {s === 'error' && <AlertCircle size={12} className="shrink-0 text-destructive" />}
              {s === 'idle' && <Circle size={12} className="shrink-0 text-border" />}
              <span className={cn('truncate', s === 'idle' && 'text-muted-foreground')}>{step.label}</span>
            </li>
          );
        })}
      </ul>
      {log.length > 0 && (
        <ol className="mt-2.5 space-y-0.5 rounded-md bg-muted/50 px-2.5 py-2 font-mono text-[11px] leading-relaxed" aria-label="Activity">
          {log.map((line) => (
            <li key={line.id} className={cn('flex gap-1.5', line.state === 'warning' && 'text-warning', line.state === 'error' && 'text-destructive')}>
              <span className="shrink-0 text-muted-foreground">{line.state === 'running' ? '[…]' : line.state === 'done' ? '[✓]' : '[!]'}</span>
              <span className="min-w-0">{line.message}</span>
            </li>
          ))}
        </ol>
      )}
      {stream.phase === 'error' && <p className="mt-2 text-xs text-destructive">{stream.error}</p>}
      {stream.phase === 'success' && stream.applicationId && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t pt-2.5">
          <span className="text-xs text-muted-foreground">
            {result?.role} · {result?.company}
            {typeof result?.score === 'number' && <span className="ml-1 font-medium text-foreground">{Math.round(result.score)}% match</span>}
          </span>
          <Button size="sm" onClick={() => (onReview ? onReview(stream.applicationId!) : open({ view: 'detail', applicationId: stream.applicationId! }))}>
            Review
            <ArrowRight size={13} className="ml-1" />
          </Button>
        </div>
      )}
    </Shell>
  );
}

function ProposalPreview({ r }: { r: Result }) {
  const [showCurrent, setShowCurrent] = useState(false);
  const args = r.args ?? {};
  if (r.preview_proposed) {
    const text = showCurrent ? String(r.preview_current ?? '') : String(r.preview_proposed);
    return (
      <div>
        <div className="mb-1.5 inline-flex rounded-md bg-secondary p-0.5 text-xs">
          {(['Proposed', 'Current'] as const).map((label) => (
            <button
              key={label}
              type="button"
              onClick={() => setShowCurrent(label === 'Current')}
              className={cn('rounded px-2 py-0.5 font-medium', showCurrent === (label === 'Current') ? 'bg-card shadow-sm' : 'text-muted-foreground hover:text-foreground')}
            >
              {label}
            </button>
          ))}
        </div>
        <pre className="max-h-64 overflow-y-auto whitespace-pre-wrap rounded-md border bg-muted/50 p-2.5 font-sans text-xs leading-relaxed">{text}</pre>
      </div>
    );
  }
  if (r.action === 'update_status') {
    return (
      <div className="flex items-center gap-2">
        <StatusBadge status={(r.current?.status ?? 'saved') as ApplicationStatus} />
        <ArrowRight size={14} className="text-muted-foreground" />
        <StatusBadge status={args.status as ApplicationStatus} />
      </div>
    );
  }
  if (r.action === 'save_referral') {
    return (
      <pre className="max-h-64 overflow-y-auto whitespace-pre-wrap rounded-md border bg-muted/50 p-2.5 font-sans text-xs leading-relaxed">
        {String(args.message ?? '')}
      </pre>
    );
  }
  const proposed = r.action === 'update_email' ? `Subject: ${args.subject}\n\n${args.body}` : String(args.cover_letter ?? '');
  const current = r.action === 'update_email' ? `Subject: ${r.current?.subject ?? ''}\n\n${r.current?.body ?? ''}` : String(r.current?.cover_letter ?? '');
  return (
    <div>
      <div className="mb-1.5 inline-flex rounded-md bg-secondary p-0.5 text-xs">
        {(['Proposed', 'Current'] as const).map((label) => (
          <button
            key={label}
            type="button"
            onClick={() => setShowCurrent(label === 'Current')}
            className={cn(
              'rounded px-2 py-0.5 font-medium',
              showCurrent === (label === 'Current') ? 'bg-card shadow-sm' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {label}
          </button>
        ))}
      </div>
      <pre className="max-h-52 overflow-y-auto whitespace-pre-wrap rounded-md border bg-muted/50 p-2.5 font-sans text-xs leading-relaxed">
        {showCurrent ? current || '(empty)' : proposed}
      </pre>
    </div>
  );
}

function ApprovalCard({ part }: { part: ToolPart }) {
  const r = part.result as Result;
  const queryClient = useQueryClient();
  const setApproval = useChatStore((s) => s.setApproval);
  const open = useOpen();
  const [busy, setBusy] = useState(false);
  const args = r.args ?? {};
  const appId = args.application_id as string;
  const state = part.approval ?? 'pending';

  const approve = async () => {
    setBusy(true);
    try {
      if (r.action === 'update_status') await api.put(`/applications/${appId}/status`, { status: args.status });
      else if (r.action === 'update_email') await api.put(`/applications/${appId}/emails/${args.email_id}`, { subject: args.subject, body: args.body });
      else if (r.action === 'update_cover_letter') await api.patch(`/applications/${appId}`, { cover_letter: args.cover_letter });
      else if (r.action === 'update_resume') await api.put(`/resume/tailored/${appId}`, args.content);
      else if (r.action === 'save_referral')
        await api.post('/network/referrals', { application_id: appId, contact_id: args.contact_id, message: args.message });
      else throw new Error(`Unknown action ${String(r.action)}`);
      setApproval(part.id, 'approved');
      queryClient.invalidateQueries({ queryKey: ['applications'] });
      queryClient.invalidateQueries({ queryKey: ['application-detail', appId] });
      queryClient.invalidateQueries({ queryKey: ['analytics', 'skill-gaps'] });
      queryClient.invalidateQueries({ queryKey: ['network', 'referrals', appId] });
      queryClient.invalidateQueries({ queryKey: ['analytics'] });
    } catch (e) {
      setApproval(part.id, 'failed', e instanceof Error ? e.message : 'Failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell className={cn('p-3', state === 'pending' && 'border-foreground/25 shadow-sm', state === 'declined' && 'opacity-60')}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            {state === 'pending' ? 'Needs your approval' : state === 'approved' ? 'Approved' : state === 'declined' ? 'Declined' : 'Failed'}
          </p>
          <p className="mt-0.5 text-sm font-medium">{r.summary}</p>
          {r.reason && <p className="mt-0.5 text-xs text-muted-foreground">{r.reason}</p>}
          {Array.isArray(r.warnings) && r.warnings.length > 0 && (
            <ul className="mt-2 space-y-1 rounded-md border border-warning/30 bg-warning/5 px-2.5 py-2 text-xs">
              {(r.warnings as string[]).map((w) => (
                <li key={w} className="flex gap-1.5">
                  <AlertTriangle size={12} className="mt-0.5 shrink-0 text-warning" />
                  {w}
                </li>
              ))}
            </ul>
          )}
        </div>
        {appId && (
          <button
            type="button"
            onClick={() =>
              open({
                view: 'detail',
                applicationId: appId,
                tab: ({ update_email: 'email', update_cover_letter: 'cover-letter', save_referral: 'referral', update_resume: 'resume' } as Record<string, string>)[
                  r.action
                ],
              })
            }
            className="shrink-0 rounded-md p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
            title="Open application"
            aria-label="Open application"
          >
            <ExternalLink size={14} />
          </button>
        )}
      </div>
      <div className="mt-2.5">
        <ProposalPreview r={r} />
      </div>
      {part.approvalError && <p className="mt-2 text-xs text-destructive">{part.approvalError}</p>}
      {(state === 'pending' || state === 'failed') && (
        <div className="mt-3 flex gap-2">
          <Button size="sm" onClick={approve} disabled={busy}>
            {busy ? <Loader2 size={13} className="mr-1.5 animate-spin" /> : <Check size={13} className="mr-1.5" />}
            {state === 'failed' ? 'Retry' : 'Approve'}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setApproval(part.id, 'declined')} disabled={busy}>
            <X size={13} className="mr-1.5" />
            Decline
          </Button>
        </div>
      )}
      {state === 'approved' && (
        <p className="mt-2.5 flex items-center gap-1.5 text-xs font-medium text-accent">
          <CheckCircle2 size={13} />
          Change applied
        </p>
      )}
    </Shell>
  );
}

/** The card a finished tool call contributes below the activity list, if any. */
export function ToolResultCard({ part }: { part: ToolPart }) {
  const r = part.result as Result | undefined;
  if (part.status === 'running' || !r || r.error) return null;
  if (r.awaiting_approval) return <ApprovalCard part={part} />;
  switch (part.name) {
    case 'get_overview':
      return <OverviewCard r={r} />;
    case 'list_applications':
      return <ApplicationsCard r={r} />;
    case 'get_application':
      return <ApplicationCard r={r} />;
    case 'create_application':
    case 'draft_job':
      return r.run_id ? <PipelineCard runId={String(r.run_id)} /> : null;
    case 'find_referrals':
      return <ReferralsCard r={r} />;
    case 'get_job_feed':
      return <PostingsCard postings={(r.postings ?? []) as Result[]} total={r.total} />;
    case 'get_briefing':
      return <PostingsCard postings={(r.top_matches ?? []) as Result[]} />;
    case 'get_skill_gaps':
      return (
        <Shell className="p-3">
          <SkillGapsView data={r as SkillGaps} compact />
        </Shell>
      );
    default:
      return null;
  }
}
