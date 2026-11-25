// ============================================================
// JobDots — Auth store
// ============================================================
// Sign-in happens on the API (plan section 4.1): Google or GitHub, or the owner token as
// break-glass. The API sets an HttpOnly session cookie; this store only asks who is
// signed in (GET /api/v1/auth/me) and never holds a credential.

import { create } from 'zustand';
import { resetQueryAccount } from '../lib/query-client';
import { selectChatAccount } from '../agent/store';
import { stopChat } from '../agent/client';
import { authErrorMessage, loginErrorFromUrl } from '../lib/auth-errors';
import { setAccountContext } from '../lib/account-context';
import { cleanAuthCallbackUrl } from '../lib/auth-redirect';
import { API_BASE_URL, API_URL } from '../lib/constants';
import { sessionFetch } from '../lib/session';

export type SignInProvider = 'google' | 'github';
export interface Owner { id: string; email: string }
export interface Providers { google: boolean; github: boolean; token: boolean }

let accountId: string | null | undefined;
let initialization: Promise<void> | null = null;

function isolateAccount(user: Owner | null) {
  const nextId = user?.id ?? null;
  if (accountId === nextId) return;
  setAccountContext(nextId);
  stopChat();
  resetQueryAccount();
  selectChatAccount(nextId);
  // Never resume a previous account's standalone generation run.
  try { sessionStorage.removeItem('jobpilot:active-run'); } catch { /* blocked storage */ }
  accountId = nextId;
}

async function whoAmI(): Promise<Owner | null> {
  const response = await sessionFetch(`${API_URL}/auth/me`);
  if (response.status === 401) return null;
  if (!response.ok) throw Object.assign(new Error('session check failed'), { status: response.status });
  const body = await response.json();
  return { id: body.user_id, email: body.email ?? '' };
}

interface AuthState {
  user: Owner | null;
  providers: Providers | null;
  loading: boolean;
  initialized: boolean;
  error: string | null;
  activeProvider: SignInProvider | null;

  initialize: () => Promise<void>;
  signInWithProvider: (provider: SignInProvider) => void;
  signInWithToken: (token: string) => Promise<void>;
  clearError: () => void;
  signOut: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  providers: null,
  loading: true,
  initialized: false,
  error: null,
  activeProvider: null,
  clearError: () => set({ error: null }),

  initialize: () => {
    if (initialization) return initialization;
    const run = async () => {
      set({ loading: true, error: null });
      // The API sends failed logins back as /login?auth_error=<code>.
      const urlError = loginErrorFromUrl(window.location.href);
      if (urlError) window.history.replaceState(window.history.state, '', cleanAuthCallbackUrl(window.location.href));
      try {
        const [user, providers] = await Promise.all([
          whoAmI(),
          fetch(`${API_BASE_URL}/auth/providers`).then(r => (r.ok ? r.json() : null)).catch(() => null),
        ]);
        isolateAccount(user);
        set({ user, providers, loading: false, initialized: true, error: user ? null : urlError });
      } catch (err) {
        set({ error: authErrorMessage(err, 'session'), loading: false, initialized: true });
      }
    };
    // React StrictMode may run startup effects twice; share one in-flight check.
    initialization = run().finally(() => { initialization = null; });
    return initialization;
  },

  signInWithProvider: (provider: SignInProvider) => {
    if (get().loading && get().activeProvider) return;
    if (!['google', 'github'].includes(provider)) return;
    set({ loading: true, error: null, activeProvider: provider });
    // Full-page navigation: the API sets state and PKCE, then redirects to the provider.
    window.location.assign(`${API_BASE_URL}/auth/${provider}/start`);
  },

  signInWithToken: async (token: string) => {
    set({ loading: true, error: null });
    try {
      const response = await fetch(`${API_BASE_URL}/auth/session`, {
        method: 'POST', credentials: 'include',
        headers: { Authorization: `Bearer ${token.trim()}` },
      });
      if (!response.ok) throw Object.assign(new Error('token rejected'), { status: response.status });
      const user = await whoAmI();
      isolateAccount(user);
      set({ user, loading: false });
    } catch (err) {
      const message = authErrorMessage(err, 'token');
      set({ error: message, loading: false });
      throw new Error(message);
    }
  },

  signOut: async () => {
    set({ loading: true, error: null });
    try {
      await sessionFetch(`${API_BASE_URL}/auth/logout`, { method: 'POST' });
    } finally {
      isolateAccount(null);
      set({ user: null, loading: false });
    }
  },
}));
