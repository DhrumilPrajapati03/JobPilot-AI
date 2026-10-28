import api from './api';
import { useAuthStore } from '../stores/auth-store';

export interface QueuedRun { status: 'queued' | 'running' | 'retry_wait' | 'succeeded' | 'failed'; run_id: string }

/** Keep mutation feedback pending until a durable worker commits success. */
export async function resolveRun<T>(response: T | QueuedRun): Promise<T> {
  if (!response || typeof response !== 'object' || !('run_id' in response)) {
    return response as T;
  }
  const account = useAuthStore.getState().user?.id;
  const deadline = Date.now() + 10 * 60_000;
  while (Date.now() < deadline) {
    if (useAuthStore.getState().user?.id !== account) throw new Error('Account changed while waiting for background work.');
    const run = await api.get<{ status: string; result: T; last_error: string | null }>(`/runs/${response.run_id}`);
    if (useAuthStore.getState().user?.id !== account) throw new Error('Account changed while waiting for background work.');
    if (run.status === 'succeeded') return run.result;
    if (run.status === 'failed') throw new Error(run.last_error || 'Background work failed.');
    await new Promise((resolve) => window.setTimeout(resolve, 2000));
  }
  throw new Error('Background work is still pending. Check the feed or tracker shortly.');
}
