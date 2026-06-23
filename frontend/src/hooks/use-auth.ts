// ============================================================
// JobPilot AI — Auth Hook (Zustand Integrated)
// ============================================================

import { useAuthStore } from '../stores/auth-store';
import type { User } from '@supabase/supabase-js';

interface UseAuthReturn {
  user: User | null;
  loading: boolean;
  error: string | null;
  signIn: (email: string) => Promise<void>;
  signOut: () => Promise<void>;
  isAuthenticated: boolean;
}

export function useAuth(): UseAuthReturn {
  const { user, session, loading, error, signIn, signOut } = useAuthStore();

  return {
    user,
    loading,
    error,
    signIn,
    signOut,
    isAuthenticated: !!session,
  };
}

export default useAuth;
