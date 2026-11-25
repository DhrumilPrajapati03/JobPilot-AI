// ============================================================
// JobDots — Sign-in options (plan section 4.1)
// ============================================================

import { useState } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { useAuth } from '../../hooks/use-auth';
import { GitBranch, KeyRound, Loader2 } from 'lucide-react';

function GoogleMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
    </svg>
  );
}

export function LoginForm() {
  const { providers, signInWithProvider, signInWithToken, activeProvider, loading, error, clearError } = useAuth();
  const [token, setToken] = useState('');
  const noProviders = providers !== null && !providers.google && !providers.github;
  const [showToken, setShowToken] = useState(noProviders);

  const submitToken = async (e: React.FormEvent) => {
    e.preventDefault();
    if (loading || !token.trim()) return;
    clearError();
    try {
      await signInWithToken(token);
    } catch {
      // The store shows safe copy; the field keeps its value so it can be corrected.
    }
  };

  return (
    <div className="login-form">
      {error && <p className="login-error" role="alert">{error}</p>}

      <Button type="button" variant="outline" className="login-provider" disabled={loading || providers?.google === false}
        onClick={() => { clearError(); signInWithProvider('google'); }}>
        {activeProvider === 'google' ? <Loader2 className="animate-spin" size={18} /> : <GoogleMark />}
        Continue with Google
      </Button>
      <Button type="button" variant="outline" className="login-provider" disabled={loading || providers?.github === false}
        onClick={() => { clearError(); signInWithProvider('github'); }}>
        {activeProvider === 'github' ? <Loader2 className="animate-spin" size={18} /> : <GitBranch size={18} />}
        Continue with GitHub
      </Button>
      {noProviders && (
        <p className="login-note">Google and GitHub sign-in are not set up on the server yet. Use your owner token.</p>
      )}

      {showToken ? (
        <form className="login-token" onSubmit={submitToken}>
          <Label htmlFor="owner-token">Owner token</Label>
          <Input id="owner-token" type="password" autoComplete="current-password" spellCheck={false}
            value={token} onChange={e => setToken(e.target.value)} placeholder="OWNER_API_TOKEN from your .env" />
          <Button type="submit" className="w-full gap-2" disabled={loading || !token.trim()}>
            {loading && !activeProvider ? <Loader2 className="animate-spin" size={16} /> : <KeyRound size={16} />}
            Sign in with token
          </Button>
          <p className="login-note">Use this the first time, then link Google and GitHub in Settings.</p>
        </form>
      ) : (
        <button type="button" className="login-token-toggle" onClick={() => setShowToken(true)}>
          Use owner token instead
        </button>
      )}
    </div>
  );
}
