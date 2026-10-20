// ============================================================
// JobPilot — chat conversation store
// Threads are kept on this device (localStorage, memory fallback).
// ============================================================

import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import { safeStorage } from '../lib/storage';

export type ApprovalState = 'pending' | 'approved' | 'declined' | 'failed';

export interface TextPart {
  kind: 'text';
  text: string;
}

export interface ToolPart {
  kind: 'tool';
  id: string;
  name: string;
  args: Record<string, unknown>;
  result?: Record<string, unknown>;
  status: 'running' | 'done';
  approval?: ApprovalState;
  approvalError?: string;
}

export type MessagePart = TextPart | ToolPart;

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  parts: MessagePart[];
  createdAt: string;
  error?: string;
}

export interface Thread {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: string;
  updatedAt: string;
}

export type StageView = 'applications' | 'detail' | 'analytics' | 'new' | 'profile' | 'feed' | 'network' | 'queue';

export interface StageState {
  view: StageView;
  applicationId?: string;
  tab?: string;
  /** Changes every time a view is opened, so the panel remounts and scrolls to top. */
  key: number;
}

export type StreamEvent =
  | { type: 'text'; delta: string }
  | { type: 'tool_start'; id: string; name: string; args: Record<string, unknown> }
  | { type: 'tool_result'; id: string; name: string; result: Record<string, unknown> }
  | { type: 'error'; message: string }
  | { type: 'done' };

const MAX_THREADS = 20;
const MAX_MESSAGES = 120;

const uid = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);
const now = () => new Date().toISOString();

function newThread(): Thread {
  const t = now();
  return { id: uid(), title: 'New chat', messages: [], createdAt: t, updatedAt: t };
}

interface ChatState {
  threads: Thread[];
  activeId: string;
  stage: StageState | null;
  streaming: boolean;

  activeThread: () => Thread;
  startThread: () => void;
  selectThread: (id: string) => void;
  deleteThread: (id: string) => void;

  addUserMessage: (text: string) => void;
  startAssistant: () => string;
  applyEvent: (messageId: string, event: StreamEvent) => void;
  finishAssistant: (messageId: string, error?: string) => void;
  setApproval: (toolId: string, approval: ApprovalState, error?: string) => void;

  openStage: (stage: Omit<StageState, 'key'>) => void;
  closeStage: () => void;
  setStreaming: (streaming: boolean) => void;
}

function updateThread(threads: Thread[], id: string, fn: (t: Thread) => Thread) {
  return threads.map((t) => (t.id === id ? fn(t) : t));
}

function updateMessage(thread: Thread, messageId: string, fn: (m: ChatMessage) => ChatMessage): Thread {
  return { ...thread, updatedAt: now(), messages: thread.messages.map((m) => (m.id === messageId ? fn(m) : m)) };
}

const initial = newThread();

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      threads: [initial],
      activeId: initial.id,
      stage: null,
      streaming: false,

      activeThread: () => get().threads.find((t) => t.id === get().activeId) ?? get().threads[0],

      startThread: () => {
        const current = get().activeThread();
        if (current && current.messages.length === 0) return; // reuse the empty one
        const thread = newThread();
        set((s) => ({ threads: [thread, ...s.threads].slice(0, MAX_THREADS), activeId: thread.id, stage: null }));
      },

      selectThread: (id) => set({ activeId: id, stage: null }),

      deleteThread: (id) =>
        set((s) => {
          const remaining = s.threads.filter((t) => t.id !== id);
          const threads = remaining.length ? remaining : [newThread()];
          return { threads, activeId: s.activeId === id ? threads[0].id : s.activeId };
        }),

      addUserMessage: (text) =>
        set((s) => ({
          threads: updateThread(s.threads, s.activeId, (t) => ({
            ...t,
            title: t.messages.length === 0 ? text.replace(/\s+/g, ' ').slice(0, 48) : t.title,
            updatedAt: now(),
            messages: [...t.messages, { id: uid(), role: 'user' as const, parts: [{ kind: 'text' as const, text }], createdAt: now() }].slice(-MAX_MESSAGES),
          })),
        })),

      startAssistant: () => {
        const id = uid();
        set((s) => ({
          threads: updateThread(s.threads, s.activeId, (t) => ({
            ...t,
            updatedAt: now(),
            messages: [...t.messages, { id, role: 'assistant' as const, parts: [], createdAt: now() }].slice(-MAX_MESSAGES),
          })),
        }));
        return id;
      },

      applyEvent: (messageId, event) => {
        if (event.type === 'tool_result' && event.result && typeof event.result.opened === 'string') {
          get().openStage({
            view: event.result.opened as StageView,
            applicationId: (event.result.application_id as string) || undefined,
            tab: (event.result.tab as string) || undefined,
          });
        }
        set((s) => ({
          threads: updateThread(s.threads, s.activeId, (t) =>
            updateMessage(t, messageId, (m) => {
              const parts = [...m.parts];
              if (event.type === 'text') {
                const last = parts[parts.length - 1];
                if (last?.kind === 'text') parts[parts.length - 1] = { ...last, text: last.text + event.delta };
                else parts.push({ kind: 'text', text: event.delta });
              } else if (event.type === 'tool_start') {
                parts.push({ kind: 'tool', id: event.id, name: event.name, args: event.args, status: 'running' });
              } else if (event.type === 'tool_result') {
                const index = parts.findIndex((p) => p.kind === 'tool' && p.id === event.id);
                const isProposal = !!event.result?.awaiting_approval;
                const update: Partial<ToolPart> = { result: event.result, status: 'done', ...(isProposal ? { approval: 'pending' as const } : {}) };
                if (index >= 0) parts[index] = { ...(parts[index] as ToolPart), ...update };
                else parts.push({ kind: 'tool', id: event.id, name: event.name, args: {}, ...update } as ToolPart);
              } else if (event.type === 'error') {
                return { ...m, parts, error: event.message };
              }
              return { ...m, parts };
            }),
          ),
        }));
      },

      finishAssistant: (messageId, error) =>
        set((s) => ({
          threads: updateThread(s.threads, s.activeId, (t) =>
            updateMessage(t, messageId, (m) => ({
              ...m,
              error: error ?? m.error,
              // Tools still "running" when a stream ends never reported back.
              parts: m.parts.map((p) => (p.kind === 'tool' && p.status === 'running' ? { ...p, status: 'done' as const, result: p.result ?? { error: 'Interrupted' } } : p)),
            })),
          ),
        })),

      setApproval: (toolId, approval, error) =>
        set((s) => ({
          threads: s.threads.map((t) => ({
            ...t,
            messages: t.messages.map((m) => ({
              ...m,
              parts: m.parts.map((p) => (p.kind === 'tool' && p.id === toolId ? { ...p, approval, approvalError: error } : p)),
            })),
          })),
        })),

      openStage: (stage) => set((s) => ({ stage: { ...stage, key: (s.stage?.key ?? 0) + 1 } })),
      closeStage: () => set({ stage: null }),
      setStreaming: (streaming) => set({ streaming }),
    }),
    {
      name: 'jobpilot-chat',
      storage: createJSONStorage(() => safeStorage),
      partialize: (s) => ({ threads: s.threads, activeId: s.activeId }),
    },
  ),
);
