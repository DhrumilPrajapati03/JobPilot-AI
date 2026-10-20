import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../lib/api';
import type { Resume } from './use-profile';

export type ApplicationStatus = 'saved' | 'applied' | 'interviewing' | 'offer' | 'rejected' | 'archived';

export interface JDAnalysis {
  role: string;
  company: string;
  seniority: string;
  tone: string;
  required_skills: string[];
  keywords: string[];
  tech_stack: string[];
  salary_range: string | null;
  remote: boolean | null;
  /** "mnc" | "startup" | "sme" — absent on applications parsed before it existed. */
  company_type?: string;
  /** Skip rules this job broke when it was created (empty = none). */
  skip_flags?: string[];
}

export interface LinkedInDM {
  connection_request: string;
  follow_up: string;
}

export interface JobApplication {
  id: string;
  user_id: string;
  company: string;
  role: string;
  jd_url: string;
  jd_text?: string;
  jd_analysis: JDAnalysis | null;
  status: ApplicationStatus;
  source: string;
  applied_at: string | null;
  follow_up_at: string | null;
  notes: string;
  cover_letter: string;
  linkedin_dm: LinkedInDM;
  created_at: string;
  updated_at: string | null;
  /** Only present in list responses. */
  keyword_match_score?: number | null;
  /** List responses: how many people in your network work there. */
  referral_count?: number;
  /** List responses: the prepared application form, summarised. */
  prepared_summary?: { total: number; filled: number; flagged: number; required_missing: number } | null;
  apply_url?: string;
}

export interface TailoredResume {
  id: string;
  application_id: string;
  user_id: string;
  version: number;
  content: Resume;
  pdf_url: string;
  keyword_match_score: number;
  missing_keywords: string[];
  generated_at?: string;
  created_at?: string;
}

export interface ColdEmail {
  id: string;
  application_id: string;
  to_email: string;
  to_name: string;
  subject: string;
  body: string;
  sequence_number: number;
  sent_at: string | null;
  opened: boolean;
  replied: boolean;
}

export interface ApplicationDetails {
  application: JobApplication;
  tailored_resume: TailoredResume | null;
  cold_emails: ColdEmail[];
}

export interface GenerateApplicationResponse {
  status: string;
  run_id: string;
  message: string;
}

type ApplicationList = { applications: JobApplication[]; total: number };

export type ApplicationUpdate = Partial<
  Pick<JobApplication, 'company' | 'role' | 'jd_url' | 'notes' | 'cover_letter' | 'linkedin_dm' | 'follow_up_at'>
>;

export type ColdEmailUpdate = Partial<Pick<ColdEmail, 'to_email' | 'to_name' | 'subject' | 'body' | 'replied'>> & {
  sent?: boolean;
};

export function useApplications(filters?: { status?: string; source?: string }) {
  return useQuery<ApplicationList>({
    queryKey: ['applications', filters ?? {}],
    queryFn: () => {
      const params = new URLSearchParams();
      if (filters?.status) params.append('status', filters.status);
      if (filters?.source) params.append('source', filters.source);
      return api.get<ApplicationList>(`/applications/?${params.toString()}`);
    },
  });
}

export function useApplicationDetail(id: string) {
  return useQuery<ApplicationDetails>({
    queryKey: ['application-detail', id],
    queryFn: () => api.get<ApplicationDetails>(`/applications/${id}`),
    enabled: !!id,
  });
}

export function useGenerateApplication() {
  return useMutation<GenerateApplicationResponse, Error, { jd_url?: string; jd_text?: string }>({
    mutationFn: (data) => api.post<GenerateApplicationResponse>('/applications/generate', data),
  });
}

/** Status change with an optimistic update so kanban drags feel instant. */
export function useUpdateApplicationStatus() {
  const queryClient = useQueryClient();

  return useMutation<
    { application: JobApplication },
    Error,
    { id: string; status: ApplicationStatus },
    { snapshots: [readonly unknown[], ApplicationList | undefined][] }
  >({
    mutationFn: ({ id, status }) => api.put(`/applications/${id}/status`, { status }),
    onMutate: async ({ id, status }) => {
      await queryClient.cancelQueries({ queryKey: ['applications'] });
      const snapshots = queryClient.getQueriesData<ApplicationList>({ queryKey: ['applications'] });
      queryClient.setQueriesData<ApplicationList>({ queryKey: ['applications'] }, (old) =>
        old && { ...old, applications: old.applications.map((a) => (a.id === id ? { ...a, status } : a)) },
      );
      return { snapshots };
    },
    onError: (_err, _vars, context) => {
      context?.snapshots.forEach(([key, data]) => queryClient.setQueryData(key, data));
    },
    onSettled: (_data, _err, variables) => {
      queryClient.invalidateQueries({ queryKey: ['applications'] });
      queryClient.invalidateQueries({ queryKey: ['application-detail', variables.id] });
      queryClient.invalidateQueries({ queryKey: ['analytics'] });
    },
  });
}

export function useUpdateApplication(id: string) {
  const queryClient = useQueryClient();

  return useMutation<JobApplication, Error, ApplicationUpdate>({
    mutationFn: (data) => api.patch<JobApplication>(`/applications/${id}`, data),
    onSuccess: (application) => {
      queryClient.setQueryData<ApplicationDetails>(['application-detail', id], (old) =>
        old && { ...old, application: { ...old.application, ...application } },
      );
      queryClient.invalidateQueries({ queryKey: ['applications'] });
    },
  });
}

export function useUpdateColdEmail(applicationId: string) {
  const queryClient = useQueryClient();

  return useMutation<ColdEmail, Error, { emailId: string; data: ColdEmailUpdate }>({
    mutationFn: ({ emailId, data }) => api.put<ColdEmail>(`/applications/${applicationId}/emails/${emailId}`, data),
    onSuccess: (email) => {
      queryClient.setQueryData<ApplicationDetails>(['application-detail', applicationId], (old) =>
        old && { ...old, cold_emails: old.cold_emails.map((e) => (e.id === email.id ? email : e)) },
      );
      queryClient.invalidateQueries({ queryKey: ['analytics'] });
    },
  });
}

export function useUpdateTailoredResume(applicationId: string) {
  const queryClient = useQueryClient();

  return useMutation<TailoredResume, Error, Resume>({
    mutationFn: (content) => api.put<TailoredResume>(`/resume/tailored/${applicationId}`, content),
    onSuccess: (tailored) => {
      queryClient.setQueryData<ApplicationDetails>(['application-detail', applicationId], (old) =>
        old && { ...old, tailored_resume: tailored },
      );
      queryClient.invalidateQueries({ queryKey: ['applications'] });
    },
  });
}

export function useDeleteApplication() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, string>({
    mutationFn: (id) => api.delete<void>(`/applications/${id}`),
    onSuccess: (_data, id) => {
      queryClient.removeQueries({ queryKey: ['application-detail', id] });
      queryClient.invalidateQueries({ queryKey: ['applications'] });
      queryClient.invalidateQueries({ queryKey: ['analytics'] });
    },
  });
}

/** Downloads the server-rendered PDF; throws if the renderer is unavailable. */
export async function downloadTailoredPdf(applicationId: string, filename: string) {
  const blob = await api.getBlob(`/resume/tailored/${applicationId}/pdf`);
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
