import { useRef, useState, type KeyboardEvent } from 'react';
import { ArrowRight, ArrowUpRight, Check, CheckCheck, ChevronRight, FileText, Layers3, Mail, MessageSquare, MoreHorizontal, Radar, ShieldCheck, Sparkles, X } from 'lucide-react';

const BASE = 'Built a Python service for retrieval-augmented generation using FastAPI and a vector database.';
const TAILORED = 'Built a Python retrieval service with FastAPI and a vector database to support retrieval-augmented generation (RAG).';
const SKILLS = ['Python', 'RAG', 'LangChain', 'FastAPI', 'Vector DB'];
const JOBS = [
  { title: 'Generative AI Engineer', company: 'Example AI Studio', source: 'Ashby', score: 92 },
  { title: 'LLM Developer', company: 'Example Research Lab', source: 'Greenhouse', score: 86 },
  { title: 'Python Backend Engineer', company: 'Example Systems', source: 'Lever', score: 81 },
];
const TABS = ['Discover', 'Match', 'Tailor', 'Prepare', 'Track'];
function DemoLabel() { return <span className="lp-demo-label"><span /> Interactive example</span>; }
function SkillTags() { return <div className="lp-tags">{SKILLS.map((s) => <span key={s}>{s}</span>)}</div>; }

export function HeroDemo() {
  const [view, setView] = useState<'feed' | 'package'>('feed');
  return <div className="lp-product-preview">
    <div className="lp-preview-topbar"><span className="lp-window-dots" aria-hidden="true"><i /><i /><i /></span><span>JOBPILOT / YOUR WORKSPACE</span><DemoLabel /></div>
    <div className="lp-preview-body">
      <aside className="lp-preview-sidebar" aria-label="Example preview views"><span className="lp-preview-brand">JP<span> / workspace</span></span><span className="lp-preview-sidebar-label">YOUR SEARCH</span><button type="button" className={view === 'feed' ? 'is-active' : ''} onClick={() => setView('feed')} aria-pressed={view === 'feed'}><Radar size={15} /> Job feed <span>03</span></button><button type="button" className={view === 'package' ? 'is-active' : ''} onClick={() => setView('package')} aria-pressed={view === 'package'}><Layers3 size={15} /> Apply queue <span>01</span></button><div className="lp-preview-identity"><span>JD</span><div>Jamie Demo<small>Personal workspace</small></div></div></aside>
      <div className="lp-preview-main"><div className="lp-preview-heading"><div><span className="lp-eyebrow">YOUR NEXT CHAPTER</span><h3>{view === 'feed' ? 'A good place to start.' : 'The details, brought together.'}</h3></div><span className="lp-pill"><span className="lp-live-dot" /> Demo workspace</span></div>
        <div className="lp-preview-columns"><div className="lp-featured-job"><div className="lp-row"><span className="lp-company-avatar">E<span>✦</span></span><span className="lp-fit-badge">92% <small>ILLUSTRATIVE FIT</small></span></div><span className="lp-job-company">Example AI Studio <ArrowUpRight size={12} /></span><h4>Generative AI<br />Engineer</h4><p>Remote, India <span>·</span> Full time <span>·</span> via Ashby</p><SkillTags /><div className="lp-eligibility"><Check size={14} /> India remote eligibility confirmed <span>DEMO</span></div>{view === 'feed' ? <button type="button" className="lp-demo-action" onClick={() => setView('package')}>Review application package <ArrowRight size={15} /></button> : <div className="lp-package-inline" role="status">{['Tailored résumé', 'Cover letter & outreach drafts', 'Form answers for review'].map((text) => <span key={text}><Check size={13} />{text}</span>)}</div>}</div>
        <div className="lp-agent-mini"><div className="lp-agent-title"><Sparkles size={15} /><span>Your copilot</span><MoreHorizontal size={16} /></div><p>I found a role that lines up with your Python and RAG experience.</p><div className="lp-agent-log">{['Checked skills & location', 'Tailored résumé wording', 'Prepared outreach drafts'].map((text) => <span key={text}><CheckCheck size={13} />{text}</span>)}</div><div className="lp-review-notice"><ShieldCheck size={17} /><div>Ready for your eyes.<small>Review the details before you apply.</small></div></div><div className="lp-agent-input">What should we work on next?<ArrowUpRight size={15} /></div></div></div>
      </div>
    </div>
  </div>;
}

export function ResumeDemo() {
  const [tailored, setTailored] = useState(true);
  return <div className="lp-resume-demo"><div className="lp-segmented" role="group" aria-label="Example résumé version"><button type="button" aria-pressed={!tailored} onClick={() => setTailored(false)}>Base résumé</button><button type="button" aria-pressed={tailored} onClick={() => setTailored(true)}>Tailored résumé <Sparkles size={11} /></button></div><div className="lp-resume-paper" aria-live="polite"><span className="lp-eyebrow">Jamie Demo / Experience</span><strong>Software Engineer</strong><span className="lp-paper-rule" /><p key={String(tailored)} className="lp-demo-enter">• {tailored ? <>Built a <mark>Python retrieval service</mark> with <mark>FastAPI</mark> and a vector database to support <mark>retrieval-augmented generation (RAG).</mark></> : BASE}</p><small>Same project. {tailored ? 'Relevant terminology.' : 'Original wording.'}</small></div></div>;
}

