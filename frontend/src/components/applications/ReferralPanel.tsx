// ============================================================
// JobPilot — Referral tab: people you know at this company
// ============================================================

import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, Check, Copy, ExternalLink, Loader2, Send, Sparkles, UserPlus, Users } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Textarea } from '../ui/textarea';
import { cn } from '@/lib/utils';
import type { JobApplication } from '../../hooks/use-applications';
import {
  REFERRAL_STATUS_LABEL,
  useCreateReferral,
  useReferrals,
  useUpdateReferral,
  type ReferralCandidate,
  type ReferralStatus,
} from '../../hooks/use-network';

const OUTCOMES: ReferralStatus[] = ['sent', 'referred', 'declined', 'no_reply'];

function StatusPill({ status }: { status: ReferralStatus }) {
  const tone =
    status === 'referred'
      ? 'bg-accent/10 text-accent'
      : status === 'declined' || status === 'no_reply'
        ? 'bg-secondary text-muted-foreground'
        : status === 'sent'
          ? 'bg-[var(--status-applied)]/10 text-[var(--status-applied-fg)]'
          : 'bg-warning/10 text-warning';
  return <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', tone)}>{REFERRAL_STATUS_LABEL[status]}</span>;
}

function RequestEditor({ application, candidate }: { application: JobApplication; candidate: ReferralCandidate }) {
  const request = candidate.request!;
  const update = useUpdateReferral(application.id);
  const [text, setText] = useState(request.message);
  const [copied, setCopied] = useState(false);
  useEffect(() => setText(request.message), [request.message]);
  const dirty = text !== request.message;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard blocked (insecure context): the text is still selectable.
    }
  };

  return (
    <div className="mt-3 space-y-2.5 border-t pt-3">
      <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={7} className="text-sm" aria-label={`Message to ${candidate.contact.full_name}`} />
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="outline" onClick={copy}>
          {copied ? <Check size={13} className="mr-1.5" /> : <Copy size={13} className="mr-1.5" />}
          {copied ? 'Copied' : 'Copy message'}
        </Button>
        {candidate.contact.linkedin_url && (
          <Button size="sm" variant="outline" asChild>
            <a href={candidate.contact.linkedin_url} target="_blank" rel="noreferrer">
              Open LinkedIn
              <ExternalLink size={12} className="ml-1.5" />
            </a>
          </Button>
        )}
        {dirty && (
          <Button size="sm" variant="ghost" onClick={() => update.mutate({ id: request.id, message: text })} disabled={update.isPending}>
            Save edits
          </Button>
        )}
        <span className="ml-auto flex flex-wrap items-center gap-1">
          {request.status === 'drafted' ? (
            <Button size="sm" onClick={() => update.mutate({ id: request.id, status: 'sent', ...(dirty ? { message: text } : {}) })} disabled={update.isPending}>
              <Send size={13} className="mr-1.5" />
              I sent it
            </Button>
          ) : (
            <select
              value={request.status}
              onChange={(e) => update.mutate({ id: request.id, status: e.target.value as ReferralStatus })}
              className="h-8 rounded-md border border-input bg-card px-2 text-xs"
              aria-label="What happened"
            >
              {OUTCOMES.map((s) => (
                <option key={s} value={s}>
                  {REFERRAL_STATUS_LABEL[s]}
                </option>
              ))}
            </select>
          )}
        </span>
      </div>
      {update.error && <p className="text-xs text-destructive">{update.error.message}</p>}
    </div>
  );
}

function CandidateRow({ application, candidate }: { application: JobApplication; candidate: ReferralCandidate }) {
  const create = useCreateReferral();
  const [open, setOpen] = useState(false);
  const { contact, request } = candidate;
  const draft = () => create.mutate({ application_id: application.id, contact_id: contact.id }, { onSuccess: () => setOpen(true) });

  return (
    <li className="rounded-lg border p-3">
      <div className="flex items-start gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-secondary text-sm font-semibold">
          {contact.full_name.charAt(0).toUpperCase()}
        </span>
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
            {contact.full_name}
            {request && <StatusPill status={request.status} />}
          </p>
          <p className="truncate text-xs text-muted-foreground">{candidate.reason}</p>
        </div>
        {request ? (
          <Button size="sm" variant="ghost" onClick={() => setOpen(!open)} aria-expanded={open}>
            {open ? 'Hide' : 'View message'}
          </Button>
        ) : (
          <Button size="sm" variant="outline" onClick={draft} disabled={create.isPending}>
            {create.isPending ? <Loader2 size={13} className="mr-1.5 animate-spin" /> : <Sparkles size={13} className="mr-1.5" />}
            Ask for a referral
          </Button>
        )}
      </div>
      {create.error && <p className="mt-2 text-xs text-destructive">{create.error.message}</p>}
      {create.data?.used_fallback && (
        <p className="mt-2 flex items-center gap-1.5 text-xs text-warning">
          <AlertTriangle size={12} />
          The AI provider failed, so this is a template. Personalise it before sending.
        </p>
      )}
      {open && request && <RequestEditor application={application} candidate={candidate} />}
    </li>
  );
}

export function ReferralPanel({ application }: { application: JobApplication }) {
  const { data, isLoading, error } = useReferrals(application.id);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Users size={17} />
          Referrals at {application.company}
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          A referral is often the fastest way past the resume screen. Ask before you apply. JobPilot drafts the message; you send it yourself.
        </p>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex h-24 items-center justify-center text-muted-foreground">
            <Loader2 className="animate-spin" size={18} />
          </div>
        ) : error ? (
          <p className="flex items-start gap-2 text-sm">
            <AlertTriangle size={15} className="mt-0.5 shrink-0 text-warning" />
            {error.message}
          </p>
        ) : !data?.contacts.length ? (
          <div className="rounded-lg border border-dashed p-6 text-center">
            <p className="text-sm font-medium">No one in your network works at {application.company} yet</p>
            <p className="mt-1 text-sm text-muted-foreground">Import your LinkedIn connections, or add someone you know there.</p>
            <Button size="sm" className="mt-3" asChild>
              <Link to="/network">
                <UserPlus size={14} className="mr-1.5" />
                Go to Network
              </Link>
            </Button>
          </div>
        ) : (
          <>
            <ul className="space-y-2">
              {data.contacts.map((c) => (
                <CandidateRow key={c.contact.id} application={application} candidate={c} />
              ))}
            </ul>
            {data.total > data.contacts.length && (
              <p className="mt-2 text-xs text-muted-foreground">
                Showing the best {data.contacts.length} of {data.total} people.
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
