import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import {build} from 'esbuild';
const built=await build({stdin:{contents:`import React from 'react'; import {renderToStaticMarkup} from 'react-dom/server'; import {EvidenceView} from './src/components/applications/ExecutionEvidence'; export const view=data=>renderToStaticMarkup(React.createElement(EvidenceView,{data}));`,resolveDir:process.cwd()},bundle:true,write:false,format:'cjs',platform:'node',external:['react','react-dom/server','@tanstack/react-query'],plugins:[{name:'offline',setup(b){b.onLoad({filter:/[\\/]lib[\\/]api\.ts$/},()=>({contents:'export default {};'}));}}]});
const module={exports:{}};vm.runInNewContext(built.outputFiles[0].text,{module,exports:module.exports,require:createRequire(import.meta.url),console,process});
const history={sessions:[{id:'session',document_id:'doc'}],documents:[{id:'doc',name:'<script>resume</script>',sha256:'a'.repeat(64),resume_version:2,size_bytes:100}],events:[]};
const event=(kind,details={})=>({id:1,session_id:'session',kind,created_at:'2026-10-28T12:00:00Z',details});
test('preparation accuracy does not imply submission or employer upload acceptance',()=>{
  const html=module.exports.view({...history,events:[event('form_prepared',{summary:{filled:2,preserved:1,review:1,required_missing:1,total:5},document_sha256:'a'.repeat(64)})]});
  assert.match(html,/2 filled and checked; 1 preserved/);assert.match(html,/upload acceptance unverified/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
});
test('attempt, browser confirmation and user report have distinct honest labels',()=>{
  for(const [kind,label] of [['submission_attempted','Submission attempt observed'],['submission_confirmation_observed','Browser confirmation observed'],['user_reported_submitted','User reported submitted']]) {
    const html=module.exports.view({...history,events:[event(kind)]});assert.match(html,new RegExp(label));assert.doesNotMatch(html,/Submission verified|Employer confirmed/);
    if(kind!=='submission_attempted')assert.match(html,/not independently verified/);
  }
});
test('missing history does not manufacture submission evidence from legacy status',()=>{
  const html=module.exports.view(history);assert.match(html,/No submission evidence recorded/);assert.match(html,/manually reported/);
});
