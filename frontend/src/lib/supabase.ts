// ============================================================
// JobPilot AI — Supabase Client
// ============================================================

import { createClient } from '@supabase/supabase-js';
import { SUPABASE_URL, SUPABASE_ANON_KEY } from './constants';

if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
  console.error(
    'Supabase configuration is missing. Ensure VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY are set in your frontend .env file.'
  );
}

// Create a singleton instance of the client
export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

export default supabase;
