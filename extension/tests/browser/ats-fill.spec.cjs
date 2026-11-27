const {test, expect} = require('@playwright/test');
const path = require('node:path');
const crypto = require('node:crypto');
const ats = require('./fixtures-ats.cjs');

// Applicant on whole forms shaped like each provider: the fields the panel reads, then a fill
// with the tailored PDF. Consents stay unticked, a cover letter slot stays empty, nothing submits.
const raw = Buffer.from('%PDF-1.4\nfixture-only\n%%EOF');
const resume = {name: 'Ada_Example_Resume.pdf', pdf_base64: raw.toString('base64'), size_bytes: raw.length,
                sha256: crypto.createHash('sha256').update(raw).digest('hex')};

async function open(page, html, host) {
  await page.route(`https://${host}/**`, route => route.fulfill({contentType: 'text/html', body: html}));
  await page.goto(`https://${host}/example/apply`);
  await page.addScriptTag({path: path.resolve(__dirname, '../../content/form-engine.js')});
  await page.addScriptTag({path: path.resolve(__dirname, '../../sidepanel-lib.js')});
}

// What the panel would send for these labels after the Answerer (values by label start).
async function fill(page, values) {
  return page.evaluate(async ({values, resume}) => {
    const fields = JOBPILOT_FORM_ENGINE.collect().fields;
    const answers = fields.filter(f => Object.keys(values).some(v => f.label.startsWith(v))).map(f => {
      const value = values[Object.keys(values).find(v => f.label.startsWith(v))];
      return {key: f.key, panelKey: `f0:${f.key}`, label: f.label, kind: f.type === 'file' ? 'file' : 'short', value,
              required: f.required, flagged: false};
    });
    const results = await JOBDOTS_PANEL.fillFrame(answers, resume);
    return {labels: fields.map(f => [f.label, f.type]), results: Object.fromEntries(results.map(r => [r.label || answers.find(a => a.panelKey === r.panelKey).label, r.outcome]))};
  }, {values, resume});
}

test('Greenhouse: names, select, resume attached, consent left for you', async ({page}) => {
  await open(page, ats.greenhouse, 'job-boards.greenhouse.io');
  const out = await fill(page, {'First Name': 'Ada', 'Last Name': 'Example', 'Email': 'ada@example.invalid',
    'Phone': '+91 90000 00000', 'Resume/CV': '__resume__', 'LinkedIn Profile': 'https://www.linkedin.com/in/ada-example/',
    'Notice period': '30 days'});
  expect(out.labels.map(l => l[1])).toEqual(['text', 'text', 'email', 'tel', 'file', 'url', 'select', 'checkbox']);
  expect(Object.values(out.results).every(o => o === 'filled')).toBe(true);
  await expect(page.locator('#notice')).toHaveValue('30 days');
  expect(await page.locator('#resume').evaluate(n => n.files[0].name)).toBe('Ada_Example_Resume.pdf');
  await expect(page.locator('#consent')).not.toBeChecked();
  expect(await page.evaluate(() => submits)).toBe(0);
});

test('Lever: full name, resume first, radio group, URLs', async ({page}) => {
  await open(page, ats.lever, 'jobs.lever.co');
  const out = await fill(page, {'Resume/CV': '__resume__', 'Full name': 'Ada Example', 'Email': 'ada@example.invalid',
    'LinkedIn URL': 'https://www.linkedin.com/in/ada-example/', 'Are you legally authorized': 'Yes'});
  expect(out.labels.find(l => l[0].startsWith('Are you legally authorized'))[1]).toBe('radio');
  expect(Object.values(out.results).every(o => o === 'filled')).toBe(true);
  await expect(page.locator('input[name=auth][value=Yes]')).toBeChecked();
  expect(await page.locator('#resume-upload').evaluate(n => n.files[0].name)).toBe('Ada_Example_Resume.pdf');
  await expect(page.locator('#org')).toHaveValue('');           // nothing to say: left empty
  expect(await page.evaluate(() => submits)).toBe(0);
});

test('Ashby: hidden upload input behind a button, combobox location, cover letter left empty', async ({page}) => {
  await open(page, ats.ashby, 'jobs.ashbyhq.com');
  const out = await fill(page, {'Name': 'Ada Example', 'Email': 'ada@example.invalid', 'Resume': '__resume__',
    'Location': 'Pune, Maharashtra, India'});
  expect(out.labels).toEqual([['Name', 'text'], ['Email', 'email'], ['Resume', 'file'], ['Cover letter', 'file'], ['Location', 'select']]);
  expect(Object.values(out.results).every(o => o === 'filled')).toBe(true);
  expect(await page.locator('#_systemfield_resume').evaluate(n => n.files[0].name)).toBe('Ada_Example_Resume.pdf');
  expect(await page.locator('#cover').evaluate(n => n.files.length)).toBe(0);
  await expect(page.locator('#loc')).toHaveValue('Pune, Maharashtra, India');
  expect(await page.evaluate(() => submits)).toBe(0);
});
