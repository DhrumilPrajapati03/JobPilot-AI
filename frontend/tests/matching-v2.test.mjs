import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { build } from 'esbuild';

const built = await build({
  stdin: { contents: `
    import React from 'react';
    import {renderToStaticMarkup} from 'react-dom/server';
    import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
    import {FactsPanel} from './src/components/profile/FactsPanel';
    import {MatchExplanation} from './src/components/discovery/MatchExplanation';
    export function facts(vault) {
      const client=new QueryClient(); client.setQueryData(['identity-facts'],vault);
      return renderToStaticMarkup(React.createElement(QueryClientProvider,{client},React.createElement(FactsPanel)));
    }
    export const explanation=details=>renderToStaticMarkup(React.createElement(MatchExplanation,{details}));
  `, resolveDir: process.cwd() },
  bundle:true, write:false, format:'cjs', platform:'node',
  external:['react','react-dom/server','@tanstack/react-query'],
  plugins:[{name:'offline-api',setup(b){b.onLoad({filter:/[\\/]lib[\\/]api\.ts$/},()=>({contents:'export default {get:()=>{throw Error("Unexpected request")}};'}));}}],
});
const module={exports:{}};
vm.runInNewContext(built.outputFiles[0].text,{module,exports:module.exports,require:createRequire(import.meta.url),console,process});
const app=module.exports;

test('fact review starts unconfirmed and renders source text safely',()=>{
  const html=app.facts({source_digest:'snapshot',confirmed_count:0,total:1,complete:false,
    facts:[{id:'fact',kind:'skill',source_path:'skills.primary.0',value:'Python <script>bad()</script>',confirmed:false}]});
  assert.match(html,/Needs your review/);
  assert.match(html,/0 of 1 facts confirmed by you/);
  assert.match(html,/not an independent credential check/);
  assert.match(html,/&lt;script&gt;/);
  assert.doesNotMatch(html,/<script>/);
  assert.match(html,/I confirm 0 selected facts are accurate/);
});

test('confirmed facts provide revocation and still identify user attestation',()=>{
  const html=app.facts({source_digest:'snapshot',confirmed_count:1,total:1,complete:true,
    facts:[{id:'fact',kind:'education',value:{institution:'College',degree:'BSc',year:'2026'},confirmed:true}]});
  assert.match(html,/Confirmed by you/);
  assert.match(html,/Revoke/);
  assert.match(html,/College/);
});

test('a match explanation shows evidence and an explicit semantic fallback',()=>{
  const html=app.explanation({version:'matching-v2',components:{title:90,skills:80,semantic:null},identity:{complete:false},
    reasons:['Python appears in the source resume'],eligibility:{status:'review',checks:[{dimension:'authorization',reason:'Confirm work authorization',evidence:'Must be authorized in India'}]}});
  assert.match(html,/Eligibility needs review/);
  assert.match(html,/Not used/);
  assert.match(html,/not a hiring probability/);
  assert.match(html,/Automatic drafting waits/);
  assert.match(html,/Must be authorized in India/);
});
