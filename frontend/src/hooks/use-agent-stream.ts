import { useCallback, useEffect, useRef, useState } from 'react';
import { WS_BASE_URL } from '../lib/constants';
import { supabase } from '../lib/supabase';
import { useAuthStore } from '../stores/auth-store';

export const PIPELINE_STEPS = [
  { id: 'jd_parsing', label: 'Parse job description', description: 'Extracting role, skills, keywords and tone' },
  { id: 'profile_loading', label: 'Load Identity Vault', description: 'Reading your base resume and profile' },
  { id: 'resume_tailoring', label: 'Tailor resume', description: 'Rewriting summary, bullets and skills for ATS' },
  { id: 'pdf_rendering', label: 'Render PDF', description: 'Compiling a one-page resume' },
  { id: 'outreach_generation', label: 'Draft outreach', description: 'Cover letter, cold emails and LinkedIn DMs' },
  { id: 'database_saving', label: 'Log application', description: 'Adding it to your tracker' },
  { id: 'referral_check', label: 'Check referrals', description: 'Looking for people you know there' },
] as const;

export type PipelineStepId = (typeof PIPELINE_STEPS)[number]['id'];
export type StepState = 'idle' | 'running' | 'done' | 'warning' | 'error';

export interface StepProgress {
  state: StepState;
  message?: string;
  data?: Record<string, unknown>;
}

interface AgentEvent {
  type: 'status' | 'unknown_run';
  step: PipelineStepId | 'complete';
  status: 'running' | 'done' | 'warning' | 'error' | 'success';
  message: string;
  data?: Record<string, unknown>;
  application_id?: string | null;
}

export type StreamPhase = 'idle' | 'running' | 'success' | 'error';

const ACTIVE_RUN_KEY = 'jobpilot:active-run';
const MAX_RECONNECTS = 4;

const initialSteps = (): Record<string, StepProgress> =>
  Object.fromEntries(PIPELINE_STEPS.map((s) => [s.id, { state: 'idle' as StepState }]));

function readActiveRun(): string | null {
  try {
    const id = useAuthStore.getState().user?.id;
    return id ? sessionStorage.getItem(`${ACTIVE_RUN_KEY}:${id}`) : null;
  } catch {
    return null;
  }
}

function writeActiveRun(runId: string | null) {
  try {
    const id = useAuthStore.getState().user?.id;
    if (!id) return;
    const key = `${ACTIVE_RUN_KEY}:${id}`;
    if (runId) sessionStorage.setItem(key, runId);
    else sessionStorage.removeItem(key);
  } catch {
    // Storage unavailable (private mode) — resuming after refresh just won't work.
  }
}

/**
 * Follows an agent pipeline run over the backend WebSocket.
 * The server replays a run's full history on connect, so reconnects and
 * page refreshes (the run id is kept in sessionStorage) rebuild the same state.
 *
 * `persist: false` follows a run without touching sessionStorage — used by the
 * inline pipeline cards in the chat, which pass their own `runId`.
 */
export function useAgentStream({ persist = true, runId }: { persist?: boolean; runId?: string } = {}) {
  const remember = useCallback((id: string | null) => {
    if (persist) writeActiveRun(id);
  }, [persist]);

  const [steps, setSteps] = useState<Record<string, StepProgress>>(initialSteps);
  const [phase, setPhase] = useState<StreamPhase>(runId ? 'running' : 'idle');
  const [error, setError] = useState<string | null>(null);
  const [applicationId, setApplicationId] = useState<string | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const finishedRef = useRef(false);
  const reconnectsRef = useRef(0);
  const timerRef = useRef<number | undefined>(undefined);

  const close = useCallback(() => {
    window.clearTimeout(timerRef.current);
    const socket = socketRef.current;
    socketRef.current = null;
    socket?.close();
  }, []);

  const handleEvent = useCallback(
    (event: AgentEvent) => {
      if (event.type === 'unknown_run') {
        // Expired or server restarted: nothing to resume.
        finishedRef.current = true;
        remember(null);
        close();
        setSteps(initialSteps());
        setPhase('idle');
        return;
      }
      if (event.type !== 'status') return;

      if (event.step === 'complete') {
        finishedRef.current = true;
        setSteps((prev) =>
          Object.fromEntries(
            Object.entries(prev).map(([id, s]) => [id, s.state === 'warning' ? s : { ...s, state: 'done' as StepState }]),
          ),
        );
        setApplicationId(event.application_id ?? null);
        setResult(event.data ?? null);
        setPhase('success');
        remember(null);
        close();
        return;
      }

      setSteps((prev) => {
        const next = { ...prev };
        const index = PIPELINE_STEPS.findIndex((s) => s.id === event.step);
        // Anything before the reported step that never reported back is done.
        PIPELINE_STEPS.slice(0, index).forEach((s) => {
          if (next[s.id].state === 'idle' || next[s.id].state === 'running') {
            next[s.id] = { ...next[s.id], state: 'done' };
          }
        });
        next[event.step] = {
          state: event.status === 'success' ? 'done' : event.status,
          message: event.message,
          data: event.data ?? prev[event.step]?.data,
        };
        return next;
      });

      if (event.status === 'error') {
        finishedRef.current = true;
        setError(event.message);
        setApplicationId(event.application_id ?? null);
        setPhase('error');
        remember(null);
        close();
      }
    },
    [close, remember],
  );

  const connect = useCallback(
    (runId: string) => {
      close();
      // The server replays the whole run, so start from a clean slate.
      setSteps(initialSteps());
      const socket = new WebSocket(`${WS_BASE_URL}/ws/agent-stream/${runId}`);
      socketRef.current = socket;

      socket.onopen = async () => {
        const { data } = await supabase.auth.getSession();
        if (socketRef.current !== socket || socket.readyState !== WebSocket.OPEN) return;
        socket.send(JSON.stringify({ token: data.session?.access_token ?? '' }));
      };
      socket.onmessage = (message) => {
        try {
          handleEvent(JSON.parse(message.data) as AgentEvent);
        } catch {
          // Ignore malformed frames.
        }
      };
      socket.onclose = (event) => {
        if (socketRef.current !== socket || finishedRef.current) return;
        if (event.code === 4401 || event.code === 4403) {
          finishedRef.current = true;
          setError('This session cannot access the run. Sign in again or open a run from your account.');
          setPhase('error');
          remember(null);
          return;
        }
        if (reconnectsRef.current >= MAX_RECONNECTS) {
          setError('Lost connection to the agent stream. The run may still finish — check your tracker shortly.');
          setPhase('error');
          remember(null);
          return;
        }
        reconnectsRef.current += 1;
        timerRef.current = window.setTimeout(() => connect(runId), 1000 * reconnectsRef.current);
      };
    },
    [close, handleEvent, remember],
  );

  const start = useCallback(
    (runId: string) => {
      finishedRef.current = false;
      reconnectsRef.current = 0;
      setError(null);
      setApplicationId(null);
      setResult(null);
      setPhase('running');
      remember(runId);
      connect(runId);
    },
    [connect, remember],
  );

  const reset = useCallback(() => {
    finishedRef.current = true;
    close();
    remember(null);
    setSteps(initialSteps());
    setPhase('idle');
    setError(null);
    setApplicationId(null);
    setResult(null);
  }, [close, remember]);

  // Follow the given run, or resume one that was in progress before a page refresh.
  useEffect(() => {
    const id = runId ?? (persist ? readActiveRun() : null);
    if (id) start(id);
    return () => {
      finishedRef.current = true;
      close();
    };
  }, [start, close, runId, persist]);

  return { steps, phase, error, applicationId, result, start, reset };
}
