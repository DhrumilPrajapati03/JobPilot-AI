const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function harness(fetchImpl) {
  const state = { token: 'jpx_' + 'a'.repeat(43), apiBase: 'http://localhost:8000' };
  const calls = [];
  const sessions = {};
  let listener;
  const context = vm.createContext({ URL, Uint8Array, btoa, console, crypto:require('node:crypto').webcrypto,TextEncoder,
    chrome: {
      storage: {local: {get: async () => ({...state}), set: async (values) => Object.assign(state, values)},session:{get:async key=>({[key]:sessions[key]}),set:async values=>Object.assign(sessions,values)}},
      runtime: {id: 'jobpilot-id', getURL: (file) => `chrome-extension://jobpilot-id/${file}`, onMessage: {addListener: (fn) => { listener = fn; }}},
    },
    fetch: async (url, options) => {
      calls.push({url, options});
      if(fetchImpl) return fetchImpl(url,options);
      return { ok: true, status: 200, headers: {get: () => 'application/json'}, json: async () => ({}) };
    },
  });
  context.importScripts = (file) => vm.runInContext(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../background.js'),'utf8'),context);
  const send = (message, sender) => new Promise((resolve) => listener(message, {id:'jobpilot-id', ...sender}, resolve));
  return {state, calls, send, sessions};
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

const sid='28829a2c-f48e-49fb-a48f-c16e8604dce5';
const appid='4cd3e5c4-815c-48c9-97ce-538d020c8170';
const response=data=>({ok:true,status:200,headers:{get:()=> 'application/json'},json:async()=>data});
async function connectSession(h) {
  return h.send({type:'api',method:'POST',path:'/extension/sessions',body:{id:sid,application_id:appid,url:'https://attacker.test/forged'}},page('https://jobs.lever.co/example/role/apply'));
}
const sessionResponse={session:{id:sid,application_id:appid,expires_at:new Date(Date.now()+86400000).toISOString()}};

test('sessions bind to sender URL, tab, frame and current account; document scope cannot be forged',async()=>{
  const h=harness(async()=>response(sessionResponse));
  assert.equal((await connectSession(h)).ok,true);
  assert.equal(JSON.parse(h.calls[0].options.body).url,'https://jobs.lever.co/example/role/apply');
  assert.equal((await h.send({type:'execution-context'},page('https://jobs.lever.co/example/role/apply'))).ok,true);
  for(const sender of [{...page('https://jobs.lever.co/example/role/apply'),tab:{id:2}},{...page('https://jobs.lever.co/example/role/apply'),frameId:1},page('https://evil.test')]) {
    assert.equal((await h.send({type:'execution-context'},sender)).ok,false);
  }
  assert.equal((await h.send({type:'api',path:'/extension/document',method:'POST',body:{session_id:'other'}},page('https://jobs.lever.co/example/role/apply'))).ok,false);
  h.state.token='jpx_'+'b'.repeat(43);
  assert.equal((await h.send({type:'execution-context'},page('https://jobs.lever.co/example/role/apply'))).ok,false);
});

test('lost event acknowledgement replays the same key and preserves attempt across navigation',async()=>{
  let fail=true;
  const h=harness(async(url)=>{if(url.endsWith('/events') && fail){fail=false;throw Error('Lost acknowledgement');}return response(sessionResponse);});
  await connectSession(h);
  const request_key='07bd027e-38f3-4262-a440-45af2115ba1a';
  const event={session_id:sid,request_key,kind:'submission_attempted',details:{url:'https://attacker.test'}};
  assert.equal((await h.send({type:'execution-event',body:event},page('https://jobs.lever.co/example/role/apply'))).ok,false);
  const restored=await h.send({type:'execution-context'},page('https://jobs.lever.co/example/role/thanks'));
  assert.equal(restored.ok,true);assert.equal(restored.context.attempt.key,request_key);
  const requests=h.calls.filter(c=>c.url.endsWith('/events')).map(c=>JSON.parse(c.options.body));
  assert.equal(requests.length,2);assert.equal(requests[0].request_key,requests[1].request_key);
  assert.equal(requests[0].details.url,'https://jobs.lever.co/example/role/apply');
  assert.equal((await h.send({type:'api',method:'POST',path:'/extension/events',body:event},page('https://jobs.lever.co/example/role/apply'))).ok,false);
});

test('an in-flight response from an old account is discarded after reconnection',async()=>{
  let finish;const pending=new Promise(resolve=>{finish=resolve;});
  const h=harness(async()=>{await pending;return response({private:'old-account'});});
  const result=h.send({type:'api',path:'/extension/queue'},page('https://jobs.lever.co/example/role'));
  await new Promise(resolve=>setImmediate(resolve));h.state.token='jpx_'+'b'.repeat(43);finish();
  const r=await result;assert.equal(r.ok,false);assert.equal(r.status,409);assert.equal(r.data.private,undefined);
});
