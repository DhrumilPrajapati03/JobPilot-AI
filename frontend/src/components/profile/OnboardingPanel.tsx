import {useState,useEffect,useRef} from 'react';
import {Link} from 'react-router-dom';
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import api from '../../lib/api';
import {useAuthStore} from '../../stores/auth-store';
import {Card,CardHeader,CardTitle,CardContent} from '../ui/card';
import {Button} from '../ui/button';

export interface OnboardingStatus {
  ready_for_matching:boolean;
  steps:{id:string;title:string;href:string;done:boolean;required:boolean}[];
  confirmed_facts:number; total_facts:number; next_step:string|null; note:string;
}

export function Checklist({data}:{data:OnboardingStatus}) {
  return <div className="space-y-3">
    <p className="text-sm font-medium">{data.ready_for_matching?'Your profile is ready for matching':'Finish your matching setup'}</p>
    <ol className="grid gap-2 sm:grid-cols-2">{data.steps.map(step=><li key={step.id} className="rounded-md border p-3 text-sm">
      <span className={step.done?'text-accent':'text-muted-foreground'}>{step.done?'Done':'To do'} · </span>
      <Link to={step.href} className="underline underline-offset-2">{step.title}</Link>
      {!step.required && <span className="text-xs text-muted-foreground"> (recommended)</span>}
    </li>)}</ol>
    <p className="text-xs text-muted-foreground">{data.confirmed_facts} of {data.total_facts} facts confirmed by you. {data.note}</p>
  </div>;
}

export function OnboardingPanel({hasResume}:{hasResume:boolean}) {
  const client=useQueryClient();
  const query=useQuery<OnboardingStatus>({queryKey:['onboarding'],queryFn:()=>api.get('/profile/onboarding'),refetchInterval:30000,retry:false});
  const [file,setFile]=useState<File|null>(null);
  const input=useRef<HTMLInputElement>(null);
  const accountId=useAuthStore(s=>s.user?.id);
  const upload=useMutation({mutationFn:async()=>{
    if(!file || !/\.(pdf|docx)$/i.test(file.name) || file.size>10*1024*1024)throw Error('Choose a PDF or DOCX up to 10 MiB.');
    const account=useAuthStore.getState().user?.id;
    if(!account)throw Error('Sign in before importing a résumé.');
    await api.upload('/resume/upload',file,'file',account);
    if(useAuthStore.getState().user?.id!==account)throw Error('Account changed. Reopen your profile.');
    return account;
  },onSuccess:account=>{
    if(useAuthStore.getState().user?.id!==account)return;
    setFile(null);
    for(const key of ['resume','identity-facts','onboarding','discovery'])client.invalidateQueries({queryKey:[key]});
  }});
  useEffect(()=>{setFile(null);if(input.current)input.current.value='';upload.reset();},[accountId]);
  return <Card><CardHeader><CardTitle>Get started</CardTitle></CardHeader><CardContent className="space-y-4">
    {query.isPending?<p role="status">Checking your saved setup…</p>:query.isError?<p role="alert" className="text-sm text-warning">Setup status is unavailable. <button onClick={()=>query.refetch()} className="underline">Retry</button></p>:<Checklist data={query.data}/>}
    <div className="space-y-2 border-t pt-3">
      <label htmlFor="resume-import" className="block text-sm font-medium">Import a résumé (PDF or DOCX, up to 10 MiB)</label>
      <input ref={input} id="resume-import" type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" disabled={upload.isPending} onChange={e=>{setFile(e.target.files?.[0]||null);upload.reset();}} className="block w-full text-sm"/>
      <Button disabled={!file||upload.isPending} onClick={()=>{if(!hasResume||window.confirm('Replace the saved base résumé? Review the extracted content and confirm its facts again afterward.'))upload.mutate();}}>{upload.isPending?'Importing…':'Import résumé'}</Button>
      <p className="text-xs text-muted-foreground">Review extracted facts before matching. You can also edit the profile tabs directly. Gmail connection is optional.</p>
      {upload.isSuccess&&<p role="status" className="text-sm text-accent">Résumé imported. Review the content and confirm your saved facts next.</p>}
      {upload.error&&<p role="alert" className="text-sm text-warning">{upload.error.message}</p>}
    </div>
  </CardContent></Card>;
}
