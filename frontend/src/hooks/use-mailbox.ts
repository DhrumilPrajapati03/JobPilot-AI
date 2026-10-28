import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import api from '../lib/api';
import { resolveRun, type QueuedRun } from '../lib/run-poll';
import { API_URL } from '../lib/constants';
import { supabase } from '../lib/supabase';
import { useAuthStore } from '../stores/auth-store';

export interface MailConnection { id: string; email: string; status: string; last_sync_at: string | null }
export interface MailStatus { configured: boolean; send_enabled: boolean; connection: MailConnection | null }
export interface OutreachMessage {
  id: string; application_id: string; to_email: string; subject: string; body: string; revision: number;
  state: 'draft'|'approved'|'queued'|'sending'|'sent'|'send_unknown'|'failed';
  connection_id: string | null; from_email?: string | null; sent_at: string | null; provider_message_id: string | null; last_error: string | null;
  delivery_status: string; attachment: {name: string; size: number; sha256: string} | null;
  execution_status?: string | null;
}
export interface MailReply { id: string; from_email: string; excerpt: string; received_at: string; classification: string; reviewed: boolean }
export interface RecruiterLead { id?: string; email: string; full_name: string; position: string; verification: string; verified_at: string; sources: {url?: string; last_seen_on?: string; verification_date?: string}[] }
export type DraftFields = { to_email: string; subject: string; body: string; attach_resume: boolean };

export function useMailbox() {
  return useQuery<MailStatus>({ queryKey: ['mailbox','connection'], queryFn: () => api.get('/email/connection'), retry: false });
}
export function useMailHistory(applicationId: string) {
  return useQuery<{emails: OutreachMessage[]}>({ queryKey: ['mailbox','history',applicationId], queryFn: () => api.get(`/email/history?application_id=${applicationId}`),
    retry: false, refetchInterval: q => q.state.data?.emails.some(m=>['queued','sending'].includes(m.state)) ? 3000 : false });
}
export function useMailAction<T>(fn: (body:T)=>Promise<unknown>) {
  const client=useQueryClient();
  return useMutation({mutationFn:fn,onSuccess:()=>{client.invalidateQueries({queryKey:['mailbox']});}});
}
export function useSyncMailbox() {
  const client=useQueryClient();
  return useMutation({mutationFn:async()=>resolveRun<{processed:number;errors:number;has_more:boolean}>(await api.post<QueuedRun>('/email/sync',{})),onSuccess:()=>client.invalidateQueries({queryKey:['mailbox']})});
}
export function useMailReplies(id: string, enabled: boolean) {
  return useQuery<{replies:MailReply[]}>({queryKey:['mailbox','replies',id],queryFn:()=>api.get(`/email/messages/${id}/replies`),enabled,retry:false,refetchInterval:enabled?30000:false});
}
export function useRecruiterLeads(applicationId: string) {
  return useQuery<{contacts:RecruiterLead[]}>({queryKey:['mailbox','contacts',applicationId],queryFn:()=>api.get(`/contacts/?application_id=${applicationId}`),retry:false});
}
export async function downloadMailAttachment(id: string) {
  const owner=useAuthStore.getState().user?.id;
  const {data}=await supabase.auth.getSession();
  if (!owner || useAuthStore.getState().user?.id!==owner) throw new Error('Account changed before the download');
  const response=await fetch(`${API_URL}/email/messages/${id}/attachment`,{headers:{Authorization:`Bearer ${data.session?.access_token ?? ''}`}});
  if (!response.ok) throw new Error('The saved PDF could not be downloaded');
  const blob=await response.blob();
  if (useAuthStore.getState().user?.id!==owner) throw new Error('Account changed during the download');
  const url=URL.createObjectURL(blob);
  const link=document.createElement('a'); link.href=url; link.download='tailored-resume.pdf'; link.click();
  window.setTimeout(()=>URL.revokeObjectURL(url),1000);
}
