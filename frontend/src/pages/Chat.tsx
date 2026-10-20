// ============================================================
// JobPilot — Chat (agent-first home)
// Talk to the assistant; it opens applications, drafts and stats in the
// workspace panel beside the conversation.
// ============================================================

import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import { BellRing, FilePlus2, Gauge, ListChecks, PanelRight, Radar, TrendingUp } from 'lucide-react';
import { MessageList, Composer, CREATE_PREFIX } from '../components/agent/Conversation';
import { Workspace } from '../components/agent/Workspace';
import { VIEW_LABEL } from '../components/agent/ToolCards';
import { MorningBriefing } from '../components/agent/Briefing';
import { useBriefing } from '../hooks/use-discovery';
import { useChatStore } from '../agent/store';
import { sendChatMessage, stopChat } from '../agent/client';
import { useAuth } from '../hooks/use-auth';
import { useApplications } from '../hooks/use-applications';
import { useAnalyticsSummary } from '../hooks/use-analytics';
import { useResume } from '../hooks/use-profile';
import { cn } from '@/lib/utils';

interface Suggestion {
  label: string;
  prompt: string;
  icon: typeof BellRing;
  /** Put the prompt in the composer instead of sending it (it needs more input). */
  fill?: boolean;
}

function useStarter() {
  const { data: apps } = useApplications();
  const { data: summary } = useAnalyticsSummary();
  const { data: resume, isLoading } = useResume();
  const { data: briefing } = useBriefing();
  const applications = apps?.applications ?? [];
  const due = summary?.pending_follow_ups ?? 0;
  const weak = applications.filter((a) => a.status === 'saved' && (a.keyword_match_score ?? 100) < 70).length;

  const status = [
    !isLoading && resume && !resume.id ? 'No base resume yet' : null,
    due ? `${due} follow-up${due > 1 ? 's' : ''} due` : null,
    weak ? `${weak} saved application${weak > 1 ? 's' : ''} under 70% match` : null,
    applications.length ? `${applications.length} application${applications.length > 1 ? 's' : ''} tracked` : null,
  ].filter(Boolean) as string[];

  const suggestions: Suggestion[] = [
    { label: 'Create an application from a job description', prompt: CREATE_PREFIX, icon: FilePlus2, fill: true },
    due ? { label: 'Draft my due follow-ups', prompt: 'Which follow-ups are due? Draft the next email for each.', icon: BellRing } : null,
    briefing?.sources
      ? { label: 'Which new jobs suit me best?', prompt: 'Look at my job feed. Which new jobs suit me best, and why?', icon: Radar }
      : null,
    { label: 'What needs my attention today?', prompt: 'What needs my attention today?', icon: ListChecks },
    weak
      ? { label: 'Improve my weakest match', prompt: 'Which saved application has the lowest match score, and how can I improve it honestly?', icon: Gauge }
      : null,
    { label: 'How is my search going?', prompt: 'Summarise how my job search is going this week.', icon: TrendingUp },
  ].filter(Boolean) as Suggestion[];

  return { status, suggestions: suggestions.slice(0, 4) };
}

const WIDTH_KEY = 'jobpilot-workspace-width';
const clampWidth = (pct: number) => Math.min(70, Math.max(30, pct));

function readWidth() {
  try {
    const v = Number(localStorage.getItem(WIDTH_KEY));
    return Number.isFinite(v) && v > 0 ? clampWidth(v) : 50;
  } catch {
    return 50;
  }
}

