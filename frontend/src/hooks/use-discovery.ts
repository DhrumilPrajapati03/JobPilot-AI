// ============================================================
// JobPilot — Job discovery: followed boards, job feed, briefing
// ============================================================

import { useEffect } from 'react';
import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import api from '../lib/api';

export type Ats = 'greenhouse' | 'lever' | 'ashby' | 'smartrecruiters' | 'himalayas' | 'remotive';
export type PostingStatus = 'new' | 'dismissed' | 'skipped' | 'drafting' | 'drafted';
export type FeedTab = 'new' | 'drafted' | 'skipped' | 'dismissed';

export const ATS_LABEL: Record<Ats, string> = {
  greenhouse: 'Greenhouse',
  lever: 'Lever',
  ashby: 'Ashby',
  smartrecruiters: 'SmartRecruiters',
  himalayas: 'Himalayas',
  remotive: 'Remotive',
};

/** Boards that list many companies' remote jobs; they ask to be credited with a link back. */
export const REMOTE_BOARDS: Partial<Record<Ats, string>> = {
  himalayas: 'https://himalayas.app',
  remotive: 'https://remotive.com',
};

export type SuggestionGroup = 'remote' | 'india' | 'global';

export const SUGGESTION_GROUPS: { id: SuggestionGroup; label: string; hint: string }[] = [
  { id: 'remote', label: 'Remote job boards', hint: 'Remote roles from thousands of companies, searched for your target roles.' },
  { id: 'india', label: 'Indian startups', hint: 'Companies with public job boards. Some (like Zomato and Blinkit) only hire through their own sites.' },
  { id: 'global', label: 'Global tech', hint: '' },
];

export interface JobSource {
  id: string;
  ats: Ats;
  slug: string;
  company: string;
  enabled: boolean;
  job_count: number;
  last_scanned_at: string | null;
  last_error: string | null;
}

export interface SuggestedBoard {
  group: SuggestionGroup;
  ats: Ats;
  slug: string;
  company: string;
  tag: string;
}

export interface JobPosting {
  id: string;
  source_id: string | null;
  ats: Ats;
  external_id: string;
  company: string;
  title: string;
  location: string;
  remote: boolean | null;
  url: string;
  posted_at: string | null;
  fit_score: number;
  title_match: number;
  matched_skills: string[];
  missing_skills: string[];
  skip_flags: string[];
  status: PostingStatus;
  application_id: string | null;
  auto_drafted: boolean;
  drafted_at: string | null;
  closed_at: string | null;
  discovered_at: string;
  /** How many people in your network work there. */
  referral_count?: number;
}

export interface ScanSummary {
  status: 'done' | 'already_running';
  sources: number;
  fetched: number;
  new: number;
  new_matches: number;
  skipped: number;
  filtered: number;
  closed: number;
  errors: { source_id: string; company: string; error: string }[];
  auto_drafting: { posting_id: string; run_id: string; title: string; company: string }[];
  scanned_at: string;
}

export type BriefingPosting = Pick<
  JobPosting,
  'id' | 'ats' | 'title' | 'company' | 'location' | 'remote' | 'url' | 'fit_score' | 'matched_skills' | 'missing_skills' | 'status' | 'application_id' | 'discovered_at' | 'posted_at'
>;

export interface Briefing {
  generated_at: string;
  sources: number;
  last_scan_at: string | null;
  stale: boolean;
  server_scans: boolean;
  min_match_score: number;
  new_matches: number;
  open_matches: number;
  top_matches: (BriefingPosting & { referral_count?: number })[];
  drafts: BriefingPosting[];
  follow_ups_due: { id: string; role: string; company: string; follow_up_at: string }[];
  auto_draft: { enabled: boolean; min_score: number; daily_cap: number; remaining_today: number };
}

interface SourcesResponse {
  sources: JobSource[];
  suggestions: SuggestedBoard[];
  server_scans: boolean;
}

interface PostingsResponse {
  postings: JobPosting[];
  total: number;
  counts: Record<FeedTab, number>;
}

function refreshDiscovery(queryClient: QueryClient) {
  queryClient.invalidateQueries({ queryKey: ['discovery'] });
}

export function useJobSources() {
  return useQuery<SourcesResponse>({
    queryKey: ['discovery', 'sources'],
    queryFn: () => api.get<SourcesResponse>('/discovery/sources'),
    retry: false,
  });
}

export function useJobPostings(tab: FeedTab) {
  return useQuery<PostingsResponse>({
    queryKey: ['discovery', 'postings', tab],
    queryFn: () => api.get<PostingsResponse>(`/discovery/postings?status=${tab}`),
    retry: false,
    // Drafts finish in the background; poll while any are in progress.
    refetchInterval: (query) => (query.state.data?.postings.some((p) => p.status === 'drafting') ? 5000 : false),
  });
}

