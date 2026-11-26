const {test, expect} = require('@playwright/test');
const path = require('node:path');
const {pathToFileURL} = require('node:url');

// The panel page with a stand-in chrome API: one captured job whose answer set needs your first name.
async function openPanel(page) {
  await page.addInitScript(() => {
    const listeners = {activated: [], updated: []};
    const calls = window.__calls = [];
    const answers = [
      {key: 'f0:jp-1', label: '*First name', kind: 'name', type: 'text', badge: 'needs_you', value: null, required: true, options: []},
      {key: 'f0:jp-2', label: '*Email', kind: 'email', type: 'email', badge: 'vault', value: 'ada@example.invalid', required: true, options: []},
    ];
    const reply = message => {
      calls.push({path: message.path, body: message.body});
      if (message.path === '/extension/me') return {ok: true, data: {name: 'Ada Example'}};
      if (message.path === '/extension/page') return {ok: true, data: {case: {id: 'c1', company: 'Acme', role: 'Engineer'}, answer_set_id: 's1'}};
      if (message.path === '/extension/answer-set') return {ok: true, data: {status: 'ready', answer_set_id: 's1', answers, counts: {needs_you: 1, vault: 1}, notes: []}};
      if (message.path === '/extension/answer-set/approve') return {ok: true, data: {saved: calls.filter(c => c.path === message.path).length === 1 ? 1 : 0}};
      return {ok: false, data: {}};
    };
    window.chrome = {
      runtime: {sendMessage: (message, cb) => setTimeout(() => cb(reply(message)), 5)},
      permissions: {contains: async () => true, request: async () => true},
      tabs: {
        query: async () => [{id: 1, url: 'https://jobs.example.invalid/acme/apply'}],
        onActivated: {addListener: f => listeners.activated.push(f)},
        onUpdated: {addListener: f => listeners.updated.push(f)},
      },
      scripting: {executeScript: async () => []},
    };
    window.__switchTab = () => listeners.activated.forEach(f => f({tabId: 2}));
  });
  await page.goto(pathToFileURL(path.resolve(__dirname, '../../sidepanel.html')).href);
}

test('approving shows it is done, keeps your edits across a tab switch, and only re-enables after a change', async ({page}) => {
  await openPanel(page);
  const first = page.getByLabel('*First name');
  const approve = page.locator('#approve');
  await first.fill('Ada');
  await approve.click();
  await expect(approve).toHaveText('Approved');
  await expect(approve).toBeDisabled();
  await expect(page.locator('#approve-note')).toContainText('Saved 1 answer to your answer bank');
  const sent = await page.evaluate(() => window.__calls.find(c => c.path === '/extension/answer-set/approve').body.answers);
  expect(sent.find(a => a.key === 'f0:jp-1')).toEqual({key: 'f0:jp-1', value: 'Ada', edited: true, save: true});

  await page.evaluate(() => window.__switchTab());           // the same answer set reloads
  await expect(page.locator('#answers li')).toHaveCount(2);
  await expect(first).toHaveValue('Ada');                    // your edit is still there
  await expect(approve).toHaveText('Approved');

  await first.fill('Ada L.');
  await expect(approve).toBeEnabled();
  await expect(approve).toHaveText('Approve and save answers');
  await expect(page.locator('#approve-note')).toContainText('Changed since you approved');
  await approve.click();
  await expect(page.locator('#approve-note')).toContainText('nothing new to save');
});
