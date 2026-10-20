// ============================================================
// JobPilot — Applications (pipeline table + board)
// ============================================================

import { useMemo, useState, type DragEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AlertCircle, Archive, ArrowDown, ArrowRight, ArrowUp, BellRing, Check, Columns3, Download, Loader2, Mail, MessageSquare, Plus, Search, Table, Users } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { ScoreBadge, StatusSelect, daysSince, formatDate, isOverdue } from '../components/applications/shared';
import { useUIStore } from '../stores/ui-store';
import {
  downloadTailoredPdf,
  useApplications,
  useUpdateApplicationStatus,
  type ApplicationStatus,
  type JobApplication,
} from '../hooks/use-applications';
import { APPLICATION_STATUS_CONFIG, KANBAN_COLUMNS } from '../lib/constants';
import { cn } from '@/lib/utils';

const DRAG_MIME = 'application/x-jobpilot-application';

// The usual next step for each stage, offered as a one-click action on board cards.
const NEXT_STEP: Partial<Record<ApplicationStatus, { status: ApplicationStatus; label: string }>> = {
  saved: { status: 'applied', label: 'Mark applied' },
  applied: { status: 'interviewing', label: 'Interviewing' },
  interviewing: { status: 'offer', label: 'Got offer' },
};

function CardActions({
  app,
  onMove,
  onFollowUp,
  onOpenResume,
}: {
  app: JobApplication;
  onMove: (status: ApplicationStatus) => void;
  onFollowUp: () => void;
  onOpenResume: () => void;
}) {
  const next = NEXT_STEP[app.status];
  const [copied, setCopied] = useState(false);
  const [exporting, setExporting] = useState(false);
  const dm = app.linkedin_dm?.connection_request ?? '';
  const copyDm = async () => {
    try {
      await navigator.clipboard.writeText(dm);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard blocked (insecure context) — nothing useful to do.
    }
  };
  const downloadPdf = async () => {
    setExporting(true);
    try {
      await downloadTailoredPdf(app.id, `Resume_${app.company.replace(/[^A-Za-z0-9]+/g, '_')}.pdf`);
    } catch {
      onOpenResume(); // no server PDF engine: the resume tab can print to PDF instead
    } finally {
      setExporting(false);
    }
  };
  const followUpDue = app.status === 'applied' && isOverdue(app.follow_up_at);
  const stop = (fn: () => void) => (e: { stopPropagation: () => void }) => {
    e.stopPropagation();
    fn();
  };
  // Floats on the card's top edge on hover / focus, so it takes no space; always shown on touch screens.
  return (
    <div
      className="absolute -top-3 right-2 flex items-center gap-0.5 rounded-md border bg-card p-0.5 opacity-0 shadow-sm transition-opacity focus-within:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100"
      onKeyDown={(e) => e.stopPropagation()}
    >
      {next && (
        <button
          type="button"
          onClick={stop(() => onMove(next.status))}
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium hover:bg-secondary"
        >
          {next.label}
          <ArrowRight size={11} />
        </button>
      )}
      {followUpDue && (
        <button
          type="button"
          onClick={stop(onFollowUp)}
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium text-warning hover:bg-warning/10"
        >
          <Mail size={11} />
          Follow up
        </button>
      )}
      {dm && (
        <button
          type="button"
          onClick={stop(copyDm)}
          className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
          aria-label={copied ? 'LinkedIn message copied' : `Copy LinkedIn message for ${app.company}`}
          title={copied ? 'Copied' : 'Copy LinkedIn message'}
        >
          {copied ? <Check size={12} className="text-accent" /> : <MessageSquare size={12} />}
        </button>
      )}
      <button
        type="button"
        onClick={stop(downloadPdf)}
        disabled={exporting}
        className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
        aria-label={`Download resume PDF for ${app.company}`}
        title="Download resume PDF"
      >
        {exporting ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
      </button>
      {app.status !== 'archived' && (
        <button
          type="button"
          onClick={stop(() => onMove('archived'))}
          className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
          aria-label={`Archive ${app.role} at ${app.company}`}
          title="Archive"
        >
          <Archive size={12} />
        </button>
      )}
    </div>
  );
}

type SortKey = 'created_at' | 'company' | 'keyword_match_score' | 'status';

function FollowUpCell({ app }: { app: JobApplication }) {
  if (app.status !== 'applied' || !app.follow_up_at) return <span className="text-muted-foreground">—</span>;
  const due = isOverdue(app.follow_up_at);
  return (
    <span className={cn('inline-flex items-center gap-1', due ? 'font-medium text-warning' : 'text-muted-foreground')}>
      {due && <BellRing size={12} />}
      {due ? 'Due now' : formatDate(app.follow_up_at)}
    </span>
  );
}

function SortHeader({ label, column, sort, onSort }: { label: string; column: SortKey; sort: { key: SortKey; desc: boolean }; onSort: (k: SortKey) => void }) {
  const active = sort.key === column;
  return (
    <th className="px-4 py-2.5 font-medium" aria-sort={active ? (sort.desc ? 'descending' : 'ascending') : 'none'}>
      <button type="button" onClick={() => onSort(column)} className={cn('inline-flex items-center gap-1', active && 'text-foreground')}>
        {label}
        {active && (sort.desc ? <ArrowDown size={12} /> : <ArrowUp size={12} />)}
      </button>
    </th>
  );
}

function ApplicationsTable({ applications }: { applications: JobApplication[] }) {
  const updateStatus = useUpdateApplicationStatus();
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'created_at', desc: true });

  const sorted = useMemo(() => {
    const order = (a: JobApplication) =>
      sort.key === 'status' ? KANBAN_COLUMNS.indexOf(a.status) : sort.key === 'keyword_match_score' ? a.keyword_match_score ?? -1 : sort.key === 'company' ? a.company.toLowerCase() : a.created_at;
    return [...applications].sort((a, b) => {
      const [x, y] = [order(a), order(b)];
      const cmp = x < y ? -1 : x > y ? 1 : 0;
      return sort.desc ? -cmp : cmp;
    });
  }, [applications, sort]);

  const onSort = (key: SortKey) => setSort((prev) => ({ key, desc: prev.key === key ? !prev.desc : key !== 'company' }));

  return (
    <div className="overflow-hidden rounded-xl border bg-card">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="border-b bg-muted/50 text-xs text-muted-foreground">
            <tr>
              <SortHeader label="Role" column="company" sort={sort} onSort={onSort} />
              <SortHeader label="Status" column="status" sort={sort} onSort={onSort} />
              <SortHeader label="Match" column="keyword_match_score" sort={sort} onSort={onSort} />
              <SortHeader label="Added" column="created_at" sort={sort} onSort={onSort} />
              <th className="px-4 py-2.5 font-medium">Follow-up</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {sorted.map((app) => (
              <tr key={app.id} className="hover:bg-muted/40">
                <td className="px-4 py-3">
                  <Link to={`/applications/${app.id}`} className="font-medium hover:underline">
                    {app.role}
                  </Link>
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    {app.company}
                    {!!app.referral_count && (
                      <span className="inline-flex items-center gap-0.5 text-accent" title={`You know ${app.referral_count} people there`}>
                        <Users size={11} />
                        {app.referral_count}
                      </span>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <StatusSelect value={app.status} onChange={(status) => updateStatus.mutate({ id: app.id, status })} />
                </td>
                <td className="px-4 py-3">
                  <ScoreBadge score={app.keyword_match_score} />
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-xs text-muted-foreground">{formatDate(app.created_at, true)}</td>
                <td className="whitespace-nowrap px-4 py-3 text-xs">
                  <FollowUpCell app={app} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {updateStatus.error && <p className="border-t px-4 py-2 text-xs text-destructive">{updateStatus.error.message}</p>}
    </div>
  );
}

function ApplicationsBoard({ applications, columns }: { applications: JobApplication[]; columns: readonly ApplicationStatus[] }) {
  const navigate = useNavigate();
  const updateStatus = useUpdateApplicationStatus();
  const [dropTarget, setDropTarget] = useState<ApplicationStatus | null>(null);

  const onDrop = (e: DragEvent<HTMLDivElement>, status: ApplicationStatus) => {
    e.preventDefault();
    setDropTarget(null);
    const raw = e.dataTransfer.getData(DRAG_MIME);
    if (!raw) return;
    const { id, from } = JSON.parse(raw) as { id: string; from: ApplicationStatus };
    if (from !== status) updateStatus.mutate({ id, status });
  };

  return (
    <div>
      <div className="flex gap-3 overflow-x-auto pb-2">
      {columns.map((status) => {
        const config = APPLICATION_STATUS_CONFIG[status];
        const items = applications.filter((a) => a.status === status);
        return (
          <div
            key={status}
            onDragOver={(e) => {
              if (!e.dataTransfer.types.includes(DRAG_MIME)) return;
              e.preventDefault();
              setDropTarget(status);
            }}
            onDragLeave={(e) => !e.currentTarget.contains(e.relatedTarget as Node) && setDropTarget(null)}
            onDrop={(e) => onDrop(e, status)}
            className={cn('flex min-w-[220px] flex-1 flex-col rounded-xl bg-muted/60 p-2 transition-colors', dropTarget === status && 'bg-accent/10 ring-1 ring-accent/40')}
          >
            <div className="flex items-center justify-between px-1.5 pb-2 pt-1">
              <span className="flex items-center gap-2 text-sm font-medium">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: config.mark }} />
                {config.label}
              </span>
              <span className="text-xs tabular-nums text-muted-foreground">{items.length}</span>
            </div>
            <div className="flex min-h-[120px] flex-col gap-3 pt-1">
              {items.map((app) => {
                const days = daysSince(app.applied_at ?? app.created_at);
                return (
                  <div
                    key={app.id}
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData(DRAG_MIME, JSON.stringify({ id: app.id, from: app.status }));
                      e.dataTransfer.effectAllowed = 'move';
                    }}
                    onClick={() => navigate(`/applications/${app.id}`)}
                    onKeyDown={(e) => e.key === 'Enter' && navigate(`/applications/${app.id}`)}
                    role="link"
                    tabIndex={0}
                    className="group relative cursor-pointer rounded-lg border bg-card p-3 text-left shadow-sm transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <p className="line-clamp-2 text-sm font-medium leading-snug">{app.role}</p>
                    <p className="truncate text-xs text-muted-foreground">{app.company}</p>
                    {!!app.referral_count && app.status === 'saved' && (
                      <p className="mt-1.5 flex items-center gap-1 text-[11px] font-medium text-accent">
                        <Users size={11} />
                        You know {app.referral_count} there
                      </p>
                    )}
                    <div className="mt-2.5 flex items-center justify-between gap-2">
                      <ScoreBadge score={app.keyword_match_score} />
                      <span className="text-[11px] text-muted-foreground">{days === null ? '' : days === 0 ? 'Today' : `${days}d`}</span>
                    </div>
                    {app.status === 'applied' && isOverdue(app.follow_up_at) && (
                      <p className="mt-2 flex items-center gap-1 text-[11px] font-medium text-warning">
                        <BellRing size={11} />
                        Follow-up due
                      </p>
                    )}
                    <CardActions
                      app={app}
                      onMove={(next) => updateStatus.mutate({ id: app.id, status: next })}
                      onFollowUp={() => navigate(`/applications/${app.id}?tab=email`)}
                      onOpenResume={() => navigate(`/applications/${app.id}?tab=resume`)}
                    />
                  </div>
                );
              })}
              {items.length === 0 && (
                <div className="grid flex-1 place-items-center rounded-lg border border-dashed text-xs text-muted-foreground">Empty</div>
              )}
            </div>
          </div>
        );
      })}
      </div>
      {updateStatus.error && <p className="mt-2 text-xs text-destructive">Couldn't move the application: {updateStatus.error.message}</p>}
    </div>
  );
}

export default function Applications() {
  const navigate = useNavigate();
  const { trackerViewMode, setTrackerViewMode } = useUIStore();
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<ApplicationStatus | 'all' | 'active'>('active');
  const { data, isLoading, isError, error } = useApplications();
  const applications = data?.applications ?? [];

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: applications.length, active: 0 };
    applications.forEach((a) => {
      c[a.status] = (c[a.status] ?? 0) + 1;
      if (a.status !== 'archived' && a.status !== 'rejected') c.active += 1;
    });
    return c;
  }, [applications]);

  const q = query.trim().toLowerCase();
  const visible = applications.filter((a) => {
    if (statusFilter === 'active' && (a.status === 'archived' || a.status === 'rejected')) return false;
    if (statusFilter !== 'all' && statusFilter !== 'active' && a.status !== statusFilter) return false;
    return !q || [a.role, a.company, ...(a.jd_analysis?.required_skills ?? [])].some((v) => v?.toLowerCase().includes(q));
  });
  const columns =
    statusFilter === 'all' ? KANBAN_COLUMNS : statusFilter === 'active' ? KANBAN_COLUMNS.filter((s) => s !== 'archived' && s !== 'rejected') : [statusFilter];

  const filters: { value: typeof statusFilter; label: string }[] = [
    { value: 'active', label: 'Active' },
    ...KANBAN_COLUMNS.map((s) => ({ value: s, label: APPLICATION_STATUS_CONFIG[s].label })),
    { value: 'all', label: 'All' },
  ];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Applications</h1>
          <p className="text-sm text-muted-foreground">{counts.all} tracked</p>
        </div>
        <Button onClick={() => navigate('/applications/new')}>
          <Plus size={16} className="mr-1.5" />
          New application
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[200px] max-w-xs flex-1">
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search role, company or skill" className="bg-card pl-9" aria-label="Search applications" />
        </div>
        <div className="flex flex-wrap gap-1" role="group" aria-label="Filter by status">
          {filters.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => setStatusFilter(f.value)}
              aria-pressed={statusFilter === f.value}
              className={cn(
                'rounded-full px-3 py-1 text-xs font-medium transition-colors',
                statusFilter === f.value ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground hover:text-foreground',
              )}
            >
              {f.label}
              <span className="ml-1 tabular-nums opacity-70">{counts[f.value] ?? 0}</span>
            </button>
          ))}
        </div>
        <div className="ml-auto flex rounded-lg bg-secondary p-0.5" role="group" aria-label="View">
          {(
            [
              ['table', 'Table', Table],
              ['kanban', 'Board', Columns3],
            ] as const
          ).map(([mode, label, Icon]) => (
            <button
              key={mode}
              type="button"
              onClick={() => setTrackerViewMode(mode)}
              aria-pressed={trackerViewMode === mode}
              className={cn(
                'flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium',
                trackerViewMode === mode ? 'bg-card shadow-sm' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              <Icon size={13} />
              {label}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="flex h-48 items-center justify-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="animate-spin" size={18} />
          Loading applications…
        </div>
      ) : isError ? (
        <div className="flex items-center gap-2 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          <AlertCircle size={16} />
          Couldn't load applications: {error?.message}
        </div>
      ) : applications.length === 0 ? (
        <div className="rounded-xl border border-dashed bg-card p-10 text-center">
          <p className="font-medium">No applications yet</p>
          <p className="mt-1 text-sm text-muted-foreground">Paste a job description in the chat or create one here.</p>
          <Button className="mt-4" onClick={() => navigate('/applications/new')}>
            <Plus size={16} className="mr-1.5" />
            New application
          </Button>
        </div>
      ) : visible.length === 0 ? (
        <p className="py-12 text-center text-sm text-muted-foreground">No applications match these filters.</p>
      ) : trackerViewMode === 'kanban' ? (
        <ApplicationsBoard applications={visible} columns={columns} />
      ) : (
        <ApplicationsTable applications={visible} />
      )}
    </div>
  );
}
