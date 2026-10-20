// ============================================================
// JobPilot — Morning briefing on the chat home
// New matches from followed boards, drafts to review, follow-ups due.
// ============================================================

import type { ReactNode } from 'react';
import { useIsMutating } from '@tanstack/react-query';
import { BellRing, ChevronRight, FileCheck2, Loader2, Radar } from 'lucide-react';
import { useChatStore } from '../../agent/store';
import { sendChatMessage } from '../../agent/client';
import { ATS_LABEL, REMOTE_BOARDS, timeAgo, useBriefing } from '../../hooks/use-discovery';
import { formatDate, scoreColor } from '../applications/shared';

function greeting() {
  const hour = new Date().getHours();
  return hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
}

function Section({ icon, title, count, action, children }: { icon: ReactNode; title: string; count: number; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="px-4 py-3">
      <h3 className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
        {icon}
        <span className="flex-1">{title}</span>
        {action}
        <span className="tabular-nums">{count}</span>
      </h3>
      <div className="mt-1.5">{children}</div>
    </section>
  );
}

function Row({ onClick, title, meta, trailing }: { onClick: () => void; title: string; meta: string; trailing?: ReactNode }) {
  return (
    <li>
      <button type="button" onClick={onClick} className="-mx-2 flex w-[calc(100%+1rem)] items-center gap-3 rounded-md px-2 py-1.5 text-left hover:bg-secondary">
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm">{title}</span>
          <span className="block truncate text-xs text-muted-foreground">{meta}</span>
        </span>
        {trailing}
        <ChevronRight size={14} className="shrink-0 text-muted-foreground" />
      </button>
    </li>
  );
}

export function MorningBriefing() {
  const { data, isLoading, isError } = useBriefing();
  const openStage = useChatStore((s) => s.openStage);
  const scanning = useIsMutating({ mutationKey: ['discovery', 'scan'] }) > 0;
  if (isLoading || isError || !data) return null;

  if (data.sources === 0) {
    return (
      <button
        type="button"
        onClick={() => openStage({ view: 'feed' })}
        className="mt-6 flex w-full items-center gap-3 rounded-xl border border-dashed bg-card/60 px-4 py-3 text-left hover:bg-secondary"
      >
        <Radar size={18} className="shrink-0 text-accent" />
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium">Get a daily briefing</span>
          <span className="block text-xs text-muted-foreground">Follow the companies you like and JobPilot brings you new matching roles every day.</span>
        </span>
        <ChevronRight size={15} className="text-muted-foreground" />
      </button>
    );
  }

  const matches = data.top_matches;
  const auto = data.auto_draft;

  return (
    <div className="mt-6 overflow-hidden rounded-xl border bg-card text-left">
      <header className="flex items-center gap-2 border-b px-4 py-2.5">
        <p className="flex-1 text-sm font-medium">{greeting()}. Here's your briefing.</p>
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          {scanning && <Loader2 size={12} className="animate-spin" />}
          {scanning ? 'Scanning boards…' : data.last_scan_at ? `Scanned ${timeAgo(data.last_scan_at)}` : 'Not scanned yet'}
        </span>
      </header>

      <div className="divide-y">
        <Section icon={<Radar size={13} />} title={data.new_matches ? 'New matches since yesterday' : 'Best open matches'} count={data.new_matches || data.open_matches}>
          {matches.length ? (
            <ul>
              {matches.map((p) => (
                <Row
                  key={p.id}
                  onClick={() => openStage({ view: 'feed' })}
                  title={p.title}
                  meta={[
                    p.company,
                    p.remote ? 'Remote' : p.location,
                    p.referral_count ? `you know ${p.referral_count} there` : '',
                    REMOTE_BOARDS[p.ats] ? `via ${ATS_LABEL[p.ats]}` : '',
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                  trailing={
                    <span className="shrink-0 text-xs font-semibold tabular-nums" style={{ color: scoreColor(p.fit_score) }}>
                      {Math.round(Number(p.fit_score))}%
                    </span>
                  }
                />
              ))}
            </ul>
          ) : (
            <p className="text-xs text-muted-foreground">No matches at {data.min_match_score}%+ fit yet. Follow more companies or widen your target roles.</p>
          )}
        </Section>

        {data.drafts.length > 0 && (
          <Section
            icon={<FileCheck2 size={13} />}
            title="Ready to apply"
            count={data.drafts.length}
            action={
              <button type="button" onClick={() => openStage({ view: 'queue' })} className="rounded px-1.5 py-0.5 font-medium text-accent hover:bg-accent/10">
                Open queue
              </button>
            }
          >
            <ul>
              {data.drafts.map((d) => (
                <Row
                  key={d.id}
                  onClick={() => (d.application_id ? openStage({ view: 'detail', applicationId: d.application_id }) : openStage({ view: 'feed' }))}
                  title={d.title}
                  meta={d.company}
                  trailing={d.status === 'drafting' ? <Loader2 size={13} className="shrink-0 animate-spin text-muted-foreground" /> : undefined}
                />
              ))}
            </ul>
          </Section>
        )}

        {data.follow_ups_due.length > 0 && (
          <Section
            icon={<BellRing size={13} />}
            title="Follow-ups due"
            count={data.follow_ups_due.length}
            action={
              <button
                type="button"
                onClick={() =>
                  sendChatMessage(
                    `Draft the next follow-up email for each of these applications: ${data.follow_ups_due.map((a) => `${a.role} at ${a.company}`).join('; ')}.`,
                  )
                }
                className="rounded px-1.5 py-0.5 font-medium text-accent hover:bg-accent/10"
              >
                {data.follow_ups_due.length > 1 ? `Draft all ${data.follow_ups_due.length}` : 'Draft it'}
              </button>
            }
          >
            <ul>
              {data.follow_ups_due.map((a) => (
                <Row
                  key={a.id}
                  onClick={() => openStage({ view: 'detail', applicationId: a.id, tab: 'email' })}
                  title={a.role}
                  meta={`${a.company} · due ${formatDate(a.follow_up_at)}`}
                />
              ))}
            </ul>
          </Section>
        )}
      </div>

      <footer className="border-t bg-muted/40 px-4 py-2 text-xs text-muted-foreground">
        {auto.enabled
          ? `Auto-draft on: ${auto.remaining_today} of ${auto.daily_cap} drafts left today for matches at ${auto.min_score}%+.`
          : `${data.sources} board${data.sources === 1 ? '' : 's'} followed. Turn on auto-draft in Profile → Preferences to have top matches drafted for you.`}
      </footer>
    </div>
  );
}
