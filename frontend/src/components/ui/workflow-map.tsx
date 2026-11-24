import {useState} from 'react';
import {ArrowRight, FileCheck2, FileText, Radar, ScanLine, ShieldCheck} from 'lucide-react';
import {cn} from '../../lib/utils';

const STEPS = [
  {name:'Discover',icon:Radar,tag:'01 / FIND',title:'Start with the right opportunities.',copy:'Follow supported job boards. Check location eligibility and your target roles before preparing an application.',output:'Company boards → relevant roles'},
  {name:'Match',icon:ScanLine,tag:'02 / UNDERSTAND',title:'Make the evidence visible.',copy:'Compare the role with your confirmed résumé facts. Review the skills you have, the gaps, and the eligibility checks.',output:'Confirmed experience → explained fit'},
  {name:'Prepare',icon:FileText,tag:'03 / CREATE',title:'Your experience. The right emphasis.',copy:'Prepare a tailored résumé, cover letter, outreach drafts and application answers. Review the content against your original experience.',output:'Role + résumé → application materials'},
  {name:'Review',icon:ShieldCheck,tag:'04 / YOUR DECISION',title:'The final decision belongs to you.',copy:'Edit your materials, approve changes and decide when to send. With supervised autofill, you submit on the employer’s website.',output:'Prepared materials → your approval'},
];

/** A capability diagram, never an indication that background agents are running. */
export function WorkflowMap({demo=false,className,headingLevel=3}:{demo?:boolean;className?:string;headingLevel?:2|3}) {
  const [active,setActive]=useState(2);
  const step=STEPS[active];
  const Icon=step.icon;
  const DetailHeading=headingLevel===2?'h2':'h3';
  return <section className={cn('workflow-map',className)} aria-label={demo?'Interactive workflow example':'Workflow capabilities'}>
    <div className="wm-top"><span><span className="wm-square"/>JOBPILOT / WORKFLOW</span><span>{demo?'INTERACTIVE EXAMPLE':'CAPABILITY OVERVIEW'}</span></div>
    <div className="wm-canvas">
      <div className="wm-input"><span className="wm-input-icon"><FileCheck2 size={17}/></span><div><strong>Your résumé &amp; confirmed facts</strong><span>The starting point for your workflow</span></div><ShieldCheck size={15}/></div>
      <div className="wm-connector" aria-hidden="true"><i/></div>
      <div className="wm-stages" aria-label="Explore workflow stages">{STEPS.map((s,i)=><button type="button" key={s.name} onClick={()=>setActive(i)} aria-pressed={i===active} className={cn('wm-stage',i===active&&'is-active',i===3&&'wm-human')}><s.icon size={21}/><span>{s.name}</span><small>{i===3?'YOUR CONTROL':'AI ASSISTED'}</small></button>)}</div>
      <div className="wm-detail" aria-live="polite"><div className="wm-detail-head"><span className="wm-detail-icon"><Icon size={19}/></span><span>{step.tag}</span><ArrowRight size={16}/></div><DetailHeading>{step.title}</DetailHeading><p>{step.copy}</p><div className="wm-output"><span>OUTPUT</span>{step.output}</div></div>
      <div className="wm-boundary"><ShieldCheck size={15}/><span>Preparation is automated. Submission stays with you.</span></div>
    </div>
  </section>;
}
