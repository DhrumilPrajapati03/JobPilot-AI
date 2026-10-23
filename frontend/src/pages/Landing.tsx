import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { Link, Navigate } from 'react-router-dom';
import { ArrowDown, ArrowRight, ArrowUpRight, Check, ChevronDown, Command, FileText, Fingerprint, Globe2, Layers3, Loader2, Mail, Menu, Radar, ShieldCheck, Sparkles, X } from 'lucide-react';
import { useAuth } from '../hooks/use-auth';
import { ROUTES } from '../lib/constants';
import { ApprovalDemo, AssistantDemo, HeroDemo, ResumeDemo, TrackerDemo, WorkflowDemo } from '../components/landing/LandingDemos';
import './Landing.css';

const SOURCES = ['Greenhouse', 'Lever', 'Ashby', 'SmartRecruiters', 'Himalayas', 'Remotive'];
const LINKS = [['Features', '#features'], ['How it works', '#how-it-works'], ['Integrations', '#integrations'], ['FAQ', '#faq']];
const STEPS = [
  ['Build your profile', 'Your experience is the starting point. Add and verify your professional details and base résumé.'],
  ['Discover opportunities', 'Follow supported company career pages and remote boards from one focused feed.'],
  ['Evaluate the match', 'Look beyond the job title. Review skills, preferences, and India remote eligibility.'],
  ['Prepare your application', 'Tailor your résumé, draft your outreach, and prepare answers for review.'],
  ['Apply and track', 'Use supervised autofill where supported. Submit on the employer’s website, then track what happens.'],
];
const FAQS = [
  ['What is JobPilot AI?', 'JobPilot is an AI-assisted job-search workspace. Discover relevant opportunities, tailor your résumé, prepare application materials, find referral contacts in your imported network, and track your search in one place.'],
  ['How does JobPilot find relevant jobs?', 'Follow supported company career pages and remote job boards. JobPilot compares published roles with your base résumé and preferences, and checks whether the listing confirms India eligibility. Match scores are guidance, not predictions of hiring outcomes.'],
  ['Does JobPilot automatically apply to jobs?', 'No. JobPilot prepares your materials and its Chrome extension helps fill supported forms. You review the answers and submit yourself on the employer’s website. Automatic drafting is optional and controlled in your preferences.'],
  ['Can I customize my résumé before applying?', 'Yes. Review tailored content, compare it with your base résumé, edit it, and export the saved version. Always verify generated content against your actual experience.'],
  ['Which job platforms are supported?', 'Discovery supports Greenhouse, Lever, Ashby, SmartRecruiters, Himalayas, and Remotive. Supervised autofill includes dedicated support for the first four; other forms vary. These are supported sources, not endorsements or partnerships.'],
  ['Can JobPilot help me contact recruiters?', 'It drafts a cover letter, recruiter emails with follow-ups, and LinkedIn messages for you to review and send yourself. Recruiter email and LinkedIn message delivery are not automated. Morning email digests are a separate feature.'],
  ['Can I track applications and follow-ups?', 'Yes. Use list and Kanban views to manage saved roles, applications, interviews, offers, and other outcomes. Record updates and see follow-up reminders, activity, and skill-gap insights.'],
];

function Brand() {
  return <span className="lp-brand"><span className="lp-mark" aria-hidden="true"><Command size={19} strokeWidth={1.7} /></span><span>JobPilot<span className="lp-brand-ai"> AI</span></span></span>;
}

