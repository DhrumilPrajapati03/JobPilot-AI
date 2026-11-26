import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { build } from 'esbuild';

// The identity/state mapping only (pure data); the canvas itself is the library's.
const built = await build({ stdin: { contents: "export * from './src/components/experts/presence';", resolveDir: process.cwd(), loader: 'ts' },
  bundle: true, write: false, format: 'cjs', platform: 'node' });
const mod = { exports: {} };
vm.runInNewContext(built.outputFiles[0].text, { module: mod, exports: mod.exports });
const p = mod.exports;

const ROSTER = ['supervisor', 'scout', 'researcher', 'comp_analyst', 'tailor', 'answerer', 'applicant', 'recon',
  'connector', 'email_outreach', 'dm_outreach', 'inbox', 'interview_buddy', 'reviewer'];
const STATES = ['idle', 'acknowledged', 'working', 'waiting_approval', 'needs_hand_off', 'blocked', 'failed', 'done', 'paused', 'draft'];
const LIBRARY_TYPES = ['clover', 'flower', 'triangle', 'square', 'blob', 'ghost', 'circle', 'drop', 'star', 'droid', 'mech',
  'alien', 'hexagon', 'cat', 'cloud', 'pill', 'pebble', 'puddle'];

test('every built-in expert has its own body shape from the library', () => {
  const types = ROSTER.map(id => p.identityFor(id).type);
  assert.equal(new Set(types).size, ROSTER.length);
  assert.ok(types.every(t => LIBRARY_TYPES.includes(t)));
});

test('custom experts get a spare shape no built-in uses, stable per id', () => {
  const builtIn = new Set(ROSTER.map(id => p.identityFor(id).type));
  const custom = p.identityFor('referral_hunter');
  assert.ok(!builtIn.has(custom.type) && LIBRARY_TYPES.includes(custom.type));
  assert.equal(p.identityFor('referral_hunter').type, custom.type);
});

test('every expert state maps to a library motion; non-animated states carry words, not colour alone', () => {
  for (const state of STATES) {
    const presence = p.presenceFor(state);
    assert.ok(['default', 'working', 'sleeping'].includes(presence.motion), state);
    assert.ok(presence.label.length > 3, state);
    if (!['idle', 'working', 'paused', 'draft'].includes(state)) assert.ok(presence.badge && presence.icon, state);
  }
  assert.equal(p.presenceFor('working').motion, 'working');
  assert.equal(p.presenceFor('paused').motion, 'sleeping');
  assert.equal(p.presenceFor('something-new').label, 'Idle');
});

test('seeds spread a row so avatars do not blink in unison', () => {
  const seeds = ROSTER.map(p.seedFor);
  assert.ok(seeds.every(s => s >= 0 && s < 1));
  assert.ok(new Set(seeds.map(s => s.toFixed(2))).size >= ROSTER.length - 2);
});
