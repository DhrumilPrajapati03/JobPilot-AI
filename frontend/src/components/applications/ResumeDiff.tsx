// ============================================================
// JobPilot — Base vs tailored resume diff
// Word-level changes, JD keywords highlighted, and a warning for any
// skill that appears in neither the base resume nor the job description.
// ============================================================

import { Fragment, type ReactNode } from 'react';
import { AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Resume } from '../../hooks/use-profile';

type Op = { kind: 'same' | 'add' | 'del'; text: string };

const tokenize = (s: string) => (s ?? '').split(/(\s+)/).filter((t) => t.length > 0);
const norm = (s: string) => s.toLowerCase().replace(/[^\p{L}\p{N}+#.]/gu, '').replace(/\.$/, '');

/** Word-level LCS diff (whitespace tokens kept so text reflows naturally). */
export function diffWords(before: string, after: string): Op[] {
  const a = tokenize(before);
  const b = tokenize(after);
  const dp = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--) dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const ops: Op[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) ops.push({ kind: 'same', text: a[i++] }), j++;
    else if (dp[i + 1][j] >= dp[i][j + 1]) ops.push({ kind: 'del', text: a[i++] });
    else ops.push({ kind: 'add', text: b[j++] });
  }
  while (i < a.length) ops.push({ kind: 'del', text: a[i++] });
  while (j < b.length) ops.push({ kind: 'add', text: b[j++] });
  return ops;
}

function similarity(a: string, b: string) {
  const A = new Set(tokenize(a).map(norm).filter(Boolean));
  const B = new Set(tokenize(b).map(norm).filter(Boolean));
  if (!A.size || !B.size) return 0;
  let shared = 0;
  A.forEach((w) => B.has(w) && shared++);
  return shared / (A.size + B.size - shared);
}

function DiffText({ before, after, keywords }: { before: string; after: string; keywords: Set<string> }) {
  const ops = diffWords(before, after);
  return (
    <span className="leading-relaxed">
      {ops.map((op, i) => {
        if (/^\s+$/.test(op.text)) return op.kind === 'del' ? null : <Fragment key={i}>{op.text}</Fragment>;
        if (op.kind === 'same') return <Fragment key={i}>{op.text}</Fragment>;
        if (op.kind === 'del') return <del key={i} className="rounded-sm bg-destructive/10 text-destructive/80 decoration-destructive/50">{op.text} </del>;
        const isKeyword = keywords.has(norm(op.text));
        return (
          <ins key={i} className={cn('rounded-sm bg-accent/12 text-accent no-underline', isKeyword && 'font-semibold underline decoration-accent/50 underline-offset-2')}>
            {op.text}
          </ins>
        );
      })}
    </span>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
      {children}
    </section>
  );
}

/** Pair each tailored bullet with its most similar base bullet (greedy). */
function pairBullets(base: string[], tailored: string[]) {
  const used = new Set<number>();
  const pairs = tailored.map((t) => {
    let best = -1;
    let bestScore = 0.2; // below this a bullet counts as new
    base.forEach((b, i) => {
      if (used.has(i)) return;
      const s = similarity(b, t);
      if (s > bestScore) [best, bestScore] = [i, s];
    });
    if (best >= 0) used.add(best);
    return { tailored: t, base: best >= 0 ? base[best] : null };
  });
  const removed = base.filter((_, i) => !used.has(i));
  return { pairs, removed };
}