export function TrackerDemo({ compact = false }: { compact?: boolean }) {
  const [stage, setStage] = useState(0);
  const columns = ['Saved', 'Applied', 'Interviewing', 'Offer'];
  return <div className={`lp-tracker-demo ${compact ? 'lp-tracker-compact' : ''}`}><div className="lp-mini-kanban">{columns.map((column, i) => <div key={column}><span className="lp-kanban-label"><i className={`lp-stage-dot lp-stage-${i}`} />{column}<small>{stage === i ? '1' : '0'}</small></span>{stage === i && <div className="lp-kanban-card lp-demo-enter"><span>EXAMPLE AI</span><strong>AI Engineer</strong><small>Remote · India</small></div>}</div>)}</div><button className="lp-demo-text-button" type="button" onClick={() => setStage((stage + 1) % 4)}>{stage === 3 ? 'Reset example' : `Move example to ${columns[stage + 1]}`} <ArrowRight size={13} /></button><span className="lp-sr-only" aria-live="polite">Example application is {columns[stage]}.</span></div>;
}

export function WorkflowDemo() {
  const [tab, setTab] = useState(0);
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const onKey = (event: KeyboardEvent, i: number) => {
    let next = i;
    if (event.key === 'ArrowRight') next = (i + 1) % 5;
    else if (event.key === 'ArrowLeft') next = (i + 4) % 5;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = 4;
    else return;
    event.preventDefault(); setTab(next); buttons.current[next]?.focus();
  };
  return <div className="lp-workflow"><div role="tablist" aria-label="Explore the JobPilot workflow" className="lp-workflow-tabs">{TABS.map((title, i) => <button key={title} ref={(el) => { buttons.current[i] = el; }} type="button" role="tab" id={`lp-tab-${i}`} aria-selected={i === tab} aria-controls={`lp-panel-${i}`} tabIndex={i === tab ? 0 : -1} onClick={() => setTab(i)} onKeyDown={(e) => onKey(e, i)}><span>0{i + 1}</span>{title}<ChevronRight size={14} /></button>)}</div>
    <div className="lp-workflow-panel" id={`lp-panel-${tab}`} role="tabpanel" aria-labelledby={`lp-tab-${tab}`} tabIndex={0}><div className="lp-workflow-context"><DemoLabel /><span className="lp-eyebrow">{TABS[tab]} / 0{tab + 1}</span></div><div key={tab} className="lp-demo-enter">
      {tab === 0 && <div className="lp-demo-feed">{JOBS.map((job, i) => <div className="lp-demo-feed-row" key={job.title}><span className="lp-company-avatar">{['E', 'R', 'S'][i]}</span><div><strong>{job.title}</strong><p>{job.company} · Remote, India · Full time</p><small>via {job.source} · Sample newly discovered role</small></div><span className="lp-demo-feed-score">{job.score}<small>% fit</small></span></div>)}</div>}
      {tab === 1 && <div className="lp-match-panel"><div className="lp-large-score"><span>92<small>%</small></span><p>Illustrative fit score</p><small>Not a prediction of hiring outcomes</small></div><div><span className="lp-eyebrow">PROFILE ↔ GENERATIVE AI ENGINEER</span><h3>A strong technical starting point.</h3><SkillTags /><p><Check size={14} /> Relevant experience: Python retrieval services</p><p><Check size={14} /> Eligible location: India</p><p className="lp-gap"><span>!</span> To review: Kubernetes experience not in base résumé</p></div></div>}
      {tab === 2 && <div className="lp-tailor-panel"><div><span className="lp-eyebrow">Original experience</span><p>{BASE}</p></div><ArrowRight className="lp-diff-arrow" size={22} /><div><span className="lp-eyebrow">Tailored emphasis</span><p>Built a <mark>Python retrieval service</mark> with FastAPI and a vector database to support <mark>retrieval-augmented generation (RAG).</mark></p></div><small>Illustrative wording change. No new employer, metric, or achievement added.</small></div>}
      {tab === 3 && <div className="lp-prepare-panel"><div><h3>A complete starting point.<br />Your final review.</h3><p>Prepared for the sample Generative AI Engineer role.</p><span className="lp-pill">Nothing has been submitted or sent</span></div><ul>{[[FileText, 'Tailored résumé', 'Ready to review'], [FileText, 'Cover letter', 'Ready to review'], [Mail, 'Recruiter email', 'Draft only'], [MessageSquare, 'LinkedIn message', 'Draft only'], [ShieldCheck, 'Form answers', '2 need your review']].map(([Icon, title, status]) => { const ItemIcon = Icon as typeof FileText; return <li key={String(title)}><ItemIcon size={16} /><span>{String(title)}</span><small>{String(status)}</small></li>; })}</ul></div>}
      {tab === 4 && <TrackerDemo />}
    </div></div><div className="lp-workflow-footer"><span><ShieldCheck size={14} /> AI-powered preparation. You decide what happens next.</span><span>LOCAL DEMO / NO API CALLS</span></div></div>;
}

