// ============================================================
// JobDots — Login
// ============================================================

import { Navigate } from 'react-router-dom';
import { LoginForm } from '../components/auth/LoginForm';
import { useAuth } from '../hooks/use-auth';
import { ROUTES } from '../lib/constants';
import { ExpertAvatar } from '../components/experts/ExpertAvatar';

// The team sleeps until the owner signs in (bot-avatars, state "sleeping").
const TEAM = [
  { id: 'supervisor', name: 'Supervisor' },
  { id: 'scout', name: 'Scout' },
  { id: 'researcher', name: 'Researcher' },
  { id: 'tailor', name: 'Tailor' },
  { id: 'email_outreach', name: 'Email Outreach' },
];

function SleepingTeam() {
  return (
    <ul className="login-team" aria-label="Your experts are paused until you sign in">
      {TEAM.map(member => (
        <li key={member.id}>
          <ExpertAvatar expert={member.id} name={member.name} state="paused" step="Paused until you sign in" size={48} />
        </li>
      ))}
    </ul>
  );
}

export default function Login() {
  const { isAuthenticated, initialized } = useAuth();
  if (isAuthenticated) return <Navigate to={ROUTES.HOME} replace />;

  return (
    <main className="login-page">
      <section className="login-panel" aria-labelledby="sign-in-title">
        <SleepingTeam />
        <h1 id="sign-in-title">Sign in to JobDots</h1>
        <p className="login-lede">Your experts are paused. Sign in and they pick up where they left off.</p>
        {initialized ? <LoginForm /> : <p className="login-note" role="status">Checking your sign-in…</p>}
      </section>
    </main>
  );
}
