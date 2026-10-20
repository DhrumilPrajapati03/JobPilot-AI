// ============================================================
// JobPilot — Login
// ============================================================

import { Navigate } from 'react-router-dom';
import { LoginForm } from '../components/auth/LoginForm';
import { useAuth } from '../hooks/use-auth';
import { ROUTES } from '../lib/constants';

export default function Login() {
  const { isAuthenticated } = useAuth();
  if (isAuthenticated) return <Navigate to={ROUTES.CHAT} replace />;

  return (
    <div className="login-page">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center justify-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-primary text-xs font-bold text-primary-foreground">JP</span>
          <span className="text-lg font-semibold tracking-tight">JobPilot</span>
        </div>
        <div className="rounded-2xl border bg-card p-6 shadow-sm">
          <h1 className="text-xl font-semibold tracking-tight">Sign in</h1>
          <p className="mb-6 mt-1 text-sm text-muted-foreground">We'll email you a magic link — no password needed.</p>
          <LoginForm />
        </div>
      </div>
    </div>
  );
}
