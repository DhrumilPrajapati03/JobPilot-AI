// ============================================================
// JobDots — Login
// ============================================================

import { Navigate } from 'react-router-dom';
import { LoginForm } from '../components/auth/LoginForm';
import { useAuth } from '../hooks/use-auth';
import { ROUTES } from '../lib/constants';

// The team waits with eyes closed until the owner signs in. Our own shapes and colours,
// drawn inline (the full ExpertAvatar kit arrives with the roster UI).
const TEAM = [
  { name: 'Supervisor', color: 'var(--team-1)', path: 'M28 6c13 0 22 8 22 21s-9 23-22 23S6 41 6 27 15 6 28 6z' },
  { name: 'Scout', color: 'var(--team-2)', path: 'M28 5c10 2 22 9 22 23 0 13-10 22-22 22S6 41 6 28C6 14 17 3 28 5z' },
  { name: 'Tailor', color: 'var(--team-3)', path: 'M12 8h32c4 0 6 2 6 6v28c0 4-2 6-6 6H12c-4 0-6-2-6-6V14c0-4 2-6 6-6z' },
  { name: 'Recon', color: 'var(--team-4)', path: 'M28 4l20 11v24L28 51 8 39V15z' },
  { name: 'Email Outreach', color: 'var(--team-5)', path: 'M28 7c12 0 21 7 21 18 0 6-2 9-2 13 0 8-8 12-19 12S8 46 8 38c0-4-2-7-2-13C6 14 16 7 28 7z' },
];

function SleepingTeam() {
  return (
    <ul className="login-team" aria-label="Your experts are paused until you sign in">
      {TEAM.map((member, i) => (
        <li key={member.name} style={{ animationDelay: `${i * 0.6}s` }} title={`${member.name} is paused`}>
          <svg viewBox="0 0 56 56" width="44" height="44" aria-hidden="true">
            <path d={member.path} fill={member.color} />
            <path d="M18 30q4 3 8 0M30 30q4 3 8 0" fill="none" stroke="var(--team-eye)" strokeWidth="2.4" strokeLinecap="round" />
          </svg>
        </li>
      ))}
    </ul>
  );
}

export default function Login() {
  const { isAuthenticated, initialized } = useAuth();
  if (isAuthenticated) return <Navigate to={ROUTES.OVERVIEW} replace />;

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
