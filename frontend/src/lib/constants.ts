// ============================================================
// JobPilot AI — Application Constants
// ============================================================

import {
  LayoutDashboard,
  FileText,
  PlusCircle,
  User,
  BookTemplate,
  BarChart3,
  Settings,
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
  DASHBOARD: '/dashboard',
  APPLICATIONS: '/applications',
  NEW_APPLICATION: '/applications/new',
  APPLICATION_DETAIL: '/applications/:id',
  PROFILE: '/profile',
  TEMPLATES: '/templates',
  ANALYTICS: '/analytics',
  SETTINGS: '/settings',
} as const;

// --- Navigation ---
export interface NavItem {
  label: string;
  path: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { label: 'Dashboard', path: ROUTES.DASHBOARD, icon: LayoutDashboard },
  { label: 'Applications', path: ROUTES.APPLICATIONS, icon: FileText },
  { label: 'New Application', path: ROUTES.NEW_APPLICATION, icon: PlusCircle },
  { label: 'Profile', path: ROUTES.PROFILE, icon: User },
  { label: 'Templates', path: ROUTES.TEMPLATES, icon: BookTemplate },
  { label: 'Analytics', path: ROUTES.ANALYTICS, icon: BarChart3 },
  { label: 'Settings', path: ROUTES.SETTINGS, icon: Settings },
];

// --- Application Status Config ---
export const APPLICATION_STATUS_CONFIG = {
  saved: { label: 'Saved', color: '#6B7280', bgColor: '#F3F4F6' },
  applied: { label: 'Applied', color: '#1A3C5E', bgColor: '#E8EEF5' },
  interviewing: { label: 'Interviewing', color: '#0F7B6C', bgColor: '#E6F5F2' },
  offer: { label: 'Offer', color: '#059669', bgColor: '#D1FAE5' },
  rejected: { label: 'Rejected', color: '#E85D26', bgColor: '#FEE2D5' },
  archived: { label: 'Archived', color: '#9CA3AF', bgColor: '#F9FAFB' },
} as const;

// --- Kanban Columns ---
export const KANBAN_COLUMNS = [
  'saved',
  'applied',
  'interviewing',
  'offer',
  'rejected',
  'archived',
] as const;

// --- App Info ---
export const APP_NAME = 'JobPilot AI';
export const APP_DESCRIPTION = 'Autonomous Job Application Intelligence System';
export const APP_VERSION = '1.0.0';
