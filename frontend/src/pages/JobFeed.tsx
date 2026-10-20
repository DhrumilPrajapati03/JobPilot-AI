// ============================================================
// JobPilot — Job feed: roles found on followed company job boards
// ============================================================

import { useMemo, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useIsMutating } from '@tanstack/react-query';
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  Check,
  ChevronDown,
  ExternalLink,
  Loader2,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Sparkles,
  Trash2,
  Users,
  X,
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { ScoreRing } from '../components/applications/shared';
import { PipelineCard } from '../components/agent/ToolCards';
import { useChatStore } from '../agent/store';
import {
  ATS_LABEL,
  REMOTE_BOARDS,
  SUGGESTION_GROUPS,
  timeAgo,
  useAddSource,
  useFollowBoards,
  useBriefing,
  useDeleteSource,
  useDraftPosting,
  useJobPostings,
  useJobSources,
  useRefreshAfterDraft,
  useScanNow,
  useSetPostingStatus,
  useUpdateSource,
  type FeedTab,
  type JobPosting,
  type JobSource,
  type ScanSummary,
  type SuggestedBoard,
} from '../hooks/use-discovery';
import { cn } from '@/lib/utils';

const TABS: { value: FeedTab; label: string }[] = [
  { value: 'new', label: 'Matches' },
  { value: 'drafted', label: 'Drafted' },
  { value: 'skipped', label: 'Skipped' },
  { value: 'dismissed', label: 'Dismissed' },
];

function useOpenApplication(embedded: boolean) {
  const navigate = useNavigate();
  const openStage = useChatStore((s) => s.openStage);
  return (id: string) => (embedded ? openStage({ view: 'detail', applicationId: id }) : navigate(`/applications/${id}`));
}

// --- Sources ---------------------------------------------------------------------------