export function ApprovalDemo() {
  const [decision, setDecision] = useState<'pending' | 'approved' | 'rejected'>('pending');
  return <div className="lp-approval-demo"><div className="lp-panel-header"><span><ShieldCheck size={16} /> Proposed résumé edit</span><DemoLabel /></div><div className="lp-approval-body"><div className="lp-row"><span className="lp-eyebrow">EXPERIENCE / BULLET 01</span><span className={`lp-approval-status lp-decision-${decision}`}>{decision === 'pending' ? 'Needs your review' : decision === 'approved' ? 'Approved in demo' : 'Original retained'}</span></div><div className={`lp-proposal-original ${decision === 'rejected' ? 'lp-choice-selected' : ''}`}><span className="lp-eyebrow">Existing text</span><p>{BASE}</p></div><div className={`lp-proposal-new ${decision === 'approved' ? 'lp-choice-selected' : ''}`}><span className="lp-eyebrow">Suggested replacement</span><p>{TAILORED}</p></div><p className="lp-approval-reason"><Sparkles size={14} /> Emphasizes relevant RAG terminology while keeping the same project and tools.</p><div className="lp-approval-warning"><span>!</span> Verify this accurately describes your work.</div><div className="lp-approval-actions">{decision === 'pending' ? <><button type="button" className="lp-button" onClick={() => setDecision('approved')}><Check size={15} /> Approve example</button><button type="button" className="lp-button lp-button-outline" onClick={() => setDecision('rejected')}><X size={15} /> Reject</button></> : <><span role="status"><Check size={15} /> {decision === 'approved' ? 'Example updated. You remain in control.' : 'Kept the original. Your choice.'}</span><button type="button" className="lp-demo-text-button" onClick={() => setDecision('pending')}>Reset</button></>}</div><small className="lp-muted">Simulation only. No account or résumé data is changed.</small></div></div>;
}

const PROMPTS = [
  { text: 'Find remote AI roles matching my profile.', reply: 'These sample roles align with Jamie’s Python and LLM experience. Check the skills and location before preparing an application.', tool: 'Checked sample job feed', type: 'jobs' },
  { text: 'Tailor my résumé for this RAG Engineer role.', reply: 'Here’s a proposed rewrite of the sample experience bullet. Compare the wording and verify it reflects your work.', tool: 'Prepared a résumé proposal', type: 'resume' },
  { text: 'Which applications need a follow-up?', reply: 'This example application was marked applied five days ago. Review the draft before reaching out.', tool: 'Checked sample follow-up dates', type: 'followup' },
  { text: 'Prepare a recruiter email for this job.', reply: 'I’ve prepared an example draft using the role context and Jamie’s experience. Nothing has been sent.', tool: 'Prepared an outreach draft', type: 'email' },
];

export function AssistantDemo() {
  const [active, setActive] = useState(0);
  const prompt = PROMPTS[active];
  return <div className="lp-assistant-demo"><div className="lp-panel-header"><span><Sparkles size={16} /> JobPilot assistant</span><DemoLabel /></div><div className="lp-assistant-prompts" role="group" aria-label="Try an example prompt">{PROMPTS.map((p, i) => <button key={p.type} type="button" onClick={() => setActive(i)} aria-pressed={i === active}>{['Find roles', 'Tailor résumé', 'Follow-ups', 'Draft email'][i]}<ArrowUpRight size={12} /></button>)}</div><div className="lp-simulated-conversation" aria-live="polite" aria-atomic="true"><div key={active} className="lp-demo-enter"><p className="lp-demo-user">{prompt.text}</p><div className="lp-assistant-response"><span className="lp-assistant-avatar"><Sparkles size={16} /></span><div><span className="lp-tool-note"><CheckCheck size={13} />{prompt.tool}</span><p>{prompt.reply}</p>
      {prompt.type === 'jobs' && <div className="lp-chat-result"><div><strong>Generative AI Engineer</strong><small>Example AI Studio · Remote, India</small></div><span>92%<small>demo fit</small></span></div>}
      {prompt.type === 'resume' && <div className="lp-chat-result lp-chat-result-text"><FileText size={16} /><p>{TAILORED}</p></div>}
      {prompt.type === 'followup' && <div className="lp-chat-result"><div><strong>Python Engineer · Example Systems</strong><small>Sample follow-up due · Review before sending</small></div><Mail size={17} /></div>}
      {prompt.type === 'email' && <div className="lp-chat-result lp-chat-result-text"><Mail size={16} /><div><strong>Subject: Your RAG Engineer opening</strong><p>Hi Hiring Team, my Python retrieval service experience aligns with your RAG work. I’d love to learn more about the role.</p><small>DRAFT / NOT SENT</small></div></div>}
    </div></div></div></div><div className="lp-assistant-footer"><span>Illustrative conversation. No live AI calls.</span><ArrowUpRight size={15} /></div></div>;
}
