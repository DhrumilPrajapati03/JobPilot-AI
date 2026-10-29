import {useQuery} from '@tanstack/react-query';
import api from '../../lib/api';
import {Card,CardHeader,CardTitle,CardContent} from '../ui/card';
export interface ProductOutcomes {
  generated_applications:number;prepared_applications:number;attempted_applications:number;browser_observed_applications:number;user_reported_applications:number;
  independently_verified_submissions:null;
  preparation:{inspected_fields:number;filled_fields:number;preserved_fields:number;review_fields:number;invalid_fields:number;truncated_applications:number;median_seconds:number|null;p95_seconds:number|null;time_samples:number;completion_rate:number|null};
  gmail:{accepted_messages:number;correlated_replied_messages:number;reviewed_human_replied_messages:number;reviewed_human_reply_rate:number|null;bounce_observed_messages:number;unknown_outcomes:number};
  runs:{failed:number;recovered:number;pending:number};
  stage_timings:{stage:string;samples:number;median_ms:number;p95_ms:number}[];cost_per_application:null;measurement_note:string;
}
const duration=(n:number|null)=>n===null?'Not measured':`${Math.round(n)} s`;
export function OutcomesView({data:d}:{data:ProductOutcomes}) {
  return <div className="space-y-4 text-sm">
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{[
      ['Prepared applications',d.prepared_applications],['Submission attempts',d.attempted_applications],['Browser confirmations (unverified)',d.browser_observed_applications],['User reports (unverified)',d.user_reported_applications],
      ['Gmail-accepted messages',d.gmail.accepted_messages],['Correlated replied messages',d.gmail.correlated_replied_messages],['Review-confirmed human replies',d.gmail.reviewed_human_replied_messages],['Uncertain send outcomes',d.gmail.unknown_outcomes],
    ].map(([label,value])=><div key={label} className="rounded-md border p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="text-xl font-semibold">{value}</p></div>)}</div>
    <p>{d.gmail.reviewed_human_reply_rate===null?'Human reply rate: no accepted-message denominator yet.':`Review-confirmed human reply rate: ${d.gmail.reviewed_human_reply_rate}% of Gmail-accepted messages.`} Bounce notices observed: {d.gmail.bounce_observed_messages}.</p>
    <p>Observed field completion: {d.preparation.completion_rate===null?'Not measured':`${d.preparation.completion_rate}%`} of {d.preparation.inspected_fields} inspected fields, using the latest preparation per application. This measures filled/preserved controls, not answer correctness. {d.preparation.review_fields} need review; {d.preparation.invalid_fields} invalid; {d.preparation.truncated_applications} reached the inspection limit.</p>
    <p>Generation-to-first-preparation time: median {duration(d.preparation.median_seconds)}, p95 {duration(d.preparation.p95_seconds)} ({d.preparation.time_samples} samples). Includes waiting and user time.</p>
    <p>Runs: {d.runs.failed} failed, {d.runs.recovered} succeeded after retries, {d.runs.pending} pending. Independent employer verification and cost per application: not instrumented.</p>
    {!!d.stage_timings.length&&<div className="overflow-x-auto"><table className="w-full text-left text-xs"><caption className="text-left text-muted-foreground">Completed-stage server timings (new measurements only)</caption><thead><tr><th>Stage</th><th>Samples</th><th>Median ms</th><th>p95 ms</th></tr></thead><tbody>{d.stage_timings.map(s=><tr key={s.stage}><td>{s.stage}</td><td>{s.samples}</td><td>{Math.round(s.median_ms)}</td><td>{Math.round(s.p95_ms)}</td></tr>)}</tbody></table></div>}
    <p className="text-xs text-muted-foreground">{d.measurement_note}</p>
  </div>;
}
export function ProductMetrics() {
  const q=useQuery<ProductOutcomes>({queryKey:['analytics','outcomes'],queryFn:()=>api.get('/analytics/outcomes'),retry:false});
  return <Card><CardHeader><CardTitle>Observed workflow outcomes</CardTitle></CardHeader><CardContent>{q.isPending?<p role="status">Loading evidence metrics…</p>:q.isError?<p role="alert" className="text-sm text-warning">Evidence metrics are unavailable; no outcome is inferred. <button onClick={()=>q.refetch()} className="underline">Retry</button></p>:<OutcomesView data={q.data}/>}</CardContent></Card>;
}
