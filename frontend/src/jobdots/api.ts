// ============================================================
// JobDots — data layer for the command center (Day 9)
// ============================================================
// One hook per backend read; writes invalidate what they change. Polling is short where an
// expert may be working (roster, case thread) and long elsewhere.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import api from '../lib/api';

export interface Expert {
  id: string; name: string; role: string; status: string; owner?: 'builtin' | 'user';
  state: string; step: string; step_at: string | null; approvals: number;
}

export interface CaseSummary {
  id: string; company: string; role: string; stage: string; status: string; source_url: string;
  legacy: boolean; applied_at: string | null; created_at: string; updated_at: string;
}

export interface CaseEvent {
  id: number; kind: string; actor: string; actor_name: string; summary: string; data: Record<string, unknown>; at: string;
}

export interface Artifact {
  id: string; kind: string; version: number; title: string; content: any; created_by: string; legacy: boolean; created_at: string;
}

export interface Action {
  id: string; case_id?: string | null; kind: string; mode: string; agent: string; status: string;
  payload: Record<string, any>; payload_sha256: string; revision: number;
  review: { ok?: boolean; notes?: string[] } | null; block_reason: string | null; created_at: string; updated_at: string;
}

export interface CaseDetail extends CaseSummary {
  jd_text: string; events: CaseEvent[]; artifacts: Artifact[]; actions: Action[];
}

export interface Dashboard {
  pipeline: Record<'week' | 'all_time', Record<'found' | 'tailored' | 'applied' | 'replied' | 'interviews' | 'imported', number>>;
  approvals: { total: number; by_kind: Record<string, number> };
  ops: {
    kill_switch: boolean; quiet_hours: boolean; runs_last_day: Record<string, number>;
    active: { id: string; kind: string; agent: string; case_id: string | null; status: string; attempts: number; updated_at: string }[];
    failed: { id: string; kind: string; agent: string; case_id: string | null; company: string | null; error: string; updated_at: string }[];
    budget: { usd_used: number; usd_limit: number } | null;
    sent_today: Record<'emails' | 'invites' | 'dms', [number, number | null]>;
  };
}

export interface Contact {
  id: string; name: string; title: string; company: string; role_class: string; email: string; email_source: string;
  linkedin_url: string; github: string; x_handle: string; stage: string; do_not_contact: boolean; connected: boolean;
  imported: boolean; updated_at: string;
}

export interface BankAnswer {
  id: string; question: string; answer: string; type: string; source: string; company_scope: string; sensitive: boolean; version: number;
}

const fast = 4000;

export const useRoster = () =>
  useQuery({ queryKey: ['jd', 'roster'], queryFn: () => api.get<{ experts: Expert[] }>('/experts').then(r => r.experts), refetchInterval: fast });

export const useCases = () =>
  useQuery({ queryKey: ['jd', 'cases'], queryFn: () => api.get<{ cases: CaseSummary[] }>('/cases').then(r => r.cases), refetchInterval: 15000 });

export const useCase = (id: string | undefined) =>
  useQuery({ queryKey: ['jd', 'case', id], enabled: !!id, queryFn: () => api.get<CaseDetail>(`/cases/${id}`), refetchInterval: fast });

export const usePending = () =>
  useQuery({ queryKey: ['jd', 'pending'], queryFn: () => api.get<{ actions: Action[] }>('/cases/actions/pending').then(r => r.actions), refetchInterval: 8000 });

export const useDashboard = () =>
  useQuery({ queryKey: ['jd', 'dashboard'], queryFn: () => api.get<Dashboard>('/dashboard'), refetchInterval: 10000 });

export interface Health { status: 'ok' | 'warn' | 'down'; checks: { name: string; status: 'ok' | 'warn' | 'down'; detail: string }[] }
export const useHealth = () =>
  useQuery({ queryKey: ['jd', 'health'], queryFn: () => api.get<Health>('/health/deep'), refetchInterval: 30000 });

