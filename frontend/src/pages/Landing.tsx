// ============================================================
// JobPilot — Public landing page
// ============================================================

import { Link, Navigate } from 'react-router-dom';
import { ArrowRight, CheckCircle2, FileText, Loader2, Mail, MessageSquare, ShieldCheck } from 'lucide-react';
import { useAuth } from '../hooks/use-auth';
import { ROUTES } from '../lib/constants';

const FEATURES = [
  { icon: FileText, title: 'Tailored resumes', body: 'Rewrites your summary and bullets for each job, with an ATS keyword-match score and the gaps it found.' },
  { icon: Mail, title: 'Outreach drafted', body: 'A cover letter, a cold email with two follow-ups, and LinkedIn messages — ready for your edits.' },
  { icon: MessageSquare, title: 'Ask, don’t click', body: '“What needs my attention?” “Draft my follow-ups.” The assistant reads your pipeline and does the work.' },
  { icon: ShieldCheck, title: 'You approve every change', body: 'Status updates and edits arrive as proposals. Nothing changes or sends without your say.' },
];

const EXAMPLE = [
  { role: 'user', text: 'I applied to the Globex role yesterday. Also, which application needs work?' },
  {
    role: 'assistant',
    text: 'I’ve prepared the status change for your approval. Your weakest saved application is AI Platform Engineer at Initech (58% match) — it’s missing Go and Kubernetes. I’ve opened it so we can review the resume.',
  },
];

export default function Landing() {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center bg-background">
        <Loader2 className="animate-spin text-muted-foreground" size={24} />
      </div>
    );
  }
  if (isAuthenticated) return <Navigate to={ROUTES.CHAT} replace />;

  return (
    <div className="min-h-screen bg-background">
      <header className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4 sm:px-6">
        <span className="flex items-center gap-2">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-primary text-[11px] font-bold text-primary-foreground">JP</span>
          <span className="font-semibold tracking-tight">JobPilot</span>
        </span>
        <Link to={ROUTES.LOGIN} className="text-sm font-medium text-muted-foreground hover:text-foreground">
          Sign in
        </Link>
      </header>

      <section className="mx-auto max-w-5xl px-4 pb-16 pt-12 sm:px-6 sm:pt-20">
        <div className="mx-auto max-w-2xl text-center">
          <h1 className="text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">An AI assistant for your job search</h1>
          <p className="mt-5 text-lg leading-relaxed text-muted-foreground">
            Paste a job description and JobPilot tailors your resume, drafts every outreach message and keeps your pipeline up to date —
            all from one conversation.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Link
              to={ROUTES.LOGIN}
              className="inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/85"
            >
              Get started
              <ArrowRight size={16} />
            </Link>
            <span className="text-sm text-muted-foreground">Magic-link sign in</span>
          </div>
        </div>

        <div className="mx-auto mt-14 max-w-2xl rounded-2xl border bg-card p-5 shadow-sm">
          <div className="space-y-4">
            {EXAMPLE.map((m, i) =>
              m.role === 'user' ? (
                <div key={i} className="flex justify-end">
                  <p className="max-w-[85%] rounded-2xl bg-secondary px-4 py-2.5 text-sm">{m.text}</p>
                </div>
              ) : (
                <div key={i} className="space-y-2.5">
                  <p className="flex items-center gap-2 rounded-lg border bg-background px-3 py-2 text-xs text-muted-foreground">
                    <CheckCircle2 size={13} className="text-accent" />
                    Used 3 tools
                  </p>
                  <p className="text-sm leading-relaxed">{m.text}</p>
                </div>
              ),
            )}
          </div>
        </div>
      </section>

      <section className="border-t bg-card">
        <div className="mx-auto grid max-w-5xl gap-8 px-4 py-14 sm:grid-cols-2 sm:px-6">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <div key={title} className="flex gap-3">
              <Icon size={18} className="mt-0.5 shrink-0 text-accent" />
              <div>
                <h2 className="font-medium">{title}</h2>
                <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <footer className="py-8 text-center text-xs text-muted-foreground">JobPilot · Your resume facts are never invented</footer>
    </div>
  );
}
