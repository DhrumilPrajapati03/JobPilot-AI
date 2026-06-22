// ============================================================
// JobPilot AI — Login Form Component
// ============================================================

import { useState } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { useAuth } from '../../hooks/use-auth';
import { Mail, ArrowRight, Loader2, CheckCircle2 } from 'lucide-react';

export function LoginForm() {
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const { signIn, loading, error } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return;
    await signIn(email);
    setSubmitted(true);
  };

  if (submitted && !error) {
    return (
      <div className="login-success">
        <div className="login-success-icon">
          <CheckCircle2 size={48} />
        </div>
        <h3>Check your email</h3>
        <p>
          We sent a magic login link to <strong>{email}</strong>.
          <br />
          Click the link to sign in.
        </p>
        <Button
          variant="ghost"
          onClick={() => setSubmitted(false)}
          className="login-try-again"
        >
          Use a different email
        </Button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="login-form">
      <div className="login-field">
        <Label htmlFor="email">Email address</Label>
        <div className="login-input-wrapper">
          <Mail size={18} className="login-input-icon" />
          <Input
            id="email"
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoFocus
            className="login-email-input"
          />
        </div>
      </div>

      {error && (
        <p className="login-error">{error}</p>
      )}

      <Button
        type="submit"
        disabled={loading || !email.trim()}
        className="login-submit-btn"
      >
        {loading ? (
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
        By continuing, you agree to JobPilot AI's Terms of Service and Privacy Policy.
      </p>
    </form>
  );
}
