// ============================================================
// JobPilot AI — Application Detail Page
// ============================================================

import { useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  BellRing,
  Briefcase,
  Building2,
  CalendarClock,
  CheckCircle2,
  ExternalLink,
  FileText,
  Loader2,
  Mail,
  MessageSquare,
  ScrollText,
  Trash2,
  Users,
  XCircle,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { ReferralPanel } from '../components/applications/ReferralPanel';
import { ExecutionEvidence } from '../components/applications/ExecutionEvidence';
import { useReferrals } from '../hooks/use-network';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { ResumeTab } from '../components/applications/ResumeTab';
import { CoverLetterPanel, EmailPanel, LinkedInPanel } from '../components/applications/OutreachPanels';
import { ScoreBadge, StatusSelect, formatDate, isOverdue } from '../components/applications/shared';
import { useDraft } from '../hooks/use-draft';
import {
  useApplicationDetail,
  useDeleteApplication,
  useUpdateApplication,
  useUpdateApplicationStatus,
  type ApplicationDetails,
  type JobApplication,
  type TailoredResume,
} from '../hooks/use-applications';
import { APPLICATION_STATUS_CONFIG } from '../lib/constants';
import { cn } from '@/lib/utils';

function MatchCard({ application, tailored }: { application: JobApplication; tailored: TailoredResume | null }) {
  const score = tailored?.keyword_match_score ?? null;
  const missing = new Set((tailored?.missing_keywords ?? []).map((k) => k.toLowerCase()));
  const skills = application.jd_analysis?.required_skills ?? [];
  const missingExtra = (tailored?.missing_keywords ?? []).filter(
    (k) => !skills.some((s) => s.toLowerCase() === k.toLowerCase()),
  );
  const pct = Math.round(score ?? 0);
  const ring = pct >= 80 ? 'var(--color-accent)' : pct >= 60 ? '#d97706' : 'var(--color-warning)';

  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="text-sm">ATS keyword match</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 p-4 pt-0">
        <div className="flex items-center gap-4">
          <div
            className="relative grid h-20 w-20 shrink-0 place-items-center rounded-full"
            style={{ background: `conic-gradient(${ring} ${pct * 3.6}deg, var(--color-muted) 0deg)` }}
            role="img"
            aria-label={`${pct}% keyword match`}
          >
            <div className="grid h-16 w-16 place-items-center rounded-full bg-card">
              <span className="text-xl font-bold tabular-nums text-primary">{score === null ? '—' : `${pct}%`}</span>
            </div>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Share of the job's required skills and keywords that appear in your tailored resume. Aim for 80%+.
          </p>
        </div>

        {skills.length > 0 && (
          <div>
            <p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Required skills</p>
            <div className="flex flex-wrap gap-1.5">
              {skills.map((skill) => {
                const isMissing = missing.has(skill.toLowerCase());
                return (
                  <span
                    key={skill}
                    className={cn(
                      'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium',
                      isMissing
                        ? 'border-warning/30 bg-warning/5 text-warning'
                        : 'border-accent/30 bg-accent/5 text-accent',
                    )}
                  >
                    {isMissing ? <XCircle size={11} /> : <CheckCircle2 size={11} />}
                    {skill}
                  </span>
                );
              })}
            </div>
          </div>
        )}

        {missingExtra.length > 0 && (
          <div>
            <p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Other missing keywords</p>
            <div className="flex flex-wrap gap-1.5">
              {missingExtra.map((kw) => (
                <span key={kw} className="rounded border bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                  {kw}
                </span>
              ))}
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              Only add these if they're true for you — edit the resume and save to re-score.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

interface TimelineEvent {
  at: string;
  label: string;
  tone: 'default' | 'accent' | 'warning' | 'upcoming';
}

function buildTimeline({ application, cold_emails }: ApplicationDetails): TimelineEvent[] {
  const events: TimelineEvent[] = [{ at: application.created_at, label: 'Materials generated', tone: 'default' }];
  if (application.applied_at) events.push({ at: application.applied_at, label: 'Application marked applied (user reported)', tone: 'accent' });
  cold_emails.forEach((email) => {
    if (email.sent_at) {
      events.push({
        at: email.sent_at,
          label: `${email.sequence_number === 1 ? 'Cold email' : `Follow-up ${email.sequence_number - 1}`} manually marked sent${
          email.replied ? ' · replied' : ''
        }`,
        tone: email.replied ? 'accent' : 'default',
      });
    }
  });
  if (['interviewing', 'offer', 'rejected'].includes(application.status) && application.updated_at) {
    events.push({
      at: application.updated_at,
      label: `Moved to ${APPLICATION_STATUS_CONFIG[application.status].label}`,
      tone: application.status === 'rejected' ? 'warning' : 'accent',
    });
  }
  if (application.follow_up_at && application.status === 'applied') {
    events.push({
      at: application.follow_up_at,
      label: isOverdue(application.follow_up_at) ? 'Follow-up overdue' : 'Follow-up due',
      tone: isOverdue(application.follow_up_at) ? 'warning' : 'upcoming',
    });
  }
  return events.sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime());
}

const TONE_DOT: Record<TimelineEvent['tone'], string> = {
  default: 'bg-primary',
  accent: 'bg-accent',
  warning: 'bg-warning',
  upcoming: 'border-2 border-primary bg-card',
};

function TimelineCard({ details }: { details: ApplicationDetails }) {
  const events = buildTimeline(details);
  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="text-sm">Timeline</CardTitle>
      </CardHeader>
      <CardContent className="p-4 pt-1">
        <ol className="relative space-y-3 border-l border-border pl-4">
          {events.map((event, i) => (
            <li key={i} className="relative">
              <span className={cn('absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full', TONE_DOT[event.tone])} />
              <p className={cn('text-sm font-medium', event.tone === 'warning' && 'text-warning')}>{event.label}</p>
              <p className="text-xs text-muted-foreground">{formatDate(event.at, true)}</p>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}

function NotesCard({ application }: { application: JobApplication }) {
  const { draft, setDraft, dirty } = useDraft(application.notes || '');
  const followUp = application.follow_up_at ? application.follow_up_at.slice(0, 10) : '';
  const update = useUpdateApplication(application.id);

  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="text-sm">Notes & follow-up</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 p-4 pt-0">
        <div className="space-y-1.5">
          <label htmlFor="follow-up-date" className="text-xs font-semibold text-muted-foreground">
            Follow-up reminder
          </label>
          <Input
            id="follow-up-date"
            type="date"
            value={followUp}
            onChange={(e) =>
              update.mutate({ follow_up_at: e.target.value ? new Date(`${e.target.value}T09:00:00`).toISOString() : null })
            }
          />
        </div>
        <Textarea
          aria-label="Notes"
          rows={5}
          placeholder="Recruiter name, referral, interview prep…"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => dirty && update.mutate({ notes: draft })}
        />
        <p className="text-xs text-muted-foreground">
          {update.isPending ? 'Saving…' : update.error ? update.error.message : dirty ? 'Unsaved — click outside to save' : 'Saved'}
        </p>
      </CardContent>
    </Card>
  );
}

function JobDescriptionPanel({ application }: { application: JobApplication }) {
  const analysis = application.jd_analysis;
  const groups: [string, string[]][] = [
    ['Required skills', analysis?.required_skills ?? []],
    ['Tech stack', analysis?.tech_stack ?? []],
    ['Keywords', analysis?.keywords ?? []],
  ];
  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="grid gap-4 p-5 sm:grid-cols-4">
          {[
            ['Seniority', analysis?.seniority || '—'],
            ['Work style', analysis?.remote === null || analysis?.remote === undefined ? '—' : analysis.remote ? 'Remote' : 'Hybrid / onsite'],
            ['Salary', analysis?.salary_range || 'Not listed'],
            ['Tone', analysis?.tone || '—'],
          ].map(([label, value]) => (
            <div key={label}>
              <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{label}</p>
              <p className="mt-1 text-sm font-semibold capitalize">{value}</p>
            </div>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardContent className="space-y-4 p-5">
          {groups
            .filter(([, items]) => items.length > 0)
            .map(([label, items]) => (
              <div key={label}>
                <p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{label}</p>
                <div className="flex flex-wrap gap-1.5">
                  {items.map((item) => (
                    <span key={item} className="rounded-full border bg-secondary px-2.5 py-0.5 text-xs font-medium">
                      {item}
                    </span>
                  ))}
                </div>
              </div>
            ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="p-5 pb-2">
          <CardTitle className="text-sm">Original job description</CardTitle>
        </CardHeader>
        <CardContent className="p-5 pt-0">
          {application.jd_text ? (
            <p className="max-h-[520px] overflow-y-auto whitespace-pre-line text-sm leading-relaxed text-foreground/90">
              {application.jd_text}
            </p>
          ) : application.jd_url ? (
            <a href={application.jd_url} target="_blank" rel="noreferrer" className="text-sm text-accent hover:underline">
              {application.jd_url}
            </a>
          ) : (
            <p className="text-sm text-muted-foreground">No job description stored.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

interface ApplicationDetailProps {
  /** When embedded (chat workspace panel) the id and tab come from props, not the URL. */
  applicationId?: string;
  initialTab?: string;
  embedded?: boolean;
}

export default function ApplicationDetail({ applicationId, initialTab, embedded }: ApplicationDetailProps = {}) {
  const params = useParams<{ id: string }>();
  const id = applicationId ?? params.id ?? '';
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [embeddedTab, setEmbeddedTab] = useState(initialTab || 'resume');
  const activeTab = embedded ? embeddedTab : searchParams.get('tab') || 'resume';
  const setActiveTab = (tab: string) =>
    embedded ? setEmbeddedTab(tab) : setSearchParams(tab === 'resume' ? {} : { tab }, { replace: true });

  const { data: details, isLoading, isError, error } = useApplicationDetail(id);
  const { data: referralData } = useReferrals(id);
  const referralCount = referralData?.total ?? 0;
  const updateStatus = useUpdateApplicationStatus();
  const deleteApplication = useDeleteApplication();

  if (isLoading) {
    return (
      <div className="flex h-[50vh] items-center justify-center gap-2 text-muted-foreground">
        <Loader2 className="animate-spin" size={22} />
        <span className="text-sm">Loading application…</span>
      </div>
    );
  }

  if (isError || !details) {
    return (
      <div className="mx-auto mt-12 max-w-md space-y-4 text-center">
        <AlertCircle className="mx-auto text-destructive" size={44} />
        <h3 className="text-lg font-bold">Couldn't load this application</h3>
        <p className="text-sm text-muted-foreground">{error?.message || 'Application not found.'}</p>
        <Button onClick={() => navigate('/applications')}>Back to tracker</Button>
      </div>
    );
  }

  const { application, tailored_resume, cold_emails } = details;
  const analysis = application.jd_analysis;
  const followUpDue = application.status === 'applied' && isOverdue(application.follow_up_at);
  const nextFollowUp = cold_emails.find((e) => e.sequence_number > 1 && !e.sent_at);

  const handleDelete = () => {
    if (!window.confirm(`Delete the ${application.role} application at ${application.company}? This can't be undone.`)) return;
    deleteApplication.mutate(application.id, { onSuccess: () => navigate('/applications') });
  };

  return (
    <div className="page-application-detail mx-auto max-w-7xl space-y-5">
      <Link to="/applications" className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-primary">
        <ArrowLeft size={15} />
        Applications
      </Link>

      <Card>
        <CardContent className="flex flex-col gap-4 p-5 md:flex-row md:items-center md:justify-between">
          <div className="flex items-start gap-4">
            <div className="grid h-12 w-12 shrink-0 place-items-center rounded-lg bg-primary text-lg font-bold text-primary-foreground">
              {application.company.charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0">
              <h2 className="text-xl font-bold text-primary">{application.role}</h2>
              <p className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground">
                <Building2 size={14} />
                {application.company}
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <ScoreBadge score={tailored_resume?.keyword_match_score} />
                {analysis?.seniority && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 font-medium capitalize">
                    <Briefcase size={11} />
                    {analysis.seniority}
                  </span>
                )}
                {analysis?.remote !== null && analysis?.remote !== undefined && (
                  <span className="rounded-full bg-secondary px-2 py-0.5 font-medium">
                    {analysis.remote ? 'Remote' : 'Hybrid / onsite'}
                  </span>
                )}
                {analysis?.salary_range && (
                  <span className="rounded-full bg-secondary px-2 py-0.5 font-medium">{analysis.salary_range}</span>
                )}
                <span>
                  Created {formatDate(application.created_at)}
                  {application.applied_at && ` · Applied ${formatDate(application.applied_at)}`}
                </span>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <StatusSelect
              value={application.status}
              disabled={updateStatus.isPending}
              onChange={(status) => updateStatus.mutate({ id: application.id, status })}
            />
            {application.jd_url && (
              <Button variant="outline" size="sm" className="h-9" asChild>
                <a href={application.jd_url} target="_blank" rel="noreferrer">
                  Job listing
                  <ExternalLink size={13} className="ml-1.5" />
                </a>
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon"
              onClick={handleDelete}
              disabled={deleteApplication.isPending}
              aria-label="Delete application"
              title="Delete application"
              className="text-muted-foreground hover:text-destructive"
            >
              <Trash2 size={16} />
            </Button>
          </div>
        </CardContent>
      </Card>

      {(analysis?.skip_flags?.length ?? 0) > 0 && (
        <div className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/5 px-4 py-3 text-sm">
          <AlertTriangle size={16} className="mt-0.5 shrink-0 text-warning" />
          <span>
            <span className="font-medium">This job breaks your skip rules:</span> {analysis!.skip_flags!.join('; ')}.{' '}
            <Link to="/profile?tab=preferences" className="underline underline-offset-2">
              Edit rules
            </Link>
          </span>
        </div>
      )}

      {application.status === 'saved' && referralCount > 0 && activeTab !== 'referral' && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-accent/30 bg-accent/5 px-4 py-3">
          <p className="flex items-center gap-2 text-sm">
            <Users size={16} className="text-accent" />
            <span>
              <span className="font-semibold text-accent">
                You know {referralCount} {referralCount === 1 ? 'person' : 'people'} at {application.company}.
              </span>{' '}
              Ask for a referral before you apply.
            </span>
          </p>
          <Button size="sm" variant="outline" onClick={() => setActiveTab('referral')}>
            See who
          </Button>
        </div>
      )}

      {followUpDue && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-warning/30 bg-warning/5 px-4 py-3">
          <p className="flex items-center gap-2 text-sm">
            <BellRing size={16} className="text-warning" />
            <span>
              <span className="font-semibold text-warning">Follow-up due.</span>{' '}
              {nextFollowUp ? `Follow-up ${nextFollowUp.sequence_number - 1} is drafted and ready.` : 'Time to nudge the recruiter.'}
            </span>
          </p>
          <Button size="sm" variant="outline" onClick={() => setActiveTab('email')}>
            <Mail size={14} className="mr-1.5" />
            Open follow-up
          </Button>
        </div>
      )}

      <ExecutionEvidence applicationId={application.id} />
      <div className="grid gap-5 @4xl:grid-cols-12">
        <div className="min-w-0 @4xl:col-span-8">
          <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
            <TabsList className="flex w-full overflow-x-auto rounded-md border bg-card p-1">
              {[
                ['resume', 'Resume', FileText],
                ['cover-letter', 'Cover letter', ScrollText],
                ['email', 'Cold email', Mail],
                ['dm', 'LinkedIn', MessageSquare],
                ['referral', 'Referral', Users],
                ['jd', 'Job details', CalendarClock],
              ].map(([value, label, Icon]) => {
                const TabIcon = Icon as typeof FileText;
                return (
                  <TabsTrigger
                    key={value as string}
                    value={value as string}
                    className="flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded px-3 py-1.5 text-sm font-medium text-muted-foreground data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
                  >
                    <TabIcon size={15} />
                    {label as string}
                  </TabsTrigger>
                );
              })}
            </TabsList>

            <TabsContent value="resume">
              <ResumeTab application={application} tailored={tailored_resume} />
            </TabsContent>
            <TabsContent value="cover-letter">
              <CoverLetterPanel application={application} />
            </TabsContent>
            <TabsContent value="email">
              <EmailPanel application={application} emails={cold_emails} />
            </TabsContent>
            <TabsContent value="dm">
              <LinkedInPanel application={application} />
            </TabsContent>
            <TabsContent value="referral">
              <ReferralPanel application={application} />
            </TabsContent>
            <TabsContent value="jd">
              <JobDescriptionPanel application={application} />
            </TabsContent>
          </Tabs>
        </div>

        <aside className="space-y-4 @4xl:col-span-4">
          <MatchCard application={application} tailored={tailored_resume} />
          <NotesCard application={application} />
          <TimelineCard details={details} />
        </aside>
      </div>

      <ReviewBar
        details={details}
        onTab={setActiveTab}
        onMarkApplied={() => updateStatus.mutate({ id: application.id, status: 'applied' })}
        marking={updateStatus.isPending}
      />
    </div>
  );
}

/** Sticky summary of what's ready, with the next action for this application. */
function ReviewBar({
  details,
  onTab,
  onMarkApplied,
  marking,
}: {
  details: ApplicationDetails;
  onTab: (tab: string) => void;
  onMarkApplied: () => void;
  marking: boolean;
}) {
  const { application, tailored_resume, cold_emails } = details;
  if (application.status !== 'saved' && application.status !== 'applied') return null;

  const initial = cold_emails.find((e) => e.sequence_number === 1);
  const sent = cold_emails.filter((e) => e.sent_at).length;
  const followUpDue = application.status === 'applied' && isOverdue(application.follow_up_at);
  const mailto = initial
    ? `mailto:${encodeURIComponent(initial.to_email)}?subject=${encodeURIComponent(initial.subject)}&body=${encodeURIComponent(initial.body)}`
    : null;

  const checks: [string, boolean][] = [
    ['Resume tailored', !!tailored_resume],
    ['Cover letter', !!application.cover_letter],
    [`${cold_emails.length} email${cold_emails.length === 1 ? '' : 's'}${sent ? ` · ${sent} sent` : ''}`, cold_emails.length > 0],
  ];

  return (
    <div className="sticky bottom-0 z-10 -mx-1 pb-1 pt-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border bg-card/95 px-4 py-3 shadow-lg backdrop-blur">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
          <ScoreBadge score={tailored_resume?.keyword_match_score} />
          {checks.map(([label, ok]) => (
            <span key={label} className={cn('inline-flex items-center gap-1', ok ? 'text-foreground' : 'text-muted-foreground')}>
              {ok ? <CheckCircle2 size={13} className="text-accent" /> : <XCircle size={13} />}
              {label}
            </span>
          ))}
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {application.status === 'saved' ? (
            <>
              <Button size="sm" variant="ghost" onClick={() => onTab('resume')}>
                Review resume
              </Button>
              {mailto && (
                <Button size="sm" variant="outline" asChild>
                  <a href={mailto}>
                    <Mail size={14} className="mr-1.5" />
                    Open email
                  </a>
                </Button>
              )}
              <Button size="sm" onClick={onMarkApplied} disabled={marking}>
                <CheckCircle2 size={14} className="mr-1.5" />
                Mark as applied
              </Button>
            </>
          ) : followUpDue ? (
            <Button size="sm" onClick={() => onTab('email')}>
              <BellRing size={14} className="mr-1.5" />
              Send follow-up
            </Button>
          ) : (
            <span className="text-xs text-muted-foreground">
              {application.follow_up_at ? `Follow up on ${formatDate(application.follow_up_at)}` : 'Applied'}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
