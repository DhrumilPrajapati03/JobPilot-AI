// JobPilot extension — background service worker.
// Holds the connection (API URL + personal token) and makes every API call, so
// content scripts never see the token and page CORS rules don't apply.

const DEFAULT_API = 'http://localhost:8000';
importScripts('policy.js');
const policy = globalThis.JOBPILOT_POLICY;
const storageReady = Promise.all([
  chrome.storage.local.setAccessLevel?.({accessLevel:'TRUSTED_CONTEXTS'}),
  chrome.storage.session?.setAccessLevel?.({accessLevel:'TRUSTED_CONTEXTS'}),
]);

async function settings() {
  await storageReady;
  const { apiBase = DEFAULT_API, token = '', appUrl = '' } = await chrome.storage.local.get(['apiBase', 'token', 'appUrl']);
  return { apiBase: apiBase.replace(/\/+$/, ''), token, appUrl };
}

async function api(path, { method = 'GET', body } = {}) {
  const { apiBase, token } = await settings();
  if (!policy.apiBase(apiBase)) return { ok: false, status: 400, data: { detail: 'API origin is not allowed. Check extension/policy.js.' } };
  const allowed = { GET: ['/extension/me', '/extension/queue'], POST: ['/extension/match', '/extension/fill', '/extension/applied', '/extension/answers', '/extension/sessions', '/extension/document', '/extension/events'] };
  if (!(allowed[method] || []).includes(path)) return { ok: false, status: 403, data: { detail: 'Extension action is not allowed.' } };
  if (!token) return { ok: false, status: 401, data: { detail: 'Not connected. Open JobPilot → Settings → Connect extension.' } };
  try {
    const res = await fetch(`${apiBase}/api/v1${path}`, {
      method,
      headers: { 'X-JobPilot-Token': token, ...(body ? { 'Content-Type': 'application/json' } : {}) },
      body: body ? JSON.stringify(body) : undefined,
      redirect: 'error',
      credentials: 'omit',
      ...(typeof AbortSignal !== 'undefined' ? {signal:AbortSignal.timeout(30000)} : {}),
    });
    const type = res.headers.get('content-type') || '';
    const data = type.includes('application/json') ? await res.json() : null;
    const latest = await settings();
    if (latest.token !== token || latest.apiBase !== apiBase) return {ok:false,status:409,data:{detail:'Account connection changed. Reopen the form.'}};
    return { ok: res.ok, status: res.status, data };
  } catch (e) {
    return { ok: false, status: 0, data: { detail: `Can't reach JobPilot at ${apiBase}. Is the server running? (A sleeping Render instance takes ~1 minute to wake.)` } };
  }
}

// Per-tab/per-frame, private to extension contexts. Browser observations are
// persisted before transport so navigation cannot turn an attempt into success.
const frameLocks = new Map();
chrome.storage.onChanged?.addListener(async (changes,area) => {
  if (area !== 'local' || !changes.token && !changes.apiBase) return;
  try {
    const contexts = await chrome.storage.session.get(null);
    for (const key of Object.keys(contexts).filter(k=>k.startsWith('execution:'))) {
      const [,tab,frame] = key.split(':');
      await chrome.tabs.sendMessage(Number(tab),{type:'jobpilot-connection-changed'},{frameId:Number(frame)}).catch(()=>{});
    }
  } catch (_) { /* No user data is included in this invalidation signal. */ }
});
async function fingerprint() {
  const s = await settings();
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(`${s.apiBase}:${s.token}`));
  return [...new Uint8Array(digest)].map(x => x.toString(16).padStart(2,'0')).join('');
}
const frameKey = sender => `execution:${sender.tab.id}:${sender.frameId || 0}`;
async function loadContext(sender) {
  const key = frameKey(sender);
  const state = (await chrome.storage.session.get(key))[key];
  if (!state || state.connection !== await fingerprint() || state.origin !== policy.origin(sender.url) || Date.parse(state.session.expires_at) <= Date.now()) return null;
  return state;
}
async function saveContext(sender, context) { await chrome.storage.session.set({[frameKey(sender)]:context}); }
async function flush(sender, context) {
  let result = {ok:true};
  while (context.outbox.length) {
    const body = context.outbox[0];
    result = await api('/extension/events', {method:'POST',body});
    if (!result.ok) break;
    context.outbox.shift();
    if (body.kind === 'submission_confirmation_observed') context.attempt = null;
    await saveContext(sender,context);
  }
  return result;
}
async function executionMessage(message, sender) {
  const context = await loadContext(sender);
  if (!context) return {ok:false,status:409,data:{detail:'Start a new form preparation session.'}};
  if (message.type === 'execution-context') {
    await flush(sender,context);
    return {ok:true,context:{session:context.session,attempt:context.attempt,application:context.application}};
  }
  const body = message.body;
  if (!body || body.session_id !== context.session.id || !['form_prepared','submission_attempted','submission_confirmation_observed'].includes(body.kind) || !/^[a-f0-9-]{36}$/i.test(body.request_key || '')) return {ok:false};
  const event = {...body,details:{...body.details,url:sender.url}};
  if (JSON.stringify(event).length > 65536 || context.outbox.length >= 20) return {ok:false,status:413,data:{detail:'Too many pending observations. Reconnect before continuing.'}};
  // Repeated confirmation detection reuses the queued observation's key.
  const previous = context.outbox.find(e => e.kind === event.kind && (e.request_key === event.request_key || event.kind === 'submission_confirmation_observed' && e.details.attempt_key === event.details.attempt_key));
  if (!previous) context.outbox.push(event);
  if (event.kind === 'submission_attempted') context.attempt = {key:event.request_key,at:Date.now()};
  await saveContext(sender,context);
  return await flush(sender,context);
}
async function lockedExecution(message,sender) {
  const key = frameKey(sender), previous = frameLocks.get(key) || Promise.resolve();
  const task = previous.catch(()=>{}).then(()=>executionMessage(message,sender));
  frameLocks.set(key,task);
  try { return await task; } finally { if (frameLocks.get(key) === task) frameLocks.delete(key); }
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
    if (['execution-event','execution-context'].includes(message.type)) return reply(!popup ? await lockedExecution(message,sender) : {ok:false});
    if (message.type === 'api') {
      if (message.path === '/extension/events') return reply({ok:false});
      if (message.path === '/extension/sessions') {
        if (popup || message.method !== 'POST') return reply({ok:false});
        const result = await api(message.path,{method:'POST',body:{...message.body,url:sender.url}});
        if (result.ok) await saveContext(sender,{session:result.data.session,application:result.data.application,origin:policy.origin(sender.url),connection:await fingerprint(),attempt:null,outbox:[]});
        return reply(result);
      }
      if (['/extension/document','/extension/applied'].includes(message.path) && message.body?.session_id) {
        if (popup) return reply({ok:false});
        const context = await loadContext(sender);
        if (!context || context.session.id !== message.body.session_id || message.path === '/extension/applied' && context.session.application_id !== message.body.application_id) return reply({ok:false});
      }
      return reply(await api(message.path, message));
    }
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
