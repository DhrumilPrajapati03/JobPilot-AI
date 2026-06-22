// ============================================================
// JobPilot AI — Zustand UI State Store
// ============================================================

import { create } from 'zustand';
import type { AgentStep } from '../types';

interface UIState {
  // Sidebar
  sidebarOpen: boolean;
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;

  // Active modal
  activeModal: string | null;
  openModal: (modalId: string) => void;
  closeModal: () => void;

  // Agent run status
  agentRunning: boolean;
  agentStep: AgentStep | null;
  agentProgress: number;
  setAgentStatus: (running: boolean, step?: AgentStep | null, progress?: number) => void;

  // Notification count
  notificationCount: number;
  setNotificationCount: (count: number) => void;

  // Active tab in various views
  activeTab: string;
  setActiveTab: (tab: string) => void;

  // Application tracker view mode
  trackerViewMode: 'kanban' | 'table';
  setTrackerViewMode: (mode: 'kanban' | 'table') => void;
}

export const useUIStore = create<UIState>((set) => ({
  // Sidebar
  sidebarOpen: true,
  sidebarCollapsed: false,
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),

  // Modals
  activeModal: null,
  openModal: (modalId) => set({ activeModal: modalId }),
  closeModal: () => set({ activeModal: null }),

  // Agent
  agentRunning: false,
  agentStep: null,
  agentProgress: 0,
  setAgentStatus: (running, step = null, progress = 0) =>
    set({ agentRunning: running, agentStep: step, agentProgress: progress }),

  // Notifications
  notificationCount: 0,
  setNotificationCount: (count) => set({ notificationCount: count }),

  // Tabs
  activeTab: 'overview',
  setActiveTab: (tab) => set({ activeTab: tab }),

  // Tracker view mode
  trackerViewMode: 'kanban',
  setTrackerViewMode: (mode) => set({ trackerViewMode: mode }),
}));

export default useUIStore;
