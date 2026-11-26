const {test, expect} = require('@playwright/test');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const fixtures = require('./fixtures.cjs');

// The panel page with a stand-in chrome API: one captured job, its answers, and a form in frame 0.
async function openPanel(page) {
  await page.addInitScript(() => {
    const listeners = {activated: [], updated: []};
    const calls = window.__calls = [];
    const injected = window.__injected = [];
    const answers = [
      {key: 'f0:jp-1', label: '*First name', kind: 'name', type: 'text', badge: 'needs_you', value: null, required: true, options: []},
      {key: 'f0:jp-2', label: '*Email', kind: 'email', type: 'email', badge: 'vault', value: 'ada@example.invalid', required: true, options: []},
      {key: 'f0:jp-3', label: 'Current salary', kind: 'pay', type: 'text', badge: 'vault', value: '9 LPA', flagged: true, required: true, options: []},
      {key: 'f0:jp-4', label: 'I agree to the privacy terms', kind: 'legal', type: 'checkbox', badge: 'needs_you', value: null, required: true, options: []},
      {key: 'f0:jp-5', label: 'Cover letter', kind: 'open', type: 'textarea', badge: 'needs_you', value: null, required: false, options: []},
    ];
    const reply = message => {
      calls.push({path: message.path, body: message.body});
      if (message.path === '/extension/me') return {ok: true, data: {name: 'Ada Example'}};
      if (message.path === '/extension/page') return {ok: true, data: {case: {id: 'c1', company: 'Acme', role: 'Engineer'}, answer_set_id: 's1'}};
      if (message.path === '/extension/answer-set') return {ok: true, data: {status: 'ready', answer_set_id: 's1', answers, counts: {needs_you: 3, vault: 2}, notes: []}};
      if (message.path === '/extension/answer-set/approve') return {ok: true, data: {saved: 1}};
      if (message.path === '/extension/case/applied') return {ok: true, data: {stage: message.body.applied === false ? 'ready' : 'applied'}};
      return {ok: false, data: {}};
    };
    window.chrome = {
      runtime: {sendMessage: (message, cb) => setTimeout(() => cb(reply(message)), 5)},
      permissions: {contains: async () => true, request: async () => true},
      tabs: {
        query: async () => [{id: 7, url: 'https://jobs.example.invalid/acme/apply'}],
        onActivated: {addListener: f => listeners.activated.push(f)},
        onUpdated: {addListener: f => listeners.updated.push(f)},
      },
      scripting: {
        executeScript: async ({target, files, args}) => {
          injected.push({target, files, args});
          if (files) return [];
          if (!args) return [{frameId: 0, result: !!window.__submitted}];   // the confirmation-page check
          return [{frameId: 0, result: args[0].map(a => ({panelKey: a.panelKey, outcome: a.flagged ? 'review' : 'filled', note: ''}))}];
        },
      },
    };
    window.__switchTab = () => listeners.activated.forEach(f => f({tabId: 8}));
  });
  await page.goto(pathToFileURL(path.resolve(__dirname, '../../sidepanel.html')).href);
}

test('Fill the form saves your answers, fills every answer with a value, and says what happened', async ({page}) => {
  await openPanel(page);
  const fill = page.locator('#approve');
  await expect(fill).toHaveText('Fill the form');
  await expect(page.locator('#approve-note')).toContainText('2 empty ones stay for you');
  await page.getByLabel('*First name').fill('Ada');
  await page.evaluate(() => window.__switchTab());            // the same answer set reloads; your edit stays
  await expect(page.getByLabel('*First name')).toHaveValue('Ada');
  await fill.click();

  await expect(fill).toHaveText('Fill again');
  await expect(page.locator('#approve-note')).toContainText('2 filled, 1 to check. 1 new answer saved to your bank. Check the form and click Submit yourself.');
  const saved = await page.evaluate(() => window.__calls.find(c => c.path === '/extension/answer-set/approve').body.answers);
  expect(saved.find(a => a.key === 'f0:jp-1')).toEqual({key: 'f0:jp-1', value: 'Ada', edited: true, save: true});
  const run = await page.evaluate(() => window.__injected.find(i => i.args));
  expect(run.target).toEqual({tabId: 7, frameIds: [0]});
  expect(run.args[0].map(a => [a.key, a.value, a.flagged])).toEqual([
    ['jp-1', 'Ada', false], ['jp-2', 'ada@example.invalid', false], ['jp-3', '9 LPA', true],
  ]);                                                         // no consent, nothing empty
  const items = page.locator('#answers li');
  await expect(items.nth(0).locator('.result')).toHaveText('Filled on the form');
  await expect(items.nth(2).locator('.result')).toHaveText('Filled; check it on the form');
  await expect(items.nth(3).locator('.result')).toHaveCount(0);
});

