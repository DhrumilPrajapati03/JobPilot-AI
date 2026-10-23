const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function harness() {
  const state = { token: 'jpx_' + 'a'.repeat(43), apiBase: 'http://localhost:8000' };
  const calls = [];
  let listener;
  const context = vm.createContext({ URL, Uint8Array, btoa, console,
    chrome: {
      storage: {local: {get: async () => ({...state}), set: async (values) => Object.assign(state, values)}},
      runtime: {id: 'jobpilot-id', getURL: (file) => `chrome-extension://jobpilot-id/${file}`, onMessage: {addListener: (fn) => { listener = fn; }}},
    },
    fetch: async (url, options) => {
      calls.push({url, options});
      return { ok: true, status: 200, headers: {get: () => 'application/json'}, json: async () => ({}) };
    },
  });
  context.importScripts = (file) => vm.runInContext(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../background.js'),'utf8'),context);
  const send = (message, sender) => new Promise((resolve) => listener(message, {id:'jobpilot-id', ...sender}, resolve));
  return {state, calls, send};
}
const popup = {url:'chrome-extension://jobpilot-id/popup.html'};
const page = (url) => ({url, tab:{id:1}, frameId:0});

test('an unrelated Render origin or iframe cannot replace the connection', async () => {
  const {state, send} = harness();
  for (const sender of [page('https://untrusted.onrender.com'), {...page('https://jobpilot-web.onrender.com'),frameId:1}]) {
    assert.equal((await send({type:'connect',token:'jpx_'+'b'.repeat(43),apiBase:'http://localhost:8000',appUrl:new URL(sender.url).origin},sender)).ok,false);
    assert.equal(state.token,'jpx_'+'a'.repeat(43));
  }
});

test('approved top-level app can connect; API origin must be exact', async () => {
  const {state,send} = harness();
  const message = {type:'connect', token:'jpx_'+'b'.repeat(43), apiBase:'https://jobpilot-api.onrender.com', appUrl:'https://jobpilot-web.onrender.com'};
  assert.equal((await send(message,page(message.appUrl))).ok,true);
  assert.equal(state.apiBase,message.apiBase);
  assert.equal((await send({...message,apiBase:'https://jobpilot-api.onrender.com.attacker.test'},page(message.appUrl))).ok,false);
});

test('form content scripts cannot read raw credentials', async () => {
  const {send} = harness();
  assert.equal((await send({type:'settings'},page('https://jobs.lever.co/example'))).ok,false);
  assert((await send({type:'settings'},popup)).token.startsWith('jpx_'));
});

test('credentialed requests cannot leave the configured API or extension route allowlist', async () => {
  const {state,calls,send} = harness();
  for (const request of [{path:'/extension/me/../../email/send'}, {path:'/email/send',method:'POST'}, {path:'https://attacker.test'}, {path:'/extension/queue',method:'DELETE'}]) {
    assert.equal((await send({type:'api',...request},popup)).ok,false);
  }
  assert.equal(calls.length,0);
  assert.equal((await send({type:'api',path:'/extension/queue'},popup)).ok,true);
  assert.equal(calls.length,1);
  state.apiBase='https://attacker.test';
  assert.equal((await send({type:'api',path:'/extension/queue'},popup)).ok,false);
  assert.equal((await send({type:'resume',applicationId:'../bad'},popup)).ok,false);
  assert.equal(calls.length,1);
});
