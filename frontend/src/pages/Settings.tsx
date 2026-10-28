// ============================================================
// JobPilot — Settings: morning digest, overnight schedule, extension
// ============================================================

import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Check, CheckCircle2, Copy, Loader2, Mail, Moon, Puzzle, Send, Trash2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { API_BASE_URL } from '../lib/constants';
import { useProfile, useUpdateProfile } from '../hooks/use-profile';
import {
  connectExtension,
  useAutopilotStatus,
  useCreateExtensionToken,
  useDigestPreview,
  useExtensionPresence,
  useExtensionTokens,
  useRevokeExtensionToken,
  useSendDigest,
} from '../hooks/use-autopilot';
import { cn } from '@/lib/utils';
import { GmailConnection } from '../components/email/GmailConnection';

const hourLabel = (h: number) => new Date(2000, 0, 1, h).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });

function timeZones(): string[] {
  try {
    return (Intl as unknown as { supportedValuesOf(k: string): string[] }).supportedValuesOf('timeZone');
  } catch {
    return ['UTC', 'Asia/Kolkata', 'Europe/London', 'America/New_York', 'America/Los_Angeles'];
  }
}

function formatWhen(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : 'never';
}

function DigestCard() {
  const { data: profile } = useProfile();
  const update = useUpdateProfile();
  const status = useAutopilotStatus();
  const send = useSendDigest();
  const [showPreview, setShowPreview] = useState(false);
  const preview = useDigestPreview(showPreview);
  const detected = useMemo(() => Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC', []);
  const prefs = profile?.work_preferences;
  const [form, setForm] = useState({ digest_enabled: false, digest_hour: 7, digest_email: '', timezone: detected });

  useEffect(() => {
    if (!prefs) return;
    setForm({
      digest_enabled: prefs.digest_enabled ?? false,
      digest_hour: prefs.digest_hour ?? 7,
      digest_email: prefs.digest_email ?? '',
      timezone: prefs.timezone && prefs.timezone !== 'UTC' ? prefs.timezone : detected,
    });
  }, [prefs, detected]);

  // The whole preferences object is saved at once, so merge rather than replace.
  const save = () => update.mutate({ work_preferences: { ...(prefs as object), ...form } as never }, { onSuccess: () => status.refetch() });
  const dirty =
    !!prefs &&
    (form.digest_enabled !== (prefs.digest_enabled ?? false) ||
      form.digest_hour !== (prefs.digest_hour ?? 7) ||
      form.digest_email !== (prefs.digest_email ?? '') ||
      form.timezone !== (prefs.timezone ?? 'UTC'));
  // Browsers list some zones under old names (Asia/Calcutta for Asia/Kolkata), so keep the saved one selectable.
  const zones = useMemo(() => {
    const list = timeZones();
    return list.includes(form.timezone) ? list : [form.timezone, ...list];
  }, [form.timezone]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mail size={17} />
          Morning digest
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          One email each morning: applications ready to send, new matches, follow-ups due and referrals to ask for. Your boards are scanned two hours earlier.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {status.data && !status.data.email_configured && (
          <p className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/5 px-3 py-2 text-sm">
            <AlertTriangle size={15} className="mt-0.5 shrink-0 text-warning" />
            The server can't send email yet: add RESEND_API_KEY (free at resend.com) to the backend's environment.
          </p>
        )}
        <label className="flex cursor-pointer items-center gap-3">
          <input type="checkbox" checked={form.digest_enabled} onChange={(e) => setForm({ ...form, digest_enabled: e.target.checked })} className="h-4 w-4 accent-[var(--accent)]" />
          <span className="text-sm font-medium">Send me a digest every morning</span>
        </label>
        <div className={cn('grid gap-4 @2xl:grid-cols-3', !form.digest_enabled && 'opacity-60')}>
          <div className="space-y-1.5">
            <Label htmlFor="digest-hour">Send at</Label>
            <select
              id="digest-hour"
              value={form.digest_hour}
              onChange={(e) => setForm({ ...form, digest_hour: Number(e.target.value) })}
              className="h-9 w-full rounded-md border border-input bg-card px-2 text-sm"
            >
              {Array.from({ length: 24 }, (_, h) => (
                <option key={h} value={h}>
                  {hourLabel(h)}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="digest-tz">Time zone</Label>
            <select id="digest-tz" value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })} className="h-9 w-full rounded-md border border-input bg-card px-2 text-sm">
              {zones.map((z) => (
                <option key={z} value={z}>
                  {z}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="digest-email">Send to</Label>
            <Input id="digest-email" type="email" value={form.digest_email} placeholder={status.data?.digest_to || 'Your account email'} onChange={(e) => setForm({ ...form, digest_email: e.target.value })} />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={save} disabled={!dirty || update.isPending}>
            {update.isPending ? <Loader2 size={14} className="mr-1.5 animate-spin" /> : <Check size={14} className="mr-1.5" />}
            Save
          </Button>
          <Button variant="outline" onClick={() => setShowPreview(!showPreview)}>
            {showPreview ? 'Hide preview' : 'Preview'}
          </Button>
          <Button variant="outline" onClick={() => send.mutate()} disabled={send.isPending}>
            {send.isPending ? <Loader2 size={14} className="mr-1.5 animate-spin" /> : <Send size={14} className="mr-1.5" />}
            Send me one now
          </Button>
          {send.isSuccess && <span className="text-sm text-accent">Sent to {send.data.to}.</span>}
          {(send.error || update.error) && <span className="text-sm text-destructive">{(send.error ?? update.error)?.message}</span>}
        </div>
        {showPreview && (
          <div className="overflow-hidden rounded-lg border">
            {preview.isLoading ? (
              <div className="flex h-40 items-center justify-center text-muted-foreground">
                <Loader2 className="animate-spin" size={18} />
              </div>
            ) : preview.data ? (
              <>
                <p className="border-b bg-muted/50 px-3 py-2 text-xs">
                  <span className="text-muted-foreground">Subject:</span> {preview.data.subject}
                </p>
                <iframe title="Digest preview" srcDoc={preview.data.html} sandbox="" className="h-[480px] w-full bg-white" />
              </>
            ) : (
              <p className="p-3 text-sm text-destructive">{preview.error?.message}</p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ScheduleCard() {
  const { data } = useAutopilotStatus();
  if (!data) return null;
  const row = (ok: boolean, label: string, hint: string) => (
    <li className="flex items-start gap-2">
      {ok ? <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-accent" /> : <AlertTriangle size={15} className="mt-0.5 shrink-0 text-warning" />}
      <span>
        <span className="font-medium">{label}</span>
        <span className="block text-xs text-muted-foreground">{hint}</span>
      </span>
    </li>
  );
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Moon size={17} />
          Overnight schedule
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Around {hourLabel(data.scan_hour)} your time, JobPilot scans your boards and auto-drafts the best matches (if that's on). Nothing is ever submitted for you.
        </p>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2.5 text-sm">
          {row(data.tables_ready, 'Database ready', data.tables_ready ? 'Autopilot tables exist.' : 'Run supabase/migrations/20261014_autopilot.sql in Supabase.')}
          {row(data.server_scheduler, 'Server scheduler', data.server_scheduler ? 'Runs every 10 minutes while the server is awake.' : 'Add SUPABASE_SERVICE_KEY to the backend. Until then, boards are scanned when you open the app.')}
          {row(
            data.cron_configured,
            'Wake-up cron',
            data.cron_configured
              ? 'Your cron service wakes a sleeping server for the nightly run.'
              : 'Hosts like Render free sleep when idle. Set CRON_SECRET and call POST /api/v1/autopilot/tick every 10–15 minutes from cron-job.org.',
          )}
        </ul>
        <p className="mt-4 text-xs text-muted-foreground">
          Last scan: {formatWhen(data.state?.last_scan_at)} · Last digest: {formatWhen(data.state?.last_digest_at)}
          {data.state?.last_digest_error && <span className="block text-destructive">Last digest failed: {data.state.last_digest_error}</span>}
        </p>
      </CardContent>
    </Card>
  );
}

function ExtensionCard() {
  const presence = useExtensionPresence();
  const tokens = useExtensionTokens();
  const create = useCreateExtensionToken();
  const revoke = useRevokeExtensionToken();
  const [result, setResult] = useState<{ connected: boolean; token: string } | null>(null);
  const [copied, setCopied] = useState(false);

  const connect = () =>
    create.mutate(undefined, {
      onSuccess: async ({ token }) => setResult({ connected: await connectExtension(token, API_BASE_URL), token }),
    });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Puzzle size={17} />
          Chrome extension
          {presence && <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[11px] font-medium text-accent">Installed</span>}
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Fills application forms on Greenhouse, Lever, Ashby, SmartRecruiters and most other sites with your tailored resume and saved answers. It never clicks Submit.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {!presence && (
          <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
            <li>
              Open <code className="rounded bg-muted px-1">chrome://extensions</code> and turn on Developer mode.
            </li>
            <li>
              Click “Load unpacked” and pick the <code className="rounded bg-muted px-1">extension</code> folder in the JobPilot project.
            </li>
            <li>Reload this page, then click Connect.</li>
          </ol>
        )}
        {tokens.data && !tokens.data.server_ready && (
          <p className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/5 px-3 py-2 text-sm">
            <AlertTriangle size={15} className="mt-0.5 shrink-0 text-warning" />
            The extension needs SUPABASE_SERVICE_KEY on the backend to read your data.
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={connect} disabled={create.isPending}>
            {create.isPending && <Loader2 size={14} className="mr-1.5 animate-spin" />}
            Connect extension
          </Button>
          {create.error && <span className="text-sm text-destructive">{create.error.message}</span>}
          {result?.connected && <span className="text-sm text-accent">Connected. Open any application form and click “JobPilot · Fill”.</span>}
        </div>
        {result && !result.connected && (
          <div className="space-y-2 rounded-lg border p-3 text-sm">
            <p>The extension didn't answer. Paste these in the extension popup under “Connection settings”:</p>
            <p className="text-xs text-muted-foreground">API URL</p>
            <code className="block break-all rounded bg-muted px-2 py-1 text-xs">{API_BASE_URL}</code>
            <p className="text-xs text-muted-foreground">Token (shown once)</p>
            <div className="flex items-center gap-2">
              <code className="block min-w-0 flex-1 break-all rounded bg-muted px-2 py-1 text-xs">{result.token}</code>
              <Button
                size="sm"
                variant="outline"
                onClick={() => navigator.clipboard.writeText(result.token).then(() => setCopied(true), () => undefined)}
              >
                {copied ? <Check size={13} /> : <Copy size={13} />}
              </Button>
            </div>
          </div>
        )}
        {!!tokens.data?.tokens.length && (
          <div>
            <p className="mb-1.5 text-xs font-medium text-muted-foreground">Connected extensions</p>
            <ul className="divide-y rounded-lg border">
              {tokens.data.tokens.map((t) => (
                <li key={t.id} className="flex items-center gap-3 px-3 py-2 text-sm">
                  <span className="min-w-0 flex-1">
                    {t.label}
                    <span className="block text-xs text-muted-foreground">
                      Connected {formatWhen(t.created_at)} · last used {formatWhen(t.last_used_at)}
                    </span>
                  </span>
                  <button
                    type="button"
                    onClick={() => window.confirm('Disconnect this extension? It will stop working until you connect it again.') && revoke.mutate(t.id)}
                    className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-destructive"
                    aria-label="Disconnect"
                  >
                    <Trash2 size={14} />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        {tokens.error && <p className="text-sm text-destructive">{tokens.error.message}</p>}
      </CardContent>
    </Card>
  );
}

export default function Settings() {
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">Your morning digest, the overnight schedule and the Chrome extension.</p>
      </div>
      <GmailConnection />
      <DigestCard />
      <ExtensionCard />
      <ScheduleCard />
    </div>
  );
}
