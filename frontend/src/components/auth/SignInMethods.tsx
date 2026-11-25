// ============================================================
// JobDots — Settings: linked sign-in accounts (plan section 4.1)
// ============================================================

import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { GitBranch, KeyRound, Link2, Unlink } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { API_BASE_URL } from '../../lib/constants';
import { sessionFetch } from '../../lib/session';

type Provider = 'google' | 'github';
interface Identity { provider: Provider; email: string; name: string; linked_at: string; last_login_at: string | null }
interface IdentityList { identities: Identity[]; available: Record<Provider, boolean> }

const LABEL: Record<Provider, string> = { google: 'Google', github: 'GitHub' };
const LINK_ERRORS: Record<string, string> = {
  linked_elsewhere: 'That account is already linked to another JobDots owner.',
  already_linked: 'Unlink the current account for this provider first, then link the new one.',
};

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await sessionFetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export function SignInMethods() {
  const queryClient = useQueryClient();
  const [notice, setNotice] = useState<string | null>(null);
  const list = useQuery<IdentityList>({ queryKey: ['auth', 'identities'], queryFn: () => json('/auth/identities') });
  const unlink = useMutation({
    mutationFn: (provider: Provider) => json<void>(`/auth/identities/${provider}`, { method: 'DELETE' }),
    onSuccess: (_d, provider) => { setNotice(`${LABEL[provider]} unlinked.`); queryClient.invalidateQueries({ queryKey: ['auth', 'identities'] }); },
  });

  // The API returns here after linking: /settings?linked=google or ?link_error=<code>.
  useEffect(() => {
    const url = new URL(window.location.href);
    const linked = url.searchParams.get('linked') as Provider | null;
    const failed = url.searchParams.get('link_error');
    if (linked && linked in LABEL) setNotice(`${LABEL[linked]} linked. You can sign in with it now.`);
    if (failed) setNotice(LINK_ERRORS[failed] ?? 'Linking did not complete. Try again.');
    if (linked || failed) {
      url.searchParams.delete('linked'); url.searchParams.delete('link_error');
      window.history.replaceState(window.history.state, '', url.pathname + url.search + url.hash);
    }
  }, []);

  const linkedBy = new Map(list.data?.identities.map(i => [i.provider, i]) ?? []);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><KeyRound size={17} />Sign-in</CardTitle>
        <p className="text-sm text-muted-foreground">
          Link your Google and GitHub accounts so you can sign in without the owner token. Only these exact accounts are accepted.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        {notice && <p className="text-sm" role="status">{notice}</p>}
        {list.isError && <p className="text-sm text-destructive" role="alert">Linked accounts could not be loaded. Reload the page.</p>}
        {(['google', 'github'] as Provider[]).map(provider => {
          const identity = linkedBy.get(provider);
          const available = list.data?.available[provider] ?? false;
          return (
            <div key={provider} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border px-4 py-3">
              <div className="flex items-center gap-3">
                {provider === 'github' ? <GitBranch size={18} /> : <span className="text-base font-semibold" aria-hidden="true">G</span>}
                <div>
                  <p className="text-sm font-medium">{LABEL[provider]}</p>
                  <p className="text-xs text-muted-foreground">
                    {identity ? `Linked${identity.email ? ` as ${identity.email}` : identity.name ? ` as ${identity.name}` : ''}`
                      : available ? 'Not linked' : 'Not set up on the server (see backend/.env.example)'}
                  </p>
                </div>
              </div>
              {identity ? (
                <Button variant="outline" size="sm" className="gap-2" disabled={unlink.isPending} onClick={() => unlink.mutate(provider)}>
                  <Unlink size={15} />Unlink {LABEL[provider]}
                </Button>
              ) : (
                <Button size="sm" className="gap-2" disabled={!available} onClick={() => window.location.assign(`${API_BASE_URL}/auth/${provider}/start?intent=link`)}>
                  <Link2 size={15} />Link {LABEL[provider]}
                </Button>
              )}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
