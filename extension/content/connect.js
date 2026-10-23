// JobPilot extension — runs on the JobPilot web app so "Connect extension" in
// Settings can hand this extension a personal token without copy-paste.

(() => {
  const policy = globalThis.JOBPILOT_POLICY;
  if (window !== window.top || !policy?.appOrigins.includes(window.location.origin)) return;
  const announce = () => window.postMessage({ source: 'jobpilot-extension', type: 'present', version: chrome.runtime.getManifest().version }, window.location.origin);

  window.addEventListener('message', (event) => {
    if (event.source !== window || event.origin !== window.location.origin) return;
    const msg = event.data || {};
    if (msg.source !== 'jobpilot-app') return;
    if (msg.type === 'ping') announce();
    if (msg.type === 'connect' && typeof msg.token === 'string' && msg.token.startsWith('jpx_')) {
      chrome.runtime.sendMessage({ type: 'connect', token: msg.token, apiBase: msg.apiBase, appUrl: msg.appUrl }, (res) => {
        window.postMessage({ source: 'jobpilot-extension', type: 'connected', ok: !!(res && res.ok) }, window.location.origin);
      });
    }
  });

  announce();
})();
