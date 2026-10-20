// ============================================================
// JobPilot — Autopilot: apply queue, morning digest, extension
// ============================================================

import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import api from '../lib/api';

export interface PreparedField {
  key: string;
  label: string;
  type: string;
  required: boolean;
  value: string | string[] | null;
  source: string;
  flagged: boolean;
  note: string;
}

export interface FormSummary {
  total: number;
  filled: number;
  flagged: number;
  required_missing: number;
}

export interface QueueItem {
  id: string;
  role: string;
  company: string;
  created_at: string | null;
  source: string | null;
  match_score: number | null;
  apply_url: string;
  ats: string | null;
  summary: FormSummary | null;
  flagged: PreparedField[];
  prepared: boolean;
  referral_count: number;
  skip_flags: string[];
}

export interface AutopilotStatus {
  tables_ready: boolean;
  server_scheduler: boolean;
  cron_configured: boolean;
  email_configured: boolean;
  digest_to: string;
  scan_hour: number;
  state: {
    last_scan_on: string | null;
    last_scan_at: string | null;
    last_digest_on: string | null;
    last_digest_at: string | null;
    last_digest_error: string | null;
  } | null;
}

export interface ExtensionToken {
  id: string;
  label: string;
  created_at: string;
  last_used_at: string | null;
}

export function useApplyQueue() {
  return useQuery<{ queue: QueueItem[] }>({
    queryKey: ['autopilot', 'queue'],
    queryFn: () => api.get('/autopilot/queue'),
  });
}

export function useAutopilotStatus() {
  return useQuery<AutopilotStatus>({
    queryKey: ['autopilot', 'status'],
    queryFn: () => api.get('/autopilot/status'),
  });
}

export function usePrepareForm() {
  const queryClient = useQueryClient();
  return useMutation<unknown, Error, string>({
    mutationFn: (id) => api.post(`/autopilot/prepare/${id}`, {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['autopilot', 'queue'] }),
  });
}

export function useDigestPreview(enabled: boolean) {
  return useQuery<{ subject: string; html: string; to: string }>({
    queryKey: ['autopilot', 'digest-preview'],
    queryFn: () => api.get('/autopilot/digest/preview'),
    enabled,
    staleTime: 0,
  });
}

export function useSendDigest() {
  return useMutation<{ to: string; subject: string }, Error, void>({
    mutationFn: () => api.post('/autopilot/digest/send', {}),
  });
}

export function useExtensionTokens() {
  return useQuery<{ tokens: ExtensionToken[]; server_ready: boolean }>({
    queryKey: ['autopilot', 'extension-tokens'],
    queryFn: () => api.get('/autopilot/extension-tokens'),
    retry: false,
  });
}

export function useCreateExtensionToken() {
  const queryClient = useQueryClient();
  return useMutation<{ id: string; token: string }, Error, void>({
    mutationFn: () => api.post('/autopilot/extension-tokens', {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['autopilot', 'extension-tokens'] }),
  });
}

export function useRevokeExtensionToken() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => api.delete(`/autopilot/extension-tokens/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['autopilot', 'extension-tokens'] }),
  });
}

type ExtensionMessage = { source?: string; type?: string; ok?: boolean; version?: string };

/** Whether the JobPilot extension is installed in this browser (it announces itself on this page). */
export function useExtensionPresence() {
  const [version, setVersion] = useState<string | null>(null);
  useEffect(() => {
    const onMessage = (event: MessageEvent<ExtensionMessage>) => {
      if (event.source === window && event.data?.source === 'jobpilot-extension' && event.data.type === 'present') {
        setVersion(event.data.version ?? 'installed');
      }
    };
    window.addEventListener('message', onMessage);
    window.postMessage({ source: 'jobpilot-app', type: 'ping' }, window.location.origin);
    return () => window.removeEventListener('message', onMessage);
  }, []);
  return version;
}

/** Hand a token to the extension via its content script. Resolves false if no extension answers. */
export function connectExtension(token: string, apiBase: string): Promise<boolean> {
  return new Promise((resolve) => {
    const timer = window.setTimeout(() => finish(false), 2000);
    function finish(ok: boolean) {
      window.clearTimeout(timer);
      window.removeEventListener('message', onMessage);
      resolve(ok);
    }
    function onMessage(event: MessageEvent<ExtensionMessage>) {
      if (event.source === window && event.data?.source === 'jobpilot-extension' && event.data.type === 'connected') finish(!!event.data.ok);
    }
    window.addEventListener('message', onMessage);
    window.postMessage({ source: 'jobpilot-app', type: 'connect', token, apiBase, appUrl: window.location.origin }, window.location.origin);
  });
}
