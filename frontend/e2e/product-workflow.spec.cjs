const {test,expect}=require('@playwright/test');
const ALICE='11111111-1111-4111-8111-111111111111',BOB='22222222-2222-4222-8222-222222222222';
const jwt=uid=>Buffer.from(JSON.stringify({alg:'HS256',typ:'JWT'})).toString('base64url')+'.'+Buffer.from(JSON.stringify({sub:uid,email:uid===ALICE?'alice@example.invalid':'bob@example.invalid',exp:Math.floor(Date.now()/1000)+3600})).toString('base64url')+'.synthetic-signature';
async function signedIn(context,uid) {
  const user={id:uid,email:uid===ALICE?'alice@example.invalid':'bob@example.invalid',aud:'authenticated',role:'authenticated',app_metadata:{},user_metadata:{},created_at:'2026-10-29T00:00:00Z'};
  await context.addInitScript(({user,access_token})=>localStorage.setItem('sb-e2e-auth-token',JSON.stringify({access_token,refresh_token:'synthetic-refresh',expires_at:Math.floor(Date.now()/1000)+3600,expires_in:3600,token_type:'bearer',user})),{user,access_token:jwt(uid)});
  await context.route('https://e2e.supabase.test/**',r=>r.fulfill({contentType:'application/json',body:JSON.stringify(user)}));
}
test('new user imports, reviews facts, sets roles, generates, reports and inspects honest metrics',async({browser,request})=>{
  const context=await browser.newContext();await signedIn(context,ALICE);const page=await context.newPage();
  try {
    await page.goto('/profile');
    await expect(page.getByText('Finish your matching setup')).toBeVisible();
    const pdf=await request.get('http://127.0.0.1:8001/__fixture__/resume.pdf');
    await page.locator('#resume-import').setInputFiles({name:'synthetic.pdf',mimeType:'application/pdf',buffer:await pdf.body()});
    await page.getByRole('button',{name:'Import résumé',exact:true}).click();
    await expect(page.getByText('Résumé imported. Review the content')).toBeVisible();
    await page.getByRole('link',{name:'Review and confirm your saved facts'}).click();
    await page.getByRole('button',{name:'Select unconfirmed facts'}).click();
    await page.getByRole('button',{name:/I confirm \d+ selected facts are accurate/}).click();
    await page.getByRole('link',{name:'Choose your target roles and work preferences'}).click();
    await page.locator('#pref-roles').fill('ML Engineer');await page.locator('#pref-roles').press('Enter');
    await page.getByRole('button',{name:/Save preferences/}).click();
    await expect(page.getByText('Your profile is ready for matching')).toBeVisible();
    await page.goto('/applications/new');
    await page.getByPlaceholder('Paste the full job description',{exact:false}).fill('FixtureCo is hiring an entry-level ML Engineer. Build Python tools for remote teams. Responsibilities include testing, documenting and maintaining Python applications.');
    await page.getByRole('button',{name:'Analyse job & generate materials'}).click();
    await expect(page.getByRole('button',{name:'Review materials',exact:true})).toBeVisible({timeout:30000});
    await page.getByRole('button',{name:'Review materials',exact:true}).click();
    await expect(page.getByText('Preparation & submission evidence')).toBeVisible();
    await expect(page.getByText('No submission evidence recorded.')).toBeVisible();
    await page.goto('/apply');
    const keys=[];
    await page.route('**/api/v1/applications/*/report-submission',async route=>{
      keys.push(route.request().postDataJSON().request_key);
      if(keys.length===1){await route.fetch();await route.abort('failed');}else await route.continue();
    });
    page.once('dialog',d=>d.accept());
    await page.getByRole('button',{name:'Report that I submitted',exact:true}).click();
    await expect(page.getByRole('alert')).toBeVisible();
    page.once('dialog',d=>d.accept());
    await page.getByRole('button',{name:'Report that I submitted',exact:true}).click();
    await expect.poll(()=>keys.length).toBe(2);expect(keys[0]).toBe(keys[1]);
    await page.goto('/analytics');
    await expect(page.getByText('Observed workflow outcomes')).toBeVisible();
    await expect(page.getByText('User reports (unverified)',{exact:true}).locator('..').getByText('1',{exact:true})).toBeVisible();
    await expect(page.getByText('Independent employer verification and cost per application: not instrumented.')).toBeVisible();
    await expect(page.getByText('Human reply rate: no accepted-message denominator yet.')).toBeVisible();
    const apps=await request.get('http://127.0.0.1:8001/api/v1/applications/',{headers:{Authorization:`Bearer ${jwt(ALICE)}`}});
    const id=(await apps.json()).applications[0].id;
    const stranger=await request.get(`http://127.0.0.1:8001/api/v1/applications/${id}`,{headers:{Authorization:`Bearer ${jwt(BOB)}`}});
    expect(stranger.status()).toBe(404);
    const other=await browser.newContext();await signedIn(other,BOB);const otherPage=await other.newPage();
    await otherPage.goto('/profile');await expect(otherPage.getByText('Finish your matching setup')).toBeVisible();
    await expect(otherPage.getByText('Ada Fixture',{exact:true})).toHaveCount(0);await other.close();
  } finally {await context.close();}
});

test('invalid upload and unavailable analytics expose retryable errors without marking onboarding ready',async({browser,request})=>{
  const context=await browser.newContext();await signedIn(context,BOB);const page=await context.newPage();
  try{
    await page.goto('/profile');
    await page.locator('#resume-import').setInputFiles({name:'broken.pdf',mimeType:'application/pdf',buffer:Buffer.from('not a PDF')});
    await page.getByRole('button',{name:'Import résumé',exact:true}).click();
    await expect(page.getByRole('alert')).toBeVisible();
    await expect(page.getByText('Finish your matching setup')).toBeVisible();
    const pdf=await request.get('http://127.0.0.1:8001/__fixture__/resume.pdf');
    await page.locator('#resume-import').setInputFiles({name:'valid.pdf',mimeType:'application/pdf',buffer:await pdf.body()});
    await page.getByRole('button',{name:'Import résumé',exact:true}).click();
    await expect(page.getByText('Résumé imported. Review the content')).toBeVisible();
    await expect(page.getByText('Your profile is ready for matching')).toHaveCount(0);
    let recovered=false;
    await page.route('**/api/v1/analytics/summary',async r=>{if(!recovered){await r.fulfill({status:503,contentType:'application/json',body:'{"detail":"Synthetic temporary outage"}'});}else await r.continue();});
    await page.goto('/analytics');
    await expect(page.getByRole('alert')).toContainText('Analytics could not be loaded',{timeout:15000});
    recovered=true;await page.getByRole('button',{name:'Retry',exact:true}).click();
    await expect(page.getByText('Observed workflow outcomes')).toBeVisible({timeout:20000});
    await expect(page.getByText('User reports (unverified)',{exact:true}).locator('..').getByText('0',{exact:true})).toBeVisible();
    await expect(page.getByText('Human reply rate: no accepted-message denominator yet.')).toBeVisible();
  }finally{await context.close();}
});
