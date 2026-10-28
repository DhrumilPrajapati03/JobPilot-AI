import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import {build} from 'esbuild';

const built=await build({
  stdin:{contents:`
    import React from 'react'; import {renderToStaticMarkup} from 'react-dom/server';
    import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
    import {MessageCard} from './src/components/email/MailOutreach';
    export {downloadMailAttachment} from './src/hooks/use-mailbox';
    export function render(message, email='owner@example.invalid') {
      const client=new QueryClient();
      client.setQueryData(['mailbox','connection'],{configured:true,send_enabled:true,connection:{id:'connection',email}});
      client.setQueryData(['mailbox','replies',message.id],{replies:[]});
      return renderToStaticMarkup(React.createElement(QueryClientProvider,{client},React.createElement(MessageCard,{message})));
    }
  `,resolveDir:process.cwd()}, bundle:true,write:false,format:'cjs',platform:'node',
  external:['react','react-dom/server','@tanstack/react-query'],
  plugins:[{name:'offline-mail',setup(b){
    b.onLoad({filter:/[\\/]lib[\\/]api\.ts$/},()=>({contents:'export default {get:()=>{throw Error("Unexpected request")}};'}));
    b.onLoad({filter:/[\\/]lib[\\/]constants\.ts$/},()=>({contents:'export const API_URL="http://localhost:8000/api/v1";'}));
    b.onLoad({filter:/[\\/]lib[\\/]supabase\.ts$/},()=>({contents:'export const supabase={auth:{getSession:async()=>({data:{session:null}})}};'}));
    b.onLoad({filter:/[\\/]stores[\\/]auth-store\.ts$/},()=>({contents:'export const useAuthStore={getState:()=>({user:{id:globalThis.currentAccount || "owner"}})};'}));
  }}],
});
const module={exports:{}};
let downloads=0;
const context={module,exports:module.exports,require:createRequire(import.meta.url),console,process,currentAccount:'owner',
  fetch:async()=>({ok:true,blob:async()=>{context.currentAccount='different-owner';return {};}}),
  URL:{createObjectURL:()=>{downloads++;return 'blob:private';},revokeObjectURL:()=>{}},
  document:{createElement:()=>({click:()=>{downloads++;}})},window:{setTimeout:()=>{}}};
vm.runInNewContext(built.outputFiles[0].text,context);
const render=module.exports.render;
const message={id:'email',application_id:'app',revision:1,to_email:'recruiter@example.invalid',subject:'<script>untrusted</script>',body:'Reviewed text',state:'draft',connection_id:'connection',from_email:'owner@example.invalid',attachment:null,delivery_status:'unknown'};

test('a draft exposes review but cannot be mistaken for a sent message',()=>{
  const html=render(message);
  assert.match(html,/Draft — not sent/); assert.match(html,/Approve this recipient, email and attachment/);
  assert.doesNotMatch(html,/Send approved email from Gmail/); assert.doesNotMatch(html,/<script>/);
});
test('approval exposes a separate send action and can be revoked',()=>{
  const html=render({...message,state:'approved'});
  assert.match(html,/Approved — not sent/); assert.match(html,/Send approved email from Gmail/); assert.match(html,/Revoke approval/);
});
test('the approved sender remains visible and a changed account disables sending',()=>{
  const html=render({...message,state:'approved'},'changed@example.invalid');
  assert.match(html,/From: owner@example.invalid/);
  assert.match(html,/<button[^>]*disabled=""[^>]*>Send approved email from Gmail/);
});
test('uncertain sends offer reconciliation and no send action',()=>{
  const html=render({...message,state:'send_unknown'});
  assert.match(html,/no automatic resend/); assert.match(html,/Synchronize status and replies/);
  assert.doesNotMatch(html,/Send approved email from Gmail/); assert.doesNotMatch(html,/Approve this recipient/);
});
test('provider acceptance is distinguished from recipient delivery and read status',()=>{
  const html=render({...message,state:'sent',provider_message_id:'receipt'});
  assert.match(html,/Gmail accepted/); assert.match(html,/Recipient delivery and read status are unknown/);
  assert.match(html,/No correlated reply observed yet/);
});
test('an account change during a private PDF request never triggers its download',async()=>{
  await assert.rejects(module.exports.downloadMailAttachment('email'),/Account changed during/);
  assert.equal(downloads,0);
});