export function useBriefing(enabled = true) {
  return useQuery<Briefing>({
    queryKey: ['discovery', 'briefing'],
    queryFn: () => api.get<Briefing>('/discovery/briefing'),
    enabled,
    retry: false,
    staleTime: 60_000,
  });
}

export function useAddSource() {
  const queryClient = useQueryClient();
  return useMutation<{ source: JobSource; scan: ScanSummary }, Error, { url: string; ats?: Ats }>({
    mutationFn: (body) => api.post('/discovery/sources', body),
    onSuccess: () => refreshDiscovery(queryClient),
  });
}

/** Follow several suggested boards, then scan them all at once. */
export function useFollowBoards() {
  const queryClient = useQueryClient();
  const scan = useScanNow();
  return useMutation<{ sources: JobSource[] }, Error, SuggestedBoard[]>({
    mutationFn: (boards) => api.post('/discovery/sources/bulk', { boards: boards.map(({ ats, slug }) => ({ ats, slug })) }),
    onSuccess: (res) => {
      refreshDiscovery(queryClient);
      if (res.sources.length) scan.mutate();
    },
  });
}

export function useUpdateSource() {
  const queryClient = useQueryClient();
  return useMutation<JobSource, Error, { id: string; enabled?: boolean; company?: string }>({
    mutationFn: ({ id, ...body }) => api.patch(`/discovery/sources/${id}`, body),
    onSuccess: () => refreshDiscovery(queryClient),
  });
}

export function useDeleteSource() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => api.delete(`/discovery/sources/${id}`),
    onSuccess: () => refreshDiscovery(queryClient),
  });
}

export function useScanNow() {
  const queryClient = useQueryClient();
  return useMutation<ScanSummary, Error, void>({
    mutationKey: ['discovery', 'scan'],
    mutationFn: () => api.post('/discovery/scan', {}),
    onSuccess: (summary) => {
      refreshDiscovery(queryClient);
      if (summary.auto_drafting?.length) queryClient.invalidateQueries({ queryKey: ['applications'] });
    },
  });
}

/** Dismiss or restore a posting; it leaves the current tab immediately. */
export function useSetPostingStatus() {
  const queryClient = useQueryClient();
  return useMutation<JobPosting, Error, { id: string; status: 'new' | 'dismissed' }, { snapshots: [readonly unknown[], PostingsResponse | undefined][] }>({
    mutationFn: ({ id, status }) => api.patch(`/discovery/postings/${id}`, { status }),
    onMutate: async ({ id }) => {
      await queryClient.cancelQueries({ queryKey: ['discovery', 'postings'] });
      const snapshots = queryClient.getQueriesData<PostingsResponse>({ queryKey: ['discovery', 'postings'] });
      queryClient.setQueriesData<PostingsResponse>({ queryKey: ['discovery', 'postings'] }, (old) =>
        old && { ...old, postings: old.postings.filter((p) => p.id !== id) },
      );
      return { snapshots };
    },
    onError: (_e, _v, context) => context?.snapshots.forEach(([key, data]) => queryClient.setQueryData(key, data)),
    onSettled: () => refreshDiscovery(queryClient),
  });
}

export function useDraftPosting() {
  const queryClient = useQueryClient();
  return useMutation<{ posting_id: string; run_id: string; title: string; company: string }, Error, string>({
    mutationFn: (id) => api.post(`/discovery/postings/${id}/draft`, {}),
    onSuccess: () => refreshDiscovery(queryClient),
  });
}

/** Once the pipeline for a draft finishes, refresh the feed and tracker. */
export function useRefreshAfterDraft() {
  const queryClient = useQueryClient();
  return () => {
    refreshDiscovery(queryClient);
    queryClient.invalidateQueries({ queryKey: ['applications'] });
    queryClient.invalidateQueries({ queryKey: ['analytics'] });
  };
}

let autoScanStarted = false;

/**
 * Scans followed boards when the app opens and the last scan is stale, so the
 * daily briefing stays fresh even when the server has no scheduler. Once per page load.
 */
export function useAutoScan() {
  const { data } = useBriefing();
  const scan = useScanNow();
  useEffect(() => {
    if (!data?.stale || autoScanStarted) return;
    autoScanStarted = true;
    scan.mutate();
  }, [data?.stale, scan]);
  return scan;
}

export function timeAgo(value: string | null | undefined) {
  if (!value) return '';
  const minutes = Math.round((Date.now() - new Date(value).getTime()) / 60_000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return days < 30 ? `${days}d ago` : new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}
