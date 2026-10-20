// ============================================================
// JobPilot — Skill-gap insights (shared by Analytics and chat)
// ============================================================

import { CheckCircle2, Wrench } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { SkillGaps } from '../../hooks/use-analytics';

function BarRow({
  label,
  share,
  detail,
  tag,
  title,
}: {
  label: string;
  share: number;
  detail: string;
  tag?: { text: string; tone: 'accent' | 'muted' };
  title?: string;
}) {
  return (
    <li className="grid grid-cols-[minmax(80px,140px)_1fr_150px] items-center gap-3 py-1" title={title}>
      <span className="truncate text-sm">{label}</span>
      <span className="relative h-2 overflow-hidden rounded-full bg-secondary" aria-hidden>
        <span className="absolute inset-y-0 left-0 rounded-full bg-foreground/70" style={{ width: `${Math.max(share, 3)}%` }} />
      </span>
      <span className="flex items-center justify-end gap-2 text-xs tabular-nums text-muted-foreground">
        {detail}
        {tag && (
          <span
            className={cn(
              'inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium',
              tag.tone === 'accent' ? 'bg-accent/10 text-accent' : 'bg-secondary text-muted-foreground',
            )}
          >
            {tag.tone === 'accent' ? <Wrench size={10} /> : null}
            {tag.text}
          </span>
        )}
      </span>
    </li>
  );
}

export function SkillGapsView({ data, compact }: { data: SkillGaps; compact?: boolean }) {
  const gaps = compact ? data.gaps.slice(0, 5) : data.gaps;
  const requested = compact ? [] : data.most_requested;
  const quickFixes = data.gaps.filter((g) => g.in_base_resume);
  const top = data.gaps.find((g) => !g.in_base_resume);

  if (!data.applications_analyzed) {
    return <p className="text-sm text-muted-foreground">Skill gaps appear once you've created a few tailored applications.</p>;
  }

  return (
    <div className="space-y-5">
      <p className="text-sm text-muted-foreground">
        Across {data.applications_analyzed} tailored application{data.applications_analyzed > 1 ? 's' : ''}
        {top ? (
          <>
            , <span className="font-medium text-foreground">{top.keyword}</span> is your most common real gap (missing in {Math.round(top.share)}%)
          </>
        ) : null}
        .{' '}
        {quickFixes.length > 0 && (
          <>
            {quickFixes.length} gap{quickFixes.length > 1 ? 's are' : ' is'} already in your base resume — a tailoring fix, not a skill to learn.
          </>
        )}
      </p>

      <div>
        <p className="mb-1.5 text-xs font-medium text-muted-foreground">Missing from your tailored resumes · share of applications</p>
        <ul>
          {gaps.map((g) => (
            <BarRow
              key={g.keyword}
              label={g.keyword}
              share={g.share}
              detail={`${g.count} of ${data.applications_analyzed}`}
              tag={g.in_base_resume ? { text: 'In your resume', tone: 'accent' } : undefined}
              title={g.examples.length ? `e.g. ${g.examples.join(', ')}` : undefined}
            />
          ))}
        </ul>
      </div>

      {requested.length > 0 && (
        <div>
          <p className="mb-1.5 text-xs font-medium text-muted-foreground">Most requested by your target jobs · share of jobs</p>
          <ul>
            {requested.map((r) => (
              <li key={r.skill} className="grid grid-cols-[minmax(80px,140px)_1fr_150px] items-center gap-3 py-1">
                <span className="truncate text-sm">{r.skill}</span>
                <span className="relative h-2 overflow-hidden rounded-full bg-secondary" aria-hidden>
                  <span className="absolute inset-y-0 left-0 rounded-full bg-foreground/70" style={{ width: `${Math.max(r.share, 3)}%` }} />
                </span>
                <span className="flex items-center justify-end gap-1.5 text-xs tabular-nums text-muted-foreground">
                  {Math.round(r.share)}%
                  {r.you_have ? (
                    <span className="inline-flex items-center gap-0.5 text-accent">
                      <CheckCircle2 size={11} />
                      You have it
                    </span>
                  ) : (
                    <span>Not in resume</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