export default function Landing() {
  const { isAuthenticated, loading } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = root.current;
    if (!element || !('IntersectionObserver' in window)) return;
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('lp-in-view');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08 });
    element.querySelectorAll('[data-reveal]').forEach((section) => observer.observe(section));
    return () => observer.disconnect();
  }, [loading]);

  if (loading) return <div className="lp-loading" role="status"><Loader2 size={24} className="animate-spin" /><span className="sr-only">Loading JobPilot</span></div>;
  if (isAuthenticated) return <Navigate to={ROUTES.CHAT} replace />;

  return (
    <div className="jobpilot-landing" ref={root} onClick={(event) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const anchor = (event.target as Element).closest<HTMLAnchorElement>('a[href^="#"]');
      const target = anchor && document.getElementById(anchor.hash.slice(1));
      if (!target) return;
      event.preventDefault();
      target.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' });
      window.history.replaceState(null, '', anchor!.hash);
      // Move focus as well as the viewport, including for the skip link.
      target.setAttribute('tabindex', '-1');
      target.focus({ preventScroll: true });
    }}>
      <title>JobPilot AI — Your job search, intelligently organized</title>
      <meta name="description" content="Discover relevant jobs, tailor your résumé, prepare applications, and track your search with an AI copilot. You review the work and decide when to apply." />
      <meta property="og:title" content="JobPilot AI — Your job search copilot" />
      <meta property="og:description" content="Less repetitive work. More focused applications. Discover, tailor, prepare, and track in one workspace." />
      <meta property="og:type" content="website" />
      <meta name="twitter:card" content="summary" />
      <a className="lp-skip" href="#main-content">Skip to content</a>
      <header className="lp-nav">
        <div className="lp-container lp-nav-inner">
          <a href="#main-content" aria-label="JobPilot AI home"><Brand /></a>
          <nav className="lp-desktop-links" aria-label="Main navigation">{LINKS.map(([name, href]) => <a key={href} href={href}>{name}</a>)}</nav>
          <div className="lp-nav-actions"><Link className="lp-login" to={ROUTES.LOGIN}>Log in <ArrowUpRight size={13} /></Link><Link className="lp-button lp-button-small" to={ROUTES.LOGIN}>Get started <ArrowRight size={14} /></Link></div>
          <button ref={menuButton} type="button" className="lp-menu-button" aria-expanded={menuOpen} aria-controls="lp-mobile-menu" aria-label={menuOpen ? 'Close navigation' : 'Open navigation'} onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X /> : <Menu />}</button>
        </div>
        {menuOpen && <nav id="lp-mobile-menu" className="lp-mobile-menu" aria-label="Mobile navigation" onKeyDown={(e) => { if (e.key === 'Escape') { setMenuOpen(false); menuButton.current?.focus(); } }}>{LINKS.map(([name, href]) => <a key={href} href={href} onClick={() => setMenuOpen(false)}>{name}<ArrowUpRight size={16} /></a>)}<Link to={ROUTES.LOGIN}>Log in / Get started <ArrowRight size={16} /></Link></nav>}
      </header>

      <main id="main-content">
        <section className="lp-hero">
          <div className="lp-container lp-hero-content">
            <div className="lp-eyebrow lp-hero-badge"><span className="lp-live-dot" /> AI-powered job search workspace</div>
            <h1>Stop searching.<br />Start getting closer to<br /><span className="lp-headline-highlight">your next role<span className="lp-corner" /></span><span className="lp-period">.</span></h1>
            <p className="lp-hero-copy">Discover relevant jobs, tailor your résumé, and prepare<br className="lp-desktop-break" /> your next application. One workspace. A clearer way forward.</p>
            <div className="lp-cta-row"><Link className="lp-button" to={ROUTES.LOGIN}>Get started <ArrowUpRight size={17} /></Link><a className="lp-button lp-button-outline" href="#demo">Explore the platform <ArrowDown size={15} /></a></div>
            <div className="lp-hero-note"><span><Check size={12} /> Magic-link sign in</span><span><Check size={12} /> Human-controlled decisions</span></div>
            <HeroDemo />
            <div className="lp-preview-caption"><span><span className="lp-tiny-square" /> A little less scattered. A lot more focused.</span><span>ILLUSTRATIVE PRODUCT PREVIEW / NO LIVE DATA</span></div>
          </div>
          <span className="lp-hero-coordinate" aria-hidden="true">JP_AI / WORKSPACE_01</span>
        </section>

        <section id="integrations" className="lp-sources"><div className="lp-container">
          <div className="lp-source-heading"><div><span className="lp-eyebrow">Connected to your search</span><h2>One workspace. Multiple job sources.</h2></div><p>Supported career systems and remote boards.<br />Fewer tabs between you and the right opportunity.</p></div>
          <div className="lp-source-strip">{SOURCES.map((source, i) => <div className="lp-source" key={source}><span className={`lp-source-symbol lp-source-symbol-${i}`} aria-hidden="true">{['g', 'L', 'a', 'sr', '△', 'r'][i]}</span><span>{source}</span></div>)}</div>
          <p className="lp-source-disclaimer">Public discovery sources. No endorsement or partnership implied.</p>
        </div></section>

        <section id="demo" className="lp-light lp-section"><div className="lp-container" data-reveal>
          <span className="lp-eyebrow">[ 01 // The intelligence engine ]</span>
          <div className="lp-section-heading"><h2>From job discovery to<br />application readiness.</h2><p>A scattered search becomes a focused workflow.<br />Take a look under the hood.</p></div>
          <WorkflowDemo />
        </div></section>

        <section id="features" className="lp-light lp-section lp-features-section"><div className="lp-container" data-reveal>
          <span className="lp-eyebrow">[ 02 // Core capabilities ]</span>
          <h2>Everything your job search needs.<br /><span className="lp-soft-text">Nothing it doesn’t.</span></h2>
          <div className="lp-bento">
            <article className="lp-feature lp-feature-match"><div className="lp-feature-icon"><Radar size={21} /></div><h3>Good opportunities.<br />Better alignment.</h3><p>See how your skills and preferences line up before you invest in an application.</p><div className="lp-match-mini"><div className="lp-row"><span className="lp-company-avatar">E</span><div><strong>AI Engineer</strong><small>Example AI Studio · Remote, India</small></div><span className="lp-score-small">92<span>%</span></span></div><div className="lp-mini-bars"><span>Technical alignment</span><i style={{ '--fill': '92%' } as CSSProperties} /><span>Role relevance</span><i style={{ '--fill': '85%' } as CSSProperties} /></div><div className="lp-tags"><span>Python</span><span>RAG</span><span>FastAPI</span></div><small className="lp-muted">Illustrative fit, not hiring probability</small></div></article>
            <article className="lp-feature lp-feature-resume"><div className="lp-feature-icon"><FileText size={21} /></div><h3>Your experience.<br />The right emphasis.</h3><p>Tailor the wording, keep the facts. Compare your original and revised résumé.</p><ResumeDemo /></article>
            <article className="lp-feature lp-feature-prepare"><div className="lp-feature-icon"><Layers3 size={21} /></div><h3>Ready for your review.</h3><p>Bring the moving parts into one prepared application package.</p><ol className="lp-mini-timeline">{['Job analyzed', 'Résumé tailored', 'Answers prepared', 'Ready for review'].map((step, i) => <li key={step}><span>{i < 3 ? <Check size={12} /> : <ArrowRight size={12} />}</span>{step}<small>{i === 3 ? 'YOUR TURN' : 'PREPARED'}</small></li>)}</ol></article>
            <article className="lp-feature lp-feature-outreach"><div className="lp-feature-icon"><Mail size={21} /></div><h3>Start a real conversation.</h3><p>Company-aware outreach, ready for your edits. You choose when and where to send.</p><div className="lp-email-mini"><div className="lp-row"><span className="lp-eyebrow">Recruiter email</span><span className="lp-pill">Draft only</span></div><strong>Subject: Building RAG systems at Example AI</strong><p>Hi Hiring Team,<br /><br />Your AI Engineer role caught my attention. My experience building a Python retrieval service with FastAPI aligns with your RAG work. I’d love to learn more.</p></div></article>
            <article className="lp-feature lp-feature-tracker"><div className="lp-feature-icon"><Layers3 size={21} /></div><h3>Know where things stand.</h3><p>From saved to interviewing. A clear view of your next action.</p><TrackerDemo compact /></article>
            <article className="lp-feature lp-feature-digest"><div className="lp-feature-icon"><Sparkles size={21} /></div><h3>A calmer kind of morning.</h3><p>Optional scheduled scans and email digests help you pick up where you left off.</p><div className="lp-digest-mini"><div className="lp-row"><span className="lp-eyebrow">Your morning briefing</span><span className="lp-muted">07:00</span></div><strong>Good morning. Here’s your next move.</strong>{[['03', 'new sample matches'], ['02', 'packages to review'], ['01', 'follow-up reminder']].map(([n, label]) => <div key={label}><span>{n}</span>{label}<ArrowUpRight size={13} /></div>)}<small className="lp-muted">Sample briefing · Requires email setup</small></div></article>
          </div>
        </div></section>

        <section className="lp-control lp-section"><div className="lp-container lp-split" data-reveal><div><span className="lp-eyebrow">[ 03 // Built around your decisions ]</span><h2>AI does the preparation.<br /><span className="lp-blue-text">You stay in control.</span></h2><p className="lp-section-copy">Less repetitive work doesn’t mean giving up the final say. Review the details. Make them yours. Apply when you’re ready.</p><ul className="lp-control-list">{['Review and edit generated résumé content', 'Keep recruiter messages as drafts until you send', 'Choose your discovery and auto-draft preferences', 'Submit applications yourself on the employer’s website'].map((text) => <li key={text}><Check size={15} />{text}</li>)}</ul></div><ApprovalDemo /></div></section>

        <section id="how-it-works" className="lp-light lp-section"><div className="lp-container lp-steps-layout" data-reveal><div><span className="lp-eyebrow">The workflow / end to end</span><h2>Five steps.<br />One clear<br /><span className="lp-soft-text">way forward.</span></h2><p className="lp-section-copy">A more organized job search starts with the experience you already have.</p><Link to={ROUTES.LOGIN} className="lp-text-link">Build your workspace <ArrowUpRight size={17} /></Link></div><ol className="lp-steps">{STEPS.map(([title, body], i) => <li key={title}><span className="lp-step-number">0{i + 1}</span><div><h3>{title}</h3><p>{body}</p></div><ArrowUpRight size={17} aria-hidden="true" /></li>)}</ol></div></section>

        <section id="assistant" className="lp-assistant-section lp-section"><div className="lp-container lp-split" data-reveal><div><span className="lp-eyebrow">[ 04 // Your job search copilot ]</span><h2>Ask for what you need.<br /><span className="lp-blue-text">Organize what’s next.</span></h2><p className="lp-section-copy">A conversation that connects to your workflow. Explore matches, prepare materials, or work through your next follow-up.</p><div className="lp-assistant-annotation"><span className="lp-live-dot" /> Try a prompt in the interactive example <ArrowRight size={15} /></div></div><AssistantDemo /></div></section>

        <section className="lp-trust lp-light"><div className="lp-container lp-trust-inner"><div><Fingerprint size={26} /><h2>Your career information<br />deserves careful handling.</h2></div><div className="lp-trust-items"><span><ShieldCheck size={18} /> Account sign-in</span><span><FileText size={18} /> Reviewable materials</span><span><Globe2 size={18} /> Explicit extension connection</span><span><Check size={18} /> Your application decisions</span></div></div></section>

        <section id="faq" className="lp-light lp-section"><div className="lp-container lp-faq-layout" data-reveal><div><span className="lp-eyebrow">A little more clarity</span><h2>Good questions.<br /><span className="lp-soft-text">Straight answers.</span></h2><p className="lp-section-copy">What JobPilot does, and where you come in.</p></div><div className="lp-faq-list">{FAQS.map(([question, answer], i) => <details key={question} name="jobpilot-faq"><summary><span className="lp-faq-number">0{i + 1}</span><h3>{question}</h3><ChevronDown size={17} /></summary><div className="lp-faq-answer"><p>{answer}</p></div></details>)}</div></div></section>

        <section className="lp-final-cta"><div className="lp-container"><span className="lp-eyebrow">Your next chapter / starts here</span><h2>Your next opportunity<br />deserves a <span className="lp-blue-text">smarter search.</span></h2><p>Bring discovery, tailored applications, and tracking<br className="lp-desktop-break" /> together in one AI-powered workspace.</p><div className="lp-cta-row"><Link className="lp-button" to={ROUTES.LOGIN}>Start with JobPilot <ArrowUpRight size={17} /></Link><a className="lp-button lp-button-outline" href="#how-it-works">See how it works <ArrowRight size={16} /></a></div><span className="lp-final-label">AI-POWERED PREPARATION. HUMAN-CONTROLLED DECISIONS.</span></div></section>
      </main>

      <footer className="lp-footer"><div className="lp-container"><div className="lp-footer-top"><div><Brand /><p>A focused workspace for your next opportunity.</p></div><nav aria-label="Footer product links"><span className="lp-eyebrow">Product</span>{LINKS.slice(0, 3).map(([name, href]) => <a href={href} key={href}>{name}</a>)}</nav><nav aria-label="Footer resources"><span className="lp-eyebrow">Explore</span><a href="#faq">FAQ</a><a href="#demo">Interactive demo</a><Link to={ROUTES.LOGIN}>Open workspace <ArrowUpRight size={12} /></Link></nav></div><div className="lp-footer-bottom"><span>© {new Date().getFullYear()} JobPilot AI</span><span className="lp-eyebrow">Built for the next step.</span><a href="#main-content">Back to top ↑</a></div></div></footer>
    </div>
  );
}
