const {test,expect,chromium} = require('@playwright/test');
const path = require('node:path');
const crypto = require('node:crypto');
const fixtures = require('./fixtures.cjs');

async function exercise(info,navigate=false) {
  const extensionPath=path.resolve(__dirname,'../..');
  const context=await chromium.launchPersistentContext(info.outputPath('profile'),{
    channel:'chromium',headless:true,args:[`--disable-extensions-except=${extensionPath}`,`--load-extension=${extensionPath}`],
  });
  const application={id:'a9d61591-1204-4408-b95b-04f0bc563298',role:'Engineer',company:'Example',apply_url:'https://job-boards.greenhouse.io/example/jobs/123'};
  const events=[],pdf=Buffer.from('%PDF-1.4\nfixture\n%%EOF');let reports=0,session;
  try {
    const worker=context.serviceWorkers()[0] || await context.waitForEvent('serviceworker');
    await worker.evaluate(async()=>chrome.storage.local.set({apiBase:'http://localhost:8000',token:'jpx_'+'x'.repeat(43)}));
    await context.route('https://job-boards.greenhouse.io/**',r=>r.fulfill({contentType:'text/html',body:r.request().url().endsWith('/thanks') ? fixtures.shell('<div id="application_confirmation">Your application has been received</div>') : fixtures.native}));
    await context.route('http://localhost:8000/api/v1/**',async r=>{
      const endpoint=new URL(r.request().url()).pathname.split('/extension/')[1];
      const body=r.request().postDataJSON();let data={};
      if(endpoint==='queue') data={queue:[application]};
      if(endpoint==='match') data={application};
      if(endpoint==='sessions') {session={id:body.id,application_id:application.id,page_url:body.url,expires_at:new Date(Date.now()+86400000).toISOString()};data={session,application,document:{id:'snapshot'}};}
      if(endpoint==='document') data={name:'Frozen.pdf',pdf_base64:pdf.toString('base64'),size_bytes:pdf.length,sha256:crypto.createHash('sha256').update(pdf).digest('hex')};
      if(endpoint==='fill') data={answers:body.fields.map(f=>({...f,value:({'First name':'Ada','Email':'ada@example.invalid','Country':'India','Resume/CV':'__resume__'})[f.label] || null,source:f.type==='file'?'resume':'profile',flagged:/agree/.test(f.label),note:/agree/.test(f.label)?'Review consent yourself':''}))};
      if(endpoint==='events') {events.push(body);data={id:events.length};}
      if(endpoint==='applied') {reports++;data={status:'applied',evidence:'user_reported'};}
      await r.fulfill({contentType:'application/json',body:JSON.stringify(data)});
    });
    const page=await context.newPage();
    const cdp=await context.newCDPSession(page),worlds=[];
    cdp.on('Runtime.executionContextCreated',({context})=>worlds.push(context));
    await cdp.send('Runtime.enable');
    await page.goto(application.apply_url);
    await expect(page.getByRole('button',{name:'JobPilot · Fill this application'})).toBeVisible();
    const extensionId=new URL(worker.url()).host;
    const isolated=worlds.find(world=>world.origin===`chrome-extension://${extensionId}`);
    expect(isolated,'extension isolated-world execution context').toBeTruthy();
    const access=await cdp.send('Runtime.evaluate',{contextId:isolated.id,expression:"chrome.storage.local.get('token').then(()=>'allowed',()=>'blocked')",awaitPromise:true,returnByValue:true});
    expect(access.result.value).toBe('blocked');
    // Page scripts cannot invoke isolated-world extension functions.
    expect(await page.evaluate(()=>typeof window.__jobpilot)).toBe('undefined');
    await page.getByRole('button',{name:'JobPilot · Fill this application'}).click();
    await page.getByRole('button',{name:'Fill form',exact:true}).click();
    await expect.poll(()=>events.filter(e=>e.kind==='form_prepared').length).toBe(1);
    expect(await page.evaluate(()=>submits)).toBe(0);
    expect(reports).toBe(0);
    await expect(page.locator('#consent')).not.toBeChecked();
    expect(events[0].details.fields.some(f=>'value' in f || 'label' in f)).toBe(false);
    await page.locator('#consent').check();
    await page.getByRole('button',{name:'Submit application',exact:true}).evaluate(node=>node.textContent='Next');
    await page.getByRole('button',{name:'Next',exact:true}).click();
    expect(events.filter(e=>e.kind==='submission_attempted').length).toBe(0);
    await page.getByRole('button',{name:'Next',exact:true}).evaluate(node=>node.textContent='Submit application');
    await page.locator('#email').fill('not-an-email');
    await page.getByRole('button',{name:'Submit application',exact:true}).click();
    expect(events.filter(e=>e.kind==='submission_attempted').length).toBe(0);
    await page.locator('#email').fill('ada@example.invalid');
    await page.evaluate(navigate=>document.querySelector('form').onsubmit=e=>{
      e.preventDefault();window.submits++;
      if(navigate) { location.href='https://job-boards.greenhouse.io/example/jobs/123/thanks';return; }
      const confirmation=document.createElement('div');confirmation.id='application_confirmation';confirmation.textContent='Your application has been received';
      e.target.replaceWith(confirmation);
    },navigate);
    await page.getByRole('button',{name:'Submit application',exact:true}).click();
    await expect.poll(()=>events.filter(e=>e.kind==='submission_confirmation_observed').length).toBe(1);
    expect(events.map(e=>e.kind)).toEqual(['form_prepared','submission_attempted','submission_confirmation_observed']);
    expect(events[2].details.attempt_key).toBe(events[1].request_key);
    expect(reports).toBe(0);
    // The observed confirmation alone never calls the manual applied endpoint.
    page.once('dialog',dialog=>dialog.accept());
    await page.getByRole('button',{name:'Report that I submitted',exact:true}).click();
    await expect.poll(()=>reports).toBe(1);
    await expect(page.locator('#jobpilot-root')).toContainText('user-reported submitted');
  } finally {await context.close();}
}
test('unpacked extension: prepare, user submit, observed confirmation and explicit manual report',async({},info)=>exercise(info));
test('unpacked extension: submission observation survives a full same-origin navigation',async({},info)=>exercise(info,true));
