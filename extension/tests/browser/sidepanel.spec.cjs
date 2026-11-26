const {test, expect, chromium} = require('@playwright/test');
const path = require('node:path');

// The side panel page loads in the unpacked extension, talks only to the service worker,
// and asks before it reads any job page.
test('side panel asks for page access before reading anything', async ({}, info) => {
  const extensionPath = path.resolve(__dirname, '../..');
  const context = await chromium.launchPersistentContext(info.outputPath('profile'), {
    channel: 'chromium', headless: true, args: [`--disable-extensions-except=${extensionPath}`, `--load-extension=${extensionPath}`],
  });
  const calls = [];
  try {
    const worker = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker');
    await worker.evaluate(async () => chrome.storage.local.set({apiBase: 'http://localhost:8000', token: 'jpx_' + 'x'.repeat(43)}));
    await context.route('http://localhost:8000/api/v1/**', async r => {
      calls.push(new URL(r.request().url()).pathname);
      await r.fulfill({contentType: 'application/json', body: JSON.stringify({name: 'Ada Example', email: 'ada@example.invalid'})});
    });
    const id = new URL(worker.url()).host;
    const errors = [];
    const panel = await context.newPage();
    panel.on('pageerror', e => errors.push(e.message));
    await panel.goto(`chrome-extension://${id}/sidepanel.html`);
    await expect(panel.getByRole('heading', {name: 'Let JobDots read job pages'})).toBeVisible();
    await expect(panel.getByRole('button', {name: 'Allow on job pages'})).toBeEnabled();
    await expect(panel.locator('#who')).toHaveText('Ada Example');
    await expect(panel.locator('#job')).toBeHidden();
    expect(calls).toEqual(['/api/v1/extension/me']);     // nothing else until you allow page access
    expect(errors).toEqual([]);
  } finally {
    await context.close();
  }
});
