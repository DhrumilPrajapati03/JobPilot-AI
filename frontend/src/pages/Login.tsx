// ============================================================
// JobPilot — Login
// ============================================================

import { Link, Navigate } from 'react-router-dom';
import { LoginForm } from '../components/auth/LoginForm';
import { useAuth } from '../hooks/use-auth';
import { ROUTES } from '../lib/constants';
import {Brand} from '../components/ui/brand';
import {ArrowLeft, Check, ShieldCheck} from 'lucide-react';

export default function Login() {
  const { isAuthenticated, initialized } = useAuth();
  if (isAuthenticated) return <Navigate to={ROUTES.OVERVIEW} replace />;

  return (
    <div className="login-page">
      <div className="login-layout">
        <section className="login-intro">
          <Link to="/" aria-label="JobPilot home"><Brand/></Link>
          <p className="eyebrow mt-12 text-accent">A clearer way to your next role</p>
          <h1>Your experience.<br/>Your next opportunity.</h1>
          <p className="text-muted-foreground">Find relevant roles, prepare thoughtful applications and keep every next step in one place.</p>
          <ul className="mt-8 space-y-3 text-sm text-muted-foreground">
            {['Discover with clear match evidence','Prepare materials from your actual experience','Review every application before you submit'].map(t=><li key={t} className="flex gap-3"><Check size={17} className="shrink-0 text-accent"/>{t}</li>)}
          </ul>
          <Link to="/" className="mt-10 inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft size={15}/>Back to JobPilot</Link>
        </section>
        <section className="login-card" aria-labelledby="sign-in-title">
          <div className="login-lock"><ShieldCheck size={23}/></div>
          <h2 id="sign-in-title" className="text-2xl font-semibold tracking-tight">Welcome to your workspace</h2>
          <p className="mb-7 mt-2 text-sm text-muted-foreground">Continue with Google or GitHub, or get a magic link by email.</p>
          {initialized ? <LoginForm /> : <p className="text-sm text-muted-foreground" role="status">Checking your sign-in…</p>}
        </section>
      </div>
    </div>
  );
}
