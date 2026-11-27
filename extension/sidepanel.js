// JobDots side panel: capture the job on this page, read the form's questions, review the
// Answerer's answers (each with where it came from), edit, and fill them into the form. It never
// submits: you check the form and click Submit yourself. The panel never holds your token (the
// service worker makes the calls).
(() => {
  const lib = globalThis.JOBDOTS_PANEL;
  const $ = id => document.getElementById(id);
  const send = message => new Promise(resolve => chrome.runtime.sendMessage(message, r => resolve(r || { ok: false })));
  const post = (path, body) => send({ type: 'api', path, method: 'POST', body });
  const PAGES = { origins: ['https://*/*'] };
  // edits and skipped belong to one answer set (editsFor): they survive a tab switch or reload of that set.
  const state = { tab: null, page: null, set: null, edits: {}, skipped: {}, editsFor: null, filled: {}, busy: false, token: 0, noAuto: {}, checking: false };

  function status(text, error = false) {
    $('status').textContent = text || '';
    $('status').className = error ? 'status err' : 'status';
  }
  const detail = (r, fallback) => (r && r.data && typeof r.data.detail === 'string' ? r.data.detail : fallback);
  function busy(on) {
    state.busy = on;
    for (const id of ['capture', 'read', 'grant']) $(id).disabled = on;
    fillButton();
  }
  function fillButton() {
    $('approve').disabled = state.busy;
    $('approve').textContent = state.busy ? 'Filling…' : Object.keys(state.filled).length ? 'Fill again' : 'Fill the form';
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
    // On LinkedIn (profiles, feed, messages) the panel is your queue; only job posts are jobs.
    if (/^https:\/\/([a-z]{2,3}\.)?(www\.)?linkedin\.com\//i.test(url) && !/linkedin\.com\/jobs\//i.test(url)) {
      $('job').hidden = $('form').hidden = true;
      state.page = null; state.set = null;
      status('');
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
      showApplied(page.data.case.stage);
      checkSubmitted();
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
    if (state.editsFor !== state.set.id) {
      state.edits = {}; state.skipped = {}; state.editsFor = state.set.id; state.filled = {};
    }
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
        result(state.filled[a.key], a),
        !locked && !['vault'].includes(a.badge) ? el('label', { class: 'skip' },
          el('input', { type: 'checkbox', checked: !!state.skipped[a.key], onchange: e => { state.skipped[a.key] = e.target.checked; } }),
          "Don't save this one to my answer bank") : null));
    }
    if (!Object.keys(state.filled).length) {
      const empty = answers.filter(a => !['legal', 'file'].includes(a.kind) && !lib.asText(a.key in state.edits ? state.edits[a.key] : a.value).trim()).length;
      $('approve-note').textContent = (empty ? `Fills every answer that has a value; ${empty} empty one${empty === 1 ? '' : 's'} stay${empty === 1 ? 's' : ''} for you. ` : 'Fills these answers into the form. ')
        + 'You check it and click Submit yourself.';
    }
    fillButton();
  }

  const RESULT = { filled: 'Filled on the form', review: 'Filled; check it on the form', preserved: 'Already filled on the form; left as is',
    missing: 'Not filled; fill it yourself', invalid: 'The form rejected this value', skipped: 'Not filled' };
  function result(r, a) {
    if (!r) return null;
    const good = r.outcome === 'filled' || r.outcome === 'preserved';
    const file = a && a.kind === 'file';
    const words = file && r.outcome === 'filled' ? 'Attached your tailored resume'
      : file && r.outcome === 'review' ? 'Attached your tailored resume; check it on the form'
      : file && r.outcome === 'preserved' ? 'A file is already attached; left as is'
      : RESULT[r.outcome] || r.outcome;
    return el('p', { class: `result ${good ? 'ok' : 'check'}` }, words, r.note && !good && !(file && r.outcome === 'review') ? `: ${r.note}` : '');
  }

  async function copy(a) {
    const value = lib.asText(Object.prototype.hasOwnProperty.call(state.edits, a.key) ? state.edits[a.key] : a.value);
    try { await navigator.clipboard.writeText(value); status('Copied.'); } catch (e) { status("Couldn't copy; select the text instead.", true); }
  }

  // Save new and edited answers to your bank, then fill the form in every frame it lives in.
  async function fill() {
    if (state.busy || !state.set || !state.tab) return;
    const plan = lib.fillPlan(state.set.answers, state.edits, state.skipped);
    if (!Object.keys(plan).length) { status('No answers with a value to fill yet.', true); return; }
    busy(true);
    try {
      const approved = lib.approval(state.set.answers, state.edits, state.skipped);
      const saved = await post('/extension/answer-set/approve', { case_id: state.set.case_id, answer_set_id: state.set.id, answers: approved });
      const tabId = state.tab.id;
      const results = [];
      // The tailored resume, only when a resume field is in the plan (the form engine checks its hash again).
      let resume = null;
      const wantsResume = Object.values(plan).some(list => list.some(a => a.value === lib.RESUME));
      if (wantsResume) {
        const r = await post('/extension/resume', { case_id: state.set.case_id });
        if (r.ok) resume = r.data;
        else {
          for (const [frameId, list] of Object.entries(plan)) {
            for (const a of list.filter(x => x.value === lib.RESUME)) results.push({ panelKey: a.panelKey, outcome: 'review', note: detail(r, 'No tailored resume to attach; attach yours yourself.') });
            plan[frameId] = list.filter(x => x.value !== lib.RESUME);
          }
        }
      }
      await chrome.scripting.executeScript({ target: { tabId, allFrames: true }, files: ['content/form-engine.js'] });
      for (const [frameId, answers] of Object.entries(plan)) {
        if (!answers.length) continue;
        const doc = answers.some(a => a.value === lib.RESUME) ? resume : null;
        try {
          const [out] = await chrome.scripting.executeScript({ target: { tabId, frameIds: [Number(frameId)] }, func: lib.fillFrame, args: [answers, doc] });
          results.push(...((out && out.result) || []));
        } catch (e) {
          results.push(...answers.map(a => ({ panelKey: a.panelKey, outcome: 'review', note: 'That part of the form has reloaded. Read the questions again.' })));
        }
      }
      state.filled = Object.fromEntries(results.map(r => [r.panelKey, r]));
      renderAnswers();
      const byKey = Object.fromEntries(state.set.answers.map(a => [a.key, a]));
      const attached = results.some(r => byKey[r.panelKey] && byKey[r.panelKey].kind === 'file' && ['filled', 'review'].includes(r.outcome) && resume);
      post('/extension/fill-report', { case_id: state.set.case_id, url: state.tab.url || '', attached_resume: !!attached,
        results: results.map(r => ({ label: (byKey[r.panelKey] || {}).label || '', outcome: r.outcome })) });
      const n = saved.ok && saved.data ? saved.data.saved : 0;
      $('approve-note').textContent = `${lib.fillSummary(results)}${attached ? ', resume attached' : ''}. ${n ? `${n} new answer${n === 1 ? '' : 's'} saved to your bank. ` : ''}Check the form and click Submit yourself.`;
      status(saved.ok ? '' : detail(saved, "Filled, but couldn't save the answers to your bank."), !saved.ok);
    } catch (e) {
      status("Chrome doesn't let extensions fill this page.", true);
    } finally { busy(false); }
  }

  // Applied: the panel marks the case when it sees the employer's confirmation page, or when you say so.
  const APPLIED = ['applied', 'replied', 'interview', 'offer', 'closed'];
  const caseNow = () => state.page && state.page.case;
  function showApplied(stage) {
    const applied = APPLIED.includes(stage);
    $('job-applied').textContent = applied ? 'Applied. JobDots tracks it from here.' : '';
    $('job-applied').className = applied ? 'quiet done' : 'quiet';
    $('mark-applied').hidden = applied;
    $('undo-applied').hidden = stage !== 'applied';
  }
  async function markApplied(applied, seen) {
    const c = caseNow();
    if (!c) return;
    const r = await post('/extension/case/applied', { case_id: c.id, applied, seen });
    if (!r.ok) { status(detail(r, "Couldn't update the case."), true); return; }
    c.stage = r.data.stage;
    showApplied(c.stage);
    if (!applied) state.noAuto[c.id] = true;      // you said no: stop marking it from the page
    status(applied ? (seen ? 'You submitted it: JobDots saw the confirmation page and marked the case applied.' : 'Marked as applied.')
      : 'Back to ready; not marked as applied.');
  }
  async function checkSubmitted() {
    const c = caseNow();
    if (!c || !state.tab || state.checking || APPLIED.includes(c.stage) || state.noAuto[c.id]) return;
    state.checking = true;
    try {
      const frames = await chrome.scripting.executeScript({ target: { tabId: state.tab.id, allFrames: true }, func: lib.submittedPage });
      if ((frames || []).some(f => f && f.result === true) && caseNow() === c) await markApplied(true, true);
    } catch (e) { /* the page can't be read right now; try again on the next check */ }
    finally { state.checking = false; }
  }
  // After a fill, watch for the confirmation (single-page forms swap content without loading a page).
  setInterval(() => { if (!document.hidden && Object.keys(state.filled).length) checkSubmitted(); }, 3000);
  $('mark-applied').addEventListener('click', () => markApplied(true, false));
  $('undo-applied').addEventListener('click', () => markApplied(false, false));

  // LinkedIn queue: Connector's invitations (and later DMs). You approve each one, open the
  // profile from here (the cap is counted then), paste the copied note, send it yourself on
  // LinkedIn, and say whether you did. The panel never clicks anything on LinkedIn.
  const PROFILE = /^https:\/\/([a-z]{2,3}\.)?(www\.)?linkedin\.com\/in\/[^/?#\s]+\/?$/i;
  const queue = { items: [], edits: {}, busy: false };
  async function loadQueue() {
    const r = await post('/extension/linkedin/queue', {});
    if (!r.ok) return;
    queue.items = r.data.items || [];
    for (const id of Object.keys(queue.edits)) if (!queue.items.some(i => i.id === id)) delete queue.edits[id];
    $('queue').hidden = false;
    const flags = [r.data.kill_switch ? 'The kill switch is on: nothing can be sent.' : '',
      r.data.quiet_hours ? "Quiet hours: sending waits until they're over." : ''].filter(Boolean).join(' ');
    $('queue-usage').textContent = `${lib.usageLine(r.data.usage)}${flags ? ' ' + flags : ''}`;
    $('queue-empty').hidden = queue.items.length > 0;
    renderQueue();
  }
  function queueText(item) { return Object.prototype.hasOwnProperty.call(queue.edits, item.id) ? queue.edits[item.id] : item.text; }
  function renderQueue() {
    const list = $('queue-items');
    list.replaceChildren();
    for (const item of queue.items) {
      const [cls, words] = lib.QUEUE_STATE[item.status] || ['waiting', item.status];
      const editable = ['reviewed', 'approved'].includes(item.status);
      const text = queueText(item);
      const changed = editable && text !== item.text;
      const count = lib.noteCount(text, item.kind);
      const id = `q-${item.id}`;
      const countLine = el('p', { class: `count${count.over ? ' over' : ''}` }, count.text);
      const field = editable
        ? el('textarea', { id, rows: 4, 'aria-label': `${item.kind === 'invite' ? 'Note' : 'Message'} to ${item.name}`,
            oninput: e => {
              queue.edits[item.id] = e.target.value;
              const c = lib.noteCount(e.target.value, item.kind);
              countLine.textContent = c.text; countLine.className = `count${c.over ? ' over' : ''}`;
              if ((e.target.value !== item.text) !== changed) {      // the buttons change: redraw, keep your cursor
                const at = e.target.selectionStart;
                renderQueue();
                const again = $(id);
                if (again) { again.focus(); again.setSelectionRange(at, at); }
              }
            } })
        : el('p', { class: 'note' }, text || '(no note)');
      if (editable) field.value = text;
      const buttons = [];
      if (changed) buttons.push(el('button', { class: 'primary', type: 'button', onclick: () => queueEdit(item) }, 'Save and check again'));
      else if (item.status === 'reviewed') buttons.push(el('button', { class: 'primary', type: 'button', disabled: count.over, onclick: () => queueApprove(item) }, 'Approve'));
      else if (item.status === 'approved') buttons.push(el('button', { class: 'primary', type: 'button', onclick: () => queueOpen(item) }, 'Open profile and copy note'));
      else if (item.status === 'executing') {
        buttons.push(el('button', { class: 'primary', type: 'button', onclick: () => queueDone(item, true) }, 'I sent it'));
        buttons.push(el('button', { class: 'small', type: 'button', onclick: () => queueDone(item, false) }, "I didn't send it"));
        buttons.push(el('button', { class: 'small', type: 'button', onclick: () => queueOpen(item) }, 'Open profile again'));
      }
      if (item.status !== 'executing') buttons.push(el('button', { class: 'small', type: 'button', onclick: () => queueReject(item) }, item.status === 'blocked' ? 'Discard' : 'Reject'));
      list.append(el('li', { class: 'answer' },
        el('p', { class: 'person' }, item.name || 'Someone'),
        el('p', { class: 'person-meta' }, [item.title, item.company].filter(Boolean).join(' at ') + (item.kind === 'dm' ? ' (message)' : ' (invitation)')),
        el('div', { class: 'row' }, el('span', { class: `badge ${cls}` }, words)),
        field, editable ? countLine : null,
        item.blocked ? el('p', { class: 'note result check' }, item.blocked) : null,
        (item.notes || []).length ? el('p', { class: 'note' }, `Reviewer: ${item.notes.join(' ')}`) : null,
        item.status === 'executing' ? el('p', { class: 'howto quiet' }, item.kind === 'invite'
          ? 'On the profile: Connect, then "Add a note", paste (Ctrl+V), Send. Then tell JobDots below.'
          : 'On the profile: Message, paste (Ctrl+V), Send. Then tell JobDots below.') : null,
        el('div', { class: 'actions' }, buttons)));
    }
  }
  async function queueCall(path, body, done) {
    if (queue.busy) return;
    queue.busy = true;
    try {
      const r = await post(path, body);
      if (!r.ok) { status(detail(r, "Couldn't update the queue."), true); return; }
      if (done) done(r.data);
    } finally { queue.busy = false; await loadQueue(); }
  }
  const queueApprove = item => queueCall('/extension/linkedin/approve', { action_id: item.id, payload_sha256: item.payload_sha256 },
    () => status(`Approved. Open ${item.name || 'the profile'} from the queue when you're ready to send it.`));
  const queueReject = item => queueCall('/extension/linkedin/reject', { action_id: item.id }, () => status('Removed from the queue. Nothing was sent.'));
  const queueEdit = item => queueCall('/extension/linkedin/edit', { action_id: item.id, text: queueText(item) }, d => {
    delete queue.edits[item.id];
    status(d.status === 'blocked' ? `The Reviewer blocked the new text: ${d.blocked}` : 'Saved. Check it again and approve it.', d.status === 'blocked');
  });
  async function queueOpen(item) {
    if (!PROFILE.test(item.profile_url || '')) { status("That isn't a LinkedIn profile link; reject it.", true); return; }
    let copied = true;
    try { await navigator.clipboard.writeText(item.text || ''); } catch (e) { copied = false; }
    await queueCall('/extension/linkedin/start', { action_id: item.id }, d => {
      if (!d.ok) { status(`Not now: ${(d.reasons || []).join(' ')}`, true); return; }
      chrome.tabs.create({ url: d.profile_url });
      status(copied ? 'Note copied. Paste it in LinkedIn, send it, then tell JobDots here.' : "Couldn't copy the note; select it in the queue and copy it.", !copied);
    });
  }
  const queueDone = (item, sent) => queueCall('/extension/linkedin/done', { action_id: item.id, sent },
    () => status(sent ? `Recorded: you sent it to ${item.name || 'them'}.` : 'Recorded as not sent.'));
  setInterval(() => { if (!document.hidden && !queue.busy && !document.activeElement?.closest?.('#queue')) loadQueue(); }, 60000);

  $('grant').addEventListener('click', async () => {
    const granted = await chrome.permissions.request(PAGES).catch(() => false);
    if (!granted) status('Without this the panel can’t read job pages.', true);
    refresh();
  });
  $('capture').addEventListener('click', () => capture());
  $('read').addEventListener('click', () => readQuestions());
  $('approve').addEventListener('click', () => fill());
  chrome.tabs.onActivated.addListener(() => { state.set = null; refresh(); });
  chrome.tabs.onUpdated.addListener((id, info) => { if (state.tab && id === state.tab.id && info.status === 'complete') refresh(); });

  (async () => {
    const me = await send({ type: 'api', path: '/extension/me' });
    if (!me.ok) { status(detail(me, 'Not connected. Open JobDots → Settings → Connect extension.'), true); }
    else { $('who').textContent = me.data.name || me.data.email || ''; loadQueue(); }
    refresh();
  })();
})();
