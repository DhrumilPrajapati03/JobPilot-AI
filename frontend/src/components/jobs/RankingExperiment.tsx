import {useRef} from 'react';
import {useMutation,useQuery} from '@tanstack/react-query';
import api from '../../lib/api';
import {resolveRun,FailedRunError,retryFailedRun,type QueuedRun} from '../../lib/run-poll';
import {Button} from '../ui/button';
import type {JobPosting} from '../../hooks/use-discovery';

export function RankingExperiment({postings}:{postings:JobPosting[]}) {
  const status=useQuery({queryKey:['recommendations-status'],queryFn:()=>api.get<{experimental:boolean}>('/recommendations/status'),retry:false,staleTime:60000});
  const attempt=useRef<{payload:string;key:string}|null>(null);
  const compare=useMutation({mutationFn:async(retryId?:string)=>{
    if(retryId){const result=await retryFailedRun<{ordered_ids:string[];status:string;duration_ms:number}>(retryId);attempt.current=null;return result;}
    const ids=postings.slice(0,20).map(p=>p.id),payload=ids.join(',');
    if(attempt.current?.payload!==payload)attempt.current={payload,key:crypto.randomUUID()};
    const result=await resolveRun<{ordered_ids:string[];status:string;duration_ms:number}>(await api.post<QueuedRun>('/recommendations/experiment',{posting_ids:ids,request_key:attempt.current.key}));
    attempt.current=null;return result;
  }});
  if(!status.data?.experimental||!postings.length)return null;
  return <details className="rounded-lg border bg-card p-4 text-sm"><summary className="cursor-pointer font-medium">Optional local ranking experiment</summary><p className="my-3 text-xs leading-relaxed text-muted-foreground">Compare an eligible shortlist using the prepared local reranker. This is an evaluation view. The default feed and its fit scores stay unchanged.</p><Button size="sm" variant="outline" onClick={()=>compare.mutate(undefined)} disabled={compare.isPending}>{compare.isPending?'Comparing shortlist…':'Compare up to 20 opportunities'}</Button>{compare.error&&<p role="alert" className="mt-2 text-xs text-destructive">{compare.error.message}</p>}{compare.error instanceof FailedRunError&&<Button size="sm" variant="outline" className="mt-2" disabled={compare.isPending} onClick={()=>compare.mutate((compare.error as FailedRunError).runId)}>Retry failed experiment</Button>}{compare.data&&<div className="mt-3"><p className="text-xs text-muted-foreground">{compare.data.status==='experimental'?'Experimental order':'Baseline fallback: optional model unavailable'} · {Math.round(compare.data.duration_ms)} ms · Quality improvement has not been established.</p><ol className="mt-3 list-decimal space-y-1 pl-5">{compare.data.ordered_ids.map(id=>{const p=postings.find(row=>row.id===id);return p?<li key={id}>{p.title} · {p.company}</li>:null})}</ol></div>}</details>;
}
