// Supervised form preparation. Employer submission always belongs to the user.
(() => {
  if (window.__jobpilot) return;
  const engine = globalThis.JOBPILOT_FORM_ENGINE;
  if (!engine) return;
  const AMBER = '#b45309';
  const EEO = /\b(gender|race|ethnic|hispanic|latin|veteran|disabilit|sexual orientation|pronoun)/i;
  const send = message => new Promise(resolve => chrome.runtime.sendMessage(message, result => resolve(result || {ok:false})));
  const api = (path, method = 'GET', body) => send({type:'api',path,method,body});
  const {collect, currentValue, clean} = engine;
  const STYLE = `
    :host { all: initial; }
    * { box-sizing: border-box; font-family: -apple-system, "Segoe UI", Roboto, sans-serif; }
    .pill, .card { position: fixed; right: 16px; bottom: 16px; z-index: 2147483647; color: #1f1e1d; }
    .pill { background: #1f1e1d; color: #fff; border: 0; border-radius: 999px; padding: 10px 16px; font-size: 13px; font-weight: 600; cursor: pointer; box-shadow: 0 6px 20px rgba(0,0,0,.25); }
    .card { width: 340px; max-height: 70vh; display: flex; flex-direction: column; background: #fff; border: 1px solid #e7e4de; border-radius: 12px; box-shadow: 0 12px 32px rgba(0,0,0,.2); font-size: 13px; }
    header { display: flex; align-items: center; gap: 8px; padding: 10px 12px; border-bottom: 1px solid #e7e4de; font-weight: 600; }
    header .logo { display: grid; place-items: center; width: 22px; height: 22px; border-radius: 6px; background: #1f1e1d; color: #fff; font-size: 10px; }
    header button { margin-left: auto; border: 0; background: none; cursor: pointer; font-size: 16px; color: #6b6966; }
    .body { padding: 10px 12px; overflow-y: auto; }
    label { display: block; font-size: 11px; color: #6b6966; margin-bottom: 4px; }
    select { width: 100%; padding: 6px; border: 1px solid #dedad3; border-radius: 6px; font-size: 12px; background: #fff; }
    .status { margin: 10px 0 6px; line-height: 1.45; }
    .status.err { color: #c4321f; }
    ul { list-style: none; margin: 0; padding: 0; }
    li { padding: 6px 8px; margin-bottom: 4px; border-radius: 6px; background: #fdf6ec; cursor: pointer; line-height: 1.35; }
    li b { display: block; font-size: 12px; }
    li span { font-size: 11px; color: ${AMBER}; }
    .actions { display: flex; flex-wrap: wrap; gap: 6px; padding: 10px 12px; border-top: 1px solid #e7e4de; }
    .actions button { flex: 1 1 auto; border: 1px solid #dedad3; background: #fff; border-radius: 6px; padding: 7px 8px; font-size: 12px; font-weight: 600; cursor: pointer; }
    .actions button.primary { background: #1f1e1d; border-color: #1f1e1d; color: #fff; }
    .actions button:disabled { opacity: .5; cursor: default; }
    .note { margin: 0; padding: 0 12px 10px; font-size: 11px; color: #6b6966; line-height: 1.4; }
  `;

  const state = { applicationId: null, queue: [], last: null, open: false, session: null, document: null, attempt: null, busy: false, epoch: 0 };
  let host, root;

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => (k === 'class' ? (node.className = v) : k.startsWith('on') ? node.addEventListener(k.slice(2), v) : node.setAttribute(k, v)));
    children.flat().forEach((c) => c != null && node.append(c.nodeType ? c : document.createTextNode(String(c))));
    return node;
  }

  function render(status = '', isError = false) {
    state.status = status; state.statusError = isError;
    root.innerHTML = '';
    root.append(el('style', {}, STYLE));
    if (!state.open) {
      root.append(el('button', { class: 'pill', onclick: event => { if (event.isTrusted) openPanel(false); } }, 'JobPilot · Fill this application'));
      return;
    }
    const options = [el('option', { value: '' }, 'Not linked (profile answers only)'), ...state.queue.map((q) => {
      const o = el('option', { value: q.id }, `${q.role} · ${q.company}`);
      if (q.id === state.applicationId) o.setAttribute('selected', '');
      return o;
    })];
    const flags = (state.last || []).filter((a) => a.flagged);
    root.append(el('div', { class: 'card', role: 'dialog', 'aria-label': 'JobPilot autofill' },
      el('header', {}, el('span', { class: 'logo' }, 'JP'), 'JobPilot', el('button', { 'aria-label': 'Close', onclick: () => { state.open = false; render(); } }, '×')),
      el('div', { class: 'body' },
        el('label', {}, 'Application'),
        el('select', { ...(state.busy ? {disabled:''} : {}), onchange: (e) => { if (!e.isTrusted) return; state.applicationId = e.target.value || null; state.session = null; state.last = null; state.attempt = null; state.document = null; state.epoch++; render('Application changed. Fill again to start a new session.'); } }, options),
        el('div', { class: `status${isError ? ' err' : ''}` }, status),
        flags.length ? el('ul', {}, flags.map((f) => el('li', { onclick: () => focusField(f.key) }, el('b', {}, f.label.slice(0, 90)), el('span', {}, f.note || 'Check this')))) : null,
      ),
      el('div', { class: 'actions' },
        el('button', { class: 'primary', onclick: event => { if (event.isTrusted) fill(); }, ...(state.busy ? {disabled:''} : {}) }, state.last ? 'Read and fill again' : 'Fill form'),
        el('button', { onclick: event => { if (event.isTrusted && !state.busy) saveAnswers(); }, ...(state.last && !state.busy ? {} : { disabled: '' }) }, 'Save my answers'),
        el('button', { onclick: markApplied, ...(state.applicationId && !state.busy ? {} : { disabled: '' }) }, 'Report that I submitted'),
      ),
      el('p', { class: 'note' }, 'Review every field and submit yourself. Selected files are not proof of employer upload acceptance. Browser confirmations and your reports are recorded separately.'),
    ));
  }

  let current = { elements: new Map() };

  function focusField(key) {
    const ref = current.elements.get(key);
    const target = ref && (ref.el || ref.group[0]);
    if (!target) return;
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    if (target.focus) target.focus({ preventScroll: true });
  }

  async function fill() {
    if (state.busy) return;
    state.busy = true;
    const epoch = state.epoch;
    const filledThisTime = new Map();
    try {
      if (state.session && Date.parse(state.session.expires_at) <= Date.now()) { state.session = null; state.document = null; state.attempt = null; }
      render('Reading the form…');
      current = collect();
      if (!current.fields.length) throw Error('No supported fields found. Open the employer’s application form and try again.');
      if (state.applicationId && !state.session) {
        const id = crypto.randomUUID();
        let res = await api('/extension/sessions', 'POST', {id, application_id:state.applicationId, url:location.href});
        if (!res.ok && res.status === 409 && /Confirm that this form/.test(res.data?.detail || '')) {
          const app = state.queue.find(q => q.id === state.applicationId);
          if (!confirm(`Is this form at ${location.hostname} for ${app?.role} at ${app?.company}? Check the company and opening before continuing.`)) return;
          res = await api('/extension/sessions', 'POST', {id, application_id:state.applicationId, url:location.href, link_confirmed:true});
        }
        if (!res.ok) throw Error(res.data?.detail || 'Could not start a preparation session.');
        state.session = res.data.session;
      }
      for (let pass = 0; pass < 3; pass++) {
        current = collect();
        render(`Checking ${current.fields.length} visible controls…`);
        const res = await api('/extension/fill', 'POST', {url:location.href, application_id:state.applicationId, fields:current.fields});
        if (epoch !== state.epoch) return;
        if (!res.ok) throw Error(res.data?.detail || 'Could not prepare answers.');
        if (state.session && res.data.answers.some(a => a.value === '__resume__') && !state.document) {
          const doc = await api('/extension/document', 'POST', {session_id:state.session.id});
          if (doc.ok) state.document = doc.data;
        }
        if (epoch !== state.epoch) return;
        const applied = await engine.apply(res.data.answers, current.elements, state.document, () => epoch === state.epoch);
        if (epoch !== state.epoch) return;
        state.last = applied;
        state.last = state.last.map(answer => {
          const previous = filledThisTime.get(answer.key), ref = current.elements.get(answer.key);
          const expected = previous && (Array.isArray(previous.value) ? previous.value.join(', ') : previous.value);
          if (answer.outcome === 'preserved' && previous && ref && (currentValue(ref) === expected || ref.kind === 'file' && previous.value === '__resume__' && engine.uploads.has(ref.el))) return {...answer,outcome:previous.outcome,source:previous.source,flagged:previous.flagged,note:previous.note};
          if (answer.outcome === 'filled' || answer.source === 'ai' && answer.outcome === 'review') filledThisTime.set(answer.key, answer);
          return answer;
        });
        const fresh = collect();
        if (fresh.fields.every(f => current.elements.has(f.key))) break;
      }
      state.last = await engine.audit(state.last || [], current.elements);
      const latest = collect();
      const unseen = latest.fields.filter(f => !current.elements.has(f.key));
      if (unseen.length) {
        current.elements = new Map([...current.elements, ...latest.elements]);
        state.last.push(...unseen.map(f => ({...f, value:null, source:'none', flagged:true, outcome:'review', note:'New question appeared. Read and fill again.'})));
      }
      let saved = true;
      if (state.session) {
        const selectedHash = [...current.elements.values()].some(r => engine.uploads.get(r.el) === state.document?.sha256 && r.el.files?.length) ? state.document?.sha256 : null;
        const event = await send({type:'execution-event', body:{session_id:state.session.id, request_key:crypto.randomUUID(), kind:'form_prepared', details:{url:location.href, truncated:latest.truncated, document_sha256:selectedHash, fields:state.last.slice(0,150).map(a => ({key:a.key,type:a.type,required:a.required,outcome:a.outcome,source:a.outcome === 'preserved' ? 'user' : a.source}))}}});
        saved = event.ok;
        if (!saved && [404,409,422].includes(event.status)) { state.session = null; state.document = null; state.attempt = null; }
      }
      const filled = state.last.filter(a => a.outcome === 'filled').length;
      const preserved = state.last.filter(a => a.outcome === 'preserved').length;
      const need = state.last.filter(a => a.flagged).length;
      render(`${filled} filled and checked; ${preserved} existing entries preserved. ${need} need review.${latest.truncated ? ' Only the first 150 controls were inspected; review the remaining form yourself.' : ''}${!saved ? ' Evidence not saved yet; reconnect and read/fill again to recover.' : ''}`);
    } catch (error) { render(error.message || 'Preparation failed. Review the form yourself.', true); }
    finally { state.busy = false; render(state.status, state.statusError); }
  }

  async function saveAnswers() {
    if (!state.last) return;
    const answers = [];
    for (const a of state.last) {
      if (!(a.flagged || a.source === 'none') || EEO.test(a.label) || a.type === 'file') continue;
      if (/agree|consent|acknowledg|arbitrat|terms|privacy|certif/i.test(a.label)) continue;
      const ref = current.elements.get(a.key);
      const value = ref ? currentValue(ref) : '';
      if (value) answers.push({ question: a.label.slice(0, 500), answer: value.slice(0, 4000) });
    }
    if (!answers.length) return render('Type your answers into the amber fields first, then save them for next time.');
    const res = await api('/extension/answers', 'POST', { answers });
    render(res.ok ? `Saved ${res.data.saved} answer${res.data.saved === 1 ? '' : 's'} to your answer bank. Next time they fill automatically.` : res.data?.detail || 'Saving failed', !res.ok);
  }

  async function markApplied(event) {
    if (!event?.isTrusted) return;
    if (!state.applicationId) return;
    if (!confirm('Did you click Submit on this application? JobPilot will move it to Applied and remind you to follow up in 5 days.')) return;
    const res = await api('/extension/applied', 'POST', { application_id: state.applicationId, session_id:state.session?.id, request_key:crypto.randomUUID() });
    render(res.ok ? 'Saved as user-reported submitted. Employer acceptance has not been independently verified.' : res.data?.detail || 'Update failed', !res.ok);
  }

  async function openPanel(autoFill) {
    state.open = true;
    render('Connecting to JobPilot…');
    const [queue, match, pending] = await Promise.all([api('/extension/queue'), api('/extension/match', 'POST', { url: location.href, title: document.title }), send({type:'execution-context'})]);
    if (!queue.ok) return render(queue.data?.detail || 'Not connected to JobPilot.', true);
    state.queue = queue.data.queue || [];
    if (pending.ok && pending.context) { state.session = pending.context.session; state.applicationId = state.session.application_id; state.attempt = pending.context.attempt; if (pending.context.application && !state.queue.some(q => q.id === state.applicationId)) state.queue.unshift(pending.context.application); }
    const matched = match.ok && match.data.application;
    if (matched && !state.session) {
      state.applicationId = matched.id;
      if (!state.queue.some((q) => q.id === matched.id)) state.queue.unshift(matched);
    }
    render(matched ? `Linked to ${matched.role} at ${matched.company}.` : 'Pick the application this form is for (or fill from your profile only).');
    if (autoFill) fill();
  }

  function mount() {
    host = document.createElement('div');
    host.id = 'jobpilot-root';
    root = host.attachShadow({ mode: 'open' });
    document.documentElement.append(host);
    render();
  }

  function looksLikeApplication() {
    return collect().fields.length > 0;
  }

  window.__jobpilot = {
    open: (autoFill = false) => {
      if (!host) mount();
      openPanel(autoFill);
    },
  };

  let userIntent = null;
  const finalSubmit = button => !!button && /^(submit(?: (?:my|your|this))?(?: application)?|send application|apply(?: now)?|complete application|finish application)$/i.test(clean(button.getAttribute('aria-label') || button.textContent || button.value));
  chrome.runtime.onMessage.addListener((message,sender) => {
    if (sender.id !== chrome.runtime.id || message.type !== 'jobpilot-connection-changed') return;
    state.epoch++; state.applicationId = null; state.queue = []; state.session = null; state.document = null; state.last = null; state.attempt = null;
    if (host) render('Account connection changed. Reopen this form to continue.',true);
  });
  document.addEventListener('click', event => {
    if (!event.isTrusted) return;
    const button = event.target.closest?.('button,input[type="submit"]');
    if (button?.form && (button.type || 'submit') === 'submit') userIntent = finalSubmit(button) ? {form:button.form, at:Date.now()} : null;
  }, true);
  document.addEventListener('keydown', event => {
    if (event.isTrusted && event.key === 'Enter' && event.target.form && event.target.tagName !== 'TEXTAREA') userIntent = {form:event.target.form, at:Date.now()};
  }, true);
  document.addEventListener('submit', async event => {
    if (!event.isTrusted || !state.session || !userIntent || userIntent.form !== event.target || Date.now() - userIntent.at > 2500 || !state.last) return;
    if (!finalSubmit(event.submitter || event.target.querySelector('button[type="submit"],input[type="submit"],button:not([type])'))) return;
    userIntent = null;
    const request_key = crypto.randomUUID();
    const res = await send({type:'execution-event',body:{session_id:state.session.id,request_key,kind:'submission_attempted',details:{url:location.href}}});
    // Pending metadata is also persisted by the broker before the network call.
    state.attempt = {key:request_key, at:Date.now()};
    if (!res.ok) render('Submission attempt observed; evidence is waiting for reconnection. This does not prove acceptance.');
    checkConfirmation();
  }, true);
  let checking = false;
  async function checkConfirmation() {
    if (checking || !state.session || !state.attempt || Date.now() - state.attempt.at > 15*60*1000) return;
    const rule = engine.confirmationFor();
    if (!rule) return;
    checking = true;
    const result = await send({type:'execution-event',body:{session_id:state.session.id,request_key:crypto.randomUUID(),kind:'submission_confirmation_observed',details:{url:location.href,attempt_key:state.attempt.key,rule}}});
    if (result.ok) { state.attempt = null; if (!host) mount(); state.open = true; render('Confirmation observed in this browser. It is not independently verified. You can report submission to update your application status.'); }
    checking = false;
  }
  let timer;
  new MutationObserver(mutations => {
    if (mutations.every(m => m.target === host || host?.contains(m.target))) return;
    clearTimeout(timer); timer = setTimeout(checkConfirmation, 350);
  }).observe(document.documentElement, {childList:true,subtree:true});
  send({type:'execution-context'}).then(pending => {
    if (pending.ok && pending.context) { state.session = pending.context.session; state.applicationId = state.session.application_id; state.attempt = pending.context.attempt; if (pending.context.application) state.queue = [pending.context.application]; checkConfirmation(); }
  });

  // On known job boards, offer the launcher once the form has rendered (they're single-page apps).
  let tries = 0;
  const wait = setInterval(() => {
    tries += 1;
    if (looksLikeApplication()) {
      clearInterval(wait);
      if (!host) mount();
    } else if (tries > 20) clearInterval(wait);
  }, 750);
})();
