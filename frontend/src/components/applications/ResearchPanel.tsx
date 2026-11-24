import {useRef,useState} from 'react';
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {ExternalLink,Loader2,Search,ShieldCheck} from 'lucide-react';
import api from '../../lib/api';
import {resolveRun,FailedRunError,retryFailedRun,type QueuedRun} from '../../lib/run-poll';
import {Button} from '../ui/button';
import {Textarea} from '../ui/textarea';
import {useUpdateApplication} from '../../hooks/use-applications';

interface Research {run_id:string;company:string;sources:{url:string;title:string;excerpt:string;fetched_at:string}[];warnings:string[]}
export function ResearchPanel({applicationId}:{applicationId:string}) {
  const [urls,setUrls]=useState('');
  const [draft,setDraft]=useState('');
  const [fallback,setFallback]=useState(false);
  const [draftResearch,setDraftResearch]=useState<Research|null>(null);
  const attempt=useRef<{urls:string;key:string}|null>(null);
  const client=useQueryClient();
  const research=useQuery({queryKey:['company-research',applicationId],queryFn:()=>api.get<{research:Research|null}>(`/research/${applicationId}`),retry:false});
  const collect=useMutation({mutationFn:async(retryId?:string)=>{
    if(retryId){await retryFailedRun(retryId);return;}
    const list=urls.split('\n').map(v=>v.trim()).filter(Boolean);
    if(!list.length||list.length>3)throw new Error('Add one to three public page URLs, one per line.');
    for(const value of list){let url:URL;try{url=new URL(value)}catch{throw new Error('Enter complete public HTTPS URLs.')}if(url.protocol!=='https:')throw new Error('Use HTTPS source URLs.');}
    if(attempt.current?.urls!==urls)attempt.current={urls,key:crypto.randomUUID()};
    await resolveRun(await api.post<QueuedRun>(`/research/${applicationId}`,{urls:list,request_key:attempt.current.key}));
  },onSuccess:()=>{attempt.current=null;void client.invalidateQueries({queryKey:['company-research',applicationId]})}});
  const write=useMutation({mutationFn:()=>api.post<{draft:string;fallback:boolean;research:Research}>(`/research/${applicationId}/cover-letter`,{}),onSuccess:r=>{setDraft(r.draft);setFallback(r.fallback);setDraftResearch(r.research)}});
  const save=useUpdateApplication(applicationId);
  return <section className="space-y-5 rounded-xl border bg-card p-5" aria-labelledby="research-title">
    <div><p className="desk-eyebrow">COMPANY CONTEXT / YOUR SOURCES</p><h2 id="research-title" className="mt-2 text-xl font-semibold">Research you can inspect.</h2><p className="mt-2 text-sm leading-relaxed text-muted-foreground">Add public company pages such as About, Product or Careers. JobPilot saves cited excerpts. Confirm that each source belongs to the company; web content isn’t independently verified.</p></div>
    <form className="space-y-3" onSubmit={e=>{e.preventDefault();collect.mutate(undefined)}}><label htmlFor="research-urls" className="text-sm font-medium">Source URLs (up to three, one per line)</label><Textarea id="research-urls" value={urls} onChange={e=>setUrls(e.target.value)} placeholder="https://company.example/about" rows={3}/><Button type="submit" disabled={collect.isPending||write.isPending||save.isPending||!urls.trim()}>{collect.isPending?<Loader2 size={15} className="mr-2 animate-spin"/>:<Search size={15} className="mr-2"/>}{collect.isPending?'Collecting sources…':'Collect sources'}</Button></form>
    {(collect.error||write.error||save.error)&&<p role="alert" className="text-sm text-destructive">{(collect.error||write.error||save.error)?.message}</p>}
    {collect.error instanceof FailedRunError&&<Button variant="outline" disabled={collect.isPending||write.isPending} onClick={()=>collect.mutate((collect.error as FailedRunError).runId)}>Retry failed research</Button>}
    {research.isLoading?<p role="status" className="text-sm text-muted-foreground">Loading saved research…</p>:research.isError?<div className="space-y-2"><p role="alert" className="text-sm text-muted-foreground">{research.error.message}</p><Button variant="outline" size="sm" onClick={()=>void research.refetch()}>Retry saved research</Button></div>:research.data?.research?<div className="space-y-4">{research.data.research.sources.map((s,i)=><article key={s.url} className="rounded-lg border p-4"><a href={s.url} target="_blank" rel="noreferrer" className="flex items-center gap-2 text-sm font-medium text-accent">[{i+1}] {s.title}<ExternalLink size={13}/></a><p className="mt-1 break-all text-xs text-muted-foreground">{s.url} · Fetched {new Date(s.fetched_at).toLocaleString()}</p><blockquote className="mt-3 border-l-2 pl-3 text-sm leading-relaxed text-muted-foreground">{s.excerpt}</blockquote></article>)}{research.data.research.warnings.map(w=><p key={w} className="text-sm text-warning">{w}</p>)}<Button variant="outline" onClick={()=>write.mutate()} disabled={write.isPending||collect.isPending||save.isPending}>{write.isPending?'Preparing a draft…':'Draft a source-informed cover letter'}</Button></div>:<p className="text-sm text-muted-foreground">No saved research yet. Your existing application materials remain available.</p>}
    {draft&&<div className="space-y-3 border-t pt-5"><h3 className="font-medium">Review the new draft</h3><p className="text-xs text-muted-foreground"><ShieldCheck size={13} className="mr-1 inline"/>Check company statements and candidate claims against the sources.{fallback?' A basic fallback was used; rewrite before saving.':''}</p><p className="text-xs text-muted-foreground">Sources used for this draft (saved research {draftResearch?.run_id.slice(0,8)}):</p><ul className="space-y-2">{draftResearch?.sources.map((s,i)=><li key={s.url} className="text-xs"><a href={s.url} target="_blank" rel="noreferrer" className="break-all text-accent">[{i+1}] {s.title} ? {s.url}</a><p className="mt-1 text-muted-foreground">{s.excerpt}</p></li>)}</ul><Textarea aria-label="Research cover letter draft" disabled={write.isPending||save.isPending} rows={12} value={draft} onChange={e=>setDraft(e.target.value)}/><Button onClick={()=>save.mutate({cover_letter:draft},{onSuccess:()=>setDraft('')})} disabled={save.isPending||write.isPending}>Replace saved cover letter with this draft</Button><Button variant="ghost" disabled={write.isPending||save.isPending} onClick={()=>setDraft('')}>Discard draft</Button></div>}
  </section>;
}
