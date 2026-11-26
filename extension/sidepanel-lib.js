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

  // What to put into the form, grouped by frame: every answer with a value except consents and files.
  // Keys lose their frame prefix (the form engine in that frame knows them without it).
  function fillPlan(answers, edits, skipped) {
    const byKey = Object.fromEntries((answers || []).map(a => [a.key, a]));
    const frames = {};
    for (const a of approval(answers, edits, skipped)) {
      const src = byKey[a.key];
      if (!src || ['legal', 'file'].includes(src.kind)) continue;
      const m = /^f(\d+):(.*)$/.exec(a.key);
      if (!m) continue;
      (frames[m[1]] = frames[m[1]] || []).push({
        key: m[2], panelKey: a.key, label: src.label, value: a.value, required: !!src.required,
        flagged: !!src.flagged && !a.edited,
      });
    }
    return frames;
  }

  // One line for the result of a fill.
  const FILL_WORDS = { filled: 'filled', review: 'to check', preserved: 'already filled (left as is)', missing: 'still empty', invalid: 'rejected by the form', skipped: 'not filled' };
  function fillSummary(results) {
    const counts = {};
    for (const r of results || []) counts[r.outcome] = (counts[r.outcome] || 0) + 1;
    const order = ['filled', 'review', 'preserved', 'missing', 'invalid', 'skipped'];
    return order.filter(o => counts[o]).map(o => `${counts[o]} ${FILL_WORDS[o]}`).join(', ');
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

  // Runs inside one frame of the form (passed to chrome.scripting.executeScript, after form-engine.js).
  // Fills by the keys the panel read; if the page re-rendered, falls back to a unique exact label.
  // Never submits: the form engine has no submit path.
  async function fillFrame(answers) {
    const engine = globalThis.JOBPILOT_FORM_ENGINE;
    if (!engine) return answers.map(a => ({ panelKey: a.panelKey, outcome: 'review', note: 'Could not reach this part of the form.' }));
    const { fields, elements } = engine.collect();
    const norm = s => engine.clean(s).toLowerCase();
    const mapped = answers.map(a => {
      if (elements.has(a.key)) return a;
      const same = fields.filter(f => norm(f.label) === norm(a.label));
      return same.length === 1 ? { ...a, key: same[0].key } : a;
    });
    const results = await engine.apply(mapped, elements);
    const done = new Set(results.map(r => r.panelKey));
    return [...results.map(r => ({ panelKey: r.panelKey, outcome: r.outcome, note: r.note || '' })),
      ...mapped.filter(a => !done.has(a.panelKey)).map(a => ({ panelKey: a.panelKey, outcome: 'review', note: 'This field is gone from the form. Read the questions again.' }))];
  }

  globalThis.JOBDOTS_PANEL = Object.freeze({ BADGES, mergeFrames, countsLine, approval, fillPlan, fillSummary, fillFrame, extractJob, asText });
})();
