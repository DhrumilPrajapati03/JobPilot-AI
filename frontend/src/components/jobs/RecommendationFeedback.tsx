import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {useEffect,useRef,useState} from 'react';
import {Check,ThumbsUp,ThumbsDown} from 'lucide-react';
import api from '../../lib/api';
import {Button} from '../ui/button';

type Signal='interested'|'not_relevant'|'clear';
interface Feedback {posting_id:string;signal:Signal;reason:string|null}
export function RecommendationFeedback({postingId}:{postingId:string}) {
  const query=useQuery({queryKey:['recommendation-feedback'],queryFn:()=>api.get<{feedback:Feedback[]}>('/recommendations/feedback'),retry:false,staleTime:30000});
  const current=query.data?.feedback.find(f=>f.posting_id===postingId);
  const client=useQueryClient();
  const [reason,setReason]=useState('wrong_role');
  const [choosing,setChoosing]=useState(false);
  const update=useMutation({mutationFn:(signal:Signal)=>api.put('/recommendations/feedback/'+postingId,{signal,reason:signal==='not_relevant'?reason:null}),onSuccess:()=>{setChoosing(false);void client.invalidateQueries({queryKey:['recommendation-feedback']})}});
  if(query.isError)return <p className="mt-4 text-xs text-muted-foreground">Feedback is unavailable. Your existing match and application actions still work.</p>;
  return <div className="mt-4 space-y-2 border-t pt-3"><p className="text-xs text-muted-foreground">Is this opportunity relevant? Explicit feedback is stored for evaluation.</p><div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" aria-pressed={current?.signal==='interested'} disabled={update.isPending} onClick={()=>update.mutate('interested')}><ThumbsUp size={13} className="mr-1.5"/>Interested{current?.signal==='interested'&&<Check size={12} className="ml-1"/>}</Button><Button size="sm" variant="outline" aria-pressed={current?.signal==='not_relevant'} disabled={update.isPending||query.isLoading} onClick={()=>{if(!choosing)setReason(current?.reason??'wrong_role');setChoosing(!choosing)}}><ThumbsDown size={13} className="mr-1.5"/>Not relevant</Button>{current&&<Button size="sm" variant="ghost" onClick={()=>update.mutate('clear')} disabled={update.isPending}>Clear feedback</Button>}</div>{choosing&&<div className="flex flex-wrap items-center gap-2"><label className="text-xs">Reason<select className="ml-2 rounded border border-input bg-card px-2 py-1.5" value={reason} onChange={e=>setReason(e.target.value)}>{[['wrong_role','Wrong role'],['location','Location'],['seniority','Seniority'],['skills','Skills'],['other','Other']].map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label><Button size="sm" onClick={()=>update.mutate('not_relevant')} disabled={update.isPending}>Save feedback</Button></div>}{update.error&&<p role="alert" className="text-xs text-destructive">{update.error.message}</p>}</div>;
}

/** A visible viewport exposure, not a fetched row or an inferred dislike. */
export function useVisibleRecommendations(ids:string[],enabled:boolean) {
  const root=useRef<HTMLDivElement>(null);
  const visibility=useRef<(()=>void)|null>(null);
  const key=ids.slice(0,100).join(',');
  useEffect(()=>{
    if(!enabled||!key)return;
    let cancelled=false;
    const timers=new Map<Element,number>();
    const visible=new Set<Element>();
    const seen=new Set<string>();
    let observer:IntersectionObserver|undefined;
    const stop=(el:Element)=>{const timer=timers.get(el);if(timer)clearTimeout(timer);timers.delete(el)};
    void api.post<{id:string;items:{posting_id:string;position:number}[]}>('/recommendations/runs',{request_key:crypto.randomUUID(),posting_ids:key.split(',')}).then(run=>{
      if(cancelled||!root.current)return;
      const begin=(el:Element)=>{
        const pid=el.getAttribute('data-recommendation-id');
        if(!pid||seen.has(pid)||timers.has(el)||document.visibilityState!=='visible')return;
        const started=performance.now();
        timers.set(el,window.setTimeout(()=>{timers.delete(el);if(cancelled||document.visibilityState!=='visible'||!visible.has(el))return;const item=run.items.find(i=>i.posting_id===pid);if(!item)return;seen.add(pid);void api.post('/recommendations/impressions',{run_id:run.id,posting_id:pid,request_key:crypto.randomUUID(),position:item.position,visible_ms:Math.min(60000,Math.floor(performance.now()-started))}).catch(()=>{seen.delete(pid)})},600));
      };
      observer=new IntersectionObserver(entries=>{for(const entry of entries){if(entry.isIntersecting&&entry.intersectionRatio>=.5){visible.add(entry.target);begin(entry.target)}else{visible.delete(entry.target);stop(entry.target)}}},{threshold:[0,.5]});
      for(const el of root.current.querySelectorAll('[data-recommendation-id]'))observer.observe(el);
      visibility.current=()=>{for(const el of visible){if(document.visibilityState==='visible')begin(el);else stop(el)}};
    }).catch(()=>{});
    const changed=()=>visibility.current?.();document.addEventListener('visibilitychange',changed);
    return ()=>{cancelled=true;observer?.disconnect();for(const timer of timers.values())clearTimeout(timer);visibility.current=null;document.removeEventListener('visibilitychange',changed)};
  },[key,enabled]);
  return root;
}
