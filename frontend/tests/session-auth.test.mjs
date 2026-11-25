import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { webcrypto } from 'node:crypto';
import { build } from 'esbuild';

// The real auth store, API client and chat store, with fetch and window faked.
const built = await build({
  stdin: { contents: `
    export { useAuthStore } from './src/stores/auth-store';
    export { useChatStore } from './src/agent/store';
    export { queryClient } from './src/lib/query-client';
    export { default as api } from './src/lib/api';
    export { loginErrorMessage } from './src/lib/auth-errors';
  `, resolveDir: process.cwd() },
  bundle: true, write: false, format: 'cjs', platform: 'node',
  define: { 'process.env.NODE_ENV': '"test"', 'import.meta.env.VITE_API_BASE_URL': '"http://localhost:8000"',
    'import.meta.env.VITE_WS_BASE_URL': '"ws://localhost:8000"' },
});

function harness(href = 'http://localhost:5173/login') {
  const entries = new Map(), calls = [], redirects = [], replacements = [];
  const storage = { getItem: k => entries.get(k) ?? null, setItem: (k, v) => entries.set(k, v), removeItem: k => entries.delete(k) };
  const state = { me: null, sessionStatus: 200, hold: null };
  const json = (status, body) => ({ ok: status < 300, status, json: async () => body });
  async function fetch(url, init = {}) {
    calls.push({ url, init });
    if (state.hold) await state.hold;
    if (url.endsWith('/auth/providers')) return json(200, { google: true, github: false, token: true });
    if (url.endsWith('/api/v1/auth/me')) return state.me ? json(200, { user_id: state.me, email: `${state.me}@example.invalid` }) : json(401, {});
    if (url.endsWith('/auth/session')) return json(state.sessionStatus, {});
    if (url.endsWith('/auth/logout')) return json(204, {});
    return json(200, { ok: true });
  }
  const window = { location: { href, origin: new URL(href).origin, assign: url => redirects.push(url) },
    history: { state: {}, replaceState: (_s, _t, url) => replacements.push(url) } };
  const module = { exports: {} };
  vm.runInNewContext(built.outputFiles[0].text, { module, exports: module.exports, console, crypto: webcrypto,
    localStorage: storage, sessionStorage: storage, setTimeout, clearTimeout, AbortController, TextDecoder, URL,
    URLSearchParams, window, fetch });
  return { app: module.exports, state, calls, redirects, replacements, entries };
}

async function signInAs(h, id) {
  h.state.me = id;
  await h.app.useAuthStore.getState().initialize();
}

test('no session shows the login page; a session cookie signs in without any token in the browser', async () => {
  const h = harness();
  await h.app.useAuthStore.getState().initialize();
  assert.equal(h.app.useAuthStore.getState().user, null);
  assert.deepEqual({ ...h.app.useAuthStore.getState().providers }, { google: true, github: false, token: true });
  await signInAs(h, 'owner');
  assert.equal(h.app.useAuthStore.getState().user.id, 'owner');
  const me = h.calls.find(c => c.url.endsWith('/api/v1/auth/me'));
  assert.equal(me.init.credentials, 'include');
  assert.equal(me.init.headers['X-JobDots-Request'], '1');
  assert.equal(me.init.headers.Authorization, undefined);
});

test('provider sign-in is a full-page navigation to the API, which owns state and PKCE', async () => {
  const h = harness();
  await h.app.useAuthStore.getState().initialize();
  h.app.useAuthStore.getState().signInWithProvider('google');
  assert.deepEqual(h.redirects, ['http://localhost:8000/auth/google/start']);
  assert.equal(h.app.useAuthStore.getState().activeProvider, 'google');
  h.app.useAuthStore.getState().signInWithProvider('evil');
  assert.equal(h.redirects.length, 1);
});

test('a failed provider login shows plain copy and cleans the address bar', async () => {
  const h = harness('http://localhost:5173/login?auth_error=not_linked');
  await h.app.useAuthStore.getState().initialize();
  assert.match(h.app.useAuthStore.getState().error, /not linked to JobDots/);
  assert.deepEqual(h.replacements, ['/login']);
  assert.match(h.app.loginErrorMessage('<script>'), /did not complete/);
});

test('owner token is traded for a session once and never stored', async () => {
  const h = harness();
  await h.app.useAuthStore.getState().initialize();
  h.state.sessionStatus = 401;
  await assert.rejects(h.app.useAuthStore.getState().signInWithToken('wrong'), /not accepted/);
  h.state.sessionStatus = 200; h.state.me = 'owner';
  await h.app.useAuthStore.getState().signInWithToken('  right-token  ');
  const post = h.calls.filter(c => c.url.endsWith('/auth/session')).at(-1);
  assert.equal(post.init.headers.Authorization, 'Bearer right-token');
  assert.equal(post.init.credentials, 'include');
  assert.equal(h.app.useAuthStore.getState().user.id, 'owner');
  assert.ok(![...h.entries.values()].some(v => String(v).includes('right-token')));
});

test('account history and query cache are isolated per account', async () => {
  const h = harness();
  await signInAs(h, 'alice');
  h.app.useChatStore.getState().addUserMessage('Alice private résumé');
  h.app.queryClient.setQueryData(['profile'], { owner: 'alice' });
  const aliceClient = h.app.queryClient;
  await signInAs(h, 'bob');
  assert.equal(h.app.useChatStore.getState().activeThread().messages.length, 0);
  assert.notEqual(aliceClient, h.app.queryClient);
  assert.equal(h.app.queryClient.getQueryData(['profile']), undefined);
  await signInAs(h, 'alice');
  assert.equal(h.app.useChatStore.getState().activeThread().messages[0].parts[0].text, 'Alice private résumé');
});

test('a reply that lands after an account switch is dropped', async () => {
  const h = harness();
  await signInAs(h, 'alice');
  let release; h.state.hold = new Promise(r => { release = r; });
  const saving = h.app.api.put('/templates/email', { content: 'Alice private draft' });
  await new Promise(setImmediate);
  h.state.hold = null; h.state.me = 'bob';
  await h.app.useAuthStore.getState().initialize();
  release();
  await assert.rejects(saving, /Account changed/);
  await assert.rejects(h.app.api.put('/templates/email', { content: 'x' }, { expectedUserId: 'alice' }), /Account changed/);
});

test('sign out revokes the session on the API and clears private state', async () => {
  const h = harness();
  await signInAs(h, 'alice');
  h.app.useChatStore.getState().addUserMessage('Private');
  await h.app.useAuthStore.getState().signOut();
  const logout = h.calls.find(c => c.url.endsWith('/auth/logout'));
  assert.equal(logout.init.method, 'POST');
  assert.equal(logout.init.headers['X-JobDots-Request'], '1');
  assert.equal(h.app.useAuthStore.getState().user, null);
  assert.equal(h.app.useChatStore.getState().activeThread().messages.length, 0);
});
