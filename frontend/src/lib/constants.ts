// ============================================================
// JobPilot AI — Application Constants
// ============================================================

import {
  BarChart3,
  FileText,
  FolderKanban,
  PlusCircle,
  Send,
  Radar,
  Settings,
  User,
  Users,
  type LucideIcon,
} from 'lucide-react';

// --- API ---
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
export const API_VERSION = 'v1';
export const API_URL = `${API_BASE_URL}/api/${API_VERSION}`;

// --- WebSocket ---
export const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000';

// --- Supabase ---
export const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || '';
export const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || '';

// --- Routes ---
export const ROUTES = {
  LOGIN: '/login',
  CHAT: '/chat',
  APPLICATIONS: '/applications',
  JOBS: '/jobs',
  APPLY_QUEUE: '/apply',
  NETWORK: '/network',
  NEW_APPLICATION: '/applications/new',
  APPLICATION_DETAIL: '/applications/:id',
  ANALYTICS: '/analytics',
  PROFILE: '/profile',
  TEMPLATES: '/templates',
  SETTINGS: '/settings',
} as const;

// --- Navigation (workspace links under the chat list) ---
export interface NavItem {
  label: string;
  path: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { label: 'Job feed', path: ROUTES.JOBS, icon: Radar },
  { label: 'Apply queue', path: ROUTES.APPLY_QUEUE, icon: Send },
  { label: 'Applications', path: ROUTES.APPLICATIONS, icon: FolderKanban },
  { label: 'Network', path: ROUTES.NETWORK, icon: Users },
  { label: 'New application', path: ROUTES.NEW_APPLICATION, icon: PlusCircle },
  { label: 'Analytics', path: ROUTES.ANALYTICS, icon: BarChart3 },
  { label: 'Profile & resume', path: ROUTES.PROFILE, icon: User },
  { label: 'Templates', path: ROUTES.TEMPLATES, icon: FileText },
  { label: 'Settings', path: ROUTES.SETTINGS, icon: Settings },
];

// --- Application Status Config ---
// Colors are CSS variables so they follow light/dark mode (see index.css).
// `mark` is the chart/dot color; `color` is pill text; `bgColor` is the pill fill.
const status = (key: string, label: string) => ({
  label,
  mark: `var(--status-${key})`,
  color: `var(--status-${key}-fg)`,
  bgColor: `color-mix(in srgb, var(--status-${key}) 14%, transparent)`,
});

export const APPLICATION_STATUS_CONFIG = {
  saved: status('saved', 'Saved'),
  applied: status('applied', 'Applied'),
  interviewing: status('interviewing', 'Interviewing'),
  offer: status('offer', 'Offer'),
  rejected: status('rejected', 'Rejected'),
  archived: status('archived', 'Archived'),
} as const;

// --- Pipeline columns ---
export const KANBAN_COLUMNS = [
  'saved',
  'applied',
  'interviewing',
  'offer',
  'rejected',
  'archived',
] as const;

// --- App Info ---
export const APP_NAME = 'JobPilot';
export const APP_DESCRIPTION = 'AI job application assistant';
export const APP_VERSION = '2.0.0';
