// JobPilot extension — background service worker.
// Holds the connection (API URL + personal token) and makes every API call, so
// content scripts never see the token and page CORS rules don't apply.

const DEFAULT_API = 'http://localhost:8000';
importScripts('policy.js');
const policy = globalThis.JOBPILOT_POLICY;

async function settings() {
  const { apiBase = DEFAULT_API, token = '', appUrl = '' } = await chrome.storage.local.get(['apiBase', 'token', 'appUrl']);
  return { apiBase: apiBase.replace(/\/+$/, ''), token, appUrl };
}

async function api(path, { method = 'GET', body } = {}) {
  const { apiBase, token } = await settings();
  if (!policy.apiBase(apiBase)) return { ok: false, status: 400, data: { detail: 'API origin is not allowed. Check extension/policy.js.' } };
  const allowed = { GET: ['/extension/me', '/extension/queue'], POST: ['/extension/match', '/extension/fill', '/extension/applied', '/extension/answers'] };
  if (!(allowed[method] || []).includes(path)) return { ok: false, status: 403, data: { detail: 'Extension action is not allowed.' } };
  if (!token) return { ok: false, status: 401, data: { detail: 'Not connected. Open JobPilot → Settings → Connect extension.' } };
  try {
    const res = await fetch(`${apiBase}/api/v1${path}`, {
      method,
      headers: { 'X-JobPilot-Token': token, ...(body ? { 'Content-Type': 'application/json' } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
    const type = res.headers.get('content-type') || '';
    const data = type.includes('application/json') ? await res.json() : null;
    return { ok: res.ok, status: res.status, data };
  } catch (e) {
    return { ok: false, status: 0, data: { detail: `Can't reach JobPilot at ${apiBase}. Is the server running? (A sleeping Render instance takes ~1 minute to wake.)` } };
  }
}

async function resume(applicationId) {
  const { apiBase, token } = await settings();
  if (!policy.apiBase(apiBase) || !/^[a-zA-Z0-9-]{1,64}$/.test(applicationId || '')) return { ok: false, detail: 'Invalid API origin or application.' };
  try {
    const res = await fetch(`${apiBase}/api/v1/extension/resume/${applicationId}`, { headers: { 'X-JobPilot-Token': token } });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      return { ok: false, detail: data.detail || `Resume download failed (${res.status})` };
    }
    const disposition = res.headers.get('content-disposition') || '';
    const name = (disposition.match(/filename="([^"]+)"/) || [])[1] || 'Resume.pdf';
    const bytes = new Uint8Array(await res.arrayBuffer());
    let binary = '';
    for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return { ok: true, name, base64: btoa(binary) };
  } catch (e) {
    return { ok: false, detail: 'Could not download the resume PDF.' };
  }
}

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  (async () => {
    if (sender.id !== chrome.runtime.id) return reply({ ok: false });
    const popup = sender.url === chrome.runtime.getURL('popup.html');
    const origin = policy.origin(sender.url);
    if (!popup && (!sender.tab || !origin || !/^https?:/.test(origin))) return reply({ ok: false });
    if (message.type === 'api') return reply(await api(message.path, message));
    if (message.type === 'resume') return reply(await resume(message.applicationId));
    // Raw credentials are accessible to the extension popup only, never content scripts.
    if (message.type === 'settings') return reply(popup ? await settings() : { ok: false });
    if (message.type === 'connect') {
      const apiBase = policy.apiBase(message.apiBase || DEFAULT_API);
      if (!apiBase || typeof message.token !== 'string' || !/^jpx_[A-Za-z0-9_-]{40,80}$/.test(message.token) ||
          (!popup && (sender.frameId !== 0 || !policy.appOrigins.includes(origin) || message.appUrl !== origin))) return reply({ ok: false });
      await chrome.storage.local.set({ token: message.token, apiBase, appUrl: popup ? '' : origin });
      return reply({ ok: true });
    }
    reply({ ok: false });
  })().catch(() => reply({ ok: false, data: { detail: 'Invalid extension request.' } }));
  return true; // async reply
});
