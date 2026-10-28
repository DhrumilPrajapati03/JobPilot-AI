// Opt-in, read-only inspection of public employer pages. No extension token,
// filling, clicks, uploads, authentication or submissions. Stop on blocking pages.
const {chromium}=require('playwright');
const fs=require('node:fs');const path=require('node:path');
process.env.PLAYWRIGHT_BROWSERS_PATH ||= path.resolve(__dirname,'../../.tool-cache/playwright');
const allowed=new Set(['boards.greenhouse.io','job-boards.greenhouse.io','job-boards.eu.greenhouse.io','jobs.lever.co','jobs.eu.lever.co','jobs.ashbyhq.com','jobs.smartrecruiters.com']);
async function main(){
  const [input,output]=process.argv.slice(2);
  if(!input || !output)throw Error('Usage: node scripts/check-live-forms.cjs input.json output.json');
  const entries=JSON.parse(fs.readFileSync(input,'utf8')).filter(x=>x.url).slice(0,8);
  const browser=await chromium.launch({headless:true});const context=await browser.newContext();const results=[];
  try{
    for(const entry of entries){
      const url=new URL(entry.url);if(url.protocol!=='https:' || !allowed.has(url.hostname) || url.username || url.password)throw Error('Only approved HTTPS ATS origins are allowed');
      const page=await context.newPage();const row={ats:entry.ats,url:entry.url,title:entry.title,checked_at:new Date().toISOString(),mode:'read_only_no_personal_data'};
      try{
        const response=await page.goto(entry.url,{waitUntil:'domcontentloaded',timeout:20000});
        await page.waitForTimeout(2500);
        row.http_status=response?.status();
        if(!allowed.has(new URL(page.url()).hostname)){row.status='unsupported_redirect';}
        else if(row.http_status>=400 || /access denied|verify you are human|checking your browser/i.test((await page.locator('body').innerText()).slice(0,4000))){row.status='blocked_or_unavailable';}
        else{
          await page.addScriptTag({path:path.resolve(__dirname,'../content/form-engine.js')});
          const snapshot=await page.evaluate(()=>{const {fields}=JOBPILOT_FORM_ENGINE.collect();return {fields:fields.length,required:fields.filter(f=>f.required).length,types:[...new Set(fields.map(f=>f.type))]};});
          Object.assign(row,snapshot);row.status=snapshot.fields>=2?'controls_detected_read_only':'application_step_not_opened';
        }
      }catch(error){row.status=error.name==='TimeoutError'?'navigation_timeout':'inspection_unavailable';}
      finally{await page.close();}
      results.push(row);console.log(`${row.ats}: ${row.status} (${row.fields ?? 0} visible controls)`);
    }
  }finally{await context.close();await browser.close();}
  fs.writeFileSync(output,JSON.stringify({scope:'Public pages inspected without filling or submitting; not live submission acceptance',results},null,2)+'\n');
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
