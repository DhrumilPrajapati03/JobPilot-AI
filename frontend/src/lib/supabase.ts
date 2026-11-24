// ============================================================
// JobPilot AI — Supabase Client
// ============================================================

import { createClient } from '@supabase/supabase-js';
import { SUPABASE_URL, SUPABASE_ANON_KEY } from './constants';
import { legacySessionFromUrl } from './auth-redirect';

if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
  console.error(
    'Supabase configuration is missing. Ensure VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY are set in your frontend .env file.'
  );
}

// Create a singleton instance of the client
export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    flowType: 'pkce',
    detectSessionInUrl: typeof window === 'undefined' || !legacySessionFromUrl(window.location.href),
    persistSession: true,
    autoRefreshToken: true,
  },
});

export default supabase;