export default function Chat() {
  const { user } = useAuth();
  const thread = useChatStore((s) => s.activeThread());
  const streaming = useChatStore((s) => s.streaming);
  const stage = useChatStore((s) => s.stage);
  const openStage = useChatStore((s) => s.openStage);
  const [draft, setDraft] = useState('');
  const [expanded, setExpanded] = useState(false);
  // Below xl the chat and workspace share the screen as tabs.
  const [mobileTab, setMobileTab] = useState<'chat' | 'workspace'>('chat');
  const [widthPct, setWidthPct] = useState(readWidth);
  const containerRef = useRef<HTMLDivElement>(null);

  // Drag the divider to resize the workspace; the width is remembered per browser.
  const startResize = (e: ReactPointerEvent<HTMLDivElement>) => {
    const container = containerRef.current;
    if (!container) return;
    e.preventDefault();
    const rect = container.getBoundingClientRect();
    const onMove = (ev: PointerEvent) => setWidthPct(clampWidth(((rect.right - ev.clientX) / rect.width) * 100));
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };
  const starter = useStarter();
  const firstName = (user?.user_metadata?.full_name || user?.user_metadata?.name || user?.email?.split('@')[0] || '').split(' ')[0];

  useEffect(() => {
    if (!stage) setExpanded(false);
    setMobileTab(stage ? 'workspace' : 'chat');
  }, [stage]);

  useEffect(() => {
    try {
      localStorage.setItem(WIDTH_KEY, String(Math.round(widthPct)));
    } catch {
      // Storage blocked — the width just won't persist.
    }
  }, [widthPct]);

  // Remember the last view the assistant opened so it can be reopened after closing.
  const lastView = [...thread.messages]
    .reverse()
    .flatMap((m) => [...m.parts].reverse())
    .find((p) => p.kind === 'tool' && p.name === 'open_view' && p.result?.opened);

  const retry = () => {
    const lastUser = [...thread.messages].reverse().find((m) => m.role === 'user');
    const text = lastUser?.parts.map((p) => (p.kind === 'text' ? p.text : '')).join('');
    if (text) sendChatMessage(text);
  };

  const empty = thread.messages.length === 0;

  return (
    <div ref={containerRef} className="flex h-full min-h-0 flex-col xl:flex-row">
      {stage && (
        <div className="flex shrink-0 gap-1 border-b p-1.5 xl:hidden" role="tablist" aria-label="Chat or workspace">
          {(['chat', 'workspace'] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              role="tab"
              aria-selected={mobileTab === tab}
              onClick={() => setMobileTab(tab)}
              className={cn(
                'flex-1 rounded-md py-1.5 text-sm font-medium',
                mobileTab === tab ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {tab === 'chat' ? 'Chat' : VIEW_LABEL[stage.view]}
            </button>
          ))}
        </div>
      )}
      <section
        className={cn('flex min-h-0 min-w-0 flex-1 flex-col', stage && expanded && 'xl:hidden', stage && mobileTab === 'workspace' && 'max-xl:hidden')}
        aria-label="Chat"
      >
        <header className="flex h-12 shrink-0 items-center gap-2 border-b px-4">
          <p className="min-w-0 flex-1 truncate text-sm font-medium">{empty ? 'New chat' : thread.title}</p>
          {!stage && lastView && lastView.kind === 'tool' && (
            <button
              type="button"
              onClick={() =>
                openStage({
                  view: lastView.result!.opened as never,
                  applicationId: (lastView.result!.application_id as string) || undefined,
                  tab: (lastView.result!.tab as string) || undefined,
                })
              }
              className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground"
            >
              <PanelRight size={14} />
              Workspace
            </button>
          )}
        </header>

        {empty ? (
          <div className="flex min-h-0 flex-1 flex-col items-center justify-center overflow-y-auto px-4 py-10">
            <div className="w-full max-w-2xl">
              <h1 className="text-center text-3xl font-semibold tracking-tight">
                {firstName ? `What can I help with, ${firstName}?` : 'What can I help with?'}
              </h1>
              {starter.status.length > 0 && <p className="mt-2 text-center text-sm text-muted-foreground">{starter.status.join(' · ')}</p>}
              <Composer
                className="mt-7"
                streaming={streaming}
                onSend={sendChatMessage}
                onStop={stopChat}
                draft={draft}
                onDraftChange={setDraft}
                autoFocus
              />
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {starter.suggestions.map((s) => {
                  const Icon = s.icon;
                  return (
                    <button
                      key={s.label}
                      type="button"
                      onClick={() => (s.fill ? setDraft(s.prompt) : sendChatMessage(s.prompt))}
                      disabled={streaming}
                      className="flex items-center gap-2.5 rounded-xl border bg-card px-3.5 py-3 text-left text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-50"
                    >
                      <Icon size={16} className="shrink-0" />
                      {s.label}
                    </button>
                  );
                })}
              </div>
              <MorningBriefing />
            </div>
          </div>
        ) : (
          <>
            <MessageList messages={thread.messages} streaming={streaming} onRetry={retry} />
            <div className="shrink-0 px-4 pb-4 sm:px-6">
              <Composer className="mx-auto max-w-3xl" streaming={streaming} onSend={sendChatMessage} onStop={stopChat} draft={draft} onDraftChange={setDraft} />
            </div>
          </>
        )}
      </section>

      {stage && !expanded && (
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize workspace"
          aria-valuenow={Math.round(widthPct)}
          aria-valuemin={30}
          aria-valuemax={70}
          tabIndex={0}
          onPointerDown={startResize}
          onKeyDown={(e) => {
            if (e.key === 'ArrowLeft') setWidthPct((w) => clampWidth(w + 2));
            if (e.key === 'ArrowRight') setWidthPct((w) => clampWidth(w - 2));
          }}
          className="group relative z-10 hidden w-0 cursor-col-resize xl:block"
        >
          <span className="absolute inset-y-0 -left-1 w-2 transition-colors group-hover:bg-accent/30 group-focus-visible:bg-accent/40" />
        </div>
      )}
      <Workspace expanded={expanded} onToggleExpand={() => setExpanded(!expanded)} widthPct={widthPct} mobileHidden={mobileTab === 'chat'} />
    </div>
  );
}
