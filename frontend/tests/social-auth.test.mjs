import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';
import {build} from 'esbuild';

const built=await build({stdin:{contents:`
 export {useAuthStore} from './src/stores/auth-store';
 export {supabase} from './src/lib/supabase';
 export * from './src/lib/auth-redirect';
 export {authErrorMessage} from './src/lib/auth-errors';
 `,resolveDir:process.cwd()},bundle:true,write:false,format:'cjs',platform:'node',
 define:{'process.env.NODE_ENV':'"test"','import.meta.env.VITE_API_BASE_URL':'"http://localhost:8000"',
 'import.meta.env.VITE_WS_BASE_URL':'"ws://localhost:8000"','import.meta.env.VITE_SUPABASE_URL':'"https://example.supabase.co"',
 'import.meta.env.VITE_SUPABASE_ANON_KEY':'"synthetic-public-key"'},
 plugins:[{name:'fake-supabase',setup(b){b.onLoad({filter:/[\\/]lib[\\/]supabase\.ts$/},()=>({contents:`
 export const supabase={auth:{
 initialize:async()=>({error:null}),getSession:async()=>({data:{session:null},error:null}),
 onAuthStateChange:()=>({data:{subscription:{unsubscribe(){}}}}),
 signInWithOAuth:async args=>({data:{url:'https://example.supabase.co/auth/v1/authorize?provider='+args.provider},error:null}),
 signInWithOtp:async()=>({error:null}),setSession:async()=>({error:null}),signOut:async()=>({error:null})}};
 `,loader:'ts'}));}}]});

function harness(href='http://localhost:5173/login'){
 const storage=new Map(),listeners=new Map(),redirects=[],replacements=[];
 const entries={getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)};
 const window={location:{href,origin:new URL(href).origin,assign:url=>redirects.push(url)},
 history:{state:{},replaceState:(_state,_title,url)=>replacements.push(url)},
 addEventListener:(name,fn)=>listeners.set(name,fn),removeEventListener:name=>listeners.delete(name)};
 const module={exports:{}};
 vm.runInNewContext(built.outputFiles[0].text,{module,exports:module.exports,console,crypto:webcrypto,localStorage:entries,sessionStorage:entries,
 setTimeout,clearTimeout,AbortController,AbortSignal,TextDecoder,URL,URLSearchParams,window,
 fetch:async()=>({ok:true,json:async()=>({external:{google:true,github:true}})})});
 return {app:module.exports,window,listeners,redirects,replacements};
}

for(const provider of ['google','github'])test(`${provider} uses a fixed callback, minimum scopes and a pending redirect until browser return`,async()=>{
 const {app,listeners,redirects}=harness();await app.useAuthStore.getState().initialize();const calls=[];
 app.supabase.auth.signInWithOAuth=async args=>{calls.push(args);return {data:{url:'https://example.supabase.co/auth/v1/authorize'},error:null}};
 await app.useAuthStore.getState().signInWithProvider(provider);
 assert.equal(calls[0].provider,provider);assert.equal(calls[0].options.redirectTo,'http://localhost:5173/login');
 assert.equal(calls[0].options.skipBrowserRedirect,true);
 assert.equal(calls[0].options.scopes,provider==='google'?'openid email profile':'user:email');
 assert.equal(redirects.length,1);assert.equal(app.useAuthStore.getState().activeProvider,provider);
 assert.equal(app.useAuthStore.getState().loading,true);
 await assert.rejects(app.useAuthStore.getState().signInWithProvider(provider),/already in progress/);
 listeners.get('pageshow')({persisted:true});assert.equal(app.useAuthStore.getState().loading,false);
 assert.equal(app.useAuthStore.getState().activeProvider,null);
});

test('provider failure stays actionable without echoing upstream payloads',async()=>{
 const {app,redirects}=harness();await app.useAuthStore.getState().initialize();
 app.supabase.auth.signInWithOAuth=async()=>({data:{url:null},error:{message:'PRIVATE_TOKEN <script>alert(1)</script>'}});
 await assert.rejects(app.useAuthStore.getState().signInWithProvider('github'),/could not complete/);
 assert.equal(redirects.length,0);assert.equal(app.useAuthStore.getState().loading,false);
 assert.doesNotMatch(app.useAuthStore.getState().error,/PRIVATE|script/);
});

test('callback cancellation removes credentials and raw errors while retaining unrelated query parameters',async()=>{
 const {app,replacements}=harness('http://localhost:5173/login?next=https://evil.invalid&code=secret#error=access_denied&error_description=PRIVATE_TOKEN');
 app.supabase.auth.initialize=async()=>({error:{details:{error:'access_denied',code:'unspecified_code'}}});
 await app.useAuthStore.getState().initialize();
 assert.match(app.useAuthStore.getState().error,/canceled/);assert.equal(app.useAuthStore.getState().initialized,true);
 assert.equal(replacements[0],'/login?next=https%3A%2F%2Fevil.invalid');
 assert.equal(app.authReturnUrl('https://app.example.invalid'),'https://app.example.invalid/login');
});

test('missing verifier callback offers a fresh attempt, not a fabricated session',async()=>{
 const {app,replacements}=harness('http://localhost:5173/login?code=missing-verifier');
 await app.useAuthStore.getState().initialize();
 assert.match(app.useAuthStore.getState().error,/same browser/);assert.equal(app.useAuthStore.getState().session,null);
 assert.equal(replacements[0],'/login');
});

test('legacy tokens are consumed once through SDK without changing subsequent sign-in behavior',async()=>{
 const {app}=harness('http://localhost:5173/login#access_token=legacy-access&refresh_token=legacy-refresh&type=magiclink');
 const calls=[];app.supabase.auth.setSession=async tokens=>{calls.push(tokens);return {error:null}};
 await app.useAuthStore.getState().initialize();assert.equal(calls.length,1);assert.equal(calls[0].access_token,'legacy-access');
 assert.equal(app.legacySessionFromUrl('http://localhost/login#access_token=a&refresh_token=b&error=access_denied'),null);
});

test('magic-link initiation remains available and returns to the same sign-in page',async()=>{
 const {app}=harness();await app.useAuthStore.getState().initialize();const calls=[];
 app.supabase.auth.signInWithOtp=async args=>{calls.push(args);return {error:null}};
 await app.useAuthStore.getState().signIn('  sample@example.invalid  ');
 assert.equal(calls[0].email,'sample@example.invalid');assert.equal(calls[0].options.emailRedirectTo,'http://localhost:5173/login');
 assert.equal(app.useAuthStore.getState().loading,false);
});

test('concurrent startup shares one legacy callback consumption',async()=>{
 const {app}=harness('http://localhost:5173/login#access_token=legacy-access&refresh_token=legacy-refresh&type=magiclink');
 let calls=0;app.supabase.auth.setSession=async()=>{calls++;return {error:null}};
 await Promise.all([app.useAuthStore.getState().initialize(),app.useAuthStore.getState().initialize()]);
 assert.equal(calls,1);assert.equal(app.useAuthStore.getState().initialized,true);
});
