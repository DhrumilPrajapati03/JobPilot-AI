// ============================================================
// JobPilot AI — Auth Hook (Placeholder)
// ============================================================

import { useState, useEffect, useCallback } from 'react';

interface AuthUser {
  id: string;
  email: string;
  name?: string;
}

interface UseAuthReturn {
  user: AuthUser | null;
  loading: boolean;
  error: string | null;
  signIn: (email: string) => Promise<void>;
  signOut: () => Promise<void>;
  isAuthenticated: boolean;
}

/**
 * Placeholder auth hook. 
 * In production, this will use Supabase Auth with magic link login.
 * Currently returns a mock authenticated user for development.
 */
export function useAuth(): UseAuthReturn {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Simulate checking for existing session
    const checkSession = async () => {
      try {
        // TODO: Replace with real Supabase session check
        // const { data: { session } } = await supabase.auth.getSession();

        // For development, auto-login with mock user
        setUser({
          id: 'dev-user-001',
          email: 'dhrumil@jobpilot.dev',
          name: 'Dhrumil',
        });
      } catch {
        setError('Failed to check authentication status');
      } finally {
        setLoading(false);
      }
    };

    checkSession();
  }, []);

  const signIn = useCallback(async (email: string) => {
    setLoading(true);
    setError(null);
    try {
      // TODO: Replace with real Supabase magic link sign-in
      // const { error } = await supabase.auth.signInWithOtp({ email });
      console.log(`[Auth Placeholder] Magic link sent to: ${email}`);

      // Simulate successful login for development
      setUser({
        id: 'dev-user-001',
        email,
        name: email.split('@')[0],
      });
    } catch {
      setError('Failed to send magic link');
    } finally {
      setLoading(false);
    }
  }, []);

  const signOut = useCallback(async () => {
    setLoading(true);
    try {
      // TODO: Replace with real Supabase sign-out
      // await supabase.auth.signOut();
      setUser(null);
    } catch {
      setError('Failed to sign out');
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    user,
    loading,
    error,
    signIn,
    signOut,
    isAuthenticated: !!user,
  };
}

export default useAuth;
