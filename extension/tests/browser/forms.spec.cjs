const {test,expect} = require('@playwright/test');
const path = require('node:path');
const crypto = require('node:crypto');
const fixtures = require('./fixtures.cjs');
const engine = path.resolve(__dirname,'../../content/form-engine.js');
const raw = Buffer.from('%PDF-1.4\nfixture-only\n%%EOF');
const document = {pdf_base64:raw.toString('base64'),sha256:crypto.createHash('sha256').update(raw).digest('hex'),size_bytes:raw.length,name:'Ada_Resume.pdf'};

async function load(page,html) {
  await page.route('https://job-boards.greenhouse.io/**',route=>route.fulfill({contentType:'text/html',body:html}));
  await page.goto('https://job-boards.greenhouse.io/example/jobs/123');
  await page.addScriptTag({path:engine});
}
async function fill(page,values,doc=document) {
  return page.evaluate(async ({values,doc})=>{
    const e=JOBPILOT_FORM_ENGINE,c=e.collect();
    const answers=c.fields.map(f=>({...f,value:values[f.label] ?? null,source:'profile',flagged:false,note:''}));
    return e.apply(answers,c.elements,doc);
  },{values,doc});
}
test('Greenhouse pattern: exact options, PDF hash, legal review and no submit',async({page})=>{
  await load(page,fixtures.native);
  const result=await fill(page,{'First name':'Ada','Email':'ada@example.invalid','Country':'India','Resume/CV':'__resume__','I agree to the privacy terms':'I agree to the privacy terms'});
  await expect(page.locator('#first')).toHaveValue('Ada');
  await expect(page.locator('#country')).toHaveValue('India');
  await expect(page.locator('#consent')).not.toBeChecked();
  expect(await page.evaluate(()=>submits)).toBe(0);
  expect(result.find(a=>a.type==='file').outcome).toBe('filled');
  expect(result.find(a=>a.type==='file').note).toContain('acceptance is not verified');
  expect(await page.locator('#resume').evaluate(n=>n.files[0].size)).toBe(raw.length);
});
test('Lever pattern: scoped radio and checkbox groups; existing answers preserved',async({page})=>{
  await load(page,fixtures.radio);
  await page.locator('input[value=yes]').check();
  await fill(page,{'Visa sponsorship':'No','Technologies':['Python','SQL']});
  await expect(page.locator('input[value=yes]')).toBeChecked();
  await expect(page.locator('input[value=no]')).not.toBeChecked();
  expect(await page.locator('input[name=skills]:checked').count()).toBe(2);
  expect(await page.evaluate(()=>JOBPILOT_FORM_ENGINE.collect().fields.length)).toBe(2);
});
test('Ashby pattern: portal options are scoped and require exact selection',async({page})=>{
  await load(page,fixtures.custom);
  const ambiguous=await fill(page,{'Location':'Pune'});
  expect(ambiguous[0].flagged).toBe(true);
  await expect(page.locator('#city')).toHaveValue('');
  const result=await fill(page,{'Location':'Pune, India'});
  expect(result[0].outcome).toBe('filled');
  await expect(page.locator('#city')).toHaveValue('Pune, India');
});
test('button ARIA combobox supports exact selection without submitting',async({page})=>{
  await load(page,fixtures.buttonCombo);
  expect((await fill(page,{'Country':'India'}))[0].outcome).toBe('filled');
  await expect(page.locator('#loc')).toHaveText('India');
});
test('native validation exposes invalid email, number, pattern and readonly fields',async({page})=>{
  await load(page,fixtures.validation);
  const result=await fill(page,{'Email':'invalid','Years of experience':'99','Short answer':'ABCDE','Read-only':'No'});
  expect(result.filter(a=>a.outcome==='invalid').length).toBe(3);
  expect(result.find(a=>a.label==='Read-only').flagged).toBe(true);
  await expect(page.locator('#readonly')).toHaveValue('');
});
test('SmartRecruiters pattern: native multiselect and rejected file formats',async({page})=>{
  await load(page,fixtures.multiple);
  const result=await fill(page,{'Skills':['Python','SQL'],'Resume':'__resume__','Resume rejected':'__resume__'});
  expect(await page.locator('#skills').evaluate(n=>[...n.selectedOptions].map(o=>o.text))).toEqual(['Python','SQL']);
  expect(result.filter(a=>a.type==='file').every(a=>a.flagged)).toBe(true);
  expect(await page.locator('#docx').evaluate(n=>n.files.length)).toBe(0);
});
test('a pre-existing different PDF is preserved and flagged, not overwritten',async({page})=>{
  await load(page,fixtures.native);
  await page.locator('#resume').setInputFiles({name:'existing.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-different')});
  const result=await fill(page,{'Resume/CV':'__resume__'});
  expect(result.find(a=>a.type==='file').outcome).toBe('review');
  expect(await page.locator('#resume').evaluate(n=>n.files[0].name)).toBe('existing.pdf');
});
test('corrupt PDF never reaches the file control',async({page})=>{
  await load(page,fixtures.native);
  const result=await fill(page,{'Resume/CV':'__resume__'},{...document,sha256:'0'.repeat(64)});
  expect(result.find(a=>a.type==='file').flagged).toBe(true);
  expect(await page.locator('#resume').evaluate(n=>n.files.length)).toBe(0);
});
test('dynamic questions are discovered, and rerendered controls are not counted filled',async({page})=>{
  await load(page,fixtures.dynamic);
  await fill(page,{'First name':'Ada'});
  expect(await page.evaluate(()=>JOBPILOT_FORM_ENGINE.collect().fields.length)).toBe(2);
  const stale=await page.evaluate(()=>{
    const e=JOBPILOT_FORM_ENGINE,c=e.collect(),f=c.fields[0];document.querySelector('#first').remove();
    return e.audit([{...f,value:'Ada',source:'profile',outcome:'filled',flagged:false}],c.elements);
  });
  expect(stale[0].outcome).toBe('review');
});
test('generic thank-you text is not submission evidence; provider selector is required',async({page})=>{
  await load(page,fixtures.shell('<h2>Thank you for applying</h2>'));
  expect(await page.evaluate(()=>JOBPILOT_FORM_ENGINE.confirmationFor())).toBeNull();
  await page.setContent(fixtures.shell('<div id="application_confirmation">Your application has been received</div>'));
  expect(await page.evaluate(()=>JOBPILOT_FORM_ENGINE.confirmationFor())).toBe('greenhouse_confirmation');
  expect(await page.evaluate(()=>JOBPILOT_FORM_ENGINE.confirmationFor('unrelated.example'))).toBeNull();
});

