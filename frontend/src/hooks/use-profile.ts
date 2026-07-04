import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../lib/api';

// Define TS Interfaces corresponding to FastAPI Pydantic Models
export interface UserProfile {
  id?: string;
  name: string;
  headline: string;
  location: string;
  salary_range: string;
  work_preferences: Record<string, any>;
}

export interface ResumeExperience {
  company: string;
  role: string;
  duration: string;
  bullets: string[];
}

export interface ResumeSkills {
  primary: string[];
  secondary: string[];
}

export interface ResumeProject {
  name: string;
  description: string;
  tech: string[];
}

export interface ResumeEducation {
  institution: string;
  degree: string;
  year: string;
}

export interface ResumeCertification {
  name: string;
  issuer: string;
  year: string;
}

export interface Resume {
  id?: string;
  user_id?: string;
  name: string;
  headline: string;
  summary: string;
  experience: ResumeExperience[];
  skills: ResumeSkills;
  projects: ResumeProject[];
  education: ResumeEducation[];
  certifications: ResumeCertification[];
}

// ==========================================
// 1. User Profile Hooks
// ==========================================

export function useProfile() {
  return useQuery<UserProfile>({
    queryKey: ['profile'],
    queryFn: () => api.get<UserProfile>('/api/v1/profile/'),
  });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (data: Partial<UserProfile>) => 
      api.post<UserProfile>('/api/v1/profile/update', data),
    onSuccess: () => {
      // Invalidate the 'profile' query cache so the browser refetches fresh data
      queryClient.invalidateQueries({ queryKey: ['profile'] });
    },
  });
}

// ==========================================
// 2. Base Resume Hooks
// ==========================================

export function useResume() {
  return useQuery<Resume>({
    queryKey: ['resume'],
    queryFn: () => api.get<Resume>('/api/v1/resume/base'),
  });
}

export function useUpdateResume() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (data: Resume) => 
      api.post<Resume>('/api/v1/resume/base', data),
    onSuccess: () => {
      // Invalidate 'resume' so any list previews are updated
      queryClient.invalidateQueries({ queryKey: ['resume'] });
    },
  });
}
