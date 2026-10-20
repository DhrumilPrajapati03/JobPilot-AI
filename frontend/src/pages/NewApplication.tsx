// ============================================================
// JobPilot AI — New Application Page
// ============================================================

import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Circle,
  FileText,
  Link2,
  Loader2,
  RotateCcw,
  Sparkles,
  UserRound,
  Zap,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { ScoreBadge } from '../components/applications/shared';
import { useGenerateApplication } from '../hooks/use-applications';
import { useResume } from '../hooks/use-profile';
import { PIPELINE_STEPS, useAgentStream, type StepProgress } from '../hooks/use-agent-stream';
import { cn } from '@/lib/utils';

const MIN_JD_CHARS = 200;

function StepIcon({ state }: { state: StepProgress['state'] }) {
  if (state === 'done') return <CheckCircle2 className="text-accent" size={20} />;
  if (state === 'running') return <Loader2 className="animate-spin text-primary" size={20} />;
  if (state === 'warning') return <AlertTriangle className="text-warning" size={20} />;
  if (state === 'error') return <AlertCircle className="text-destructive" size={20} />;
  return <Circle className="text-border" size={20} />;
}

function StepDetails({ id, data }: { id: string; data?: Record<string, unknown> }) {
  if (!data) return null;
  if (id === 'jd_parsing' && Array.isArray(data.skills) && data.skills.length > 0) {
    return (
      <div className="mt-2 flex flex-wrap gap-1">
        {(data.skills as string[]).map((skill) => (
          <span key={skill} className="rounded-full bg-secondary px-2 py-0.5 text-[11px] font-medium">
            {skill}
          </span>
        ))}
      </div>
    );
  }
  if (id === 'resume_tailoring' && Array.isArray(data.missing_keywords) && data.missing_keywords.length > 0) {
    return (
      <p className="mt-1.5 text-xs text-muted-foreground">
        Not in your resume yet: {(data.missing_keywords as string[]).join(', ')}
      </p>
    );
  }
  return null;
}