test('a controlled input that replaces the answer is flagged instead of counted as filled',async({page})=>{
  await load(page,fixtures.shell('<form><label>First name<input id="first" onchange="this.value=\'Employer reset\'"></label></form>'));
  const result=await fill(page,{'First name':'Ada'});
  expect(result[0].outcome).toBe('review');
  await expect(page.locator('#first')).toHaveValue('Employer reset');
});

test('a late attachment replacement fails the final hash audit',async({page})=>{
  await load(page,fixtures.native);
  await page.locator('#resume').evaluate(node=>node.onchange=()=>setTimeout(()=>{
    const transfer=new DataTransfer();transfer.items.add(new File(['%PDF-changed'],'Ada_Resume.pdf',{type:'application/pdf'}));node.files=transfer.files;
  },400));
  const result=await fill(page,{'Resume/CV':'__resume__'});
  expect(result.find(a=>a.type==='file').outcome).toBe('review');
});

test('ARIA radio groups select only an exact option in the right question',async({page})=>{
  await load(page,fixtures.shell('<form><div role="radiogroup" aria-label="Visa sponsorship" aria-required="true"><div role="radio" aria-checked="false" onclick="this.setAttribute(\'aria-checked\',\'true\')">Yes</div><div role="radio" aria-checked="false" onclick="this.setAttribute(\'aria-checked\',\'true\')">No</div></div></form>'));
  const result=await fill(page,{'Visa sponsorship':'No'});
  expect(result.length).toBe(1);expect(result[0].outcome).toBe('filled');
  expect(await page.getByRole('radio',{name:'No',exact:true}).getAttribute('aria-checked')).toBe('true');
  expect(await page.getByRole('radio',{name:'Yes',exact:true}).getAttribute('aria-checked')).toBe('false');
});
