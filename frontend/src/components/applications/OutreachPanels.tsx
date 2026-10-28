// ============================================================
// JobPilot AI — Cover letter, cold email and LinkedIn DM editors
// ============================================================

import { CheckCircle2, Mail, MailCheck, Reply, Save } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Textarea } from '../ui/textarea';
import { CopyButton, formatDate } from './shared';
import { useDraft } from '../../hooks/use-draft';
import {
  useUpdateApplication,
  useUpdateColdEmail,
  type ColdEmail,
  type JobApplication,
} from '../../hooks/use-applications';
import { cn } from '@/lib/utils';
import { MailOutreach } from '../email/MailOutreach';

const LINKEDIN_NOTE_LIMIT = 300;
// Matches the email writer prompt: initial, +5 days, +12 days.
const SEQUENCE_OFFSETS_DAYS = [0, 5, 12];

function SaveBar({
  dirty,
  saving,
  error,
  onSave,
  onReset,
}: {
  dirty: boolean;
  saving: boolean;
  error?: string;
  onSave: () => void;
  onReset: () => void;
}) {
  return (
    <div className="flex items-center gap-2">
      {error && <span className="text-xs text-destructive">{error}</span>}
      {dirty && (
        <Button type="button" variant="ghost" size="sm" onClick={onReset} disabled={saving}>
          Discard
        </Button>
      )}
      <Button type="button" size="sm" onClick={onSave} disabled={!dirty || saving}>
        <Save size={14} className="mr-1.5" />
        {saving ? 'Saving…' : 'Save'}
      </Button>
    </div>
  );
}

export function CoverLetterPanel({ application }: { application: JobApplication }) {
  const { draft, setDraft, dirty, reset } = useDraft(application.cover_letter || '');
  const update = useUpdateApplication(application.id);
  const words = draft.trim() ? draft.trim().split(/\s+/).length : 0;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 border-b p-4">
        <div>
          <CardTitle className="text-base">Cover letter</CardTitle>
          <p className="text-xs text-muted-foreground mt-1">
            {words} words · aim for 250–350
          </p>
        </div>
        <div className="flex items-center gap-2">
          <CopyButton text={draft} />
          <SaveBar
            dirty={dirty}
            saving={update.isPending}
            error={update.error?.message}
            onSave={() => update.mutate({ cover_letter: draft })}
            onReset={reset}
          />
        </div>
      </CardHeader>
      <CardContent className="p-4">
        <Textarea
          aria-label="Cover letter"
          className="min-h-[460px] text-[0.9rem] leading-relaxed"
          value={draft}
          placeholder="No cover letter generated yet."
          onChange={(e) => setDraft(e.target.value)}
        />
      </CardContent>
    </Card>
  );
}

function sequenceLabel(index: number) {
  return index === 0 ? 'Initial email' : `Follow-up ${index}`;
}

function EmailCard({
  email,
  index,
  application,
}: {
  email: ColdEmail;
  index: number;
  application: JobApplication;
}) {
  const { draft, setDraft, dirty, reset } = useDraft({
    to_name: email.to_name || '',
    to_email: email.to_email || '',
    subject: email.subject || '',
    body: email.body || '',
  });
  const update = useUpdateColdEmail(application.id);
  const offset = SEQUENCE_OFFSETS_DAYS[index] ?? 0;
  const sendOn = application.applied_at
    ? formatDate(new Date(new Date(application.applied_at).getTime() + offset * 86_400_000).toISOString())
    : null;

  const mailto = `mailto:${encodeURIComponent(draft.to_email)}?subject=${encodeURIComponent(
    draft.subject,
  )}&body=${encodeURIComponent(draft.body)}`;

  return (
    <Card className={cn(email.sent_at && 'border-accent/30')}>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0 border-b p-4">
        <div className="flex items-center gap-3">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">
            {index + 1}
          </span>
          <div>
            <CardTitle className="text-sm">{sequenceLabel(index)}</CardTitle>
            <p className="text-xs text-muted-foreground mt-0.5">
              {email.sent_at
                ? `Manually marked sent ${formatDate(email.sent_at)}`
                : offset === 0
                  ? 'Send when you apply'
                  : sendOn
                    ? `Send on ${sendOn} (+${offset} days)`
                    : `Send ${offset} days after applying`}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {email.sent_at && (
            <Button
              type="button"
              variant={email.replied ? 'default' : 'outline'}
              size="sm"
              onClick={() => update.mutate({ emailId: email.id, data: { replied: !email.replied } })}
            >
              <Reply size={14} className="mr-1.5" />
              {email.replied ? 'Replied' : 'Mark replied'}
            </Button>
          )}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => update.mutate({ emailId: email.id, data: { sent: !email.sent_at } })}
          >
            {email.sent_at ? <CheckCircle2 size={14} className="mr-1.5 text-accent" /> : <MailCheck size={14} className="mr-1.5" />}
            {email.sent_at ? 'Manually marked sent' : 'Mark sent manually'}
          </Button>
          <Button type="button" variant="outline" size="sm" asChild>
            <a href={mailto}>
              <Mail size={14} className="mr-1.5" />
              Open in mail app
            </a>
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 p-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Input
            aria-label="Recipient name"
            placeholder="Recipient name"
            value={draft.to_name}
            onChange={(e) => setDraft({ ...draft, to_name: e.target.value })}
          />
          <Input
            aria-label="Recipient email"
            type="email"
            placeholder="recruiter@company.com"
            value={draft.to_email}
            onChange={(e) => setDraft({ ...draft, to_email: e.target.value })}
          />
        </div>
        <Input
          aria-label="Subject"
          className="font-semibold"
          value={draft.subject}
          onChange={(e) => setDraft({ ...draft, subject: e.target.value })}
        />
        <Textarea
          aria-label="Email body"
          className="min-h-[200px] leading-relaxed"
          value={draft.body}
          onChange={(e) => setDraft({ ...draft, body: e.target.value })}
        />
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CopyButton text={`Subject: ${draft.subject}\n\n${draft.body}`} label="Copy email" />
          <SaveBar
            dirty={dirty}
            saving={update.isPending}
            error={update.error?.message}
            onSave={() => update.mutate({ emailId: email.id, data: draft })}
            onReset={reset}
          />
        </div>
      </CardContent>
    </Card>
  );
}

