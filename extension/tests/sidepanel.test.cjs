const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function harness() {
  const state = { token: 'jpx_' + 'a'.repeat(43), apiBase: 'http://localhost:8000' };
  const calls = [];
  let listener;
  const context = vm.createContext({ URL, Uint8Array, btoa, console, crypto: require('node:crypto').webcrypto, TextEncoder,
    chrome: {
      storage: { local: { get: async () => ({ ...state }), set: async v => Object.assign(state, v) }, session: { get: async () => ({}), set: async () => {} } },
      runtime: { id: 'jd', getURL: f => `chrome-extension://jd/${f}`, onMessage: { addListener: fn => { listener = fn; } } },
    },
    fetch: async (url, options) => { calls.push({ url, options }); return { ok: true, status: 200, headers: { get: () => 'application/json' }, json: async () => ({}) }; },
  });
  context.importScripts = file => vm.runInContext(fs.readFileSync(path.join(__dirname, '..', file), 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../background.js'), 'utf8'), context);
  const send = (message, sender) => new Promise(resolve => listener(message, { id: 'jd', ...sender }, resolve));
  return { calls, send };
}
const panel = { url: 'chrome-extension://jd/sidepanel.html' };
const page = url => ({ url, tab: { id: 1 }, frameId: 0 });

test('the side panel can call its own routes and nothing else', async () => {
  const { calls, send } = harness();
  for (const p of ['/extension/page', '/extension/capture', '/extension/questions', '/extension/answer-set', '/extension/answer-set/approve']) {
    assert.equal((await send({ type: 'api', path: p, method: 'POST', body: {} }, panel)).ok, true, p);
  }
  assert.equal((await send({ type: 'api', path: '/extension/me' }, panel)).ok, true);
  assert.equal(calls.length, 6);
  for (const m of [{ type: 'settings' }, { type: 'api', path: '/extension/queue' }, { type: 'api', path: '/extension/answers', method: 'POST' },
                   { type: 'api', path: '/extension/page', method: 'GET' }, { type: 'connect', token: 'jpx_' + 'b'.repeat(43) }]) {
    assert.equal((await send(m, panel)).ok, false, JSON.stringify(m));
  }
  assert.equal(calls.length, 6);
  assert.equal(calls[0].options.headers['X-JobPilot-Token'].startsWith('jpx_'), true);
});

test('web pages and content scripts cannot reach the side panel routes', async () => {
  const { calls, send } = harness();
  for (const sender of [page('https://jobs.lever.co/acme/1'), page('https://attacker.test'), { url: 'chrome-extension://jd/popup.html' }]) {
    assert.equal((await send({ type: 'api', path: '/extension/answer-set/approve', method: 'POST', body: {} }, sender)).ok, false);
  }
  assert.equal(calls.length, 0);
});

function lib() {
  const context = vm.createContext({});
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../sidepanel-lib.js'), 'utf8'), context);
  return context.JOBDOTS_PANEL;
}

test('questions from several frames keep unique keys', () => {
  const merged = lib().mergeFrames([{ frameId: 0, result: [{ key: 'jp-1', label: 'Name' }] },
                                    { frameId: 3, result: [{ key: 'jp-1', label: 'Why us?' }, { key: 'jp-2', label: '' }] }, null]);
  assert.equal(JSON.stringify(merged.map(f => f.key)), JSON.stringify(['f0:jp-1', 'f3:jp-1']));
});

test('approval sends what you see, marks your edits, and honours "don\'t save"', () => {
  const answers = [{ key: 'a', value: 'Yes' }, { key: 'b', value: 'Draft text' }, { key: 'c', value: null }, { key: 'd', value: ['Python'] }];
  const out = lib().approval(answers, { b: 'My own words', d: 'Python' }, { a: true });
  assert.deepEqual(JSON.parse(JSON.stringify(out)), [
    { key: 'a', value: 'Yes', edited: false, save: false },
    { key: 'b', value: 'My own words', edited: true, save: true },
    { key: 'd', value: ['Python'], edited: false, save: true },
  ]);
});

test('badges and counts are words, not colours', () => {
  const l = lib();
  assert.equal(l.BADGES.needs_you, 'Needs you');
  assert.equal(l.countsLine({ vault: 3, reused: 0, generated: 1, needs_you: 2 }), '3 from your vault, 1 drafted, 2 need you');
});

test('manifest declares the side panel with page access only on request', () => {
  const m = JSON.parse(fs.readFileSync(path.join(__dirname, '../manifest.json'), 'utf8'));
  assert.equal(m.side_panel.default_path, 'sidepanel.html');
  assert.ok(m.permissions.includes('sidePanel'));
  assert.deepEqual(m.optional_host_permissions, ['https://*/*']);
  assert.ok(!m.host_permissions.some(h => h.includes('*://*') || h === 'https://*/*'));
});

test('fill plan: grouped by frame, frame prefix dropped, no consents, no files but the resume, no empty answers', () => {
  const { fillPlan, fillSummary } = lib();
  const answers = [
    { key: 'f0:jp-1', label: 'First name', kind: 'name', value: 'Ada', required: true },
    { key: 'f0:jp-2', label: 'I agree', kind: 'legal', value: 'Yes' },
    { key: 'f0:jp-3', label: 'Cover letter', kind: 'file', value: null },
    { key: 'f0:jp-4', label: 'Resume', kind: 'file', value: '__resume__', flagged: true },
    { key: 'f2:jp-1', label: 'Salary', kind: 'pay', value: '9 LPA', flagged: true },
    { key: 'f2:jp-2', label: 'Why us?', kind: 'open', value: null },
  ];
  const plan = JSON.parse(JSON.stringify(fillPlan(answers, { 'f2:jp-2': 'Your RAG work.' }, {})));
  assert.deepEqual(Object.keys(plan), ['0', '2']);
  assert.deepEqual(plan['0'], [
    { key: 'jp-1', panelKey: 'f0:jp-1', label: 'First name', kind: 'name', value: 'Ada', required: true, flagged: false },
    { key: 'jp-4', panelKey: 'f0:jp-4', label: 'Resume', kind: 'file', value: '__resume__', required: false, flagged: true },
  ]);
  assert.deepEqual(plan['2'].map(a => [a.key, a.value, a.flagged]), [['jp-1', '9 LPA', true], ['jp-2', 'Your RAG work.', false]]);
  assert.equal(fillSummary([{ outcome: 'filled' }, { outcome: 'filled' }, { outcome: 'review' }, { outcome: 'preserved' }]),
    '2 filled, 1 to check, 1 already filled (left as is)');
});

test('queue helpers: caps line in words, and the invitation note limit', () => {
  const { usageLine, noteCount, QUEUE_STATE } = lib();
  assert.equal(usageLine({ invites_today: 2, invites_per_day: 10, invites_this_week: 5, invites_per_week: 40, dms_today: 0, dms_per_day: 10 }),
    'Invitations today: 2 of 10. This week: 5 of 40. Messages today: 0 of 10.');
  assert.deepEqual(JSON.parse(JSON.stringify(noteCount('x'.repeat(201), 'invite'))), { text: '201 of 200 characters', over: true });
  assert.equal(noteCount('x'.repeat(500), 'dm').over, false);
  assert.deepEqual(Object.keys(QUEUE_STATE).sort(), ['approved', 'blocked', 'executing', 'reviewed']);
});
