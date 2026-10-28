// ============================================================
// JobPilot — Apply queue: drafted applications, ready to send
// Open one, let the extension fill the form, check it, submit it yourself.
// ============================================================

import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AlertTriangle, ArrowRight, Check, ChevronDown, ExternalLink, Loader2, Puzzle, RefreshCw, Send, Users } from 'lucide-react';
import { Button } from '../components/ui/button';
import { ScoreBadge } from '../components/applications/shared';
import { useChatStore } from '../agent/store';
import { useReportSubmission } from '../hooks/use-applications';
import { useApplyQueue, useExtensionPresence, usePrepareForm, type QueueItem } from '../hooks/use-autopilot';
import { cn } from '@/lib/utils';

function Readiness({ item }: { item: QueueItem }) {
  const s = item.summary;
  if (!s) {
    return <span>{item.apply_url ? 'Questions are read from the form when you open it.' : 'No application link saved for this job.'}</span>;
  }
  const ready = s.total - s.flagged;
  return (
    <span>
      <span className="font-medium text-foreground">
        {ready} of {s.total} draft answers prepared
      </span>
      {s.flagged > 0 && <span className="text-warning"> · {s.flagged} to check</span>}
    </span>
  );
}

function QueueRow({ item, embedded }: { item: QueueItem; embedded: boolean }) {
  const navigate = useNavigate();
  const openStage = useChatStore((s) => s.openStage);
  const updateStatus = useReportSubmission();
  const prepare = usePrepareForm();
  const [showFlags, setShowFlags] = useState(false);
  const [applied, setApplied] = useState(false);
  const review = (tab?: string) =>
    embedded ? openStage({ view: 'detail', applicationId: item.id, tab }) : navigate(`/applications/${item.id}${tab ? `?tab=${tab}` : ''}`);

  return (
    <li className={cn('rounded-xl border bg-card p-4 transition-opacity', applied && 'opacity-50')}>
      <div className="flex flex-col gap-3 @2xl:flex-row @2xl:items-start">
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{item.role}</span>
            <ScoreBadge score={item.match_score} />
          </p>
          <p className="text-sm text-muted-foreground">{item.company}</p>
          <p className="mt-1.5 text-xs text-muted-foreground">
            <Readiness item={item} />
          </p>
          {item.referral_count > 0 && (
            <button type="button" onClick={() => review('referral')} className="mt-1.5 flex items-center gap-1 text-xs font-medium text-accent hover:underline">
              <Users size={12} />
              You know {item.referral_count} {item.referral_count === 1 ? 'person' : 'people'} there: ask for a referral first
            </button>
          )}
          {item.skip_flags.length > 0 && (
            <p className="mt-1.5 flex items-start gap-1 text-xs text-warning">
              <AlertTriangle size={12} className="mt-0.5 shrink-0" />
              {item.skip_flags.join('; ')}
            </p>
          )}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-1.5">
          {item.apply_url ? (
            <Button size="sm" asChild>
              <a href={item.apply_url} target="_blank" rel="noreferrer">
                Open &amp; fill
                <ExternalLink size={12} className="ml-1.5" />
              </a>
            </Button>
          ) : null}
          <Button size="sm" variant="outline" onClick={() => review()}>
            Review materials
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={applied || updateStatus.isPending}
            onClick={() =>
              window.confirm(`Did you submit the ${item.role} application at ${item.company}?`) &&
              updateStatus.mutate(item.id, { onSuccess: () => setApplied(true) })
            }
          >
            {applied ? <Check size={13} className="mr-1" /> : <Send size={13} className="mr-1" />}
            {applied ? 'Reported submitted' : 'Report that I submitted'}
          </Button>
          {updateStatus.error && <p role="alert" className="text-xs text-warning">{updateStatus.error.message}</p>}
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8"
            onClick={() => prepare.mutate(item.id)}
            disabled={prepare.isPending}
            title="Re-prepare answers (after updating your answer bank)"
            aria-label="Re-prepare answers"
          >
            <RefreshCw size={13} className={cn(prepare.isPending && 'animate-spin')} />
          </Button>
        </div>
      </div>

      {item.flagged.length > 0 && (
        <div className="mt-3 border-t pt-2">
          <button type="button" onClick={() => setShowFlags(!showFlags)} className="flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground" aria-expanded={showFlags}>
            <ChevronDown size={13} className={cn('transition-transform', showFlags && 'rotate-180')} />
            What needs you on this form
          </button>
          {showFlags && (
            <ul className="mt-2 space-y-1">
              {item.flagged.map((f) => (
                <li key={f.key} className="rounded-md bg-warning/5 px-2.5 py-1.5 text-xs">
                  <span className="font-medium">{f.label}</span>
                  <span className="text-warning"> · {f.note}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {prepare.error && <p className="mt-2 text-xs text-destructive">{prepare.error.message}</p>}
    </li>
  );
}

export default function ApplyQueue({ embedded = false }: { embedded?: boolean }) {
  const { data, isLoading, error } = useApplyQueue();
  const extension = useExtensionPresence();
  const queue = data?.queue ?? [];

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Apply queue</h1>
        <p className="text-sm text-muted-foreground">
          Drafted and waiting for you. Open one, let the JobPilot extension fill the form, check it, and click Submit yourself.
        </p>
      </div>

      {!extension && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-accent/30 bg-accent/5 px-4 py-3 text-sm">
          <p className="flex items-center gap-2">
            <Puzzle size={16} className="text-accent" />
            Install the JobPilot Chrome extension so “Open &amp; fill” fills each form for you.
          </p>
          <Button size="sm" variant="outline" asChild>
            <Link to="/settings">Set it up</Link>
          </Button>
        </div>
      )}

      {isLoading ? (
        <div className="flex h-40 items-center justify-center text-muted-foreground">
          <Loader2 className="animate-spin" size={18} />
        </div>
      ) : error ? (
        <p className="text-sm text-destructive">Couldn't load the queue: {error.message}</p>
      ) : queue.length === 0 ? (
        <div className="rounded-xl border border-dashed p-8 text-center">
          <p className="font-medium">Nothing waiting</p>
          <p className="mt-1 text-sm text-muted-foreground">Draft applications from your Job feed, or turn on auto-draft so your best new matches are ready each morning.</p>
          <div className="mt-4 flex justify-center gap-2">
            <Button size="sm" asChild>
              <Link to="/jobs">
                Job feed
                <ArrowRight size={13} className="ml-1" />
              </Link>
            </Button>
            <Button size="sm" variant="outline" asChild>
              <Link to="/profile?tab=preferences">Auto-draft settings</Link>
            </Button>
          </div>
        </div>
      ) : (
        <ul className="space-y-2.5">
          {queue.map((item) => (
            <QueueRow key={item.id} item={item} embedded={embedded} />
          ))}
        </ul>
      )}
    </div>
  );
}
