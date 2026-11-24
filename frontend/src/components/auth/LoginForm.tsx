// ============================================================
// JobPilot AI — Login Form Component
// ============================================================

import { useEffect, useState } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { useAuth } from '../../hooks/use-auth';
import { Mail, ArrowRight, Loader2, CheckCircle2, GitBranch } from 'lucide-react';

export function LoginForm() {
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const { signIn, signInWithProvider, activeProvider, loading, error, clearError } = useAuth();
  useEffect(() => {
    if (!cooldown) return;
    const timer = window.setTimeout(() => setCooldown(value => Math.max(0, value - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [cooldown]);

  const send = async () => {
    if (loading || cooldown || !email.trim()) return;
    clearError();
    try {
      await signIn(email.trim());
      setSubmitted(true);
      setCooldown(60);
    } catch {
      // The auth store presents safe copy. A rejected request is not a sent email.
    }
  };

  const openProvider = async (provider: 'google' | 'github') => {
    if (loading) return;
    clearError();
    try {
      await signInWithProvider(provider);
    } catch {
      // The auth store presents safe copy and leaves the sign-in options available.
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return;
    await send();
  };

  if (submitted) {
    return (
      <div className="login-success" role="status">
        <div className="login-success-icon">
          <CheckCircle2 size={48} />
        </div>
        <h3>Check your email</h3>
        <p>
          We sent a magic login link to <strong>{email}</strong>.
          <br />
          Click the link to sign in.
        </p>
        <p className="text-xs">Check spam too. Open the most recent link in this browser.</p>
        {error && <p className="login-error" role="alert">{error}</p>}
        <Button type="button" className="w-full" disabled={loading || cooldown > 0} onClick={send}>
          {loading ? 'Sending…' : cooldown ? `Resend in ${cooldown}s` : 'Resend sign-in link'}
        </Button>
        <Button
          type="button"
          variant="ghost"
          disabled={loading}
          onClick={() => {setSubmitted(false);setCooldown(0);clearError();}}
          className="login-try-again"
        >
          Other sign-in options
        </Button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="login-form">
      <div className="flex flex-col gap-3">
        <Button
          type="button"
          variant="outline"
          className="h-11 w-full gap-2"
          aria-label="Continue with Google"
          disabled={loading}
          onClick={() => openProvider('google')}
        >
          {activeProvider === 'google' ? (
            <Loader2 size={18} className="animate-spin" aria-hidden="true" />
          ) : (
            <span className="text-lg font-semibold leading-none" aria-hidden="true">G</span>
          )}
          {activeProvider === 'google' ? 'Opening Google…' : 'Continue with Google'}
        </Button>
        <Button
          type="button"
          variant="outline"
          className="h-11 w-full gap-2"
          aria-label="Continue with GitHub"
          disabled={loading}
          onClick={() => openProvider('github')}
        >
          {activeProvider === 'github' ? (
            <Loader2 size={18} className="animate-spin" aria-hidden="true" />
          ) : (
            <GitBranch size={18} aria-hidden="true" />
          )}
          {activeProvider === 'github' ? 'Opening GitHub…' : 'Continue with GitHub'}
        </Button>
      </div>

      <p className="sr-only" role="status">
        {activeProvider
          ? `Opening ${activeProvider === 'google' ? 'Google' : 'GitHub'} sign-in…`
          : loading ? 'Sending your sign-in link…' : ''}
      </p>

      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <span className="h-px flex-1 bg-border" aria-hidden="true" />
        <span>or use an email link</span>
        <span className="h-px flex-1 bg-border" aria-hidden="true" />
      </div>

      <div className="login-field">
        <Label htmlFor="email">Email address</Label>
        <div className="login-input-wrapper">
          <Mail size={18} className="login-input-icon" />
          <Input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={loading}
            required
            autoFocus
            className="login-email-input"
          />
        </div>
      </div>

      {error && (
        <p className="login-error" role="alert">{error}</p>
      )}

      <Button
        type="submit"
        disabled={loading || !email.trim()}
        className="login-submit-btn"
      >
        {loading && !activeProvider ? (
          <>
            <Loader2 size={18} className="animate-spin" />
            Sending...
          </>
        ) : (
          <>
            Send Magic Link
            <ArrowRight size={18} />
          </>
        )}
      </Button>

      <p className="login-disclaimer">
        Your job-search workspace. No password to remember.
      </p>
    </form>
  );
}
