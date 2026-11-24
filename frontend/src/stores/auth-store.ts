// ============================================================
// JobPilot AI — Auth Zustand Store
// ============================================================

import { create } from 'zustand';
import { supabase } from '../lib/supabase';
import type { User, Session } from '@supabase/supabase-js';
import { resetQueryAccount } from '../lib/query-client';
import { selectChatAccount } from '../agent/store';
import { stopChat } from '../agent/client';
import { authErrorMessage } from '../lib/auth-errors';
import { setAccountContext } from '../lib/account-context';
import { authReturnUrl, hasAuthCallback, cleanAuthCallbackUrl, legacySessionFromUrl } from '../lib/auth-redirect';
import { SUPABASE_URL, SUPABASE_ANON_KEY } from '../lib/constants';

export type SignInProvider = 'google' | 'github';

let accountId: string | null | undefined;
let authSubscription: { unsubscribe: () => void } | undefined;
let resumeHandler: ((event: PageTransitionEvent) => void) | undefined;
let initialization: Promise<void> | null = null;

function isolateAccount(session: Session | null) {
    const nextId = session?.user.id ?? null;
    if (accountId === nextId) return;
    setAccountContext(nextId);
    stopChat();
    resetQueryAccount();
    selectChatAccount(nextId);
    // Never resume a previous account's standalone generation run.
    try { sessionStorage.removeItem('jobpilot:active-run'); } catch { /* blocked storage */ }
    accountId = nextId;
}

interface AuthState {
    user: User | null;
    session: Session | null;
    loading: boolean;
    initialized: boolean;
    error: string | null;
    activeProvider: SignInProvider | null;

    // Actions
    initialize: () => Promise<void>;
    signIn: (email: string) => Promise<void>;
    signInWithProvider: (provider: SignInProvider) => Promise<void>;
    clearError: () => void;
    signOut: () => Promise<void>;
    setSession: (session: Session | null) => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
    user: null,
    session: null,
    loading: true,
    initialized: false,
    error: null,
    activeProvider: null,
    clearError: () => set({error:null}),

    initialize: () => {
        if(initialization)return initialization;
        const run=async()=>{
        set({ loading: true, error: null });
        const callback = hasAuthCallback(window.location.href);
        try {
            // The SDK owns PKCE exchange and verifier validation. Do not exchange twice.
            let { error: callbackError } = await supabase.auth.initialize();
            const legacy = legacySessionFromUrl(window.location.href);
            if (legacy) {
                // SDK validates/refetches the user; the singleton stays PKCE for
                // every later sign-in, including after sign-out without reload.
                const result=await supabase.auth.setSession(legacy);
                callbackError=result.error;
            }
            // 1. Get current active session (from localStorage)
            const { data: { session }, error } = await supabase.auth.getSession();
            if (error) throw error;
            if (callback) window.history.replaceState(window.history.state, '', cleanAuthCallbackUrl(window.location.href));
            isolateAccount(session);

            set({
                session,
                user: session?.user ?? null,
                loading: false,
                initialized: true,
                error: callbackError ? authErrorMessage(callbackError,'session') : callback && !session
                    ? authErrorMessage({code:'flow_state_not_found'},'session') : null,
            });

            // 2. Set up event listener for session changes
            // This will trigger automatically when a user clicks the magic link,
            // token expires, or they log out.
            authSubscription?.unsubscribe();
            const { data } = supabase.auth.onAuthStateChange((_event, session) => {
                isolateAccount(session);
                set({
                    session,
                    user: session?.user ?? null,
                    loading: session ? false : get().loading,
                    ...(session ? {activeProvider:null} : {}),
                });
            });
            authSubscription = data.subscription;
            if (resumeHandler) window.removeEventListener('pageshow',resumeHandler);
            resumeHandler = event => {
                if(event.persisted && get().activeProvider) set({loading:false,activeProvider:null,error:null});
            };
            window.addEventListener('pageshow',resumeHandler);
        } catch (err: any) {
            set({
                error: authErrorMessage(err,'session'),
                loading: false,
                initialized: true,
            });
            if (callback) window.history.replaceState(window.history.state, '', cleanAuthCallbackUrl(window.location.href));
        }
        };
        // React StrictMode may run startup effects twice. Consume old email
        // fragments and attach listeners once per in-flight initialization.
        initialization=run().finally(()=>{initialization=null;});
        return initialization;
    },

    signIn: async (email: string) => {
        set({ loading: true, error: null });
        try {
            const { error } = await supabase.auth.signInWithOtp({
                email: email.trim(),
                options: {
                    emailRedirectTo: authReturnUrl(window.location.origin),
                },
            });

            if (error) throw error;
            set({ loading: false });
        } catch (err: any) {
            const message = authErrorMessage(err);
            set({
                error: message,
                loading: false
            });
            throw new Error(message);
        }
    },

    signInWithProvider: async (provider: SignInProvider) => {
        if (get().loading) throw new Error('A sign-in request is already in progress.');
        if (!['google','github'].includes(provider)) throw new Error('Unsupported sign-in provider.');
        set({loading:true,error:null,activeProvider:provider});
        let redirectStarted=false;
        try {
            // A disabled provider's authorize endpoint can render an off-site JSON
            // error. Check public availability first, keeping the email fallback here.
            const response = await fetch(`${SUPABASE_URL}/auth/v1/settings`, {
                headers:{apikey:SUPABASE_ANON_KEY}, signal:AbortSignal.timeout(10000),
            });
            if (!response.ok) throw new Error('Sign-in availability check failed.');
            const available = await response.json();
            if (available.external?.[provider] !== true)
                throw Object.assign(new Error('Provider unavailable'),{code:'provider_disabled'});
            const {data,error} = await supabase.auth.signInWithOAuth({
                provider,
                options:{redirectTo:authReturnUrl(window.location.origin),
                    skipBrowserRedirect:true,
                    scopes:provider==='google'?'openid email profile':'user:email',
                    ...(provider==='google'?{queryParams:{prompt:'select_account'}}:{}),
                },
            });
            if (error) throw error;
            if (!data.url) throw new Error('Sign-in did not start.');
            window.location.assign(data.url);
            redirectStarted=true;
        } catch (err: unknown) {
            const message=authErrorMessage(err,'oauth');
            set({error:message});
            throw new Error(message);
        } finally {
            // Do not replace the verifier while navigation is pending. A fresh
            // load or BFCache pageshow resets this state when the user returns.
            if(!redirectStarted) set({loading:false,activeProvider:null});
        }
    },

    signOut: async () => {
        set({ loading: true, error: null });
        try {
            const { error } = await supabase.auth.signOut();
            if (error) throw error;
            isolateAccount(null);
            set({ user: null, session: null, loading: false });
        } catch (err: any) {
            set({
                error: err.message || 'Failed to sign out',
                loading: false
            });
        }
    },

    setSession: (session: Session | null) => {
        isolateAccount(session);
        set({ session, user: session?.user ?? null });
    },
}));
