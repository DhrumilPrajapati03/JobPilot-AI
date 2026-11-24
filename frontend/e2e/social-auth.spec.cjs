const {test,expect}=require('@playwright/test');
const {createHash}=require('node:crypto');
const ORIGIN='http://127.0.0.1:5174',AUTH='https://e2e.supabase.test/auth/v1';
const UID='11111111-1111-4111-8111-111111111111';
const user={id:UID,aud:'authenticated',role:'authenticated',email:'social@example.invalid',
 app_metadata:{provider:'google',providers:['google']},user_metadata:{name:'Social Fixture'},created_at:new Date().toISOString()};
const token=()=>Buffer.from('{"alg":"HS256","typ":"JWT"}').toString('base64url')+'.'+Buffer.from(JSON.stringify({sub:UID,email:user.email,aud:'authenticated',iat:Math.floor(Date.now()/1000),exp:Math.floor(Date.now()/1000)+3600})).toString('base64url')+'.c3ludGhldGlj';
const session=()=>({access_token:token(),refresh_token:'synthetic-refresh',expires_in:3600,token_type:'bearer',user});
const headers={'access-control-allow-origin':ORIGIN,'access-control-allow-headers':'*','access-control-allow-methods':'GET,POST,OPTIONS'};

async function fakeAuth(context,{enabled=true}={}){
 const seen={authorize:[],exchanges:[],otp:[]};
 await context.route(AUTH+'/**',async route=>{
  const request=route.request(),url=new URL(request.url());
  if(request.method()==='OPTIONS')return route.fulfill({status:204,headers});
  if(url.pathname.endsWith('/settings'))return route.fulfill({headers,json:{external:{google:enabled,github:enabled,email:true}}});
  if(url.pathname.endsWith('/authorize')){
   seen.authorize.push(url);
   expect(url.searchParams.get('redirect_to')).toBe(ORIGIN+'/login');
   expect(url.searchParams.get('code_challenge_method').toLowerCase()).toBe('s256');
   const callback=ORIGIN+'/login?code=synthetic-'+url.searchParams.get('provider');
   return route.fulfill({contentType:'text/html',body:`<!doctype html><html lang="en"><title>Synthetic provider</title><body><h1>Provider consent fixture</h1><a href="${callback}">Approve synthetic sign-in</a></body></html>`});
  }
  if(url.pathname.endsWith('/token')){
   expect(url.searchParams.get('grant_type')).toBe('pkce');
   const body=request.postDataJSON();seen.exchanges.push(body);
   expect(body.code_verifier.length).toBeGreaterThanOrEqual(43);
   expect(createHash('sha256').update(body.code_verifier).digest('base64url')).toBe(seen.authorize.at(-1).searchParams.get('code_challenge'));
   return route.fulfill({headers,json:session()});
  }
  if(url.pathname.endsWith('/user'))return route.fulfill({headers,json:user});
  if(url.pathname.endsWith('/logout'))return route.fulfill({status:204,headers});
  if(url.pathname.endsWith('/otp')){seen.otp.push({url,body:request.postDataJSON()});return route.fulfill({headers,json:{}});}
  return route.fulfill({status:400,headers,json:{message:'Unexpected synthetic auth request'}});
 });
 return seen;
}

for(const provider of ['google','github'])test(`${provider} completes an SDK PKCE callback and recovers after browser Back`,async({browser})=>{
 const context=await browser.newContext();const seen=await fakeAuth(context);const page=await context.newPage();
 try{
  await page.goto('/login');const button=page.getByRole('button',{name:'Continue with '+(provider==='google'?'Google':'GitHub'),exact:true});
  await button.click();await expect(page.getByRole('heading',{name:'Provider consent fixture'})).toBeVisible();
  await page.goBack();await expect(button).toBeEnabled();await button.click();
  await expect(page.getByRole('heading',{name:'Provider consent fixture'})).toBeVisible();
  const scopes=seen.authorize.at(-1).searchParams.get('scopes');expect(scopes).toBe(provider==='google'?'openid email profile':'user:email');
  await page.getByRole('link',{name:'Approve synthetic sign-in'}).click();
  await page.waitForURL(ORIGIN+'/workspace');await expect(page.getByRole('navigation',{name:'Workspace',exact:true})).toBeVisible();
  expect(seen.exchanges).toHaveLength(1);expect(seen.exchanges[0].auth_code).toBe('synthetic-'+provider);
  expect(new URL(page.url()).search).toBe('');expect(new URL(page.url()).hash).toBe('');
 }finally{await context.close()}
});

