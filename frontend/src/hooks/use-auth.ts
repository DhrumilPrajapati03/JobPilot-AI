// ============================================================
// JobDots — Auth hook
// ============================================================

import { useAuthStore } from '../stores/auth-store';
import type { Owner, Providers, SignInProvider } from '../stores/auth-store';

interface UseAuthReturn {
  user: Owner | null;
  providers: Providers | null;
  loading: boolean;
  initialized: boolean;
  error: string | null;
  signInWithProvider: (provider: SignInProvider) => void;
  signInWithToken: (token: string) => Promise<void>;
  activeProvider: SignInProvider | null;
  clearError: () => void;
  signOut: () => Promise<void>;
  isAuthenticated: boolean;
}

export function useAuth(): UseAuthReturn {
  const { user, providers, loading, initialized, error, signInWithProvider, signInWithToken, activeProvider, clearError, signOut } = useAuthStore();
  return {
    user, providers, loading, initialized, error, signInWithProvider, signInWithToken, activeProvider, clearError, signOut,
    isAuthenticated: !!user,
  };
}

export default useAuth;
