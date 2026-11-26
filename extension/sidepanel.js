// JobDots side panel: capture the job on this page, read the form's questions, review the
// Answerer's answers (each with where it came from), edit, approve. Nothing here fills or
// submits the form, and the panel never holds your token (the service worker makes the calls).
(() => {
  const lib = globalThis.JOBDOTS_PANEL;
  const $ = id => document.getElementById(id);
  const send = message => new Promise(resolve => chrome.runtime.sendMessage(message, r => resolve(r || { ok: false })));
  const post = (path, body) => send({ type: 'api', path, method: 'POST', body });
  const PAGES = { origins: ['https://*/*'] };
  const state = { tab: null, page: null, set: null, edits: {}, skipped: {}, busy: false, token: 0 };

  function status(text, error = false) {
    $('status').textContent = text || '';
    $('status').className = error ? 'status err' : 'status';
  }
  const detail = (r, fallback) => (r && r.data && typeof r.data.detail === 'string' ? r.data.detail : fallback);
  function busy(on) {
    state.busy = on;
    for (const id of ['capture', 'read', 'approve', 'grant']) $(id).disabled = on;
  }
  const wait = ms => new Promise(r => setTimeout(r, ms));

  async function activeTab() {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    return tab || null;
  }

  async function refresh() {
    const token = ++state.token;
    const allowed = await chrome.permissions.contains(PAGES);
    $('access').hidden = allowed;
    if (!allowed) { $('job').hidden = $('form').hidden = true; status(''); return; }
    const tab = await activeTab();
    if (token !== state.token) return;
    state.tab = tab;
    const url = tab && tab.url || '';
    if (!url.startsWith('https://')) {
      $('job').hidden = $('form').hidden = true;
      status('Open a job posting or an application form to use the panel.');
      return;
    }
    const page = await post('/extension/page', { url });
    if (token !== state.token) return;
    if (!page.ok) { status(detail(page, "Can't reach JobDots. Is it running?"), true); return; }
    state.page = page.data;
    const known = !!page.data.case;
    $('job').hidden = false;
    $('job-known').hidden = !known;
    $('job-unknown').hidden = known;
    $('form').hidden = false;
    status('');
    if (known) {
      $('job-company').textContent = page.data.case.company;
      $('job-role').textContent = page.data.case.role || '';
      if (page.data.answer_set_id && (!state.set || state.set.case_id !== page.data.case.id)) await loadAnswers(page.data.case.id);
    } else {
      state.set = null; renderAnswers();
    }
  }

  async function capture() {
    if (state.busy || !state.tab) return null;
    busy(true);
    try {
      status('Reading the job description…');
      const [frame] = await chrome.scripting.executeScript({ target: { tabId: state.tab.id }, func: lib.extractJob });
      const job = frame && frame.result;
      if (!job || job.text.length < 200) { status('Not enough text on this page. Select the job description and try again.', true); return null; }
      status('Opening a case…');
      const made = await post('/extension/capture', job);
      if (!made.ok) { status(detail(made, "Couldn't capture this job."), true); return null; }
      status(made.data.created ? `Captured ${made.data.company}. Supervisor is on it.` : `${made.data.company} is already a case.`);
      return made.data;
    } catch (e) {
      status("Chrome doesn't let extensions read this page.", true);
      return null;
    } finally { busy(false); await refresh(); }
  }

  async function readQuestions() {
    if (state.busy || !state.tab) return;
    let caseId = state.page && state.page.case && state.page.case.id;
    if (!caseId) {
      const made = await capture();
      if (!made) return;
      caseId = made.case_id;
    }
    busy(true);
    try {
      status("Reading the form's questions…");
      const target = { tabId: state.tab.id, allFrames: true };
      await chrome.scripting.executeScript({ target, files: ['content/form-engine.js'] });
      const frames = await chrome.scripting.executeScript({
        target, func: () => (globalThis.JOBPILOT_FORM_ENGINE ? globalThis.JOBPILOT_FORM_ENGINE.collect().fields : []),
      });
      const questions = lib.mergeFrames(frames);
      if (!questions.length) { status('No form questions on this page yet. Open the application form first.', true); return; }
      const sent = await post('/extension/questions', { url: state.tab.url, case_id: caseId, questions });
      if (!sent.ok) { status(detail(sent, "Couldn't send the questions."), true); return; }
      status(`Answerer is looking at ${questions.length} question${questions.length > 1 ? 's' : ''}…`);
      for (let i = 0; i < 90; i++) {
        await wait(2000);
        const r = await post('/extension/answer-set', { case_id: caseId, run_id: sent.data.run_id });
        if (!r.ok) { status(detail(r, 'Lost touch with JobDots.'), true); return; }
        if (r.data.status === 'working') { status(r.data.step); continue; }
        if (r.data.status === 'failed') { status(r.data.detail, true); return; }
        if (r.data.status === 'ready') { setAnswers(caseId, r.data); return; }
      }
      status('The Answerer is taking long; reopen the panel in a minute.', true);
    } catch (e) {
      status("Chrome doesn't let extensions read this page.", true);
    } finally { busy(false); }
  }

  async function loadAnswers(caseId) {
    const r = await post('/extension/answer-set', { case_id: caseId });
    if (r.ok && r.data.status === 'ready') setAnswers(caseId, r.data);
  }

  function setAnswers(caseId, data) {
    state.set = { case_id: caseId, id: data.answer_set_id, answers: data.answers || [], counts: data.counts || {}, notes: data.notes || [] };
    state.edits = {}; state.skipped = {};
    renderAnswers();
    status(lib.countsLine(state.set.counts) + (state.set.notes[0] ? `. ${state.set.notes[0]}` : ''));
  }

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === 'class') node.className = v;
      else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) node.setAttribute(k, v === true ? '' : v);
    }
    for (const c of children.flat()) if (c != null) node.append(c.nodeType ? c : document.createTextNode(String(c)));
    return node;
  }

  function editor(a) {
    const id = `a-${btoa(unescape(encodeURIComponent(a.key))).replace(/[^a-z0-9]/gi, '')}`;
    const current = Object.prototype.hasOwnProperty.call(state.edits, a.key) ? state.edits[a.key] : a.value;
    const onchange = e => { state.edits[a.key] = e.target.value; };
    if (['select', 'radio'].includes(a.type) && a.options.length) {
      return [id, el('select', { id, onchange }, el('option', { value: '' }, 'Choose…'),
        a.options.map(o => el('option', { value: o, selected: o === lib.asText(current) }, o)))];
    }
    if (a.type === 'textarea' || ['open', 'company_specific'].includes(a.kind)) {
      const t = el('textarea', { id, oninput: onchange, rows: 5 }); t.value = lib.asText(current); return [id, t];
    }
    const i = el('input', { id, type: 'text', oninput: onchange }); i.value = lib.asText(current); return [id, i];
  }

  function renderAnswers() {
    const list = $('answers');
    list.replaceChildren();
    const answers = (state.set && state.set.answers) || [];
    $('approve-bar').hidden = !answers.length;
    $('form-hint').hidden = !!answers.length;
    $('read').textContent = answers.length ? 'Read the questions again' : "Read this form's questions";
    for (const a of answers) {
      const locked = ['legal', 'file'].includes(a.kind);
      const [id, input] = locked ? [null, null] : editor(a);
      list.append(el('li', { class: `answer${a.flagged ? ' flag' : ''}` },
        el('label', { class: 'q', for: id || undefined }, a.label, a.required ? el('span', { class: 'req' }, ' (required)') : null),
        el('div', { class: 'row' },
          el('span', { class: `badge ${a.badge}` }, lib.BADGES[a.badge] || a.badge),
          el('span', { class: 'spacer' }),
          locked ? null : el('button', { class: 'small', type: 'button', onclick: () => copy(a) }, 'Copy')),
        input,
        a.note ? el('p', { class: 'note' }, a.note) : null,
        !locked && !['vault'].includes(a.badge) ? el('label', { class: 'skip' },
          el('input', { type: 'checkbox', onchange: e => { state.skipped[a.key] = e.target.checked; } }),
          "Don't save this one to my answer bank") : null));
    }
    const need = answers.filter(a => a.badge === 'needs_you').length;
    $('approve-note').textContent = need ? `${need} still need${need === 1 ? 's' : ''} you on the form itself.` : 'New and edited answers are saved to your answer bank.';
  }

  async function copy(a) {
    const value = lib.asText(Object.prototype.hasOwnProperty.call(state.edits, a.key) ? state.edits[a.key] : a.value);
    try { await navigator.clipboard.writeText(value); status('Copied.'); } catch (e) { status("Couldn't copy; select the text instead.", true); }
  }

  async function approve() {
    if (state.busy || !state.set) return;
    const answers = lib.approval(state.set.answers, state.edits, state.skipped);
    if (!answers.length) { status('Nothing to approve yet.'); return; }
    busy(true);
    try {
      const r = await post('/extension/answer-set/approve', { case_id: state.set.case_id, answer_set_id: state.set.id, answers });
      if (!r.ok) { status(detail(r, "Couldn't save your answers."), true); return; }
      status(r.data.saved ? `Approved. ${r.data.saved} saved to your answer bank.` : 'Approved. Nothing new to save.');
    } finally { busy(false); }
  }

  $('grant').addEventListener('click', async () => {
    const granted = await chrome.permissions.request(PAGES).catch(() => false);
    if (!granted) status('Without this the panel can’t read job pages.', true);
    refresh();
  });
  $('capture').addEventListener('click', () => capture());
  $('read').addEventListener('click', () => readQuestions());
  $('approve').addEventListener('click', () => approve());
  chrome.tabs.onActivated.addListener(() => { state.set = null; refresh(); });
  chrome.tabs.onUpdated.addListener((id, info) => { if (state.tab && id === state.tab.id && info.status === 'complete') refresh(); });

  (async () => {
    const me = await send({ type: 'api', path: '/extension/me' });
    if (!me.ok) { status(detail(me, 'Not connected. Open JobDots → Settings → Connect extension.'), true); }
    else $('who').textContent = me.data.name || me.data.email || '';
    refresh();
  })();
})();
