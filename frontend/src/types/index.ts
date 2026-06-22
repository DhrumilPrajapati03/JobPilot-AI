// ============================================================
// JobPilot AI — Shared TypeScript Types
// ============================================================

// --- User & Profile ---
export interface UserProfile {
  id: string;
  name: string;
  email: string;
  headline: string;
  location: string;
  salary_range: {
    min: number;
    max: number;
    currency: string;
  };
  work_preferences: WorkPreferences;
  linkedin_url: string;
  avatar_url?: string;
  created_at: string;
  updated_at: string;
}

export interface WorkPreferences {
  remote_only: boolean;
  preferred_roles: string[];
  preferred_locations: string[];
  preferred_stack: string[];
  min_company_size?: number;
  exclude_industries?: string[];
}

// --- Resume ---
export interface Resume {
  id: string;
  user_id: string;
  base_version: number;
  sections: ResumeSections;
  embeddings_synced: boolean;
  created_at: string;
  updated_at: string;
}

export interface ResumeSections {
  summary: string;
  experience: ExperienceEntry[];
  skills: SkillSet;
  education: EducationEntry[];
  projects: ProjectEntry[];
  certifications: CertificationEntry[];
}

export interface ExperienceEntry {
  company: string;
  role: string;
  duration: string;
  location?: string;
  bullets: string[];
}

export interface SkillSet {
  primary: string[];
  secondary: string[];
}

export interface EducationEntry {
  institution: string;
  degree: string;
  field: string;
  year: string;
  gpa?: string;
}

export interface ProjectEntry {
  name: string;
  description: string;
  tech: string[];
  url?: string;
}

export interface CertificationEntry {
  name: string;
  issuer: string;
  year: string;
  url?: string;
}

// --- Job Application ---
export type ApplicationStatus =
  | 'saved'
  | 'applied'
  | 'interviewing'
  | 'offer'
  | 'rejected'
  | 'archived';

export interface JobApplication {
  id: string;
  user_id: string;
  company: string;
  role: string;
  jd_url?: string;
  jd_text: string;
  status: ApplicationStatus;
  source: string;
  applied_at?: string;
  salary_range?: string;
  location?: string;
  remote: boolean;
  notes?: string;
  follow_up_date?: string;
  keyword_match_score?: number;
  created_at: string;
  updated_at: string;
}

// --- Tailored Resume ---
export interface TailoredResume {
  id: string;
  application_id: string;
  version: number;
  pdf_url: string;
  docx_url?: string;
  keyword_match_score: number;
  content_json: ResumeSections;
  diff_json?: Record<string, unknown>;
  generated_at: string;
}

// --- Cold Email ---
export interface ColdEmail {
  id: string;
  application_id: string;
  to_email: string;
  to_name: string;
  subject: string;
  body: string;
  sequence_position: number; // 1 = initial, 2 = follow-up 1, 3 = follow-up 2
  sent_at?: string;
  opened?: boolean;
  replied?: boolean;
  scheduled_at?: string;
}

// --- HR Contact ---
export interface HRContact {
  id: string;
  company: string;
  name: string;
  email: string;
  linkedin_url?: string;
  title: string;
  confidence_score: number;
  source: string;
}

// --- Template ---
export type TemplateType = 'email' | 'dm' | 'cover_letter';

export interface Template {
  id: string;
  user_id: string;
  type: TemplateType;
  name: string;
  subject?: string;
  body: string;
  variables: string[];
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

// --- JD Analysis ---
export interface JDAnalysis {
  role: string;
  company: string;
  seniority: string;
  skills_required: string[];
  skills_preferred: string[];
  keywords: string[];
  tech_stack: string[];
  tone: string;
  salary_range?: string;
  location?: string;
  remote: boolean;
}

// --- Agent Run ---
export type AgentStep =
  | 'parsing_jd'
  | 'researching_company'
  | 'tailoring_resume'
  | 'writing_cover_letter'
  | 'writing_email'
  | 'writing_dm'
  | 'scoring_ats'
  | 'completed'
  | 'error';

export interface AgentRun {
  id: string;
  application_id: string;
  current_step: AgentStep;
  steps_completed: AgentStep[];
  progress: number; // 0-100
  started_at: string;
  completed_at?: string;
  error?: string;
}

// --- Analytics ---
export interface AnalyticsSummary {
  total_applications: number;
  applied_count: number;
  interview_count: number;
  offer_count: number;
  rejection_count: number;
  avg_keyword_score: number;
  response_rate: number;
  weekly_applications: WeeklyCount[];
  status_distribution: Record<ApplicationStatus, number>;
}

export interface WeeklyCount {
  week: string;
  count: number;
}

// --- API Response Wrappers ---
export interface ApiResponse<T> {
  data: T;
  message?: string;
  success: boolean;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}
