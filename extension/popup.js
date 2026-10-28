// JobPilot extension — popup: connection status, "Fill this page", settings.

const $ = (id) => document.getElementById(id);
const send = (message) => new Promise((resolve) => chrome.runtime.sendMessage(message, resolve));

function status(text, kind = 'muted') {
  $('status').textContent = text;
  $('status').className = kind;
}

async function refresh() {
  const settings = await send({ type: 'settings' });
  $('apiBase').value = settings.apiBase || '';
  $('token').value = settings.token || '';
  if (!settings.token) {
    status('Not connected yet. Open JobPilot → Settings → Connect extension.', 'err');
    $('settings').open = true;
    return;
  }
  const me = await send({ type: 'api', path: '/extension/me' });
  if (!me.ok) {
    status(me.data?.detail || `Couldn't connect (${me.status}).`, 'err');
    return;
  }
  status(`Connected as ${me.data.name || me.data.email}.`, 'ok');
  $('fill').disabled = false;
  $('queue').disabled = !settings.appUrl;
}

$('fill').addEventListener('click', async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) return;
  try {
    await chrome.scripting.executeScript({ target: { tabId: tab.id, allFrames: true }, files: ['content/form-engine.js', 'content/fill.js'] });
    // Open the panel (and fill) in the frame that actually has the form.
    await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: true },
      func: () => {
        const fields = document.querySelectorAll('input:not([type=hidden]), textarea, select').length;
        if (window.__jobpilot && (fields >= 3 || window === window.top && fields > 0)) window.__jobpilot.open(true);
      },
    });
    window.close();
  } catch (e) {
    status("Chrome doesn't allow extensions on this page.", 'err');
  }
});

$('queue').addEventListener('click', async () => {
  const { appUrl } = await send({ type: 'settings' });
  if (appUrl) chrome.tabs.create({ url: `${appUrl.replace(/\/+$/, '')}/apply` });
});

$('save').addEventListener('click', async () => {
  await chrome.storage.local.set({ apiBase: $('apiBase').value.trim(), token: $('token').value.trim() });
  status('Saved. Checking…');
  refresh();
});

refresh();
