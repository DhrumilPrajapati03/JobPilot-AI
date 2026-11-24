import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {Mail,MessageSquare,FileText,Loader2,Check} from 'lucide-react';
import api from '../lib/api';
import {Button} from '../components/ui/button';
import {Textarea} from '../components/ui/textarea';
import {Tabs,TabsContent,TabsList,TabsTrigger} from '../components/ui/tabs';
import {useDraft} from '../hooks/use-draft';
import {useAuthStore} from '../stores/auth-store';

interface Template{kind:string;content:string;updated_at:string}
function Editor({kind,record,onReload}:{kind:string;record?:Template;onReload:()=>void}){
  const owner=useAuthStore(s=>s.user?.id);
  const {draft,setDraft,dirty,reset}=useDraft(record?.content??'');
  const client=useQueryClient();
  const save=useMutation({mutationFn:()=>api.put('/templates/'+kind,{content:draft,expected_updated_at:record?.updated_at??null},{expectedUserId:owner}),onSuccess:()=>void client.invalidateQueries({queryKey:['writing-templates']})});
  return <section className="space-y-4 rounded-xl border bg-card p-5"><div><label htmlFor={'template-'+kind} className="font-medium">Your base writing template</label><p className="mt-2 text-sm leading-relaxed text-muted-foreground">Describe the tone, structure and wording you prefer. Writers use this style with your actual résumé facts and the target role. Leave it blank to use the default writing style.</p></div><Textarea id={'template-'+kind} rows={12} disabled={save.isPending} maxLength={10000} value={draft} onChange={e=>setDraft(e.target.value)} placeholder="Use a short introduction, one paragraph connecting my evidenced experience to the role, and a concise call to action."/><div className="flex flex-wrap items-center gap-3"><Button disabled={save.isPending||(!dirty&&!!record)} onClick={()=>save.mutate()}>{save.isPending?<Loader2 size={15} className="mr-2 animate-spin"/>:null}Save template</Button><Button variant="ghost" disabled={!dirty||save.isPending} onClick={reset}>Discard changes</Button><Button variant="ghost" disabled={save.isPending} onClick={()=>{reset();onReload()}}>Reload saved</Button><span className="ml-auto text-xs text-muted-foreground">{draft.length.toLocaleString()} / 10,000</span></div>{save.error&&<p role="alert" className="text-sm text-destructive">{save.error.message}</p>}{save.isSuccess&&!dirty&&<p role="status" className="flex gap-2 text-sm text-accent"><Check size={16}/>Saved. New drafts will use this style.</p>}</section>;
}
export default function Templates(){
  const query=useQuery({queryKey:['writing-templates'],queryFn:()=>api.get<{templates:Template[]}>('/templates'),retry:false});
  return <div className="page-templates"><header className="templates-header"><div><p className="desk-eyebrow">YOUR VOICE / CONNECTED TO THE WORKFLOW</p><h1 className="mt-2 text-2xl font-semibold">Writing templates</h1><p className="mt-2 text-sm text-muted-foreground">Private base templates for new outreach and cover-letter drafts. Existing application materials stay yours to edit.</p></div></header>{query.isLoading?<p role="status">Loading templates…</p>:query.isError?<div role="alert" className="space-y-3 rounded-xl border p-5"><p>{query.error.message}</p><Button variant="outline" onClick={()=>void query.refetch()}>Retry</Button></div>:<Tabs defaultValue="email"><TabsList className="flex max-w-full overflow-x-auto">{[['email','Cold emails',Mail],['dm','LinkedIn DMs',MessageSquare],['cover_letter','Cover letters',FileText]].map(([kind,label,Icon])=>{const I=Icon as typeof Mail;return <TabsTrigger key={kind as string} value={kind as string}><I size={15} className="mr-2"/>{label as string}</TabsTrigger>})}</TabsList>{['email','dm','cover_letter'].map(kind=><TabsContent key={kind} value={kind}><Editor kind={kind} record={query.data?.templates.find(t=>t.kind===kind)} onReload={()=>void query.refetch()}/></TabsContent>)}</Tabs>}</div>;
}