function Suggestions({ suggestions, busy, onFollow }: { suggestions: SuggestedBoard[]; busy: boolean; onFollow: (boards: SuggestedBoard[]) => void }) {
  return (
    <div className="space-y-3">
      {SUGGESTION_GROUPS.map((group) => {
        const boards = suggestions.filter((s) => s.group === group.id);
        if (!boards.length) return null;
        return (
          <div key={group.id}>
            <div className="mb-1.5 flex flex-wrap items-baseline gap-x-2">
              <p className="text-xs font-medium">{group.label}</p>
              {group.hint && <p className="text-xs text-muted-foreground">{group.hint}</p>}
              {boards.length > 1 && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => onFollow(boards)}
                  className="ml-auto text-xs font-medium text-accent hover:underline disabled:opacity-50"
                >
                  Follow all {boards.length}
                </button>
              )}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {boards.map((s) => (
                <button
                  key={`${s.ats}:${s.slug}`}
                  type="button"
                  disabled={busy}
                  onClick={() => onFollow([s])}
                  className="inline-flex items-center gap-1 rounded-full border bg-card px-2.5 py-1 text-xs hover:bg-secondary disabled:opacity-50"
                  title={[s.tag, `on ${ATS_LABEL[s.ats]}`].filter(Boolean).join(' · ')}
                >
                  <Plus size={11} className="text-muted-foreground" />
                  {s.company}
                  {s.tag.includes('Recently funded') && <span className="rounded-full bg-accent/10 px-1.5 text-[10px] text-accent">New funding</span>}
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function AddSourceForm({ autoFocus }: { autoFocus?: boolean }) {
  const add = useAddSource();
  const follow = useFollowBoards();
  const [url, setUrl] = useState('');
  const { data } = useJobSources();
  const [result, setResult] = useState<string | null>(null);

  const submit = (value: string, ats?: JobSource['ats']) => {
    setResult(null);
    add.mutate(
      { url: value, ats },
      {
        onSuccess: ({ source, scan }) => {
          setUrl('');
          setResult(
            source.ats in REMOTE_BOARDS
              ? `Following ${source.company}: ${scan.new} remote role${scan.new === 1 ? '' : 's'} matching your target roles.`
              : `Following ${source.company}: ${scan.new} matching role${scan.new === 1 ? '' : 's'} out of ${scan.fetched} open.`,
          );
        },
      },
    );
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (url.trim()) submit(url.trim());
  };

  return (
    <div className="space-y-3">
      <form onSubmit={onSubmit} className="flex flex-col gap-2 @md:flex-row">
        <Input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="Paste a careers link, e.g. jobs.ashbyhq.com/sarvam"
          aria-label="Job board link"
          className="bg-card"
          autoFocus={autoFocus}
          disabled={add.isPending}
        />
        <Button type="submit" disabled={!url.trim() || add.isPending} className="shrink-0">
          {add.isPending ? <Loader2 size={15} className="mr-1.5 animate-spin" /> : <Plus size={15} className="mr-1.5" />}
          {add.isPending ? 'Checking board…' : 'Follow'}
        </Button>
      </form>
      <p className="text-xs text-muted-foreground">
        Works with company boards on Greenhouse, Lever, Ashby and SmartRecruiters, plus the Himalayas and Remotive remote job boards. No sign-in or
        API key needed.
      </p>
      {(add.error || follow.error) && <p className="text-xs text-destructive">{(add.error ?? follow.error)?.message}</p>}
      {result && <p className="text-xs text-accent">{result}</p>}
      {follow.isSuccess && <p className="text-xs text-accent">Followed {follow.data.sources.length} board{follow.data.sources.length === 1 ? '' : 's'}. Scanning them now…</p>}
      {!!data?.suggestions.length && <Suggestions suggestions={data.suggestions} busy={add.isPending || follow.isPending} onFollow={(boards) => follow.mutate(boards)} />}
    </div>
  );
}

function SourceRow({ source }: { source: JobSource }) {
  const update = useUpdateSource();
  const remove = useDeleteSource();
  return (
    <li className="flex items-center gap-3 py-2.5">
      <input
        type="checkbox"
        checked={source.enabled}
        onChange={(e) => update.mutate({ id: source.id, enabled: e.target.checked })}
        className="h-4 w-4 shrink-0 accent-[var(--accent)]"
        aria-label={`Scan ${source.company}`}
      />
      <span className="min-w-0 flex-1">
        <span className={cn('block truncate text-sm font-medium', !source.enabled && 'text-muted-foreground')}>{source.company || source.slug}</span>
        <span className="block truncate text-xs text-muted-foreground">
          {source.ats in REMOTE_BOARDS
            ? `Remote job board · ${source.job_count} result${source.job_count === 1 ? '' : 's'} for your target roles`
            : `${ATS_LABEL[source.ats]} · ${source.job_count} open role${source.job_count === 1 ? '' : 's'}`}
          {source.last_scanned_at && ` · scanned ${timeAgo(source.last_scanned_at)}`}
        </span>
        {source.last_error && (
          <span className="mt-0.5 flex items-center gap-1 text-xs text-destructive">
            <AlertCircle size={11} />
            {source.last_error}
          </span>
        )}
      </span>
      <button
        type="button"
        onClick={() => window.confirm(`Stop following ${source.company}? Its postings leave your feed; drafted applications stay.`) && remove.mutate(source.id)}
        disabled={remove.isPending}
        className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-destructive"
        aria-label={`Unfollow ${source.company}`}
        title="Unfollow"
      >
        {remove.isPending ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
      </button>
    </li>
  );
}

function SourcesPanel({ sources }: { sources: JobSource[] }) {
  const [open, setOpen] = useState(false);
  const failing = sources.filter((s) => s.last_error).length;
  return (
    <div className="rounded-xl border bg-card">
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-4 py-3 text-left" aria-expanded={open}>
        <span className="flex-1 text-sm font-medium">
          Following {sources.length} board{sources.length === 1 ? '' : 's'}
          {failing > 0 && <span className="ml-2 text-xs font-normal text-destructive">{failing} couldn't be read</span>}
        </span>
        <span className="text-xs text-muted-foreground">{open ? 'Hide' : 'Manage'}</span>
        <ChevronDown size={15} className={cn('text-muted-foreground transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="space-y-4 border-t px-4 pb-4 pt-1">
          <ul className="divide-y">
            {sources.map((s) => (
              <SourceRow key={s.id} source={s} />
            ))}
          </ul>
          <AddSourceForm />
        </div>
      )}
    </div>
  );
}

// --- Postings ---------------------------------------------------------------------------

function SkillChips({ matched, missing }: { matched: string[]; missing: string[] }) {
  if (!matched.length && !missing.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1">
      {matched.slice(0, 6).map((s) => (
        <span key={s} className="inline-flex items-center gap-0.5 rounded-full bg-accent/10 px-2 py-0.5 text-[11px] text-accent">
          <Check size={10} />
          {s}
        </span>
      ))}
      {missing.slice(0, 4).map((s) => (
        <span key={s} className="rounded-full border border-dashed px-2 py-0.5 text-[11px] text-muted-foreground" title="Mentioned in the job, not in your resume">
          {s}
        </span>
      ))}
    </div>
  );
}

function PostingRow({ posting, onOpenApplication }: { posting: JobPosting; onOpenApplication: (id: string) => void }) {
  const draft = useDraftPosting();
  const setStatus = useSetPostingStatus();
  const refresh = useRefreshAfterDraft();
  const [runId, setRunId] = useState<string | null>(null);
  const fit = Number(posting.fit_score);
  const meta = [
    posting.company,
    posting.remote ? posting.location.startsWith('Remote') ? posting.location : 'Remote' : posting.location,
    posting.posted_at ? `posted ${timeAgo(posting.posted_at)}` : `found ${timeAgo(posting.discovered_at)}`,
  ].filter(Boolean);

  const startDraft = () =>
    draft.mutate(posting.id, {
      onSuccess: (r) => setRunId(r.run_id),
    });

  return (
    <li className="rounded-xl border bg-card p-3.5">
      <div className="flex flex-col gap-3 @lg:flex-row @lg:items-start">
        <div className="flex min-w-0 flex-1 gap-3">
          <ScoreRing score={fit} size={46} label={`${Math.round(fit)}% fit`} />
          <div className="min-w-0 flex-1">
            <a
              href={posting.url}
              target="_blank"
              rel="noreferrer"
              className="group inline-flex max-w-full items-center gap-1 text-sm font-medium hover:underline"
            >
              <span className="truncate">{posting.title}</span>
              <ExternalLink size={12} className="shrink-0 text-muted-foreground" />
            </a>
            <p className="truncate text-xs text-muted-foreground">
              {meta.join(' · ')}
              {REMOTE_BOARDS[posting.ats] && (
                <>
                  {' · via '}
                  <a href={REMOTE_BOARDS[posting.ats]} target="_blank" rel="noreferrer" className="underline-offset-2 hover:underline">
                    {ATS_LABEL[posting.ats]}
                  </a>
                </>
              )}
            </p>
            {!!posting.referral_count && (
              <p className="mt-1 flex items-center gap-1 text-xs font-medium text-accent">
                <Users size={12} />
                You know {posting.referral_count} {posting.referral_count === 1 ? 'person' : 'people'} at {posting.company}
              </p>
            )}
            <SkillChips matched={posting.matched_skills} missing={posting.missing_skills} />
            {posting.skip_flags.length > 0 && (
              <ul className="mt-2 space-y-0.5">
                {posting.skip_flags.map((flag) => (
                  <li key={flag} className="flex items-center gap-1.5 text-xs text-warning">
                    <AlertTriangle size={11} className="shrink-0" />
                    {flag}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-1.5 pl-[58px] @lg:pl-0">
          {posting.status === 'new' && !runId && (
            <>
              <Button size="sm" onClick={startDraft} disabled={draft.isPending}>
                {draft.isPending ? <Loader2 size={13} className="mr-1.5 animate-spin" /> : <Sparkles size={13} className="mr-1.5" />}
                Draft application
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setStatus.mutate({ id: posting.id, status: 'dismissed' })} aria-label={`Dismiss ${posting.title}`}>
                <X size={14} />
                <span className="ml-1 @lg:sr-only">Dismiss</span>
              </Button>
            </>
          )}
          {(posting.status === 'skipped' || posting.status === 'dismissed') && (
            <Button size="sm" variant="outline" onClick={() => setStatus.mutate({ id: posting.id, status: 'new' })}>
              <RotateCcw size={13} className="mr-1.5" />
              Move to matches
            </Button>
          )}
          {posting.status === 'drafting' && !runId && (
            <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
              <Loader2 size={13} className="animate-spin" />
              Drafting…
            </span>
          )}
          {posting.status === 'drafted' && posting.application_id && (
            <>
              {posting.auto_drafted && <span className="rounded-full bg-secondary px-2 py-0.5 text-[11px] text-muted-foreground">Auto-drafted</span>}
              <Button size="sm" variant="outline" onClick={() => onOpenApplication(posting.application_id!)}>
                Review
                <ArrowRight size={13} className="ml-1" />
              </Button>
            </>
          )}
        </div>
      </div>
      {(draft.error || setStatus.error) && <p className="mt-2 text-xs text-destructive">{(draft.error ?? setStatus.error)?.message}</p>}
      {runId && (
        <div className="mt-3">
          <PipelineCard runId={runId} onReview={onOpenApplication} onFinish={refresh} />
        </div>
      )}
    </li>
  );
}

function ScanResult({ summary }: { summary: ScanSummary }) {
  if (summary.status === 'already_running') return <p className="text-xs text-muted-foreground">A scan is already running.</p>;
  const parts = [
    `${summary.new} new match${summary.new === 1 ? '' : 'es'}`,
    summary.skipped ? `${summary.skipped} skipped by your rules` : null,
    summary.closed ? `${summary.closed} closed` : null,
    summary.auto_drafting.length ? `auto-drafting ${summary.auto_drafting.length}` : null,
  ].filter(Boolean);
  return (
    <div className="rounded-lg border bg-muted/40 px-3 py-2 text-xs">
      <p>
        <span className="font-medium">Scan complete:</span> {parts.join(' · ')}
        <span className="text-muted-foreground">
          {' '}
          ({summary.fetched} open roles checked, {summary.filtered} didn't fit your target roles)
        </span>
      </p>
      {summary.errors.map((e) => (
        <p key={e.source_id} className="mt-1 text-destructive">
          {e.company}: {e.error}
        </p>
      ))}
    </div>
  );
}

// --- Page --------------------------------------------------------------------------------

export default function JobFeed({ embedded = false }: { embedded?: boolean }) {
  const [tab, setTab] = useState<FeedTab>('new');
  const [query, setQuery] = useState('');
  const [onlyStrong, setOnlyStrong] = useState(true);
  const [remoteOnly, setRemoteOnly] = useState(false);
  const sources = useJobSources();
  const postings = useJobPostings(tab);
  const { data: briefing } = useBriefing();
  const scan = useScanNow();
  const scanning = useIsMutating({ mutationKey: ['discovery', 'scan'] }) > 0;
  const openApplication = useOpenApplication(embedded);

  const minScore = briefing?.min_match_score ?? 70;
  const q = query.trim().toLowerCase();
  const visible = useMemo(
    () =>
      (postings.data?.postings ?? []).filter(
        (p) =>
          (tab !== 'new' || !onlyStrong || Number(p.fit_score) >= minScore) &&
          (!remoteOnly || p.remote === true) &&
          (!q || [p.title, p.company, p.location, ...p.matched_skills].some((v) => v?.toLowerCase().includes(q))),
      ),
    [postings.data, tab, onlyStrong, remoteOnly, minScore, q],
  );
  const hiddenWeak = tab === 'new' && onlyStrong ? (postings.data?.postings ?? []).filter((p) => Number(p.fit_score) < minScore).length : 0;

  const list = sources.data?.sources ?? [];
  const missingTables = sources.error?.message.includes('migrations');
  const counts = postings.data?.counts;
  const auto = briefing?.auto_draft;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Job feed</h1>
          <p className="text-sm text-muted-foreground">
            Roles with stated hiring eligibility in India, scored against your resume. Unclear locations are hidden.
            {briefing?.last_scan_at && ` Last scan ${timeAgo(briefing.last_scan_at)}.`}
          </p>
        </div>
        {list.length > 0 && (
          <Button variant="outline" onClick={() => scan.mutate()} disabled={scanning}>
            <RefreshCw size={15} className={cn('mr-1.5', scanning && 'animate-spin')} />
            {scanning ? 'Scanning…' : 'Scan now'}
          </Button>
        )}
      </div>

      {missingTables ? (
        <div className="flex items-start gap-2 rounded-xl border border-warning/30 bg-warning/5 p-4 text-sm">
          <AlertTriangle size={16} className="mt-0.5 shrink-0 text-warning" />
          <span>{sources.error?.message}</span>
        </div>
      ) : sources.isLoading ? (
        <div className="flex h-40 items-center justify-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="animate-spin" size={18} />
          Loading…
        </div>
      ) : sources.isError ? (
        <div className="flex items-center gap-2 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          <AlertCircle size={16} />
          Couldn't load your job boards: {sources.error?.message}
        </div>
      ) : list.length === 0 ? (
        <div className="rounded-xl border bg-card p-5">
          <h2 className="font-medium">Follow the companies you'd like to work for</h2>
          <p className="mb-4 mt-1 text-sm text-muted-foreground">
            JobPilot checks their job boards every day, keeps the roles that fit your target roles and skip rules, and ranks them by how well
            your resume matches.
          </p>
          <AddSourceForm autoFocus={!embedded} />
        </div>
      ) : (
        <>
          <SourcesPanel sources={list} />
          {scan.error && <p className="text-xs text-destructive">{scan.error.message}</p>}
          {scan.data && <ScanResult summary={scan.data} />}

          {auto && (
            <p className="text-xs text-muted-foreground">
              {auto.enabled
                ? `Auto-draft is on: the best new matches at ${auto.min_score}%+ fit get drafted, ${auto.remaining_today} of ${auto.daily_cap} left today. `
                : 'Auto-draft is off. Turn it on to have your best new matches drafted after each scan. '}
              <Link to="/profile?tab=preferences" className="font-medium text-foreground underline-offset-2 hover:underline">
                {auto.enabled ? 'Change' : 'Set up auto-draft'}
              </Link>
            </p>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <div className="flex flex-wrap gap-1" role="tablist" aria-label="Feed">
              {TABS.map((t) => (
                <button
                  key={t.value}
                  type="button"
                  role="tab"
                  aria-selected={tab === t.value}
                  onClick={() => setTab(t.value)}
                  className={cn(
                    'rounded-full px-3 py-1 text-xs font-medium transition-colors',
                    tab === t.value ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground hover:text-foreground',
                  )}
                >
                  {t.label}
                  {counts && <span className="ml-1 tabular-nums opacity-70">{counts[t.value]}</span>}
                </button>
              ))}
            </div>
            <div className="relative ml-auto min-w-[180px] max-w-xs flex-1">
              <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter by title, company, skill" className="bg-card pl-9" aria-label="Filter jobs" />
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
            {tab === 'new' && (
              <label className="flex w-fit cursor-pointer items-center gap-2 text-xs text-muted-foreground">
                <input type="checkbox" checked={onlyStrong} onChange={(e) => setOnlyStrong(e.target.checked)} className="h-3.5 w-3.5 accent-[var(--accent)]" />
                Only show {minScore}%+ fit{hiddenWeak > 0 && ` (${hiddenWeak} hidden)`}
              </label>
            )}
            <label className="flex w-fit cursor-pointer items-center gap-2 text-xs text-muted-foreground">
              <input type="checkbox" checked={remoteOnly} onChange={(e) => setRemoteOnly(e.target.checked)} className="h-3.5 w-3.5 accent-[var(--accent)]" />
              Remote only
            </label>
          </div>

          {postings.isLoading ? (
            <div className="flex h-32 items-center justify-center text-muted-foreground">
              <Loader2 className="animate-spin" size={18} />
            </div>
          ) : postings.isError ? (
            <p className="text-sm text-destructive">Couldn't load the feed: {postings.error?.message}</p>
          ) : visible.length === 0 ? (
            <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
              {tab === 'new'
                ? hiddenWeak
                  ? `No matches at ${minScore}%+ fit right now. Untick the filter to see ${hiddenWeak} weaker match${hiddenWeak === 1 ? '' : 'es'}.`
                  : 'No new matches. Scan again later, or follow more companies.'
                : tab === 'drafted'
                  ? 'Applications you draft from the feed show up here.'
                  : tab === 'skipped'
                    ? 'Nothing has broken your skip rules.'
                    : 'Nothing dismissed.'}
            </div>
          ) : (
            <ul className="space-y-2.5">
              {visible.map((p) => (
                <PostingRow key={p.id} posting={p} onOpenApplication={openApplication} />
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
