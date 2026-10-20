// ============================================================
// JobPilot AI — Analytics Page
// ============================================================

import { BarChart3, Loader2, Mail, Percent, Target, TrendingUp } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { useAnalyticsSummary, useSkillGaps, type AnalyticsSummary } from '../hooks/use-analytics';
import { SkillGapsView } from '../components/applications/SkillGaps';
import { formatDate } from '../components/applications/shared';

/** Funnel: how many applications reached at least each stage. */
function funnelStages(summary: AnalyticsSummary) {
  const b = summary.status_breakdown;
  return [
    { label: 'Generated', value: summary.total_applications },
    { label: 'Applied', value: summary.submitted },
    { label: 'Heard back', value: b.interviewing + b.offer + b.rejected },
    { label: 'Interviewing', value: b.interviewing + b.offer },
    { label: 'Offer', value: b.offer },
  ];
}

function FunnelChart({ summary }: { summary: AnalyticsSummary }) {
  const stages = funnelStages(summary);
  const max = Math.max(1, stages[0].value);
  return (
    <div className="space-y-2.5" role="list" aria-label="Application funnel">
      {stages.map((stage, i) => {
        const prev = i > 0 ? stages[i - 1].value : null;
        const conversion = prev ? Math.round((stage.value / prev) * 100) : null;
        return (
          <div key={stage.label} role="listitem" className="group grid grid-cols-[96px_1fr_88px] items-center gap-3">
            <span className="text-xs font-medium text-muted-foreground">{stage.label}</span>
            <div className="relative h-5 rounded-r bg-secondary/70">
              <div
                className="h-full rounded-r-[4px] bg-primary transition-[width] duration-500 group-hover:bg-primary/85"
                style={{ width: `${(stage.value / max) * 100}%`, minWidth: stage.value ? 4 : 0 }}
              />
              <span className="pointer-events-none absolute -top-8 left-0 z-10 hidden whitespace-nowrap rounded-md border bg-card px-2 py-1 text-xs text-foreground shadow-md group-hover:block">
                {stage.label}: <strong>{stage.value}</strong>
                {conversion !== null && ` · ${conversion}% of previous stage`}
              </span>
            </div>
            <span className="text-right text-xs tabular-nums text-foreground">
              <strong>{stage.value}</strong>
              {conversion !== null && <span className="text-muted-foreground"> · {conversion}%</span>}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function WeeklyChart({ weeks }: { weeks: AnalyticsSummary['weekly_applications'] }) {
  const max = Math.max(1, ...weeks.map((w) => w.count));
  return (
    <div>
      <div className="flex h-44 items-end gap-[2px] border-b border-border" role="list" aria-label="Applications per week">
        {weeks.map((week) => (
          <div key={week.week} role="listitem" className="group relative flex h-full flex-1 items-end justify-center">
            <div
              className="w-full max-w-[36px] rounded-t-[4px] bg-primary group-hover:bg-primary/85"
              style={{ height: `${(week.count / max) * 100}%`, minHeight: week.count ? 4 : 0 }}
            />
            <span className="pointer-events-none absolute bottom-full z-10 mb-1 hidden whitespace-nowrap rounded-md border bg-card px-2 py-1 text-xs text-foreground shadow-md group-hover:block">
              Week of {formatDate(week.week)}: <strong>{week.count}</strong>
            </span>
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex gap-[2px]">
        {weeks.map((week, i) => (
          <span key={week.week} className="flex-1 text-center text-[10px] text-muted-foreground">
            {i % 2 === weeks.length % 2 ? formatDate(week.week) : ''}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function Analytics() {
  const { data: summary, isLoading } = useAnalyticsSummary();
  const { data: skillGaps } = useSkillGaps();

  if (isLoading || !summary) {
    return (
      <div className="flex h-[40vh] items-center justify-center gap-2 text-muted-foreground">
        <Loader2 className="animate-spin" size={20} />
        <span className="text-sm">Crunching numbers…</span>
      </div>
    );
  }

  const stats = [
    { label: 'Total applications', value: `${summary.total_applications}`, icon: BarChart3 },
    { label: 'Response rate', value: summary.submitted ? `${summary.response_rate}%` : '—', icon: TrendingUp },
    { label: 'Interview rate', value: summary.submitted ? `${summary.interview_rate}%` : '—', icon: Target },
    { label: 'Avg ATS score', value: summary.avg_keyword_score === null ? '—' : `${summary.avg_keyword_score}%`, icon: Percent },
    { label: 'Email reply rate', value: summary.emails_sent ? `${summary.email_reply_rate}%` : '—', icon: Mail },
  ];

  return (
    <div className="page-analytics">
      <div className="analytics-header">
        <h2>Analytics</h2>
        <p className="text-muted">Rates are measured against applications you've marked as applied.</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 @4xl:grid-cols-5">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <Card key={stat.label} className="p-4">
              <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                <Icon size={15} className="text-accent" />
                {stat.label}
              </div>
              <p className="mt-2 text-2xl font-bold tabular-nums text-foreground">{stat.value}</p>
            </Card>
          );
        })}
      </div>

      {summary.total_applications === 0 ? (
        <Card className="p-10 text-center text-sm text-muted-foreground">
          Charts appear once you've generated your first application.
        </Card>
      ) : (
        <div className="grid gap-4 @4xl:grid-cols-2">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Application funnel</CardTitle>
              <p className="text-xs text-muted-foreground">Applications reaching each stage · % converted from the stage above</p>
            </CardHeader>
            <CardContent>
              <FunnelChart summary={summary} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Applications per week</CardTitle>
              <p className="text-xs text-muted-foreground">Last 8 weeks, by date generated</p>
            </CardHeader>
            <CardContent>
              <WeeklyChart weeks={summary.weekly_applications} />
            </CardContent>
          </Card>
          <Card className="@4xl:col-span-2">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Skill gaps</CardTitle>
              <p className="text-xs text-muted-foreground">What your target jobs ask for, and what your tailored resumes miss</p>
            </CardHeader>
            <CardContent>
              {skillGaps ? <SkillGapsView data={skillGaps} /> : <p className="text-sm text-muted-foreground">Loading…</p>}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
