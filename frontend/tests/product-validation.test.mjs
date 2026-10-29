import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import {build} from 'esbuild';
const result=await build({stdin:{contents:`import React from 'react';import {renderToStaticMarkup} from 'react-dom/server';import {MemoryRouter} from 'react-router-dom';import {Checklist} from './src/components/profile/OnboardingPanel';import {OutcomesView} from './src/components/applications/ProductMetrics';export const checklist=data=>renderToStaticMarkup(React.createElement(MemoryRouter,null,React.createElement(Checklist,{data})));export const outcomes=data=>renderToStaticMarkup(React.createElement(OutcomesView,{data}));`,resolveDir:process.cwd()},bundle:true,write:false,format:'cjs',platform:'node',external:['react','react-dom/server','react-router-dom','@tanstack/react-query'],plugins:[{name:'offline',setup(b){b.onLoad({filter:/[\\/]lib[\\/]api\.ts$/},()=>({contents:'export default {};'}));b.onLoad({filter:/[\\/]stores[\\/]auth-store\.ts$/},()=>({contents:'export const useAuthStore=()=>({});'}));}}]});
const module={exports:{}};vm.runInNewContext(result.outputFiles[0].text,{module,exports:module.exports,require:createRequire(import.meta.url),console,process});
const app=module.exports;
test('onboarding shows incomplete saved facts and clear next steps without requiring Gmail',()=>{
 const html=app.checklist({ready_for_matching:false,confirmed_facts:0,total_facts:3,steps:[{id:'facts',title:'Review saved facts',href:'/profile?tab=facts',done:false,required:true}],note:'Gmail is optional.'});
 assert.match(html,/Finish your matching setup/);assert.match(html,/0 of 3 facts/);assert.match(html,/Gmail is optional/);assert.match(html,/To do/);assert.doesNotMatch(html,/profile is ready/);
});
test('completed onboarding identifies user confirmation without claiming external verification',()=>{
 const html=app.checklist({ready_for_matching:true,confirmed_facts:3,total_facts:3,steps:[],note:'Facts are confirmed by you.'});
 assert.match(html,/ready for matching/);assert.match(html,/confirmed by you/);assert.doesNotMatch(html,/credentials verified/);
});
test('unknown denominators, costs and independent verification remain unmeasured',()=>{
 const html=app.outcomes({generated_applications:0,prepared_applications:0,attempted_applications:0,browser_observed_applications:0,user_reported_applications:0,
  preparation:{inspected_fields:0,review_fields:0,invalid_fields:0,truncated_applications:0,median_seconds:null,p95_seconds:null,time_samples:0,completion_rate:null},
  gmail:{accepted_messages:0,correlated_replied_messages:0,reviewed_human_replied_messages:0,reviewed_human_reply_rate:null,bounce_observed_messages:0,unknown_outcomes:0},runs:{failed:0,recovered:0,pending:0},stage_timings:[],measurement_note:'Gmail acceptance is not delivery.'});
 assert.match(html,/no accepted-message denominator/);assert.match(html,/not answer correctness/);assert.match(html,/not instrumented/);assert.match(html,/acceptance is not delivery/);assert.doesNotMatch(html,/100%|NaN|Infinity/);
});

test('a résumé upload cannot use a different account token after asynchronous session lookup',async()=>{
 const built=await build({stdin:{contents:`export {default as api} from './src/lib/api';`,resolveDir:process.cwd()},bundle:true,write:false,format:'cjs',platform:'node',
 plugins:[{name:'session',setup(b){b.onLoad({filter:/[\\/]lib[\\/]supabase\.ts$/},()=>({contents:'export const supabase={auth:{getSession:()=>globalThis.getSession()}};'}));b.onLoad({filter:/[\\/]lib[\\/]constants\.ts$/},()=>({contents:'export const API_URL="http://localhost:8000/api/v1";'}));}}]});
 const loaded={exports:{}};let calls=0;
 vm.runInNewContext(built.outputFiles[0].text,{module:loaded,exports:loaded.exports,fetch:()=>{calls++;},getSession:async()=>({data:{session:{user:{id:'bob'},access_token:'bob-token'}}}),FormData:class{append(){}}});
 await assert.rejects(()=>loaded.exports.api.upload('/resume/upload',{},'file','alice'),/Account changed/);
 assert.equal(calls,0);
});
