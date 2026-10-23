import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { webcrypto } from 'node:crypto';
import { build } from 'esbuild';

// Exercise the actual stores and streaming client without browser/real Supabase.
const built = await build({
  stdin: { contents: `
    export { useAuthStore } from './src/stores/auth-store';
    export { useChatStore } from './src/agent/store';
    export { sendChatMessage } from './src/agent/client';
    export { queryClient } from './src/lib/query-client';
    export { supabase } from './src/lib/supabase';
  `, resolveDir: process.cwd() },
  bundle: true, write: false, format: 'cjs', platform: 'node',
  define: { 'process.env.NODE_ENV': '"test"', 'import.meta.env.VITE_API_BASE_URL': '"http://localhost:8000"',
    'import.meta.env.VITE_WS_BASE_URL': '"ws://localhost:8000"', 'import.meta.env.VITE_SUPABASE_URL': '"https://example.supabase.co"',
    'import.meta.env.VITE_SUPABASE_ANON_KEY': '"test"' },
  plugins: [{ name: 'offline-auth', setup(builder) {
    builder.onLoad({ filter: /[\\/]lib[\\/]supabase\.ts$/ }, () => ({ contents: `
      export const supabase = { auth: {
        getSession: async () => ({data: {session: {access_token: 'test-token'}}}),
        signOut: async () => ({error: null}),
      }};
    `, loader: 'ts' }));
  }}],
});

function harness() {
  const entries = new Map();
  const storage = { getItem: (k) => entries.get(k) ?? null, setItem: (k,v) => entries.set(k,v), removeItem: (k) => entries.delete(k) };
  const module = { exports: {} };
  vm.runInNewContext(built.outputFiles[0].text, {
    module, exports: module.exports, console, crypto: webcrypto,
    localStorage: storage, sessionStorage: storage,
    setTimeout, clearTimeout, AbortController, TextDecoder,
  });
  return { app: module.exports, entries };
}
const session = (id) => ({ user: { id }, access_token: `token-${id}` });

test('account history is isolated, restored only to its owner, and legacy history is not hydrated', () => {
  const { app, entries } = harness();
  entries.set('jobpilot-chat', JSON.stringify({state: {threads: [{id:'old', messages: [{role:'user', parts:[{text:'unknown owner'}]}]}]}}));
  app.useAuthStore.getState().setSession(session('alice'));
  assert.equal(app.useChatStore.getState().activeThread().messages.length, 0);
  app.useChatStore.getState().addUserMessage('Alice private résumé');
  app.useAuthStore.getState().setSession(session('bob'));
  assert.equal(app.useChatStore.getState().activeThread().messages.length, 0);
  app.useChatStore.getState().addUserMessage('Bob private application');
  app.useAuthStore.getState().setSession(session('alice'));
  assert.equal(app.useChatStore.getState().activeThread().messages[0].parts[0].text, 'Alice private résumé');
  app.useAuthStore.getState().setSession(null);
  assert.equal(app.useChatStore.getState().activeThread().messages.length, 0);
  assert(entries.has('jobpilot-chat:alice') && entries.has('jobpilot-chat:bob'));
});

test('late mutation callbacks cannot repopulate another account cache; same-account refresh keeps it', () => {
  const { app } = harness();
  app.useAuthStore.getState().setSession(session('alice'));
  const previousClient = app.queryClient;
  previousClient.setQueryData(['application-detail','private'], { owner: 'alice' });
  app.useAuthStore.getState().setSession(session('bob'));
  previousClient.setQueryData(['application-detail','late'], { owner: 'alice' });
  assert.notEqual(previousClient, app.queryClient);
  assert.equal(app.queryClient.getQueryData(['application-detail','late']), undefined);
  app.queryClient.setQueryData(['profile'], { owner: 'bob' });
  const sameClient = app.queryClient;
  app.useAuthStore.getState().setSession(session('bob'));
  assert.equal(app.queryClient, sameClient);
  assert.equal(app.queryClient.getQueryData(['profile']).owner, 'bob');
});

test('an old chat completion cannot clear a newer stream after switching away and back', async () => {
  const { app } = harness();
  const pending = [];
  app.supabase.auth.getSession = () => new Promise((resolve) => pending.push(resolve));
  app.useAuthStore.getState().setSession(session('alice'));
  const old = app.sendChatMessage('Old request');
  await new Promise(setImmediate);
  app.useAuthStore.getState().setSession(session('bob'));
  app.useAuthStore.getState().setSession(session('alice'));
  const current = app.sendChatMessage('Current request');
  await new Promise(setImmediate);
  pending[0]({data: {session: {access_token:'old'}}});
  await old;
  assert.equal(app.useChatStore.getState().streaming, true);
  app.useAuthStore.getState().setSession(null);
  pending[1]({data: {session: {access_token:'new'}}});
  await current;
  assert.equal(app.useChatStore.getState().activeThread().messages.length, 0);
});

test('successful sign out immediately clears visible private state and cache', async () => {
  const { app } = harness();
  app.useAuthStore.getState().setSession(session('alice'));
  app.useChatStore.getState().addUserMessage('Private');
  app.queryClient.setQueryData(['profile'], {owner: 'alice'});
  await app.useAuthStore.getState().signOut();
  assert.equal(app.useAuthStore.getState().user, null);
  assert.equal(app.useChatStore.getState().activeThread().messages.length, 0);
  assert.equal(app.queryClient.getQueryData(['profile']), undefined);
});