export const useContacts = (q: string, includeImported: boolean) =>
  useQuery({ queryKey: ['jd', 'contacts', q, includeImported],
             queryFn: () => api.get<{ contacts: Contact[] }>(`/crm/contacts?limit=300&q=${encodeURIComponent(q)}&include_imported=${includeImported}`).then(r => r.contacts) });

export const useAnswerBank = (q: string) =>
  useQuery({ queryKey: ['jd', 'bank', q], queryFn: () => api.get<{ answers: BankAnswer[] }>(`/answer-bank?q=${encodeURIComponent(q)}`).then(r => r.answers) });

export const useAnswerHistory = (id: string | null) =>
  useQuery({ queryKey: ['jd', 'bank-history', id], enabled: !!id,
             queryFn: () => api.get<{ versions: { id: string; version: number; answer: string; source: string; created_at: string }[] }>(`/answer-bank/${id}/history`).then(r => r.versions) });

function useRefresh() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ['jd'] });
}

/** Approve exactly the payload you saw; reject; or edit (the draft goes back through review). */
export function useActionMutations() {
  const refresh = useRefresh();
  return {
    approve: useMutation({ mutationFn: (a: Action) => api.post<Action>(`/cases/actions/${a.id}/approve`, { payload_sha256: a.payload_sha256 }), onSettled: refresh }),
    reject: useMutation({ mutationFn: (a: Action) => api.post<Action>(`/cases/actions/${a.id}/reject`, {}), onSettled: refresh }),
    edit: useMutation({ mutationFn: ({ a, payload }: { a: Action; payload: Record<string, any> }) => api.put<Action>(`/cases/actions/${a.id}`, { payload }), onSettled: refresh }),
  };
}

export function useCaseMutations() {
  const refresh = useRefresh();
  return {
    quick: useMutation({ mutationFn: (body: { jd_text: string; source_url?: string; company?: string; role?: string }) =>
      api.post<{ case_id: string; company: string; role: string }>('/experts/cases/quick', body), onSettled: refresh }),
    stage: useMutation({ mutationFn: ({ id, stage }: { id: string; stage: string }) => api.patch(`/cases/${id}/stage`, { stage }), onSettled: refresh }),
    reviewResume: useMutation({ mutationFn: ({ caseId, artifactId, decision }: { caseId: string; artifactId: string; decision: 'approved' | 'rejected' }) =>
      api.post(`/cases/${caseId}/artifacts/${artifactId}/review`, { decision }), onSettled: refresh }),
    rerun: useMutation({ mutationFn: ({ caseId, expert }: { caseId: string; expert: 'research' | 'recon' | 'tailor' | 'connect' | 'prep' | 'supervise' }) =>
      api.post(`/experts/cases/${caseId}/${expert}`, expert === 'research' ? {} : undefined), onSettled: refresh }),
    recipient: useMutation({ mutationFn: ({ caseId, email, name }: { caseId: string; email: string; name: string }) =>
      api.post(`/experts/cases/${caseId}/recipient`, { email, name }), onSettled: refresh }),
  };
}

export function useBankMutations() {
  const refresh = useRefresh();
  return { remove: useMutation({ mutationFn: (id: string) => api.delete(`/answer-bank/${id}`), onSettled: refresh }) };
}

export function useContactMutations() {
  const refresh = useRefresh();
  return { update: useMutation({ mutationFn: ({ id, changes }: { id: string; changes: Partial<Contact> }) => api.patch(`/crm/contacts/${id}`, changes), onSettled: refresh }) };
}

/** A PDF from the API as an object URL (the session cookie goes with the request). */
export async function openArtifactFile(caseId: string, artifactId: string, format: 'pdf' | 'tex' = 'pdf') {
  const blob = await api.getBlob(`/cases/${caseId}/artifacts/${artifactId}/file?format=${format}`);
  window.open(URL.createObjectURL(blob), '_blank', 'noopener');
}
