// ============================================================
// JobPilot — Workspace panel: views the assistant opens beside the chat
// ============================================================

import { Suspense } from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink, Loader2, Maximize2, Minimize2, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatStore, type StageState } from '../../agent/store';
import { VIEW_LABEL } from './ToolCards';
import * as Pages from '../../pages/lazy';

function routeFor(stage: StageState) {
  switch (stage.view) {
    case 'applications':
      return '/applications';
    case 'detail':
      return `/applications/${stage.applicationId}${stage.tab ? `?tab=${stage.tab}` : ''}`;
    case 'analytics':
      return '/analytics';
    case 'new':
      return '/applications/new';
    case 'profile':
      return '/profile';
    case 'feed':
      return '/jobs';
    case 'network':
      return '/network';
    case 'queue':
      return '/apply';
  }
}

function StageContent({ stage }: { stage: StageState }) {
  switch (stage.view) {
    case 'detail':
      return stage.applicationId ? (
        <Pages.ApplicationDetail applicationId={stage.applicationId} initialTab={stage.tab} embedded />
      ) : (
        <Pages.Applications />
      );
    case 'applications':
      return <Pages.Applications />;
    case 'analytics':
      return <Pages.Analytics />;
    case 'new':
      return <Pages.NewApplication />;
    case 'profile':
      return <Pages.Profile />;
    case 'feed':
      return <Pages.JobFeed embedded />;
    case 'network':
      return <Pages.Network />;
    case 'queue':
      return <Pages.ApplyQueue embedded />;
  }
}

export function Workspace({
  expanded,
  onToggleExpand,
  widthPct,
  mobileHidden = false,
}: {
  expanded: boolean;
  onToggleExpand: () => void;
  widthPct: number;
  /** Below xl the workspace is a tab beside the chat; hidden while the chat tab is showing. */
  mobileHidden?: boolean;
}) {
  const stage = useChatStore((s) => s.stage);
  const closeStage = useChatStore((s) => s.closeStage);
  if (!stage) return null;

  return (
    <aside
      className={cn(
        'flex min-h-0 min-w-0 flex-1 flex-col bg-background xl:border-l',
        expanded ? 'xl:flex-[2.5]' : 'xl:w-[var(--workspace-width)] xl:flex-none',
        mobileHidden && 'max-xl:hidden',
      )}
      style={{ ['--workspace-width' as string]: `${widthPct}%` }}
      aria-label={`${VIEW_LABEL[stage.view]} workspace`}
    >
      <header className="flex h-12 shrink-0 items-center gap-1 border-b px-3">
        <p className="min-w-0 flex-1 truncate pl-1 text-sm font-medium">{VIEW_LABEL[stage.view]}</p>
        <Link
          to={routeFor(stage)}
          className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
          title="Open as a full page"
          aria-label="Open as a full page"
        >
          <ExternalLink size={15} />
        </Link>
        <button
          type="button"
          onClick={onToggleExpand}
          className="hidden rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground xl:block"
          title={expanded ? 'Restore' : 'Expand'}
          aria-label={expanded ? 'Restore workspace width' : 'Expand workspace'}
        >
          {expanded ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
        </button>
        <button
          type="button"
          onClick={closeStage}
          className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
          title="Close"
          aria-label="Close workspace"
        >
          <X size={15} />
        </button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-5">
        <Suspense
          fallback={
            <div className="flex h-40 items-center justify-center">
              <Loader2 className="animate-spin text-muted-foreground" size={20} />
            </div>
          }
        >
          <div key={stage.key} className="@container">
            <StageContent stage={stage} />
          </div>
        </Suspense>
      </div>
    </aside>
  );
}
