const {test, expect} = require('@playwright/test');
const path = require('node:path');
const {pathToFileURL} = require('node:url');

// The panel with a stand-in chrome API and a small fake of the queue routes.
async function openPanel(page, {refuse = false} = {}) {
  await page.addInitScript(({refuse}) => {
    const calls = window.__calls = [];
    const opened = window.__opened = [];
    window.__copied = [];
    const items = [
      {id: 'a1', case_id: 'c1', kind: 'invite', status: 'reviewed', name: 'Ada Example', title: 'Recruiter', company: 'Acme',
       profile_url: 'https://www.linkedin.com/in/ada-example/', text: 'Hi Ada, I applied for the ML Engineer role at Acme.',
       payload_sha256: 'a'.repeat(64), notes: [], blocked: ''},
      {id: 'a2', case_id: 'c1', kind: 'invite', status: 'blocked', name: 'Bo Example', title: 'Engineer', company: 'Acme',
       profile_url: 'https://www.linkedin.com/in/bo-example/', text: 'Hi Bo, 12 years of Rust.', payload_sha256: 'b'.repeat(64),
       notes: [], blocked: 'Claims 12 years of experience; your vault says 3.'},
    ];
    const usage = {invites_today: 0, invites_per_day: 10, invites_this_week: 3, invites_per_week: 40, dms_today: 0, dms_per_day: 10};
    const find = id => items.find(i => i.id === id);
    const reply = ({path, body}) => {
      calls.push({path, body});
      if (path === '/extension/me') return {ok: true, data: {name: 'Ada Example'}};
      if (path === '/extension/linkedin/queue') return {ok: true, data: {items: items.filter(i => !i.gone), usage, kill_switch: false, quiet_hours: false}};
      if (path === '/extension/linkedin/approve') { find(body.action_id).status = 'approved'; return {ok: true, data: {status: 'approved'}}; }
      if (path === '/extension/linkedin/reject') { find(body.action_id).gone = true; return {ok: true, data: {status: 'cancelled'}}; }
      if (path === '/extension/linkedin/edit') {
        const i = find(body.action_id); i.text = body.text; i.status = 'reviewed'; i.payload_sha256 = 'c'.repeat(64);
        return {ok: true, data: {status: 'reviewed', payload_sha256: i.payload_sha256, notes: [], blocked: ''}};
      }
      if (path === '/extension/linkedin/start') {
        if (refuse) return {ok: true, data: {ok: false, reasons: ['Daily cap reached: linkedin_invites_per_day = 10.']}};
        const i = find(body.action_id); i.status = 'executing'; usage.invites_today += 1;
        return {ok: true, data: {ok: true, profile_url: i.profile_url, text: i.text}};
      }
      if (path === '/extension/linkedin/done') { find(body.action_id).gone = true; return {ok: true, data: {status: body.sent ? 'provider_accepted' : 'failed'}}; }
      return {ok: false, data: {}};
    };
    window.chrome = {
      runtime: {sendMessage: (m, cb) => setTimeout(() => cb(reply(m)), 5)},
      permissions: {contains: async () => false, request: async () => false},
      tabs: {query: async () => [], create: ({url}) => opened.push(url), onActivated: {addListener() {}}, onUpdated: {addListener() {}}},
      scripting: {executeScript: async () => []},
    };
    Object.defineProperty(navigator, 'clipboard', {value: {writeText: async t => { window.__copied.push(t); }}});
  }, {refuse});
  await page.goto(pathToFileURL(path.resolve(__dirname, '../../sidepanel.html')).href);
}

const card = (page, name) => page.locator('#queue-items li', {hasText: name});

test('approve, open the profile with the note copied, then record that you sent it', async ({page}) => {
  await openPanel(page);
  await expect(page.locator('#queue-usage')).toHaveText('Invitations today: 0 of 10. This week: 3 of 40. Messages today: 0 of 10.');
  const ada = card(page, 'Ada Example');
  await expect(ada.locator('.badge')).toHaveText('Needs your approval');
  await expect(ada.locator('.person-meta')).toHaveText('Recruiter at Acme (invitation)');
  await expect(card(page, 'Bo Example').locator('.badge')).toHaveText('Blocked by the Reviewer');
  await expect(card(page, 'Bo Example')).toContainText('your vault says 3');

  await ada.getByRole('button', {name: 'Approve'}).click();
  await expect(ada.locator('.badge')).toHaveText('Approved, ready to send');
  const approve = await page.evaluate(() => window.__calls.find(c => c.path === '/extension/linkedin/approve').body);
  expect(approve).toEqual({action_id: 'a1', payload_sha256: 'a'.repeat(64)});       // exactly the text you saw

  await ada.getByRole('button', {name: 'Open profile and copy note'}).click();
  await expect(ada.locator('.badge')).toHaveText('Opened: did you send it?');
  expect(await page.evaluate(() => window.__opened)).toEqual(['https://www.linkedin.com/in/ada-example/']);
  expect(await page.evaluate(() => window.__copied)).toEqual(['Hi Ada, I applied for the ML Engineer role at Acme.']);
  await expect(page.locator('#queue-usage')).toContainText('Invitations today: 1 of 10');
  await expect(ada).toContainText('"Add a note"');

  await ada.getByRole('button', {name: 'I sent it'}).click();
  await expect(card(page, 'Ada Example')).toHaveCount(0);
  await expect(page.locator('#status')).toHaveText('Recorded: you sent it to Ada Example.');
  const done = await page.evaluate(() => window.__calls.find(c => c.path === '/extension/linkedin/done').body);
  expect(done).toEqual({action_id: 'a1', sent: true});
});

test('a refused open says why and opens nothing; a long note cannot be approved until you shorten it', async ({page}) => {
  await openPanel(page, {refuse: true});
  const ada = card(page, 'Ada Example');
  const note = ada.getByRole('textbox');
  await note.fill('x'.repeat(205));
  await expect(ada.locator('.count')).toHaveText('205 of 200 characters');
  await expect(ada.getByRole('button', {name: 'Approve'})).toHaveCount(0);           // changed: save first
  await ada.getByRole('button', {name: 'Save and check again'}).click();
  await expect(ada.getByRole('button', {name: 'Approve'})).toBeDisabled();           // still over the limit
  await note.fill('Hi Ada, short and true.');
  await ada.getByRole('button', {name: 'Save and check again'}).click();
  await ada.getByRole('button', {name: 'Approve'}).click();
  await ada.getByRole('button', {name: 'Open profile and copy note'}).click();
  await expect(page.locator('#status')).toHaveText('Not now: Daily cap reached: linkedin_invites_per_day = 10.');
  expect(await page.evaluate(() => window.__opened)).toEqual([]);
  await expect(ada.locator('.badge')).toHaveText('Approved, ready to send');

  await card(page, 'Bo Example').getByRole('button', {name: 'Discard'}).click();
  await expect(card(page, 'Bo Example')).toHaveCount(0);
});