test('fillFrame fills the form by key, falls back to the label after a re-render, and never submits or consents', async ({page}) => {
  await page.route('https://jobs.example.invalid/**', route => route.fulfill({contentType: 'text/html', body: fixtures.native}));
  await page.goto('https://jobs.example.invalid/apply');
  await page.addScriptTag({path: path.resolve(__dirname, '../../content/form-engine.js')});
  await page.addScriptTag({path: path.resolve(__dirname, '../../sidepanel-lib.js')});
  const results = await page.evaluate(async () => {
    const fields = JOBPILOT_FORM_ENGINE.collect().fields;
    const key = label => fields.find(f => f.label.startsWith(label)).key;
    const email = document.querySelector('#email');            // the page re-renders the email input
    const fresh = email.cloneNode(true); email.replaceWith(fresh);
    return JOBDOTS_PANEL.fillFrame([
      {key: key('First name'), panelKey: 'f0:a', label: 'First name', value: 'Ada', required: true, flagged: false},
      {key: key('Email'), panelKey: 'f0:b', label: 'Email', value: 'ada@example.invalid', required: true, flagged: false},
      {key: key('Country'), panelKey: 'f0:c', label: 'Country', value: 'India', required: false, flagged: true},
      {key: 'gone', panelKey: 'f0:d', label: 'Portfolio', value: 'https://example.invalid', required: false, flagged: false},
    ]);
  });
  await expect(page.locator('#first')).toHaveValue('Ada');
  await expect(page.locator('#email')).toHaveValue('ada@example.invalid');
  await expect(page.locator('#country')).toHaveValue('India');
  await expect(page.locator('#consent')).not.toBeChecked();
  expect(await page.evaluate(() => submits)).toBe(0);
  expect(Object.fromEntries(results.map(r => [r.panelKey, r.outcome]))).toEqual({'f0:a': 'filled', 'f0:b': 'filled', 'f0:c': 'review', 'f0:d': 'review'});
});

test('after filling, the panel sees the confirmation page, marks the case applied, and Undo stops it', async ({page}) => {
  await openPanel(page);
  await page.locator('#approve').click();
  await expect(page.locator('#approve')).toHaveText('Fill again');
  await expect(page.locator('#mark-applied')).toBeVisible();
  await page.evaluate(() => { window.__submitted = true; });     // you click Submit; the page shows "Thank you"
  await expect(page.locator('#job-applied')).toHaveText('Applied. JobDots tracks it from here.', {timeout: 8000});
  await expect(page.locator('#status')).toContainText('saw the confirmation page');
  await expect(page.locator('#mark-applied')).toBeHidden();
  const marked = await page.evaluate(() => window.__calls.filter(c => c.path === '/extension/case/applied').map(c => c.body));
  expect(marked).toEqual([{case_id: 'c1', applied: true, seen: true}]);

  await page.locator('#undo-applied').click();
  await expect(page.locator('#mark-applied')).toBeVisible();
  await page.waitForTimeout(3500);                                // one more watch tick: not marked again
  const after = await page.evaluate(() => window.__calls.filter(c => c.path === '/extension/case/applied').length);
  expect(after).toBe(2);
});

test('submittedPage needs confirmation wording and no form left', async ({page}) => {
  const check = async html => {
    await page.route('https://jobs.example.invalid/**', route => route.fulfill({contentType: 'text/html', body: html}));
    await page.goto('https://jobs.example.invalid/apply');
    await page.addScriptTag({path: path.resolve(__dirname, '../../sidepanel-lib.js')});
    const result = await page.evaluate(() => JOBDOTS_PANEL.submittedPage());
    await page.unroute('https://jobs.example.invalid/**');
    return result;
  };
  expect(await check(fixtures.shell('<h2>Thank you!</h2><p>Your application has been submitted successfully.</p>'))).toBe(true);
  expect(await check(fixtures.shell('<p>We’ve received your application for Engineer.</p><button>View jobs</button>'))).toBe(true);
  expect(await check(fixtures.native)).toBe(false);
  expect(await check(fixtures.shell('<p>Thank you for applying! Just a few questions.</p><label>Phone<input></label>'))).toBe(false);
});