test('disabled social providers keep the email fallback on the app, with narrow mobile layout',async({browser})=>{
 const context=await browser.newContext({viewport:{width:390,height:844}});const seen=await fakeAuth(context,{enabled:false});const page=await context.newPage();
 try{
  await page.goto('/login');await page.getByRole('button',{name:'Continue with Google'}).click();
  await expect(page.getByRole('alert')).toContainText('not available yet');expect(page.url()).toBe(ORIGIN+'/login');expect(seen.authorize).toHaveLength(0);
  await expect(page.getByRole('button',{name:'Continue with GitHub'})).toBeEnabled();
  await page.getByLabel('Email address').fill('sample@example.invalid');await page.getByRole('button',{name:'Send Magic Link',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Check your email'})).toBeVisible();
  expect(seen.otp[0].body.code_challenge).toBeTruthy();expect(seen.otp[0].url.searchParams.get('redirect_to')).toBe(ORIGIN+'/login');
  await page.getByRole('button',{name:'Other sign-in options'}).click();
  await expect(page.getByRole('button',{name:'Continue with Google'})).toBeEnabled();await expect(page.getByRole('alert')).toHaveCount(0);
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.evaluate(()=>document.documentElement.dataset.theme='dark');
  await expect(page.getByRole('button',{name:'Continue with GitHub'})).toBeVisible();
 }finally{await context.close()}
});

test('canceled and unverifiable callbacks remove URL data and permit a new sign-in',async({browser})=>{
 const context=await browser.newContext();await fakeAuth(context);const page=await context.newPage();
 try{
  await page.goto('/login#error=access_denied&error_description=PRIVATE_PROVIDER_PAYLOAD');
  await expect(page.getByRole('alert')).toContainText('canceled');await expect(page.locator('body')).not.toContainText('PRIVATE_PROVIDER_PAYLOAD');
  expect(new URL(page.url()).hash).toBe('');await expect(page.getByRole('button',{name:'Continue with Google'})).toBeEnabled();
  await page.goto('/login?code=unusable-code&next=https://evil.invalid');
  await expect(page.getByRole('alert')).toContainText('same browser');expect(new URL(page.url()).searchParams.has('code')).toBe(false);
  expect(new URL(page.url()).origin).toBe(ORIGIN);
 }finally{await context.close()}
});

test('old email links still work; new email and OAuth requests stay PKCE after sign-out',async({browser})=>{
 const context=await browser.newContext();const seen=await fakeAuth(context);const page=await context.newPage();
 try{
  await page.goto('/login#'+new URLSearchParams({access_token:token(),refresh_token:'legacy-refresh',expires_in:'3600',token_type:'bearer',type:'magiclink'}));
  await page.waitForURL(ORIGIN+'/workspace');await page.getByRole('button',{name:'Sign out',exact:true}).click();
  await page.waitForURL(ORIGIN+'/login');await page.getByLabel('Email address').fill('sample@example.invalid');
  await page.getByRole('button',{name:'Send Magic Link',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Check your email'})).toBeVisible();expect(seen.otp[0].body.code_challenge).toBeTruthy();
  await page.getByRole('button',{name:'Other sign-in options'}).click();await page.getByRole('button',{name:'Continue with GitHub'}).click();
  await expect(page.getByRole('heading',{name:'Provider consent fixture'})).toBeVisible();
  expect(seen.authorize[0].searchParams.get('code_challenge')).toBeTruthy();
 }finally{await context.close()}
});
