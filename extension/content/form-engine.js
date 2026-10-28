// Runs in the extension's isolated world. Never invokes submit/requestSubmit.
(() => {
  if (globalThis.JOBPILOT_FORM_ENGINE) return;
  const clean = v => String(v || '').replace(/\s+/g, ' ').replace(/\s*[*✱]\s*$/, '').trim();
  const same = (a, b) => clean(a).toLowerCase() === clean(b).toLowerCase();
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const ids = new WeakMap(); let sequence = 0;
  const uploads = new WeakMap();
  const controlSelector = 'input,textarea,select,[role="combobox"],[role="checkbox"],[role="radio"]';
  const legal = /\b(agree|agreement|consent|acknowledg\w*|arbitrat\w*|terms|privacy|attest|signature|certify|truthful|accurate and complete)\b/i;
  const visible = node => !!node?.isConnected && !node.closest('[hidden],[inert],[aria-hidden="true"]') && getComputedStyle(node).display !== 'none' && getComputedStyle(node).visibility !== 'hidden' && node.getClientRects().length > 0;
  const text = node => clean(node?.innerText || node?.textContent);
  function labelText(node) {
    if (!node) return '';
    const clone = node.cloneNode(true);
    clone.querySelectorAll(controlSelector + ',[role="listbox"]').forEach(n => n.remove());
    return clean(clone.textContent);
  }
  function labelFor(node) {
    const direct = [...(node.labels || [])].map(labelText).filter(Boolean).join(' ');
    const aria = (node.getAttribute('aria-labelledby') || '').split(/\s+/).map(id => text(document.getElementById(id))).filter(Boolean).join(' ');
    if (direct || aria || node.getAttribute('aria-label')) return clean(direct || aria || node.getAttribute('aria-label'));
    const legend = node.closest('fieldset')?.querySelector('legend');
    return labelText(node.closest('label')) || text(legend) || clean(node.placeholder || node.name);
  }
  function groupLabel(node, group) {
    const ariaGroup = node.closest('[role="radiogroup"],[role="group"]');
    if (ariaGroup && labelFor(ariaGroup)) return labelFor(ariaGroup);
    const legend = node.closest('fieldset')?.querySelector('legend');
    if (text(legend)) return text(legend);
    let p = node.parentElement;
    for (let i = 0; i < 5 && p; i++, p = p.parentElement) {
      if ([...p.querySelectorAll(controlSelector)].some(n => !group.includes(n))) break;
      const label = [...p.querySelectorAll('legend,.application-label,[data-question-label],label')].find(n => !group.some(g => n.contains(g) || n.htmlFor === g.id));
      if (text(label)) return text(label);
    }
    return labelFor(node);
  }
  const optionLabel = node => text(node.labels?.[0]) || text(node.closest('label')) || clean(node.getAttribute('aria-label') || node.value || node.textContent);
  const checked = node => node.getAttribute('role') ? node.getAttribute('aria-checked') === 'true' : node.checked;
  const key = node => { if (!ids.has(node)) ids.set(node, `jp-${++sequence}`); return ids.get(node); };
  function optionsFor(node) {
    const ids = (node.getAttribute('aria-controls') || node.getAttribute('aria-owns') || '').split(/\s+/).filter(Boolean);
    const containers = ids.map(id => document.getElementById(id)).filter(Boolean);
    return containers.flatMap(n => [...n.querySelectorAll('[role="option"]')]).filter(n => visible(n) && n.getAttribute('aria-disabled') !== 'true');
  }
  function collect() {
    const fields = [], elements = new Map(), grouped = new Set();
    let truncated = false;
    const controls = [...document.querySelectorAll(controlSelector)].filter(n => !n.closest('#jobpilot-root') && !n.disabled && !n.matches(':disabled') && !n.closest('[inert]'));
    for (const node of controls) {
      if (fields.length >= 150) { truncated = true; break; }
      const type = (node.getAttribute('type') || node.tagName).toLowerCase();
      if (node.tagName === 'INPUT' && (/^(hidden|submit|button|image|reset|password)$/.test(type) || type === 'search' && node.getAttribute('role') !== 'combobox')) continue;
      if (node.closest('[role="combobox"]') !== (node.getAttribute('role') === 'combobox' ? node : null)) continue;
      if (!visible(node) && !(type === 'file' && !node.closest('[hidden],[aria-hidden="true"]') && (visible(node.parentElement) || [...(node.labels || [])].some(visible)))) continue;
      const role = node.getAttribute('role');
      const kind = /^(checkbox|radio)$/.test(role) ? role : node.tagName === 'TEXTAREA' ? 'textarea' : node.tagName === 'SELECT' ? 'select' : role === 'combobox' ? 'combobox' : type;
      let group;
      if (kind === 'checkbox' || kind === 'radio') {
        if (grouped.has(node)) continue;
        const ariaGroup = role && node.closest('[role="radiogroup"],[role="group"]');
        group = controls.filter(n => n.form === node.form && (n.type === kind || n.getAttribute('role') === kind) && (ariaGroup ? n.closest('[role="radiogroup"],[role="group"]') === ariaGroup : node.name ? n.name === node.name : n === node) && visible(n));
        group.forEach(n => grouped.add(n));
      }
      const label = group?.length > 1 ? groupLabel(node, group) : labelFor(node);
      if (!label) continue;
      const required = (group || [node]).some(n => n.required || n.getAttribute('aria-required') === 'true') || node.closest('[role="radiogroup"],[role="group"]')?.getAttribute('aria-required') === 'true' || /[*✱]/.test(node.labels?.[0]?.textContent || node.closest('fieldset')?.querySelector('legend')?.textContent || '');
      const fieldKey = key(node);
      const options = kind === 'select' ? [...node.options].filter(o => !o.matches(':disabled') && o.value !== '').map(o => clean(o.text)) : kind === 'combobox' ? optionsFor(node).map(text) : group ? group.map(optionLabel) : [];
      fields.push({ key: fieldKey, label: label.slice(0, 1000), type: kind === 'combobox' ? 'select' : node.multiple ? 'multiselect' : ['email', 'tel', 'url', 'number', 'date', 'textarea', 'select', 'file', 'checkbox', 'radio'].includes(kind) ? kind : 'text', required, options: options.slice(0, 300) });
      elements.set(fieldKey, { kind, el: node, group });
    }
    return { fields, elements, truncated };
  }
  function value(ref) {
    if (ref.group) return ref.group.filter(checked).map(optionLabel).join(', ');
    if (ref.kind === 'file') return ref.el.files?.[0]?.name || '';
    if (ref.kind === 'select') return [...ref.el.selectedOptions].filter(o => o.value !== '' && !o.disabled).map(o => clean(o.text)).join(', ');
    if (ref.kind === 'combobox' && ref.el.tagName !== 'INPUT') return ref.el.getAttribute('data-value') || text(ref.el).replace(/^(select|choose).*$/i, '');
    return clean(ref.el.value);
  }
  function invalid(ref) {
    return (ref.group || [ref.el]).some(n => !n.isConnected || n.getAttribute('aria-invalid') === 'true' || (n.maxLength >= 0 && String(n.value || '').length > n.maxLength) || (n.willValidate && !n.validity.valid));
  }
  function setValue(node, input) {
    const proto = node.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : node.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(node, input);
    node.dispatchEvent(new Event('input', { bubbles: true }));
    node.dispatchEvent(new Event('change', { bubbles: true }));
    node.dispatchEvent(new Event('blur', { bubbles: true }));
  }
  function exact(options, target, label = text) {
    const matches = options.filter(o => same(label(o), target));
    return matches.length === 1 ? matches[0] : null;
  }
  async function combo(node, target, isCurrent) {
    node.focus(); node.click();
    if (node.tagName === 'INPUT') setValue(node, target);
    let choice;
    for (let i = 0; i < 12; i++) {
      await wait(100);
      if (!isCurrent()) throw Error('Connection changed. Reopen the form.');
      choice = exact(optionsFor(node), target);
      if (choice) break;
    }
    if (!choice) {
      if (node.tagName === 'INPUT') setValue(node, '');
      node.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      throw Error('No unique exact option in this control. Choose it yourself.');
    }
    choice.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })); choice.click();
    await wait(150);
    if (node.getAttribute('aria-expanded') === 'true' || !same(value({ kind: 'combobox', el: node }), target)) throw Error('Option selection was not confirmed. Choose it yourself.');
  }
  const hash = async bytes => [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(n => n.toString(16).padStart(2, '0')).join('');
  async function attach(node, document, isCurrent) {
    if (!document) throw Error('No frozen tailored PDF. Link an application or attach the file yourself.');
    const accepts = (node.accept || '').toLowerCase().split(',').map(s => s.trim()).filter(Boolean);
    if (accepts.length && !accepts.some(s => ['.pdf', 'application/pdf', '*/*'].includes(s))) throw Error('This field does not accept PDF. Attach an allowed format yourself.');
    const bytes = Uint8Array.from(atob(document.pdf_base64), c => c.charCodeAt(0));
    if (bytes.length !== document.size_bytes || bytes.length > 2097152 || new TextDecoder().decode(bytes.slice(0, 5)) !== '%PDF-' || await hash(bytes) !== document.sha256) throw Error('PDF integrity check failed. Nothing was attached.');
    const transfer = new DataTransfer();
    transfer.items.add(new File([bytes], document.name, { type: 'application/pdf' }));
    if (!isCurrent()) throw Error('Connection changed. Reopen the form.');
    node.files = transfer.files;
    node.dispatchEvent(new Event('input', { bubbles: true })); node.dispatchEvent(new Event('change', { bubbles: true }));
    await wait(300);
    if (node.files?.length !== 1 || await hash(await node.files[0].arrayBuffer()) !== document.sha256) throw Error('The form did not retain the PDF. Attach it yourself.');
    uploads.set(node, document.sha256);
  }
  async function audit(results, elements) {
    return Promise.all(results.map(async answer => {
      const ref = elements.get(answer.key);
      let outcome = answer.outcome, note = answer.note;
      if (!ref || !ref.el.isConnected) [outcome, note] = ['review', 'The form changed. Read the new fields and fill again.'];
      else if (invalid(ref)) [outcome, note] = ['invalid', ref.el.validationMessage || 'The form reports an invalid value. Review it.'];
      else if (!value(ref)) outcome = answer.required ? 'missing' : outcome === 'review' ? 'review' : 'skipped';
      if (ref && outcome === 'filled' && ref.kind !== 'file') {
        const expected = Array.isArray(answer.value) ? answer.value.map(clean).sort().join(', ') : clean(answer.value);
        const actual = ref.group ? ref.group.filter(checked).map(optionLabel).map(clean).sort().join(', ') : ref.kind === 'select' && ref.el.multiple ? [...ref.el.selectedOptions].map(o => clean(o.text)).sort().join(', ') : value(ref);
        if (actual !== expected) [outcome, note] = ['review', 'The form changed the proposed value. Check the actual entry.'];
      }
      if (ref?.kind === 'file' && uploads.has(ref.el)) {
        const file = ref.el.files?.[0];
        if (!file || file.size > 2097152 || await hash(await file.arrayBuffer()) !== uploads.get(ref.el)) {
          uploads.delete(ref.el); [outcome, note] = ['review', 'The selected PDF changed after filling. Review the attachment.'];
        }
      }
      if (ref && outcome === 'filled' && ref.kind === 'combobox' && ref.el.getAttribute('aria-expanded') === 'true') [outcome, note] = ['review', 'Finish choosing an option.'];
      const flagged = ['review', 'missing', 'invalid'].includes(outcome) || answer.flagged;
      if (ref) {
        const target = visible(ref.el) ? ref.el : ref.el.parentElement;
        if (target) { target.style.outline = `2px solid ${flagged ? '#b45309' : '#0f7b6c'}`; target.style.outlineOffset = '2px'; }
      }
      return { ...answer, outcome, note, flagged };
    }));
  }
  async function apply(answers, elements, document, isCurrent = () => true) {
    const results = [];
    for (const answer of answers) {
      if (!isCurrent()) return results;
      const ref = elements.get(answer.key);
      if (!ref) continue;
      let outcome = 'skipped', note = answer.note;
      const values = Array.isArray(answer.value) ? answer.value : answer.value == null ? [] : [String(answer.value)];
      try {
        if (value(ref)) {
          outcome = 'preserved';
          if (ref.kind === 'file' && document) {
            if (ref.el.files[0].size > 2097152 || await hash(await ref.el.files[0].arrayBuffer()) !== document.sha256) { outcome = 'review'; note = 'Existing file preserved; it differs from this session’s tailored PDF.'; }
            else uploads.set(ref.el, document.sha256);
          }
        } else if (legal.test(answer.label)) { outcome = 'review'; note = 'Read and answer this agreement yourself.'; }
        else if (ref.el.readOnly) { outcome = 'review'; note = 'Read-only field. Fill through the employer’s control.'; }
        else if (values.length) {
          if (ref.kind === 'file' && answer.value === '__resume__') await attach(ref.el, document, isCurrent);
          else if (ref.group) {
            const choices = values.map(v => exact(ref.group, v, optionLabel));
            if (choices.some(c => !c)) throw Error('No unique exact option. Choose it yourself.');
            for (const choice of choices) { if (!checked(choice)) choice.click(); }
            if (choices.some(c => !checked(c))) throw Error('The control did not retain its selection.');
          } else if (ref.kind === 'select') {
            const choices = values.map(v => exact([...ref.el.options].filter(o => !o.matches(':disabled')), v, o => o.text));
            if (choices.some(c => !c)) throw Error('No unique exact option. Choose it yourself.');
            if (ref.el.multiple) { choices.forEach(c => { c.selected = true; }); ref.el.dispatchEvent(new Event('change', { bubbles: true })); }
            else setValue(ref.el, choices[0].value);
          } else if (ref.kind === 'combobox') await combo(ref.el, values[0], isCurrent);
          else setValue(ref.el, values[0]);
          outcome = answer.flagged ? 'review' : 'filled';
          if (ref.kind === 'file') note = 'Frozen PDF selected in the browser; employer upload acceptance is not verified.';
        }
      } catch (error) { outcome = 'review'; note = error.message || 'Fill this field yourself.'; }
      results.push({ ...answer, outcome, note });
    }
    await wait(350);
    return audit(results, elements);
  }
  const confirmationRules = {
    'boards.greenhouse.io': ['greenhouse_confirmation', '#application_confirmation,[data-testid="application-confirmation"]'],
    'job-boards.greenhouse.io': ['greenhouse_confirmation', '#application_confirmation,[data-testid="application-confirmation"]'],
    'job-boards.eu.greenhouse.io': ['greenhouse_confirmation', '#application_confirmation,[data-testid="application-confirmation"]'],
    'jobs.lever.co': ['lever_confirmation', '.application-confirmation,[data-testid="application-confirmation"]'],
    'jobs.eu.lever.co': ['lever_confirmation', '.application-confirmation,[data-testid="application-confirmation"]'],
    'jobs.ashbyhq.com': ['ashby_confirmation', '[data-testid="application-confirmation"],[data-application-confirmation]'],
    'jobs.smartrecruiters.com': ['smartrecruiters_confirmation', '[data-testid="application-confirmation"],.application-confirmation'],
  };
  function confirmationFor(host = location.hostname) {
    const rule = confirmationRules[host];
    if (!rule || collect().fields.length) return null;
    const candidates = [...document.querySelectorAll(rule[1])].filter(visible);
    return candidates.some(n => /\b(application (?:has been )?(?:successfully )?(?:submitted|received)|thank you for applying)\b/i.test(text(n))) ? rule[0] : null;
  }
  globalThis.JOBPILOT_FORM_ENGINE = { collect, apply, audit, currentValue: value, visible, labelFor, clean, hash, confirmationFor, uploads };
})();
