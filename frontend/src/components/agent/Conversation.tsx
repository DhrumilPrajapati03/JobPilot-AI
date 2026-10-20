// ============================================================
// JobPilot — Chat conversation (messages + composer)
// ============================================================

import { Fragment, useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent } from 'react';
import { AlertCircle, ArrowUp, FileText, RotateCcw, Square } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '../ui/button';
import { Markdown } from './Markdown';
import { ActivityGroup, ToolResultCard } from './ToolCards';
import type { ChatMessage, MessagePart, ToolPart } from '../../agent/store';

const LONG_MESSAGE = 700;

function UserMessage({ message }: { message: ChatMessage }) {
  const text = message.parts.map((p) => (p.kind === 'text' ? p.text : '')).join('');
  const [expanded, setExpanded] = useState(text.length <= LONG_MESSAGE);
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] rounded-2xl bg-secondary px-4 py-2.5 text-[15px] leading-relaxed">
        <p className="whitespace-pre-wrap break-words">{expanded ? text : `${text.slice(0, LONG_MESSAGE)}…`}</p>
        {text.length > LONG_MESSAGE && (
          <button type="button" onClick={() => setExpanded(!expanded)} className="mt-1 text-xs font-medium text-muted-foreground hover:text-foreground">
            {expanded ? 'Show less' : `Show all (${text.length.toLocaleString()} characters)`}
          </button>
        )}
      </div>
    </div>
  );
}

/** Group consecutive tool parts so a burst of tool calls renders as one activity block. */
function groupParts(parts: MessagePart[]) {
  const groups: ({ kind: 'text'; text: string } | { kind: 'tools'; parts: ToolPart[] })[] = [];
  for (const part of parts) {
    const last = groups[groups.length - 1];
    if (part.kind === 'tool') {
      if (last?.kind === 'tools') last.parts.push(part);
      else groups.push({ kind: 'tools', parts: [part] });
    } else if (part.text.trim()) {
      groups.push({ kind: 'text', text: part.text });
    }
  }
  return groups;
}

function AssistantMessage({ message, streaming, onRetry }: { message: ChatMessage; streaming: boolean; onRetry?: () => void }) {
  const groups = groupParts(message.parts);
  return (
    <div className="space-y-3">
      {groups.length === 0 && streaming && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <span className="h-2 w-2 animate-soft-pulse rounded-full bg-foreground/60" aria-hidden />
          Thinking…
        </p>
      )}
      {groups.map((group, i) =>
        group.kind === 'text' ? (
          <Markdown key={i} text={group.text} />
        ) : (
          <Fragment key={i}>
            <ActivityGroup parts={group.parts} />
            {group.parts.map((part) => (
              <ToolResultCard key={part.id} part={part} />
            ))}
          </Fragment>
        ),
      )}
      {message.error && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          <AlertCircle size={15} />
          <span className="flex-1">{message.error}</span>
          {onRetry && (
            <Button size="sm" variant="outline" className="h-7" onClick={onRetry}>
              <RotateCcw size={13} className="mr-1" />
              Retry
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

export function MessageList({ messages, streaming, onRetry }: { messages: ChatMessage[]; streaming: boolean; onRetry: () => void }) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  const onScroll = () => {
    const el = scrollRef.current;
    if (el) stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  };

  // Follow the stream while the reader is at the bottom; don't pull them back if they scrolled up.
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  });

  const lastId = messages[messages.length - 1]?.id;
  return (
    <div ref={scrollRef} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto" aria-live="polite">
      <div className="mx-auto max-w-3xl space-y-7 px-4 py-6 sm:px-6">
        {messages.map((m) =>
          m.role === 'user' ? (
            <UserMessage key={m.id} message={m} />
          ) : (
            <AssistantMessage key={m.id} message={m} streaming={streaming && m.id === lastId} onRetry={m.id === lastId ? onRetry : undefined} />
          ),
        )}
      </div>
    </div>
  );
}

export const CREATE_PREFIX = 'Create an application for this job:\n\n';

export function Composer({
  streaming,
  onSend,
  onStop,
  draft,
  onDraftChange,
  autoFocus,
  className,
}: {
  streaming: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
  draft: string;
  onDraftChange: (text: string) => void;
  autoFocus?: boolean;
  className?: string;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 260)}px`;
  }, [draft]);

  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus]);

  const send = () => {
    if (!draft.trim() || streaming) return;
    onSend(draft);
    onDraftChange('');
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  };

  const looksLikeJD = draft.length > 400 && !draft.startsWith(CREATE_PREFIX) && !/\?\s*$/.test(draft.trim());

  return (
    <div className={className}>
      {looksLikeJD && (
        <button
          type="button"
          onClick={() => onDraftChange(CREATE_PREFIX + draft)}
          className="mb-2 inline-flex items-center gap-1.5 rounded-full border bg-card px-3 py-1 text-xs font-medium hover:bg-secondary"
        >
          <FileText size={13} />
          Looks like a job description — create an application from it?
        </button>
      )}
      <div className="rounded-2xl border bg-card p-2 shadow-sm transition-shadow focus-within:border-foreground/30 focus-within:shadow-md">
        <label htmlFor="chat-input" className="sr-only">
          Message JobPilot
        </label>
        <textarea
          id="chat-input"
          ref={ref}
          rows={1}
          value={draft}
          onChange={(e) => onDraftChange(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask anything, or paste a job description…"
          className="max-h-64 min-h-[44px] w-full resize-none bg-transparent px-2.5 py-2 text-[15px] leading-relaxed placeholder:text-muted-foreground focus:outline-none"
        />
        <div className="flex items-center justify-between gap-2 px-1">
          <span className="text-[11px] text-muted-foreground">Changes always ask for your approval</span>
          {streaming ? (
            <Button type="button" variant="outline" size="icon" className="h-8 w-8 rounded-full" onClick={onStop} aria-label="Stop" title="Stop">
              <Square size={12} className="fill-current" />
            </Button>
          ) : (
            <Button
              type="button"
              size="icon"
              className={cn('h-8 w-8 rounded-full')}
              onClick={send}
              disabled={!draft.trim()}
              aria-label="Send"
              title="Send (Enter)"
            >
              <ArrowUp size={16} />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