export function EmailPanel({ application, emails }: { application: JobApplication; emails: ColdEmail[] }) {
  if (emails.length === 0) {
    return (
      <div className="space-y-4"><MailOutreach applicationId={application.id} emails={emails}/><Card className="border-dashed p-12 text-center">
        <Mail size={36} className="mx-auto text-muted-foreground/40" />
        <p className="mt-3 text-sm font-semibold text-muted-foreground">No generated email templates for this application.</p>
      </Card></div>
    );
  }
  return (
    <div className="space-y-4">
      <MailOutreach applicationId={application.id} emails={emails}/>
      <p className="text-sm text-muted-foreground">Generated templates and manual activity log</p>
      {emails.map((email) => (
        <EmailCard key={email.id} email={email} index={email.sequence_number - 1} application={application} />
      ))}
    </div>
  );
}

export function LinkedInPanel({ application }: { application: JobApplication }) {
  const { draft, setDraft, dirty, reset } = useDraft({
    connection_request: application.linkedin_dm?.connection_request || '',
    follow_up: application.linkedin_dm?.follow_up || '',
  });
  const update = useUpdateApplication(application.id);
  const noteLength = draft.connection_request.length;
  const overLimit = noteLength > LINKEDIN_NOTE_LIMIT;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 border-b p-4">
          <div>
            <CardTitle className="text-sm">Connection request note</CardTitle>
            <p className="text-xs text-muted-foreground mt-0.5">Sent with your invite — LinkedIn caps notes at 300 characters.</p>
          </div>
          <CopyButton text={draft.connection_request} />
        </CardHeader>
        <CardContent className="space-y-2 p-4">
          <Textarea
            aria-label="Connection request note"
            rows={4}
            value={draft.connection_request}
            onChange={(e) => setDraft({ ...draft, connection_request: e.target.value })}
            className={cn(overLimit && 'border-destructive focus-visible:ring-destructive')}
          />
          <p className={cn('text-right text-xs font-semibold tabular-nums', overLimit ? 'text-destructive' : 'text-muted-foreground')}>
            {noteLength} / {LINKEDIN_NOTE_LIMIT}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 border-b p-4">
          <div>
            <CardTitle className="text-sm">Follow-up message</CardTitle>
            <p className="text-xs text-muted-foreground mt-0.5">Send once they accept your connection.</p>
          </div>
          <CopyButton text={draft.follow_up} />
        </CardHeader>
        <CardContent className="p-4">
          <Textarea
            aria-label="Follow-up message"
            className="min-h-[180px] leading-relaxed"
            value={draft.follow_up}
            onChange={(e) => setDraft({ ...draft, follow_up: e.target.value })}
          />
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <SaveBar
          dirty={dirty && !overLimit}
          saving={update.isPending}
          error={overLimit ? 'Connection note is over 300 characters' : update.error?.message}
          onSave={() => update.mutate({ linkedin_dm: draft })}
          onReset={reset}
        />
      </div>
    </div>
  );
}
