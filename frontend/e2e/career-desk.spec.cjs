const {test,expect}=require('@playwright/test');
const fs=require('node:fs');
const path=require('node:path');
const UID='33333333-3333-4333-8333-333333333333';
const token=()=>Buffer.from('{"alg":"HS256","typ":"JWT"}').toString('base64url')+'.'+Buffer.from(JSON.stringify({sub:UID,email:'design@example.invalid',exp:Math.floor(Date.now()/1000)+3600})).toString('base64url')+'.c3ludGhldGlj';
const now=new Date().toISOString();
const jobs=[['Orbit Studio','AI Application Engineer',92,true],['Forma Systems','Machine Learning Engineer',86,false]].map(([company,title,fit_score,remote],i)=>({id:`44444444-4444-4444-8444-44444444444${i}`,source_id:'55555555-5555-4555-8555-555555555555',ats:'greenhouse',external_id:`design-${i}`,company,title,fit_score,remote,location:remote?'Remote, India':'Pune, India',url:'https://example.invalid/careers',posted_at:now,title_match:1,matched_skills:['Python','FastAPI'],missing_skills:['Kubernetes'],skip_flags:[],status:'new',application_id:null,auto_drafted:false,drafted_at:null,closed_at:null,discovered_at:now,matching_details:{version:'v2',components:{title:100,skills:80,semantic:null},identity:{complete:true,confirmed_count:3,total:3},reasons:['Python appears in the confirmed profile'],confirmed_matched_skills:['Python']}}));
const briefing={generated_at:now,sources:1,last_scan_at:now,stale:false,server_scans:false,min_match_score:70,new_matches:2,open_matches:2,top_matches:jobs,drafts:[{...jobs[0],status:'drafting'}],follow_ups_due:[],auto_draft:{enabled:false,min_score:80,daily_cap:3,remaining_today:3}};
const summary={total_applications:0,status_breakdown:{saved:0,applied:0,interviewing:0,offer:0,rejected:0,archived:0},submitted:0,response_rate:0,interview_rate:0,offer_rate:0,emails_sent:0,email_reply_rate:0,avg_keyword_score:null,pending_follow_ups:0,follow_ups_due:[],weekly_applications:[],recent_activity:[]};
async function setup(context){
  const user={id:UID,email:'design@example.invalid',aud:'authenticated',role:'authenticated',app_metadata:{},user_metadata:{name:'Alex Example'},created_at:now};
  await context.addInitScript(({user,access_token})=>{localStorage.setItem('sb-e2e-auth-token',JSON.stringify({access_token,refresh_token:'synthetic-refresh',expires_at:Math.floor(Date.now()/1000)+3600,expires_in:3600,token_type:'bearer',user}));localStorage.setItem('jobpilot-theme','light');},{user,access_token:token()});
  await context.route('https://e2e.supabase.test/**',r=>r.fulfill({contentType:'application/json',body:JSON.stringify(user)}));
  await context.route('**/api/v1/discovery/**',r=>{
    const url=new URL(r.request().url());let body=briefing;
    if(url.pathname.endsWith('/sources'))body={sources:[{id:'55555555-5555-4555-8555-555555555555',ats:'greenhouse',slug:'orbit',company:'Orbit Studio',enabled:true,job_count:2,last_scanned_at:now,last_error:null}],suggestions:[],server_scans:false};
    if(url.pathname.endsWith('/postings')){const tab=url.searchParams.get('status');body={postings:tab==='new'?jobs:[],total:tab==='new'?2:0,counts:{new:2,drafted:0,skipped:0,dismissed:0}};}
    return r.fulfill({contentType:'application/json',body:JSON.stringify(body)});
  });
  await context.route('**/api/v1/analytics/summary',r=>r.fulfill({contentType:'application/json',body:JSON.stringify(summary)}));
  await context.route('**/api/v1/runs',r=>r.fulfill({json:{mode:'durable',runs:[]}}));
  await context.route('**/api/v1/resume/base',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({id:'66666666-6666-4666-8666-666666666666',name:'Alex Example',headline:'Engineer',summary:'Builds Python applications.',experience:[],skills:{primary:['Python'],secondary:[]},projects:[],education:[],certifications:[]})}));
}
const output=path.resolve(__dirname,'../../.tool-cache/design-review');
async function snapshot(page,name){fs.mkdirSync(output,{recursive:true});await page.screenshot({path:path.join(output,`${name}.png`),fullPage:!name.startsWith('landing')});}
async function exportDraft(page,name,selector){
  const html=await page.evaluate(({selector})=>{
    const source=document.querySelector(selector);if(!source)throw new Error('Design root missing');
    const root=source.cloneNode(true);
    root.querySelectorAll('a').forEach((a,i)=>{a.id=`preview-link-${i}`;a.setAttribute('href',`#preview-link-${i}`)});
    root.querySelectorAll('script').forEach(e=>e.remove());
    const styles=Array.from(document.querySelectorAll('style')).map(e=>e.textContent).join('\n');
    return '<!DOCTYPE html><html lang="en" data-theme="light"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>JobPilot — Design review</title><style>'+styles+'\n[data-reveal]{opacity:1!important;transform:none!important}body{margin:0}</style></head><body>'+root.outerHTML+'</body></html>';
  },{selector});
  const target=path.resolve(__dirname,'../../.superdesign/tmp');fs.mkdirSync(target,{recursive:true});fs.writeFileSync(path.join(target,`${name}.html`),html);
}

