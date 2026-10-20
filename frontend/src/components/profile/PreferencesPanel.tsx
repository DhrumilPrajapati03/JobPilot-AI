// ============================================================
// JobPilot — Job preferences & skip rules
// ============================================================

import { Loader2, Save } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { TagInput } from '../ui/tag-input';
import { useDraft } from '../../hooks/use-draft';
import { useUpdateProfile, type UserProfile, type WorkPreferences } from '../../hooks/use-profile';

const DEFAULTS: WorkPreferences = {
  remote_only: true,
  preferred_roles: [],
  preferred_locations: [],
  min_company_size: null,
  industries: [],
  min_match_score: 70,
  blocked_companies: [],
  skip_keywords: ['security clearance', 'top secret', 'polygraph'],
  requires_sponsorship: false,
  salary_min: null,
  salary_currency: 'USD',
  auto_draft_enabled: false,
  auto_draft_min_score: 80,
  auto_draft_daily_cap: 3,
};
// Digest settings live in work_preferences too (edited in Settings); the spread below keeps them.

function Toggle({ id, checked, onChange, label, hint }: { id: string; checked: boolean; onChange: (v: boolean) => void; label: string; hint: string }) {
  return (
    <label htmlFor={id} className="flex cursor-pointer items-start gap-3 rounded-lg border p-3 hover:bg-muted/40">
      <input id={id} type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-0.5 h-4 w-4 accent-[var(--accent)]" />
      <span>
        <span className="block text-sm font-medium">{label}</span>
        <span className="block text-xs text-muted-foreground">{hint}</span>
      </span>
    </label>
  );
}

export function PreferencesPanel({ profile }: { profile: UserProfile | undefined }) {
  const update = useUpdateProfile();
  const { draft, setDraft, dirty, reset } = useDraft<WorkPreferences>({ ...DEFAULTS, ...(profile?.work_preferences ?? {}) });
  const set = (patch: Partial<WorkPreferences>) => setDraft({ ...draft, ...patch });

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>What you're looking for</CardTitle>
          <p className="text-sm text-muted-foreground">Used to filter and rank the jobs in your job feed.</p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="pref-roles">Target roles</Label>
              <TagInput id="pref-roles" value={draft.preferred_roles} onChange={(v) => set({ preferred_roles: v })} placeholder="e.g. ML Engineer, AI Engineer" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pref-locations">Locations</Label>
              <TagInput id="pref-locations" value={draft.preferred_locations} onChange={(v) => set({ preferred_locations: v })} placeholder="e.g. Remote, London, Bengaluru" />
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="pref-match">Show jobs from this fit</Label>
              <div className="flex items-center gap-3">
                <input
                  id="pref-match"
                  type="range"
                  min={40}
                  max={95}
                  step={5}
                  value={draft.min_match_score}
                  onChange={(e) => set({ min_match_score: Number(e.target.value) })}
                  className="flex-1 accent-[var(--accent)]"
                />
                <span className="w-10 text-right text-sm font-medium tabular-nums">{draft.min_match_score}%</span>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pref-salary">Minimum salary</Label>
              <Input
                id="pref-salary"
                type="number"
                min={0}
                inputMode="numeric"
                value={draft.salary_min ?? ''}
                onChange={(e) => set({ salary_min: e.target.value ? Number(e.target.value) : null })}
                placeholder="Optional"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pref-currency">Currency</Label>
              <Input id="pref-currency" value={draft.salary_currency} maxLength={3} onChange={(e) => set({ salary_currency: e.target.value.toUpperCase() })} />
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <Toggle id="pref-remote" checked={draft.remote_only} onChange={(v) => set({ remote_only: v })} label="Remote only" hint="Flag roles that are hybrid or on-site." />
            <Toggle
              id="pref-sponsor"
              checked={draft.requires_sponsorship}
              onChange={(v) => set({ requires_sponsorship: v })}
              label="I need visa sponsorship"
              hint="Flag jobs that say they won't sponsor."
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Skip rules</CardTitle>
          <p className="text-sm text-muted-foreground">
            Jobs that break these rules are flagged when you add them yourself, and skipped in your job feed.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="pref-blocked">Blocked companies</Label>
            <TagInput id="pref-blocked" value={draft.blocked_companies} onChange={(v) => set({ blocked_companies: v })} placeholder="Agencies, past employers…" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="pref-skip">Skip if the job mentions</Label>
            <TagInput id="pref-skip" value={draft.skip_keywords} onChange={(v) => set({ skip_keywords: v })} placeholder="e.g. security clearance" />
            <p className="text-xs text-muted-foreground">Matched as whole words, so “go” won't match “Google”.</p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Auto-draft</CardTitle>
          <p className="text-sm text-muted-foreground">
            After each job feed scan, JobPilot can tailor your resume and draft outreach for the best new matches. Nothing is sent: drafts wait
            in Applications for your review.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <Toggle
            id="pref-auto"
            checked={draft.auto_draft_enabled}
            onChange={(v) => set({ auto_draft_enabled: v })}
            label="Draft my best new matches automatically"
            hint="Uses AI credits for each draft. Jobs that break your skip rules are never drafted."
          />
          <div className={draft.auto_draft_enabled ? 'grid gap-4 md:grid-cols-2' : 'grid gap-4 opacity-50 md:grid-cols-2'}>
            <div className="space-y-1.5">
              <Label htmlFor="pref-auto-score">Only jobs at this fit or above</Label>
              <div className="flex items-center gap-3">
                <input
                  id="pref-auto-score"
                  type="range"
                  min={50}
                  max={100}
                  step={5}
                  value={draft.auto_draft_min_score}
                  disabled={!draft.auto_draft_enabled}
                  onChange={(e) => set({ auto_draft_min_score: Number(e.target.value) })}
                  className="flex-1 accent-[var(--accent)]"
                />
                <span className="w-10 text-right text-sm font-medium tabular-nums">{draft.auto_draft_min_score}%</span>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pref-auto-cap">Drafts per day, at most</Label>
              <Input
                id="pref-auto-cap"
                type="number"
                min={1}
                max={10}
                inputMode="numeric"
                value={draft.auto_draft_daily_cap}
                disabled={!draft.auto_draft_enabled}
                onChange={(e) => set({ auto_draft_daily_cap: Math.min(10, Math.max(1, Number(e.target.value) || 1)) })}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center justify-end gap-2">
        {update.error && <span className="text-xs text-destructive">{update.error.message}</span>}
        {dirty && (
          <Button variant="ghost" onClick={reset} disabled={update.isPending}>
            Discard
          </Button>
        )}
        <Button onClick={() => update.mutate({ work_preferences: draft })} disabled={!dirty || update.isPending}>
          {update.isPending ? <Loader2 size={15} className="mr-1.5 animate-spin" /> : <Save size={15} className="mr-1.5" />}
          Save preferences
        </Button>
      </div>
    </div>
  );
}
