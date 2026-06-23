// ============================================================
// JobPilot AI — Auth Zustand Store
// ============================================================

import { create } from 'zustand';
import { supabase } from '../lib/supabase';
import type { User, Session } from '@supabase/supabase-js';

interface AuthState {
    user: User | null;
    session: Session | null;
    loading: boolean;
    error: string | null;

    // Actions
    initialize: () => Promise<void>;
    signIn: (email: string) => Promise<void>;
    signOut: () => Promise<void>;
    setSession: (session: Session | null) => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
    user: null,
    session: null,
    loading: true,
    error: null,

    initialize: async () => {
        set({ loading: true, error: null });
        try {
            // 1. Get current active session (from localStorage)
            const { data: { session } } = await supabase.auth.getSession();

            set({
                session,
                user: session?.user ?? null,
                loading: false
            });

            // 2. Set up event listener for session changes
            // This will trigger automatically when a user clicks the magic link,
            // token expires, or they log out.
            supabase.auth.onAuthStateChange((_event, session) => {
                set({
                    session,
                    user: session?.user ?? null,
                    loading: false
                });
            });
        } catch (err: any) {
            set({
                error: err.message || 'Failed to initialize session',
                loading: false
            });
        }
    },

    signIn: async (email: string) => {
        set({ loading: true, error: null });
        try {
            const { error } = await supabase.auth.signInWithOtp({
                email,
                options: {
                    emailRedirectTo: window.location.origin, // Returns user back to this domain after click
                },
            });

            if (error) throw error;
            set({ loading: false });
        } catch (err: any) {
            set({
                error: err.message || 'Failed to send magic link',
                loading: false
            });
            throw err;
        }
    },

    signOut: async () => {
        set({ loading: true, error: null });
        try {
            const { error } = await supabase.auth.signOut();
            if (error) throw error;
            set({ user: null, session: null, loading: false });
        } catch (err: any) {
            set({
                error: err.message || 'Failed to sign out',
                loading: false
            });
        }
    },

    setSession: (session: Session | null) => {
        set({ session, user: session?.user ?? null });
    },
}));
