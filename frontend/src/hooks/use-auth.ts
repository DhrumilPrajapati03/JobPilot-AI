// ============================================================
// JobPilot AI — Auth Hook (Zustand Integrated)
// ============================================================

import { useAuthStore } from '../stores/auth-store';
import type { User } from '@supabase/supabase-js';
import type { SignInProvider } from '../stores/auth-store';

interface UseAuthReturn {
  user: User | null;
  loading: boolean;
  initialized: boolean;
  error: string | null;
  signIn: (email: string) => Promise<void>;
  signInWithProvider: (provider: SignInProvider) => Promise<void>;
  activeProvider: SignInProvider | null;
  clearError: () => void;
  signOut: () => Promise<void>;
  isAuthenticated: boolean;
}

export function useAuth(): UseAuthReturn {
  const { user, session, loading, initialized, error, signIn, signInWithProvider, activeProvider, clearError, signOut } = useAuthStore();

  return {
    user,
    loading,
    initialized,
    error,
    signIn,
    signInWithProvider,
    activeProvider,
    clearError,
    signOut,
    isAuthenticated: !!session,
  };
}

export default useAuth;