export function ResumeDiff({ base, tailored, keywords }: { base: Resume; tailored: Resume; keywords: string[] }) {
  const kw = new Set(keywords.flatMap((k) => k.split(/\s+/)).map(norm).filter(Boolean));
  const kwPhrases = new Set(keywords.map((k) => k.toLowerCase().trim()));
  const baseSkills = [...base.skills.primary, ...base.skills.secondary];
  const baseSkillSet = new Set(baseSkills.map((s) => s.toLowerCase().trim()));
  const tailoredSkills = [...tailored.skills.primary, ...tailored.skills.secondary];
  const tailoredSkillSet = new Set(tailoredSkills.map((s) => s.toLowerCase().trim()));
  const unsupported = tailoredSkills.filter((s) => !baseSkillSet.has(s.toLowerCase().trim()) && !kwPhrases.has(s.toLowerCase().trim()));

  return (
    <div className="space-y-6 rounded-xl border bg-card p-5 text-sm">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span>
          <ins className="rounded-sm bg-accent/12 px-1 text-accent no-underline">added</ins>
        </span>
        <span>
          <del className="rounded-sm bg-destructive/10 px-1 text-destructive/80">removed</del>
        </span>
        <span>
          <ins className="rounded-sm bg-accent/12 px-1 font-semibold text-accent underline decoration-accent/50 underline-offset-2">job keyword</ins>
        </span>
      </div>

      {unsupported.length > 0 && (
        <p className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/5 px-3 py-2 text-xs">
          <AlertTriangle size={14} className="mt-0.5 shrink-0 text-warning" />
          <span>
            <span className="font-medium">Check these skills:</span> {unsupported.join(', ')} — they're not in your base resume or the job description. Remove
            them unless they're true.
          </span>
        </p>
      )}

      {(base.headline || tailored.headline) && (
        <Section title="Headline">
          <DiffText before={base.headline} after={tailored.headline} keywords={kw} />
        </Section>
      )}

      <Section title="Summary">
        <DiffText before={base.summary} after={tailored.summary} keywords={kw} />
      </Section>

      {tailored.experience.length > 0 && (
        <Section title="Experience">
          <div className="space-y-4">
            {tailored.experience.map((job, i) => {
              const baseJob =
                base.experience.find((b) => b.company.toLowerCase() === job.company.toLowerCase() && b.role.toLowerCase() === job.role.toLowerCase()) ??
                base.experience[i];
              const { pairs, removed } = pairBullets(baseJob?.bullets ?? [], job.bullets);
              return (
                <div key={i}>
                  <p className="font-medium">
                    {job.role} · <span className="font-normal text-muted-foreground">{job.company}</span>
                  </p>
                  <ul className="mt-1.5 list-disc space-y-1.5 pl-5">
                    {pairs.map((p, j) => (
                      <li key={j}>
                        {p.base === null && <span className="mr-1.5 rounded bg-accent/12 px-1 text-[10px] font-semibold uppercase text-accent">New</span>}
                        <DiffText before={p.base ?? ''} after={p.tailored} keywords={kw} />
                      </li>
                    ))}
                    {removed.map((b, j) => (
                      <li key={`r${j}`} className="text-muted-foreground">
                        <span className="mr-1.5 rounded bg-destructive/10 px-1 text-[10px] font-semibold uppercase text-destructive">Removed</span>
                        <del className="decoration-destructive/40">{b}</del>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        </Section>
      )}

      <Section title="Skills">
        <div className="flex flex-wrap gap-1.5">
          {tailoredSkills.map((s) => {
            const isNew = !baseSkillSet.has(s.toLowerCase().trim());
            const isUnsupported = unsupported.includes(s);
            return (
              <span
                key={s}
                className={cn(
                  'rounded-md border px-2 py-0.5 text-xs',
                  isUnsupported ? 'border-warning/40 bg-warning/10 text-warning' : isNew ? 'border-accent/30 bg-accent/10 text-accent' : 'bg-secondary',
                )}
                title={isUnsupported ? 'Not in your base resume or the job description' : isNew ? 'Added for this job' : undefined}
              >
                {isNew && '+ '}
                {s}
              </span>
            );
          })}
          {baseSkills
            .filter((s) => !tailoredSkillSet.has(s.toLowerCase().trim()))
            .map((s) => (
              <del key={s} className="rounded-md border border-dashed px-2 py-0.5 text-xs text-muted-foreground">
                {s}
              </del>
            ))}
        </div>
      </Section>

      {tailored.projects.length > 0 && (
        <Section title="Projects">
          <ul className="space-y-1.5">
            {tailored.projects.map((p, i) => {
              const baseProject = base.projects.find((b) => b.name === p.name);
              return (
                <li key={i}>
                  <span className="font-medium">{p.name}: </span>
                  <DiffText before={baseProject?.description ?? ''} after={p.description} keywords={kw} />
                </li>
              );
            })}
          </ul>
        </Section>
      )}
    </div>
  );
}
