import { useQuery } from '@tanstack/react-query';
import api from '../lib/api';
import type { ApplicationStatus } from './use-applications';

export interface AnalyticsSummary {
  total_applications: number;
  status_breakdown: Record<ApplicationStatus, number>;
  submitted: number;
  response_rate: number;
  interview_rate: number;
  offer_rate: number;
  emails_sent: number;
  email_reply_rate: number;
  avg_keyword_score: number | null;
  pending_follow_ups: number;
  follow_ups_due: { id: string; company: string; role: string; follow_up_at: string }[];
  weekly_applications: { week: string; count: number }[];
  recent_activity: {
    id: string;
    company: string;
    role: string;
    status: ApplicationStatus;
    created_at: string;
    updated_at: string | null;
  }[];
}

export interface SkillGaps {
  applications_analyzed: number;
  jobs_considered: number;
  has_base_resume: boolean;
  gaps: { keyword: string; count: number; share: number; in_base_resume: boolean; examples: string[] }[];
  most_requested: { skill: string; count: number; share: number; you_have: boolean }[];
}

export function useSkillGaps() {
  return useQuery<SkillGaps>({
    queryKey: ['analytics', 'skill-gaps'],
    queryFn: () => api.get<SkillGaps>('/analytics/skill-gaps'),
  });
}

export function useAnalyticsSummary() {
  return useQuery<AnalyticsSummary>({
    queryKey: ['analytics', 'summary'],
    queryFn: () => api.get<AnalyticsSummary>('/analytics/summary'),
  });
}
