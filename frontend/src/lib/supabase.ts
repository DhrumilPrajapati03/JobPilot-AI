// ============================================================
// JobPilot AI — Supabase Client
// ============================================================
// Placeholder: configure with real Supabase URL and anon key via env vars.

import { SUPABASE_URL, SUPABASE_ANON_KEY } from './constants';

// TODO: Install @supabase/supabase-js and uncomment below
// import { createClient } from '@supabase/supabase-js';
// export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

/**
 * Placeholder Supabase client.
 * Replace with real implementation when @supabase/supabase-js is installed.
 */
export const supabase = {
  url: SUPABASE_URL,
  anonKey: SUPABASE_ANON_KEY,

  auth: {
    signInWithOtp: async (_opts: { email: string }) => {
      console.warn('[Supabase Placeholder] signInWithOtp called — not connected.');
      return { data: null, error: null };
    },
    signOut: async () => {
      console.warn('[Supabase Placeholder] signOut called — not connected.');
      return { error: null };
    },
    getSession: async () => {
      console.warn('[Supabase Placeholder] getSession called — not connected.');
      return { data: { session: null }, error: null };
    },
    onAuthStateChange: (_callback: (_event: string, _session: unknown) => void) => {
      console.warn('[Supabase Placeholder] onAuthStateChange — not connected.');
      return { data: { subscription: { unsubscribe: () => { } } } };
    },
  },
};

export default supabase;
