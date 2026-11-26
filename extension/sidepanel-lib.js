// JobDots side panel: pure helpers (no chrome.* calls), shared with the Node tests.
(() => {
  const BADGES = {
    vault: 'From your vault',
    reused: 'Reused',
    adapted: 'Adapted',
    generated: 'Drafted',
    needs_you: 'Needs you',
  };
  const COUNT_WORDS = { vault: 'from your vault', reused: 'reused', adapted: 'adapted', generated: 'drafted', needs_you: 'need you' };

  // Questions from every frame of the page; keys are prefixed with the frame so they never collide.
  function mergeFrames(results) {
    const out = [];
    for (const r of results || []) {
      for (const f of (r && r.result) || []) {
        if (out.length >= 150) return out;
        if (!f || !f.label) continue;
        out.push({ ...f, key: `f${r.frameId || 0}:${f.key}`.slice(0, 300) });
      }
    }
    return out;
  }

  function countsLine(counts) {
    const parts = Object.entries(counts || {}).filter(([, n]) => n).map(([b, n]) => `${n} ${COUNT_WORDS[b] || b}`);
    return parts.join(', ');
  }

  const asText = v => Array.isArray(v) ? v.join(', ') : (v == null ? '' : String(v));

  // What to send when you approve: the value you see, whether you changed it, and whether to keep it.
  function approval(answers, edits, skipped) {
    return (answers || []).map(a => {
      const edited = Object.prototype.hasOwnProperty.call(edits || {}, a.key) && asText(edits[a.key]) !== asText(a.value);
      return { key: a.key, value: edited ? edits[a.key] : a.value, edited, save: !(skipped || {})[a.key] };
    }).filter(a => asText(a.value).trim());
  }

  // Runs inside the job page (passed to chrome.scripting.executeScript): selected text, else the main text.
  function extractJob() {
    const clean = s => String(s || '').replace(/ /g, ' ').replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n\n').trim();
    const selected = clean(String(getSelection && getSelection()));
    let text = selected.length >= 200 ? selected : '';
    if (!text) {
      const candidates = [...document.querySelectorAll('main, article, [role=main], #content, .content, .job, .posting, section')];
      const best = candidates.map(n => clean(n.innerText)).sort((a, b) => b.length - a.length)[0] || '';
      text = best.length >= 400 ? best : clean(document.body && document.body.innerText);
    }
    return { url: location.href, title: document.title.slice(0, 500), text: text.slice(0, 60000) };
  }

  globalThis.JOBDOTS_PANEL = Object.freeze({ BADGES, mergeFrames, countsLine, approval, extractJob, asText });
})();
