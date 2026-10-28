import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { build } from 'esbuild';

const built = await build({
  stdin: { contents: `export {resolveRun} from './src/lib/run-poll'; export {useAgentStream} from './src/hooks/use-agent-stream';`, resolveDir: process.cwd() },
  bundle: true, write: false, format: 'cjs', platform: 'node',
  define: { 'import.meta.env.VITE_API_BASE_URL': '"http://localhost:8000"', 'import.meta.env.VITE_WS_BASE_URL': '"ws://localhost:8000"' },
  plugins: [{ name: 'offline-boundaries', setup(b) {
    b.onResolve({ filter: /^react$/ }, () => ({ path: 'react', namespace: 'test' }));
    b.onLoad({ filter: /.*/, namespace: 'test' }, () => ({ contents: `
      let i=0;
      export const useState=(initial)=>{ const n=i++; globalThis.states[n]=typeof initial==='function'?initial():initial;
        return [globalThis.states[n], value=>{globalThis.states[n]=typeof value==='function'?value(globalThis.states[n]):value}]; };
      export const useRef=(current)=>({current}); export const useCallback=(fn)=>fn; export const useEffect=()=>{};
    ` }));
    b.onLoad({ filter: /[\\/]lib[\\/]api\.ts$/ }, () => ({ contents: 'export default {get:(path)=>globalThis.getStatus(path)};' }));
    b.onLoad({ filter: /[\\/]lib[\\/]constants\.ts$/ }, () => ({ contents: 'export const WS_BASE_URL="ws://localhost:8000";' }));
    b.onLoad({ filter: /[\\/]stores[\\/]auth-store\.ts$/ }, () => ({ contents: 'export const useAuthStore={getState:()=>({user:{id:globalThis.account}})};' }));
    b.onLoad({ filter: /[\\/]lib[\\/]supabase\.ts$/ }, () => ({ contents: 'export const supabase={auth:{getSession:async()=>({data:{session:{access_token:"token"}}})}};' }));
  }}],
});

function harness() {
  const context = { module: { exports: {} }, account: 'alice', states: [], sockets: [], console,
    getStatus: async () => ({ status: 'succeeded', result: { to: 'alice@example.invalid' } }),
    window: { setTimeout: (fn) => {fn(); return 1;}, clearTimeout: () => {} },
  };
  context.WebSocket = class {
    static OPEN=1;
    readyState=1;
    constructor() {context.sockets.push(this);}
    close() {this.closed=true;}
  };
  vm.runInNewContext(built.outputFiles[0].text, context);
  return {...context.module.exports, context};
}

test('queued mutations wait through retry state and return only the committed result', async () => {
  const {resolveRun, context} = harness();
  let calls=0;
  context.getStatus=async()=>++calls===1?{status:'retry_wait'}:{status:'succeeded',result:{new:7}};
  const result=await resolveRun({status:'queued',run_id:'run'});
  assert.equal(result.new,7);
  assert.equal(calls,2);
  assert.equal(await resolveRun('inline-result'),'inline-result');
});

test('a repeated request already running is still polled; worker errors are not success', async () => {
  const {resolveRun, context}=harness();
  context.getStatus=async()=>({status:'failed',last_error:'Base resume missing'});
  await assert.rejects(resolveRun({status:'running',run_id:'run'}),/Base resume missing/);
});

test('account changes reject an old background result', async () => {
  const {resolveRun, context}=harness();
  context.getStatus=async()=>{context.account='bob'; return {status:'succeeded',result:{private:'Alice'}};};
  await assert.rejects(resolveRun({status:'queued',run_id:'run'}),/Account changed/);
});

test('queue and retry events do not falsely complete pipeline steps; global failures stop the stream', () => {
  const {useAgentStream,context}=harness();
  useAgentStream({persist:false}).start('run');
  const socket=context.sockets[0];
  const emit=(step,status,message)=>socket.onmessage({data:JSON.stringify({type:'status',step,status,message})});
  emit('queued','running','Waiting for worker');
  assert.ok(Object.values(context.states[0]).every(s=>s.state==='idle'));
  emit('execution','warning','Retrying from checkpoint');
  assert.equal(context.states[1],'running');
  assert.equal(context.states[5],'Retrying from checkpoint');
  emit('pdf_rendering','warning','Use browser export');
  emit('complete','success','Done');
  assert.equal(context.states[0].pdf_rendering.state,'warning');
  assert.equal(context.states[1],'success');
});

test('worker exhaustion errors are visible even without a matching pipeline step', () => {
  const {useAgentStream,context}=harness();
  useAgentStream({persist:false}).start('run');
  context.sockets[0].onmessage({data:JSON.stringify({type:'status',step:'execution',status:'error',message:'Recovery limit reached'})});
  assert.equal(context.states[1],'error');
  assert.equal(context.states[2],'Recovery limit reached');
  assert.ok(context.sockets[0].closed);
});
