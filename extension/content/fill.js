// JobPilot extension — fills the application form on this page.
//
// Reads the form's fields, asks JobPilot for answers (profile, saved answers,
// tailored resume and cover letter, flagged AI drafts), fills empty fields, and
// shows what still needs you. It never clicks Submit: you review and submit.

(() => {
  if (window.__jobpilot) return;

  const GREEN = '#0f7b6c';
  const AMBER = '#b45309';
  const SKIP_INPUTS = new Set(['hidden', 'submit', 'button', 'image', 'reset', 'search', 'password']);
  const EEO = /\b(gender|race|ethnic|hispanic|latin|veteran|disabilit|sexual orientation|pronoun)/i;

  const send = (message) => new Promise((resolve) => chrome.runtime.sendMessage(message, resolve));
  const api = (path, method = 'GET', body) => send({ type: 'api', path, method, body });
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const clean = (t) => (t || '').replace(/\s+/g, ' ').replace(/\s*[*✱]\s*$/, '').trim();

  // --- Reading the form -------------------------------------------------------------

  function visible(el) {
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && (rect.width > 0 || rect.height > 0);
  }

  function textOf(node) {
    return clean(node ? node.innerText || node.textContent : '');
  }

  function labelFor(el) {
    if (el.id) {
      const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (textOf(l)) return textOf(l);
    }
    const aria = el.getAttribute('aria-label');
    if (aria && clean(aria)) return clean(aria);
    const by = el.getAttribute('aria-labelledby');
    if (by) {
      const t = clean(by.split(/\s+/).map((id) => document.getElementById(id)?.innerText || '').join(' '));
      if (t) return t;
    }
    const wrap = el.closest('label');
    if (textOf(wrap)) return textOf(wrap);
    return containerLabel(el) || clean(el.placeholder || el.name || '');
  }

  // The question text near a control: Lever's .application-label, Greenhouse/Ashby labels, legends.
  function containerLabel(el, exclude = [], raw = false) {
    const legend = el.closest('fieldset')?.querySelector('legend');
    if (textOf(legend)) return raw ? legend.innerText : textOf(legend);
    let node = el.parentElement;
    const own = new Set([el, ...exclude]);
    for (let depth = 0; depth < 6 && node; depth++, node = node.parentElement) {
      // Stop at the first ancestor that also holds other questions' controls.
      const others = [...node.querySelectorAll('input:not([type=hidden]), textarea, select')].some((c) => !own.has(c));
      if (others) break;
      const candidates = node.querySelectorAll('label, legend, .application-label, [class*="label"], [class*="question"], [class*="heading"]');
      for (const c of candidates) {
        if (c.contains(el) || exclude.some((x) => c.contains(x) || x.contains?.(c))) continue;
        const t = textOf(c);
        if (t && t.length < 500) return raw ? c.innerText : t;
      }
    }
    return '';
  }

  const optionLabel = (el) => {
    if (el.id) {
      const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (textOf(l)) return textOf(l);
    }
    return textOf(el.closest('label')) || clean(el.value);
  };

  function isRequired(el, rawLabel) {
    return el.required || el.getAttribute('aria-required') === 'true' || /[*✱]/.test(rawLabel || '');
  }

  function rawLabelText(el) {
    if (el.id) {
      const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l) return l.innerText;
    }
    return el.closest('label')?.innerText || '';
  }

  function collect() {
    const fields = [];
    const elements = new Map();
    const groups = new Set();
    const controls = [...document.querySelectorAll('input, textarea, select')].filter((el) => !el.closest('#jobpilot-root'));

    controls.forEach((el) => {
      const type = (el.getAttribute('type') || el.tagName).toLowerCase();
      if (el.tagName === 'INPUT' && SKIP_INPUTS.has(type)) return;
      if (el.disabled) return;
      if (type !== 'file' && !visible(el)) return;

      const key = `jp-${fields.length}`;
      if (type === 'radio' || type === 'checkbox') {
        const name = el.name || el.id;
        if (groups.has(type + name)) return;
        groups.add(type + name);
        const group = name ? controls.filter((c) => c.type === type && (c.name || c.id) === name) : [el];
        const single = type === 'checkbox' && group.length === 1;
        const label = single ? labelFor(el) : containerLabel(el, group) || labelFor(el);
        elements.set(key, { kind: type, group });
        fields.push({
          key, label, type: single ? 'checkbox' : type,
          required: group.some((g) => isRequired(g, '')) || /[*✱]/.test(containerLabel(el, group, true)),
          options: group.map(optionLabel),
        });
        return;
      }

      const kind = el.tagName === 'TEXTAREA' ? 'textarea'
        : el.tagName === 'SELECT' ? 'select'
        : el.getAttribute('role') === 'combobox' ? 'combobox'
        : type;
      const options = kind === 'select'
        ? [...el.options].filter((o, i) => !(i === 0 && (o.value === '' || /^(select|choose|--|please)/i.test(o.text)))).map((o) => clean(o.text))
        : [];
      const label = labelFor(el);
      if (!label) return;
      elements.set(key, { kind, el });
      fields.push({
        key, label,
        type: ['email', 'tel', 'url', 'number', 'date', 'textarea', 'select', 'file'].includes(kind) ? kind : kind === 'combobox' ? 'select' : 'text',
        required: isRequired(el, rawLabelText(el) || containerLabel(el, [], true)),
        options,
      });
    });
    return { fields, elements };
  }

  // --- Filling ------------------------------------------------------------------------

  function setValue(el, value) {
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, value);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.dispatchEvent(new Event('blur', { bubbles: true }));
  }

  const same = (a, b) => clean(a).toLowerCase() === clean(b).toLowerCase();
  const loose = (a, b) => same(a, b) || clean(a).toLowerCase().startsWith(clean(b).toLowerCase());

  function mark(el, flagged, note) {
    const target = el.type === 'file' && !visible(el) ? el.parentElement : el;
    if (!target) return;
    target.style.outline = `2px solid ${flagged ? AMBER : GREEN}`;
    target.style.outlineOffset = '2px';
    if (note) target.title = `JobPilot: ${note}`;
  }

  async function pickCombobox(el, value) {
    el.focus();
    el.click();
    setValue(el, value);
    await sleep(450);
    const options = [...document.querySelectorAll('[role="option"]')];
    const choice = options.find((o) => same(o.innerText, value)) || options.find((o) => loose(o.innerText, value));
    if (!choice) {
      setValue(el, '');
      el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      return false;
    }
    choice.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    choice.click();
    await sleep(100);
    return true;
  }

  async function attachResume(el, applicationId) {
    if (!applicationId) return 'Link this page to an application to attach its tailored resume.';
    if (el.files && el.files.length) return null;
    const res = await send({ type: 'resume', applicationId });
    if (!res || !res.ok) return (res && res.detail) || 'Attach your resume yourself.';
    const bytes = Uint8Array.from(atob(res.base64), (c) => c.charCodeAt(0));
    const transfer = new DataTransfer();
    transfer.items.add(new File([bytes], res.name, { type: 'application/pdf' }));
    el.files = transfer.files;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return null;
  }

  async function apply(answers, elements, applicationId) {
    const results = [];
    for (const a of answers) {
      const ref = elements.get(a.key);
      if (!ref) continue;
      let flagged = a.flagged;
      let note = a.note;
      const values = Array.isArray(a.value) ? a.value : a.value == null ? [] : [String(a.value)];
      try {
        if (ref.kind === 'radio' || ref.kind === 'checkbox') {
          for (const v of values) {
            const box = ref.group.find((g) => same(optionLabel(g), v)) || ref.group.find((g) => loose(optionLabel(g), v)) || (ref.group.length === 1 ? ref.group[0] : null);
            if (box && !box.checked) box.click();
          }
          ref.group.forEach((g) => mark(g.closest('label') || g, flagged, note));
        } else if (ref.kind === 'file') {
          if (a.value === '__resume__') {
            const problem = await attachResume(ref.el, applicationId);
            if (problem) [flagged, note] = [true, problem];
          }
          mark(ref.el, flagged, note);
        } else if (values.length && !ref.el.value) {
          if (ref.kind === 'select') {
            const opt = [...ref.el.options].find((o) => same(o.text, values[0])) || [...ref.el.options].find((o) => loose(o.text, values[0]));
            if (opt) setValue(ref.el, opt.value);
            else [flagged, note] = [true, 'Pick an option'];
          } else if (ref.kind === 'combobox') {
            if (!(await pickCombobox(ref.el, values[0]))) [flagged, note] = [true, `Choose “${values[0]}” (or the closest option)`];
          } else {
            setValue(ref.el, values[0]);
          }
          mark(ref.el, flagged, note);
        } else {
          mark(ref.el, flagged || (a.required && !ref.el.value), note);
        }
      } catch (e) {
        [flagged, note] = [true, 'Fill this one yourself'];
      }
      results.push({ ...a, flagged, note });
    }
    return results;
  }

  function currentValue(ref) {
    if (ref.kind === 'radio' || ref.kind === 'checkbox') return ref.group.filter((g) => g.checked).map(optionLabel).join(', ');
    if (ref.kind === 'select') return ref.el.selectedIndex > 0 || ref.el.value ? clean(ref.el.options[ref.el.selectedIndex]?.text) : '';
    if (ref.kind === 'file') return '';
    return clean(ref.el.value);
  }

  // --- Panel ---------------------------------------------------------------------------

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

  const state = { applicationId: null, queue: [], last: null, open: false };
  let host, root;

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => (k === 'class' ? (node.className = v) : k.startsWith('on') ? node.addEventListener(k.slice(2), v) : node.setAttribute(k, v)));
    children.flat().forEach((c) => c != null && node.append(c.nodeType ? c : document.createTextNode(String(c))));
    return node;
  }

  function render(status = '', isError = false) {
    root.innerHTML = '';
    root.append(el('style', {}, STYLE));
    if (!state.open) {
      root.append(el('button', { class: 'pill', onclick: () => openPanel(false) }, 'JobPilot · Fill this application'));
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
        el('select', { onchange: (e) => { state.applicationId = e.target.value || null; } }, options),
        el('div', { class: `status${isError ? ' err' : ''}` }, status),
        flags.length ? el('ul', {}, flags.map((f) => el('li', { onclick: () => focusField(f.key) }, el('b', {}, f.label.slice(0, 90)), el('span', {}, f.note || 'Check this')))) : null,
      ),
      el('div', { class: 'actions' },
        el('button', { class: 'primary', onclick: fill }, state.last ? 'Fill again' : 'Fill form'),
        el('button', { onclick: saveAnswers, ...(state.last ? {} : { disabled: '' }) }, 'Save my answers'),
        el('button', { onclick: markApplied, ...(state.applicationId ? {} : { disabled: '' }) }, 'I submitted it'),
      ),
      el('p', { class: 'note' }, 'JobPilot never clicks Submit. Green fields are filled, amber need you. Check everything, then submit yourself.'),
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
    render('Reading the form…');
    current = collect();
    if (!current.fields.length) return render('No form fields found on this page. Open the application form (often an “Apply” button) and try again.', true);
    render(`Getting answers for ${current.fields.length} fields…`);
    const res = await api('/extension/fill', 'POST', { url: location.href, application_id: state.applicationId, fields: current.fields });
    if (!res.ok) return render(res.data?.detail || `JobPilot error (${res.status})`, true);
    state.last = await apply(res.data.answers, current.elements, state.applicationId);
    const filled = state.last.filter((a) => a.value != null && a.value !== '' && !(a.flagged && a.value == null)).length;
    const need = state.last.filter((a) => a.flagged).length;
    render(`Filled ${filled} of ${state.last.length} fields.${need ? ` ${need} need you:` : ' Check them, then submit.'}`);
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

  async function markApplied() {
    if (!state.applicationId) return;
    if (!confirm('Did you click Submit on this application? JobPilot will move it to Applied and remind you to follow up in 5 days.')) return;
    const res = await api('/extension/applied', 'POST', { application_id: state.applicationId });
    render(res.ok ? 'Marked as applied in JobPilot. Follow-up reminder set for 5 days from now. Good luck!' : res.data?.detail || 'Update failed', !res.ok);
  }

  async function openPanel(autoFill) {
    state.open = true;
    render('Connecting to JobPilot…');
    const [queue, match] = await Promise.all([api('/extension/queue'), api('/extension/match', 'POST', { url: location.href, title: document.title })]);
    if (!queue.ok) return render(queue.data?.detail || 'Not connected to JobPilot.', true);
    state.queue = queue.data.queue || [];
    const matched = match.ok && match.data.application;
    if (matched) {
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
    return [...document.querySelectorAll('input:not([type=hidden]), textarea, select')].length >= 3 || document.querySelector('input[type=file]');
  }

  window.__jobpilot = {
    open: (autoFill = false) => {
      if (!host) mount();
      openPanel(autoFill);
    },
  };

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