function PipelineProgress({ steps }: { steps: Record<string, StepProgress> }) {
  const completed = PIPELINE_STEPS.filter((s) => ['done', 'warning'].includes(steps[s.id].state)).length;
  return (
    <div className="space-y-4">
      <div className="h-1.5 overflow-hidden rounded-full bg-secondary" role="progressbar" aria-valuemin={0} aria-valuemax={PIPELINE_STEPS.length} aria-valuenow={completed}>
        <div
          className="h-full rounded-full bg-accent transition-all duration-500"
          style={{ width: `${(completed / PIPELINE_STEPS.length) * 100}%` }}
        />
      </div>
      <ol className="space-y-1" aria-live="polite">
        {PIPELINE_STEPS.map((step) => {
          const progress = steps[step.id];
          return (
            <li
              key={step.id}
              className={cn(
                'flex gap-3 rounded-lg px-3 py-2.5 transition-colors',
                progress.state === 'running' && 'bg-primary/5',
                progress.state === 'error' && 'bg-destructive/5',
              )}
            >
              <div className="mt-0.5 shrink-0">
                <StepIcon state={progress.state} />
              </div>
              <div className="min-w-0">
                <p
                  className={cn(
                    'text-sm font-semibold',
                    progress.state === 'idle' ? 'text-muted-foreground' : 'text-foreground',
                    progress.state === 'error' && 'text-destructive',
                  )}
                >
                  {step.label}
                </p>
                <p className={cn('text-xs', progress.state === 'warning' ? 'text-warning' : 'text-muted-foreground')}>
                  {progress.state === 'idle' ? step.description : progress.message}
                </p>
                <StepDetails id={step.id} data={progress.data} />
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export default function NewApplication() {
  const navigate = useNavigate();
  const [jdUrl, setJdUrl] = useState('');
  const [jdText, setJdText] = useState('');
  const [activeTab, setActiveTab] = useState('text');
  const [submitError, setSubmitError] = useState<string | null>(null);

  const generate = useGenerateApplication();
  const stream = useAgentStream();
  const { data: baseResume, isLoading: resumeLoading } = useResume();
  const hasBaseResume = !!baseResume?.id;

  const input = activeTab === 'url' ? jdUrl.trim() : jdText.trim();
  const urlValid = activeTab !== 'url' || /^https?:\/\/\S+\.\S+/.test(input);
  const canSubmit = !!input && urlValid && !generate.isPending && hasBaseResume;

  const handleGenerate = async () => {
    setSubmitError(null);
    try {
      const payload = activeTab === 'url' ? { jd_url: input } : { jd_text: input };
      const { run_id } = await generate.mutateAsync(payload);
      stream.start(run_id);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to start the agent pipeline.');
    }
  };

  if (stream.phase !== 'idle') {
    const result = stream.result as { score?: number; company?: string; role?: string } | null;
    return (
      <div className="mx-auto max-w-2xl space-y-5">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">
            {stream.phase === 'success' ? 'Your application kit is ready' : stream.phase === 'error' ? 'The agents hit a problem' : 'Agents at work…'}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {stream.phase === 'running'
              ? 'This usually takes under a minute. You can leave this page — the run continues and lands in your tracker.'
              : stream.phase === 'success'
                ? 'Review and edit everything before you send it.'
                : 'Nothing was sent anywhere. Fix the issue below and try again.'}
          </p>
        </div>

        <Card>
          <CardContent className="p-5">
            <PipelineProgress steps={stream.steps} />
          </CardContent>
        </Card>

        {stream.phase === 'success' && stream.applicationId && (
          <Card className="border-accent/30 bg-accent/5">
            <CardContent className="flex flex-wrap items-center justify-between gap-4 p-5">
              <div>
                <p className="text-sm font-semibold text-foreground">
                  {result?.role} · {result?.company}
                </p>
                <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                  <ScoreBadge score={result?.score} />
                  Tailored resume, cover letter, 3 emails and 2 LinkedIn messages
                </div>
              </div>
              <div className="flex gap-2">
                <Button variant="ghost" onClick={stream.reset}>
                  New application
                </Button>
                <Button onClick={() => navigate(`/applications/${stream.applicationId}`)}>
                  Review materials
                  <ArrowRight size={16} className="ml-2" />
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {stream.phase === 'error' && (
          <Card className="border-destructive/30 bg-destructive/5">
            <CardContent className="flex flex-wrap items-center justify-between gap-4 p-5">
              <p className="flex items-start gap-2 text-sm text-destructive">
                <AlertCircle size={18} className="mt-0.5 shrink-0" />
                {stream.error}
              </p>
              <div className="flex gap-2">
                {stream.applicationId && (
                  <Button variant="outline" onClick={() => navigate(`/applications/${stream.applicationId}`)}>
                    Open partial application
                  </Button>
                )}
                <Button onClick={stream.reset}>
                  <RotateCcw size={15} className="mr-2" />
                  Try again
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    );
  }

  return (
    <div className="mx-auto grid max-w-5xl gap-5 @4xl:grid-cols-[1fr_300px]">
      <div className="space-y-5">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">New application</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Paste a job description and JobPilot drafts everything you need to apply — you review before anything goes out.
          </p>
        </div>

        {!resumeLoading && !hasBaseResume && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-warning/30 bg-warning/5 px-4 py-3">
            <p className="flex items-center gap-2 text-sm">
              <UserRound size={16} className="text-warning" />
              Add your base resume first — the agents tailor from it and never invent experience.
            </p>
            <Button size="sm" variant="outline" asChild>
              <Link to="/profile">Open Identity Vault</Link>
            </Button>
          </div>
        )}

        <Card>
          <CardContent className="space-y-4 p-5">
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList className="grid grid-cols-2 rounded-md border bg-secondary p-1">
                <TabsTrigger
                  value="text"
                  className="flex items-center justify-center gap-2 rounded py-1.5 text-sm font-medium text-muted-foreground data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-sm"
                >
                  <FileText size={15} />
                  Paste JD text
                </TabsTrigger>
                <TabsTrigger
                  value="url"
                  className="flex items-center justify-center gap-2 rounded py-1.5 text-sm font-medium text-muted-foreground data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-sm"
                >
                  <Link2 size={15} />
                  Paste URL
                </TabsTrigger>
              </TabsList>

              <TabsContent value="text" className="space-y-2 pt-4">
                <Label htmlFor="jd-text">Job description</Label>
                <Textarea
                  id="jd-text"
                  className="min-h-[300px] leading-relaxed"
                  placeholder="Paste the full job description — responsibilities, requirements, about the company…"
                  value={jdText}
                  onChange={(e) => setJdText(e.target.value)}
                />
                <p
                  className={cn(
                    'text-right text-xs tabular-nums',
                    jdText.trim() && jdText.trim().length < MIN_JD_CHARS ? 'text-warning' : 'text-muted-foreground',
                  )}
                >
                  {jdText.trim() && jdText.trim().length < MIN_JD_CHARS
                    ? 'Short descriptions give weaker tailoring · '
                    : ''}
                  {jdText.length.toLocaleString()} characters
                </p>
              </TabsContent>

              <TabsContent value="url" className="space-y-2 pt-4">
                <Label htmlFor="jd-url">Job listing URL</Label>
                <Input
                  id="jd-url"
                  type="url"
                  placeholder="https://boards.greenhouse.io/company/jobs/123"
                  value={jdUrl}
                  onChange={(e) => setJdUrl(e.target.value)}
                  aria-invalid={!!jdUrl.trim() && !urlValid}
                />
                <p className={cn('text-xs', jdUrl.trim() && !urlValid ? 'text-destructive' : 'text-muted-foreground')}>
                  {jdUrl.trim() && !urlValid
                    ? 'Enter a full URL starting with https://'
                    : 'Works best with public pages (Greenhouse, Lever, company career sites). LinkedIn often blocks fetching — paste the text instead.'}
                </p>
              </TabsContent>
            </Tabs>

            {submitError && (
              <p className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                <AlertCircle size={16} />
                {submitError}
              </p>
            )}

            <Button className="w-full" size="lg" onClick={handleGenerate} disabled={!canSubmit}>
              {generate.isPending ? <Loader2 size={18} className="mr-2 animate-spin" /> : <Zap size={18} className="mr-2" />}
              Analyse job & generate materials
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card className="h-fit @4xl:mt-[60px]">
        <CardHeader className="p-5 pb-3">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Sparkles size={16} className="text-accent" />
            What you'll get
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 p-5 pt-0 text-sm">
          {[
            ['Tailored resume', 'Reordered skills and rewritten bullets with an ATS keyword score'],
            ['Cover letter', 'Matched to the role, seniority and tone'],
            ['Cold email sequence', 'Initial email plus +5 and +12 day follow-ups'],
            ['LinkedIn messages', 'A sub-300-character invite note and a follow-up DM'],
          ].map(([title, body]) => (
            <div key={title} className="flex gap-2.5">
              <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-accent" />
              <div>
                <p className="font-semibold">{title}</p>
                <p className="text-xs text-muted-foreground">{body}</p>
              </div>
            </div>
          ))}
          <p className="border-t pt-3 text-xs text-muted-foreground">
            Companies, titles and dates always come from your base resume — the agents only reword.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
