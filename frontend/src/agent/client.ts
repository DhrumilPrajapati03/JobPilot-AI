// ============================================================
// JobPilot — chat streaming client
// ============================================================

import { API_URL } from '../lib/constants';
import { getChatAccountId, getChatSessionRevision, useChatStore, type ChatMessage, type StreamEvent, type ToolPart } from './store';

const HISTORY_LIMIT = 30;

const TOOL_LABELS: Record<string, string> = {
  get_overview: 'checked the overview',
  list_applications: 'listed applications',
  get_application: 'read an application',
  get_base_resume: 'read the base resume',
  get_skill_gaps: 'analysed skill gaps',
  get_job_preferences: 'read job preferences',
  get_saved_answers: 'read saved answers',
  create_application: 'started creating an application',
  get_briefing: 'read the briefing',
  get_job_feed: 'read the job feed',
  scan_jobs: 'scanned the job boards',
  find_referrals: 'checked who the user knows there',
  draft_job: 'started drafting an application',
  open_view: 'opened a view',
};

/** One-line memory of a tool call, so the model knows what happened in earlier turns. */
function describeTool(part: ToolPart): string {
  const r = part.result ?? {};
  if (r.awaiting_approval) {
    const outcome = { pending: 'awaiting the user', approved: 'APPROVED and applied', declined: 'DECLINED by the user', failed: 'approved but FAILED' }[
      part.approval ?? 'pending'
    ];
    return `[proposal: ${String(r.summary)} — ${outcome}]`;
  }
  if (r.error) return `[${part.name} failed: ${String(r.error)}]`;
  if (part.name === 'create_application' || part.name === 'draft_job') return '[started creating an application]';
  if (part.name === 'open_view') return `[opened the ${String(r.opened)} view]`;
  return `[${TOOL_LABELS[part.name] ?? part.name}]`;
}

export function messageToContent(message: ChatMessage): string {
  return message.parts
    .map((p) => (p.kind === 'text' ? p.text : describeTool(p)))
    .join('\n')
    .trim();
}

function buildHistory(messages: ChatMessage[]) {
  return messages
    .map((m) => ({ role: m.role, content: messageToContent(m) || (m.error ? `[error: ${m.error}]` : '') }))
    .filter((m) => m.content)
    .slice(-HISTORY_LIMIT);
}

async function authToken() {
  const { supabase } = await import('../lib/supabase');
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

let controller: AbortController | null = null;

export function stopChat() {
  controller?.abort();
}

/** Send a user message and stream the assistant's reply into the active thread. */
export async function sendChatMessage(text: string) {
  const accountId = getChatAccountId();
  const revision = getChatSessionRevision();
  if (!accountId) return;
  const store = useChatStore.getState();
  if (store.streaming || !text.trim()) return;

  store.addUserMessage(text.trim());
  const history = buildHistory(useChatStore.getState().activeThread().messages);
  const messageId = store.startAssistant();
  store.setStreaming(true);
  const requestController = new AbortController();
  controller = requestController;

  let error: string | undefined;
  try {
    const token = await authToken();
    if (revision !== getChatSessionRevision() || requestController.signal.aborted) return;
    const response = await fetch(`${API_URL}/agent/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({ messages: history }),
      signal: requestController.signal,
    });
    if (!response.ok || !response.body) {
      const body = await response.json().catch(() => ({}));
      throw new Error(typeof body.detail === 'string' ? body.detail : `The assistant is unreachable (${response.status}).`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (revision !== getChatSessionRevision()) { await reader.cancel(); break; }
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split('\n\n');
      buffer = frames.pop() ?? '';
      for (const frame of frames) {
        const line = frame.split('\n').find((l) => l.startsWith('data: '));
        if (!line) continue;
        try {
          const event = JSON.parse(line.slice(6)) as StreamEvent;
          if (event.type !== 'done') useChatStore.getState().applyEvent(messageId, event);
        } catch {
          // Ignore a malformed frame rather than dropping the whole reply.
        }
      }
    }
  } catch (e) {
    if ((e as Error).name !== 'AbortError') error = e instanceof Error ? e.message : 'Something went wrong.';
  } finally {
    if (controller === requestController) controller = null;
    if (revision === getChatSessionRevision()) {
      const s = useChatStore.getState();
      s.finishAssistant(messageId, error);
      s.setStreaming(false);
    }
  }
}