test('public workflow is honest, interactive and responsive; magic-link errors stay readable',async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce',colorScheme:'light'});
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'Your next role. A coordinated effort.'})).toBeVisible();
  const map=page.getByRole('region',{name:'Interactive workflow example'});
  await map.getByRole('button',{name:/Review YOUR CONTROL/}).click();
  await expect(map.getByRole('heading',{name:'The final decision belongs to you.'})).toBeVisible();
  await expect(map).toContainText('INTERACTIVE EXAMPLE');
  await page.setViewportSize({width:1440,height:1050});
  await snapshot(page,'landing-desktop');
  await exportDraft(page,'landing','.jobpilot-landing');
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await snapshot(page,'landing-mobile');
  await page.getByRole('button',{name:'Open navigation',exact:true}).click();
  await page.getByRole('navigation',{name:'Mobile navigation'}).getByRole('link',{name:/Features/}).focus();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button',{name:'Open navigation',exact:true})).toBeFocused();
  await page.route('https://e2e.supabase.test/auth/v1/otp**',r=>r.fulfill({status:429,contentType:'application/json',body:'{"code":"over_email_send_rate_limit","message":"Synthetic rate limit"}'}));
  await page.goto('/login');
  await page.getByLabel('Email address').fill('sample@example.invalid');
  await page.getByRole('button',{name:'Send Magic Link',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText(/wait/i);
  await expect(page.getByText('[object Object]')).toHaveCount(0);
});

test('overview uses account data and preserves all feature navigation; discovery selection works',async({browser})=>{
  const context=await browser.newContext({viewport:{width:1440,height:1050}});await setup(context);const page=await context.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  try{
    await page.goto('/workspace');
    await expect(page.getByRole('heading',{name:'Alex, make your next move.'})).toBeVisible();
    await expect(page.getByRole('region',{name:'Your search overview'})).toContainText('02');
    await expect(page.getByRole('link',{name:/Recent drafts ready/})).toContainText('00');
    await expect(page.getByRole('region',{name:'Workflow capabilities'})).toContainText('CAPABILITY OVERVIEW');
    const nav=page.getByRole('navigation',{name:'Workspace',exact:true});
    for(const label of ['Overview','Copilot','Job feed','Apply queue','Applications','Network','New application','Analytics','Profile & resume','Templates','Settings'])await expect(nav.getByRole('link',{name:label,exact:true})).toHaveCount(1);
    await snapshot(page,'overview-desktop');await exportDraft(page,'overview','.app-shell');
    await page.evaluate(()=>document.documentElement.dataset.theme='dark');
    await snapshot(page,'overview-dark');
    await page.goto('/jobs');
    await expect(page.getByRole('button',{name:'View AI Application Engineer at Orbit Studio'})).toBeVisible();
    await page.getByRole('button',{name:'View Machine Learning Engineer at Forma Systems'}).click();
    await expect(page.getByRole('region',{name:'Selected opportunity'})).toContainText('Machine Learning Engineer');
    await page.getByLabel('Filter jobs').fill('impossible-search');
    await expect(page.getByRole('region',{name:'Selected opportunity'})).toHaveCount(0);
    await page.getByLabel('Filter jobs').fill('');
    await page.getByLabel('Remote only').check();
    await expect(page.locator('.opportunity-index>li')).toHaveCount(1);
    await snapshot(page,'discovery-desktop');
    await page.goto('/jobs?tab=drafted');
    await expect(page.getByRole('tab',{name:/Drafted/})).toHaveAttribute('aria-selected','true');
    await expect(page.getByText('Applications you draft from the feed show up here.')).toBeVisible();
    expect(errors).toEqual([]);
  }finally{await context.close()}
});

