import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import api from '../../lib/api';
import { Button } from '../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';

interface Fact { id: string; kind: string; source_path: string; value: string | Record<string, string | string[]>; confirmed: boolean }
interface Vault { source_digest: string; facts: Fact[]; complete: boolean; confirmed_count: number; total: number }

function factText(fact: Fact): string {
  return typeof fact.value === 'string' ? fact.value : Object.values(fact.value).flat().filter(Boolean).join('\n');
}

export function FactsPanel() {
  const client = useQueryClient();
  const query = useQuery<Vault>({ queryKey: ['identity-facts'], queryFn: () => api.get('/profile/facts'), retry: false });
  const [selected, setSelected] = useState<string[]>([]);
  useEffect(() => setSelected([]), [query.data?.source_digest]);
  const refresh = () => {
    setSelected([]);
    client.invalidateQueries({ queryKey: ['identity-facts'] });
    client.invalidateQueries({ queryKey: ['discovery'] });
  };
  const confirm = useMutation({
    mutationFn: async () => {
      // A large resume can be reviewed in several batches without dropping facts.
      for (let i = 0; i < selected.length; i += 500) await api.post('/profile/facts/confirm', {
        source_digest: query.data!.source_digest, fact_ids: selected.slice(i, i + 500),
      });
    }, onSuccess: refresh, onError: () => client.invalidateQueries({ queryKey: ['identity-facts'] }),
  });
  const revoke = useMutation({ mutationFn: (id: string) => api.delete(`/profile/facts/${id}`), onSuccess: refresh });
  const busy = confirm.isPending || revoke.isPending;
  if (query.isLoading) return <p role="status">Loading your saved resume facts…</p>;
  if (query.error) return <p className="text-sm text-destructive" role="alert">{query.error.message}</p>;
  const vault = query.data;
  return <Card>
    <CardHeader><CardTitle>Review your resume facts</CardTitle>
      <p className="text-sm text-muted-foreground">Confirm what is accurate in your saved base resume before enabling automatic drafts. Confirmation is your declaration, not an independent credential check. Saving changed resume content requires a fresh review.</p>
    </CardHeader>
    <CardContent className="space-y-4">
      <p className="text-sm" role="status">{vault?.confirmed_count ?? 0} of {vault?.total ?? 0} facts confirmed by you. Scan your boards after a review to refresh match explanations.</p>
      {!vault?.facts.length && <p className="text-sm text-muted-foreground">Save your resume content in the other profile tabs, then return here.</p>}
      {!!vault?.facts.length && <div className="flex flex-wrap items-center gap-3">
        <Button variant="outline" disabled={busy} onClick={() => setSelected(vault.facts.filter(f => !f.confirmed).map(f => f.id))}>Select unconfirmed facts</Button>
        <Button disabled={busy || !selected.length} onClick={() => confirm.mutate()}>{confirm.isPending ? 'Confirming…' : `I confirm ${selected.length} selected facts are accurate`}</Button>
      </div>}
      {(confirm.error || revoke.error) && <p className="text-sm text-destructive" role="alert">{(confirm.error || revoke.error)?.message}</p>}
      <ul className="space-y-3">{vault?.facts.map(fact => <li key={fact.id} className="rounded-lg border p-3">
        <div className="flex items-start gap-3">
          {!fact.confirmed && <input type="checkbox" aria-label={`Select ${fact.kind}: ${factText(fact).slice(0,80)}`} checked={selected.includes(fact.id)} disabled={busy} onChange={e => setSelected(e.target.checked ? [...selected, fact.id] : selected.filter(id => id !== fact.id))} className="mt-1" />}
          <div className="min-w-0 flex-1"><p className="text-xs font-medium capitalize text-muted-foreground">Base resume · {fact.kind} · {fact.confirmed ? 'Confirmed by you' : 'Needs your review'}</p>
            <p className="mt-1 whitespace-pre-line break-words text-sm">{factText(fact)}</p></div>
          {fact.confirmed && <Button size="sm" variant="ghost" disabled={busy} onClick={() => revoke.mutate(fact.id)}>Revoke</Button>}
        </div>
      </li>)}</ul>
    </CardContent>
  </Card>;
}
