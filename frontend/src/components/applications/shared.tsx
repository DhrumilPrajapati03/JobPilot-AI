// ============================================================
// JobPilot AI — Shared application UI (status, score, copy)
// ============================================================

import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { Button } from '../ui/button';
import { cn } from '@/lib/utils';
import { APPLICATION_STATUS_CONFIG, KANBAN_COLUMNS } from '../../lib/constants';
import type { ApplicationStatus } from '../../hooks/use-applications';

export function StatusBadge({ status, className }: { status: ApplicationStatus; className?: string }) {
  const config = APPLICATION_STATUS_CONFIG[status] ?? APPLICATION_STATUS_CONFIG.saved;
  return (
    <span
      className={cn('inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold', className)}
      style={{ color: config.color, backgroundColor: config.bgColor }}
    >
      {config.label}
    </span>
  );
}

export function StatusSelect({
  value,
  onChange,
  disabled,
}: {
  value: ApplicationStatus;
  onChange: (status: ApplicationStatus) => void;
  disabled?: boolean;
}) {
  const config = APPLICATION_STATUS_CONFIG[value];
  return (
    <select
      aria-label="Application status"
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value as ApplicationStatus)}
      className="h-9 rounded-md border border-input px-3 text-sm font-semibold focus:outline-none focus:ring-1 focus:ring-ring cursor-pointer disabled:opacity-60"
      style={{ color: config?.color, backgroundColor: config?.bgColor }}
    >
      {KANBAN_COLUMNS.map((status) => (
        <option key={status} value={status} className="bg-card text-foreground">
          {APPLICATION_STATUS_CONFIG[status].label}
        </option>
      ))}
    </select>
  );
}

/** Keyword match score with a traffic-light color. */
export function ScoreBadge({ score, className }: { score: number | null | undefined; className?: string }) {
  if (score === null || score === undefined) return null;
  const tone =
    score >= 80
      ? 'bg-accent/10 text-accent border-accent/20'
      : score >= 60
        ? 'bg-warning/10 text-warning border-warning/25'
        : 'bg-destructive/10 text-destructive border-destructive/25';
  return (
    <span
      className={cn('inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-bold tabular-nums', tone, className)}
      title="ATS keyword match"
    >
      {Math.round(score)}% match
    </span>
  );
}

export function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard blocked (insecure context) — nothing useful to do.
    }
  };
  return (
    <Button type="button" variant="outline" size="sm" onClick={copy} disabled={!text}>
      {copied ? <Check size={14} className="mr-1.5" /> : <Copy size={14} className="mr-1.5" />}
      {copied ? 'Copied' : label}
    </Button>
  );
}

export function formatDate(value: string | null | undefined, withYear = false) {
  if (!value) return '';
  return new Date(value).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    ...(withYear ? { year: 'numeric' } : {}),
  });
}

export function daysSince(value: string | null | undefined) {
  if (!value) return null;
  return Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 86_400_000));
}

export function isOverdue(value: string | null | undefined) {
  return !!value && new Date(value).getTime() <= Date.now();
}

export function scoreColor(score: number | null | undefined) {
  if (score === null || score === undefined) return 'var(--muted-foreground)';
  return score >= 80 ? 'var(--accent)' : score >= 60 ? 'var(--warning)' : 'var(--destructive)';
}

/** Compact score ring (ATS keyword match unless `label` says otherwise). */
export function ScoreRing({ score, size = 56, label }: { score: number | null | undefined; size?: number; label?: string }) {
  const pct = Math.max(0, Math.min(100, Math.round(score ?? 0)));
  return (
    <div
      className="relative grid shrink-0 place-items-center rounded-full"
      style={{ width: size, height: size, background: `conic-gradient(${scoreColor(score)} ${pct * 3.6}deg, var(--secondary) 0deg)` }}
      role="img"
      aria-label={label ?? (score === null || score === undefined ? 'No match score' : `${pct}% keyword match`)}
    >
      <div className="grid place-items-center rounded-full bg-card" style={{ width: size - 10, height: size - 10 }}>
        <span className="text-xs font-semibold tabular-nums">{score === null || score === undefined ? '—' : `${pct}%`}</span>
      </div>
    </div>
  );
}