test('mobile drawer traps focus and returns it; overview failure is visible and retryable',async({browser})=>{
  const context=await browser.newContext({viewport:{width:390,height:844}});await setup(context);const page=await context.newPage();let unavailable=true;
  await context.route('**/api/v1/analytics/summary',r=>r.fulfill({status:unavailable?503:200,contentType:'application/json',body:JSON.stringify(unavailable?{detail:'Synthetic outage'}:summary)}));
  try{
    await page.goto('/workspace');
    await expect(page.getByRole('alert')).toContainText('Part of your overview couldn’t load.',{timeout:15000});
    unavailable=false;await page.getByRole('button',{name:'Retry',exact:true}).click();
    await expect(page.getByRole('alert')).toHaveCount(0);
    await page.getByRole('button',{name:'Open sidebar'}).click();
    const dialog=page.getByRole('dialog',{name:'Sidebar'});await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('link',{name:'JobPilot workspace'})).toBeFocused();
    await page.keyboard.press('Shift+Tab');await expect(dialog.getByRole('button',{name:'Sign out',exact:true})).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button',{name:'Open sidebar'})).toBeFocused();
    await expect(page.locator('#workspace-main')).not.toHaveAttribute('inert','');
    await page.getByRole('button',{name:'Open sidebar'}).click();
    await dialog.getByRole('link',{name:'Job feed',exact:true}).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await page.getByRole('button',{name:'View AI Application Engineer at Orbit Studio'}).click();
    await expect(page.getByRole('button',{name:'← All opportunities'})).toBeVisible();
    await expect(page.getByRole('button',{name:'← All opportunities'})).toBeFocused();
    await expect(page.locator('.opportunity-index')).not.toBeVisible();
    await snapshot(page,'discovery-mobile');
    await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.getByRole('button',{name:'← All opportunities'}).click();
    await expect(page.locator('.opportunity-index')).toBeVisible();
    await expect(page.getByRole('button',{name:'View AI Application Engineer at Orbit Studio'})).toBeFocused();
    await page.goto('/workspace');await snapshot(page,'overview-mobile');
    await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  }finally{await context.close()}
});

test('remaining workspace routes stay reachable without mobile viewport overflow',async({browser})=>{
  const context=await browser.newContext({viewport:{width:390,height:844}});await setup(context);const page=await context.newPage();
  try{
    for(const route of ['/chat','/applications','/applications/new','/apply','/network','/analytics','/profile','/templates','/settings']){
      await page.goto(route);
      await expect(page.locator('#workspace-main')).toBeVisible();
      await expect(page.locator('#workspace-main').locator('h1,h2').first()).toBeVisible({timeout:15000});
      await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),{message:`Viewport overflow on ${route}`}).toBe(true);
    }
  }finally{await context.close()}
});

test('private templates save, survive reload, and preserve text on a conflict',async({browser})=>{
  const context=await browser.newContext();await setup(context);const page=await context.newPage();let saved=null,conflict=false;
  await context.route('**/api/v1/templates**',async r=>{
    if(r.request().method()==='GET')return r.fulfill({json:{templates:saved?[saved]:[]}});
    if(conflict)return r.fulfill({status:409,json:{detail:'This template changed. Reload the saved version before replacing it.'}});
    const data=r.request().postDataJSON();saved={kind:'email',content:data.content,updated_at:new Date().toISOString()};
    return r.fulfill({json:{template:saved}});
  });
  try{
    await page.goto('/templates');await page.getByLabel('Your base writing template').fill('Keep my outreach concise and factual.');
    await page.getByRole('button',{name:'Save template',exact:true}).click();
    await expect(page.getByRole('status')).toContainText('Saved.');await page.reload();
    await expect(page.getByLabel('Your base writing template')).toHaveValue('Keep my outreach concise and factual.');
    conflict=true;await page.getByLabel('Your base writing template').fill('Keep this unsaved draft.');
    await page.getByRole('button',{name:'Save template',exact:true}).click();
    await expect(page.getByRole('alert')).toContainText('template changed');
    await expect(page.getByLabel('Your base writing template')).toHaveValue('Keep this unsaved draft.');
    await page.getByRole('button',{name:'Reload saved',exact:true}).click();
    await expect(page.getByLabel('Your base writing template')).toHaveValue(saved.content);
  }finally{await context.close()}
});

