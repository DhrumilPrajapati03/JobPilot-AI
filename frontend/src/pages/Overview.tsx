import {Link} from 'react-router-dom';
import {ArrowRight, ArrowUpRight, CircleAlert, FileCheck2, ListChecks, Loader2, Radar, Sparkles} from 'lucide-react';
import {useAuth} from '../hooks/use-auth';
import {useBriefing} from '../hooks/use-discovery';
import {useAnalyticsSummary} from '../hooks/use-analytics';
import {useResume} from '../hooks/use-profile';
import {ROUTES} from '../lib/constants';
import {WorkflowMap} from '../components/ui/workflow-map';
import {Button} from '../components/ui/button';
import {RunActivity} from '../components/agent/RunActivity';

export default function Overview() {
  const {user}=useAuth();
  const briefing=useBriefing();
  const analytics=useAnalyticsSummary();
  const resume=useResume();
  const name=(user?.user_metadata?.full_name||user?.user_metadata?.name||'').split(' ')[0];
  const drafts=(briefing.data?.drafts??[]).filter(d=>d.status==='drafted'&&d.application_id);
  const matches=briefing.data?.top_matches??[];
  const stats=[
    {label:'Open matches',value:briefing.data?.open_matches,path:ROUTES.JOBS,icon:Radar,note:'Review the evidence'},
    {label:'Recent drafts ready',value:briefing.data?drafts.length:undefined,path:ROUTES.JOBS+'?tab=drafted',icon:FileCheck2,note:'From your latest briefing'},
    {label:'Follow-ups due',value:analytics.data?.pending_follow_ups,path:ROUTES.APPLICATIONS,icon:ListChecks,note:'Choose your next conversation'},
  ];
  return <div className="desk-overview">
    <header className="desk-heading"><div><p className="desk-eyebrow">YOUR CAREER DESK</p><h1>{name?`${name}, make your next move.`:'Make your next move.'}</h1><p>A coordinated workflow. A clear next step. Every decision stays yours.</p></div><Button asChild><Link to={ROUTES.NEW_APPLICATION}><Sparkles size={16}/>New application<ArrowUpRight size={15}/></Link></Button></header>
    {(briefing.isError||analytics.isError||resume.isError)&&<div className="desk-notice" role="alert"><CircleAlert size={17}/><div><strong>Part of your overview couldn’t load.</strong><p>Your existing work is still available from the navigation.</p></div><Button size="sm" variant="outline" onClick={()=>{void briefing.refetch();void analytics.refetch();void resume.refetch()}}>Retry</Button></div>}
    <section className="desk-stats" aria-label="Your search overview">{stats.map(s=><Link key={s.label} to={s.path}><div><s.icon size={17}/><ArrowUpRight size={15}/></div><span>{s.label}</span><strong>{s.value===undefined?'—':s.value.toString().padStart(2,'0')}</strong><small>{s.value===undefined?'Waiting for your data':s.note}</small></Link>)}</section>
    <div className="desk-overview-grid"><div>
      <div className="desk-section-heading"><div><p className="desk-eyebrow">THE WORK, CONNECTED</p><h2>One workflow, from finding to following up.</h2></div></div><WorkflowMap/>
      <section className="desk-next"><div className="desk-section-heading"><h2>Your next useful step</h2><Link to={ROUTES.CHAT}>Open copilot<ArrowUpRight size={14}/></Link></div>
        {resume.isLoading?<p className="desk-wait"><Loader2 size={15} className="animate-spin"/>Checking your profile…</p>:resume.isError?<p className="text-sm text-muted-foreground">Open Profile &amp; resume to check your saved experience.</p>:!resume.data?.id?<><p>Give your workflow a reliable foundation. Import your résumé and review the extracted facts before matching.</p><Button variant="outline" asChild><Link to={ROUTES.PROFILE}>Build your profile<ArrowRight size={15}/></Link></Button></>:drafts.length?<><p>Your latest briefing includes {drafts.length} completed {drafts.length===1?'draft':'drafts'} to review. Check the facts, edit the wording, and choose your next action. Older work remains in Applications.</p><Button variant="outline" asChild><Link to={ROUTES.JOBS+'?tab=drafted'}>Review prepared applications<ArrowRight size={15}/></Link></Button></>:<><p>Review the opportunities in your feed, or bring a job description. JobPilot can prepare a package from your saved experience.</p><Button variant="outline" asChild><Link to={ROUTES.JOBS}>Explore opportunities<ArrowRight size={15}/></Link></Button></>}
      </section>
      <RunActivity/>
    </div><aside className="desk-attention"><div className="desk-section-heading"><h2>On your radar</h2><Link to={ROUTES.JOBS} aria-label="View all job matches"><ArrowUpRight size={17}/></Link></div><p className="desk-subtle">Top matches from your latest briefing.</p>
      {briefing.isLoading?<p className="desk-wait"><Loader2 size={16} className="animate-spin"/>Loading your briefing…</p>:briefing.isError?<p className="desk-subtle">Briefing unavailable. Retry above or open your job feed.</p>:matches.length===0?<div className="desk-radar-empty"><Radar size={28}/><h3>Room for your next opportunity.</h3><p>Follow job boards and confirm your profile to build your feed.</p><Link to={ROUTES.JOBS}>Set up discovery<ArrowRight size={14}/></Link></div>:<ul className="desk-radar-list">{matches.slice(0,4).map(j=><li key={j.id}><span className="desk-company-initial" aria-hidden="true">{j.company.slice(0,1)}</span><div><span>{j.company}</span><h3><Link to={ROUTES.JOBS}>{j.title}</Link></h3><small>{j.location}</small></div><span className="desk-fit">{Math.round(j.fit_score)}<small>fit</small></span></li>)}</ul>}
      <div className="desk-ground-rule"><FileCheck2 size={19}/><h3>Facts first. Always.</h3><p>Review a match’s skills and eligibility checks. A score describes overlap; it doesn’t predict a hiring decision.</p><Link to={ROUTES.PROFILE+'?tab=facts'}>Review your facts<ArrowUpRight size={14}/></Link></div>
    </aside></div>
  </div>;
}
