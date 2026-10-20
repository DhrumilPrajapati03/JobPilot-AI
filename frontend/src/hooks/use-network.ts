// ============================================================
// JobPilot — Network: contacts and referral requests
// ============================================================

import { keepPreviousData, useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import api from '../lib/api';

export type ReferralStatus = 'drafted' | 'sent' | 'referred' | 'declined' | 'no_reply';

export const REFERRAL_STATUS_LABEL: Record<ReferralStatus, string> = {
  drafted: 'Drafted',
  sent: 'Sent',
  referred: 'Referred you',
  declined: 'Declined',
  no_reply: 'No reply',
};

export interface Contact {
  id: string;
  full_name: string;
  first_name: string;
  company: string;
  position: string;
  linkedin_url: string;
  email: string;
  connected_on: string | null;
  source: 'linkedin' | 'manual';
  notes: string;
}

export interface ReferralRequest {
  id: string;
  application_id: string;
  contact_id: string;
  status: ReferralStatus;
  message: string;
  sent_at: string | null;
  updated_at?: string;
}

export interface ReferralCandidate {
  contact: Contact;
  reason: string;
  score: number;
  request: ReferralRequest | null;
}

export interface NetworkCompany {
  company: string;
  count: number;
  applications: number;
  followed: boolean;
}

export interface ImportResult {
  imported: number;
  updated: number;
  skipped: number;
  with_company: number;
  top_companies: { company: string; count: number }[];
}

function refresh(queryClient: QueryClient) {
  queryClient.invalidateQueries({ queryKey: ['network'] });
  // Referral counts appear on applications and the job feed.
  queryClient.invalidateQueries({ queryKey: ['applications'] });
  queryClient.invalidateQueries({ queryKey: ['discovery'] });
}

export function useContacts(q: string, company = '') {
  return useQuery<{ contacts: Contact[]; total: number }>({
    queryKey: ['network', 'contacts', q, company],
    queryFn: () => api.get(`/network/contacts?${new URLSearchParams({ q, company, limit: '200' })}`),
    placeholderData: keepPreviousData,
    retry: false,
  });
}

export function useNetworkCompanies() {
  return useQuery<{ companies: NetworkCompany[]; total_contacts: number; total_companies: number }>({
    queryKey: ['network', 'companies'],
    queryFn: () => api.get('/network/companies'),
    retry: false,
  });
}

export function useReferrals(applicationId: string) {
  return useQuery<{ company: string; contacts: ReferralCandidate[]; total: number }>({
    queryKey: ['network', 'referrals', applicationId],
    queryFn: () => api.get(`/network/referrals/${applicationId}`),
    enabled: !!applicationId,
    retry: false,
  });
}

export function useImportConnections() {
  const queryClient = useQueryClient();
  return useMutation<ImportResult, Error, File>({
    mutationFn: (file) => api.upload('/network/import', file),
    onSuccess: () => refresh(queryClient),
  });
}

export function useAddContact() {
  const queryClient = useQueryClient();
  return useMutation<Contact, Error, Pick<Contact, 'full_name' | 'company' | 'position' | 'linkedin_url' | 'email'>>({
    mutationFn: (body) => api.post('/network/contacts', body),
    onSuccess: () => refresh(queryClient),
  });
}

export function useDeleteContact() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => api.delete(`/network/contacts/${id}`),
    onSuccess: () => refresh(queryClient),
  });
}

export function useCreateReferral() {
  const queryClient = useQueryClient();
  return useMutation<ReferralRequest & { used_fallback?: boolean }, Error, { application_id: string; contact_id: string; message?: string }>({
    mutationFn: (body) => api.post('/network/referrals', body),
    onSuccess: (_r, vars) => queryClient.invalidateQueries({ queryKey: ['network', 'referrals', vars.application_id] }),
  });
}

export function useUpdateReferral(applicationId: string) {
  const queryClient = useQueryClient();
  return useMutation<ReferralRequest, Error, { id: string; status?: ReferralStatus; message?: string }>({
    mutationFn: ({ id, ...body }) => api.patch(`/network/referrals/${id}`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['network', 'referrals', applicationId] }),
  });
}