test('feedback restores its reason; visibility logging requires opt-in and visible dwell',async({browser})=>{
  const context=await browser.newContext({viewport:{width:1440,height:1050}});await setup(context);const page=await context.newPage();
  let feedback=[{posting_id:jobs[0].id,signal:'not_relevant',reason:'location'}],snapshots=0;const impressions=[];
  await context.route('**/api/v1/recommendations/**',async r=>{
    const url=new URL(r.request().url());
    if(url.pathname.endsWith('/status'))return r.fulfill({json:{experimental:false}});
    if(url.pathname.endsWith('/feedback'))return r.fulfill({json:{feedback}});
    if(url.pathname.includes('/feedback/')){const data=r.request().postDataJSON();feedback=data.signal==='clear'?[]:[{posting_id:jobs[0].id,...data}];return r.fulfill({json:feedback[0]??{}});}
    if(url.pathname.endsWith('/runs')){snapshots++;return r.fulfill({json:{id:'77777777-7777-4777-8777-777777777777',items:r.request().postDataJSON().posting_ids.map((posting_id,i)=>({posting_id,position:i+1}))}});}
    if(url.pathname.endsWith('/impressions')){impressions.push(r.request().postDataJSON());return r.fulfill({json:{}});}
    return r.fulfill({json:{}});
  });
  try{
    await page.goto('/jobs');const selected=page.getByRole('region',{name:'Selected opportunity'});
    await selected.getByRole('button',{name:'Not relevant',exact:true}).click();
    await expect(selected.getByLabel('Reason')).toHaveValue('location');
    await selected.getByRole('button',{name:'Save feedback'}).click();
    expect(feedback[0].reason).toBe('location');expect(snapshots).toBe(0);expect(impressions).toHaveLength(0);
    const optin=page.getByRole('checkbox',{name:/Help evaluate recommendations/});await optin.check();
    await expect.poll(()=>snapshots).toBe(1);
    // Scroll the observed opportunity buttons into view; fetch alone never logs.
    await page.getByRole('button',{name:'View AI Application Engineer at Orbit Studio'}).scrollIntoViewIfNeeded();
    await expect.poll(()=>impressions.length).toBeGreaterThan(0);
    expect(impressions.every(i=>i.visible_ms>=500&&i.position>=1)).toBe(true);
    await optin.uncheck();const count=impressions.length;await page.waitForTimeout(750);expect(impressions).toHaveLength(count);
  }finally{await context.close()}
});

test('research exposes terminal retry, retains exact draft sources, and saves only on review',async({browser})=>{
  const context=await browser.newContext();await setup(context);const page=await context.newPage();const id='88888888-8888-4888-8888-888888888888';
  let revision=1,failed=true,saves=0;
  const source=n=>({run_id:`research-${n}`,company:'Example',sources:[{url:`https://example.invalid/source-${n}`,title:`Source ${n}`,excerpt:`Evidence from source ${n}`,fetched_at:now}],warnings:[]});
  const application={id,user_id:UID,company:'Example',role:'Engineer',status:'saved',source:'manual',notes:'',cover_letter:'Original cover',linkedin_dm:{},jd_analysis:null,created_at:now,jd_url:''};
  await context.route(`**/api/v1/applications/${id}`,async r=>{
    if(r.request().method()==='PATCH'){saves++;Object.assign(application,r.request().postDataJSON());return r.fulfill({json:application});}
    return r.fulfill({json:{application,tailored_resume:null,cold_emails:[]}});
  });
  await context.route(`**/api/v1/research/${id}**`,async r=>{
    if(r.request().url().endsWith('/cover-letter'))return r.fulfill({json:{draft:'Review this source-informed draft.',fallback:false,research_id:'research-1',research:source(1),saved:false}});
    if(r.request().method()==='GET')return r.fulfill({json:{research:source(revision)}});
    revision=2;return r.fulfill({json:{run_id:'fixture-research',status:'queued'}});
  });
  await context.route('**/api/v1/runs/fixture-research**',r=>{
    if(r.request().url().endsWith('/retry')){failed=false;return r.fulfill({json:{id:'fixture-research',status:'queued'}});}
    return r.fulfill({json:{status:failed?'failed':'succeeded',last_error:failed?'Synthetic source failure':null,result:{}}});
  });
  try{
    await page.goto(`/applications/${id}?tab=research`);
    await page.getByRole('button',{name:'Draft a source-informed cover letter'}).click();
    await expect(page.getByLabel('Research cover letter draft')).toHaveValue('Review this source-informed draft.');expect(saves).toBe(0);
    await page.getByLabel('Source URLs').fill('https://example.invalid/source-2');
    await page.getByRole('button',{name:'Collect sources',exact:true}).click();
    await expect(page.getByRole('alert')).toContainText('Synthetic source failure');
    await page.getByRole('button',{name:'Retry failed research'}).click();
    await expect(page.getByRole('link',{name:'[1] Source 2',exact:true})).toBeVisible();
    const draftSection=page.getByRole('heading',{name:'Review the new draft'}).locator('..');
    await expect(draftSection).toContainText('Evidence from source 1');
    await expect(draftSection).not.toContainText('Evidence from source 2');expect(saves).toBe(0);
    await page.getByRole('button',{name:'Replace saved cover letter with this draft'}).click();
    await expect.poll(()=>saves).toBe(1);expect(application.cover_letter).toBe('Review this source-informed draft.');
  }finally{await context.close()}
});
