/* Fieldnote customer UI controller. Browser-local only; no network or provider calls. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.FieldnoteApp = api;
  if (root && root.document && typeof root.addEventListener === 'function') {
    root.addEventListener('DOMContentLoaded', function () {
      if (root.Fieldnote) api.mount(root.document, root.Fieldnote, root.localStorage);
    });
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const STORAGE_KEY = 'fieldnote.workspace.v1';
  const REQUIRED_MODEL_METHODS = [
    'empty', 'clone', 'safeURL', 'previewImport', 'commitImport', 'mergeDuplicates',
    'updateAccount', 'filterAccounts', 'exportCSV', 'saveSegment', 'validateState'
  ];

  function assertModel(model) {
    if (!model || REQUIRED_MODEL_METHODS.some(name => typeof model[name] !== 'function')) {
      throw new Error('Fieldnote model.js is missing or incompatible.');
    }
  }

  class StorageBridge {
    constructor(storage, key = STORAGE_KEY) {
      this.storage = storage || null;
      this.key = key;
      this.persistent = Boolean(storage);
      this.writeBlocked = false;
      this.status = this.persistent ? 'Local browser storage ready.' : 'Memory only; browser storage unavailable.';
    }

    load(model) {
      assertModel(model);
      const empty = model.empty();
      if (!this.storage) return { state: empty, status: this.status };
      let raw;
      try {
        raw = this.storage.getItem(this.key);
      } catch (_) {
        this.storage = null;
        this.persistent = false;
        this.status = 'Memory only; browser storage could not be read.';
        return { state: empty, status: this.status };
      }
      if (!raw) return { state: empty, status: this.status };
      try {
        const parsed = JSON.parse(raw);
        model.validateState(parsed);
        return { state: model.clone(parsed), status: this.status };
      } catch (_) {
        this.writeBlocked = true;
        this.status = 'Saved browser data is invalid; it was left untouched. Edits stay in memory until you restore a known-good backup or reset locally.';
        return { state: empty, status: this.status };
      }
    }

    persist(model, state) {
      assertModel(model);
      model.validateState(state);
      if (!this.storage || this.writeBlocked) return false;
      const text = JSON.stringify(state);
      try {
        this.storage.setItem(this.key, text);
        this.persistent = true;
        this.status = 'Saved in this browser.';
        return true;
      } catch (_) {
        this.storage = null;
        this.persistent = false;
        this.status = 'Memory only; browser storage write failed. Export a backup before leaving this page.';
        return false;
      }
    }

    clear() {
      if (!this.storage) {
        this.status = 'Memory workspace reset; browser storage is unavailable.';
        return false;
      }
      try {
        this.storage.removeItem(this.key);
        this.writeBlocked = false;
        this.status = 'Local workspace deleted from this browser.';
        return true;
      } catch (_) {
        this.storage = null;
        this.persistent = false;
        this.status = 'Memory workspace reset; browser storage deletion could not be confirmed.';
        return false;
      }
    }
  }

  function createController(model, options = {}) {
    assertModel(model);
    const bridge = options.bridge || new StorageBridge(options.storage || null, options.key || STORAGE_KEY);
    const loaded = bridge.load(model);
    let state = loaded.state;
    let stateGeneration = 0;
    const previewGenerations = new WeakMap();

    function replace(next) {
      model.validateState(next);
      state = model.clone(next);
      stateGeneration += 1;
      bridge.persist(model, state);
      return model.clone(state);
    }

    return {
      bridge,
      getState: () => model.clone(state),
      getStatus: () => bridge.status,
      preview(text, filename, mapping) {
        const preview = model.previewImport(state, text, { filename: filename || 'Customer import', mapping });
        if (preview && typeof preview === 'object') previewGenerations.set(preview, stateGeneration);
        return preview;
      },
      commit(preview) {
        if (!preview || !preview.report) throw new Error('Preview the import first.');
        if (previewGenerations.get(preview) !== stateGeneration) {
          throw new Error('Preview is stale; preview the import again after workspace changes.');
        }
        if (preview.report.errors && preview.report.errors.length) {
          throw new Error('Fix all import errors before committing; partial imports are not applied.');
        }
        return replace(model.commitImport(preview));
      },
      merge(ids) {
        return replace(model.mergeDuplicates(state, ids).state);
      },
      update(id, changes) {
        return replace(model.updateAccount(state, id, changes));
      },
      query(filters) {
        return model.filterAccounts(state, filters || {});
      },
      saveSegment(name, filters) {
        return replace(model.saveSegment(state, name, filters || {}));
      },
      exportCSV(filters) {
        return model.exportCSV(model.filterAccounts(state, filters || {}));
      },
      backupText() {
        model.validateState(state);
        return JSON.stringify(state, null, 2) + '\n';
      },
      reset() {
        state = model.empty();
        stateGeneration += 1;
        bridge.clear();
        return model.clone(state);
      },
      restoreText(text) {
        let parsed;
        try { parsed = JSON.parse(String(text)); }
        catch (_) { throw new Error('Backup is not valid JSON.'); }
        model.validateState(parsed);
        bridge.writeBlocked = false;
        return replace(parsed);
      },
      sourceHref(value) {
        return model.safeURL(value) || '';
      }
    };
  }

  function currentFilters(doc) {
    return {
      q: doc.getElementById('filter-q').value,
      industry: doc.getElementById('filter-industry').value,
      tag: doc.getElementById('filter-tag').value,
      stage: doc.getElementById('filter-stage').value,
      withEmail: doc.getElementById('filter-email').checked
    };
  }

  function textNode(doc, tag, text, className) {
    const node = doc.createElement(tag);
    if (className) node.className = className;
    node.textContent = text == null ? '' : String(text);
    return node;
  }

  function button(doc, text, action, className) {
    const node = textNode(doc, 'button', text, className);
    node.type = 'button';
    node.addEventListener('click', action);
    return node;
  }

  function download(doc, filename, text, type) {
    const blob = new Blob([text], { type: type || 'text/plain;charset=utf-8' });
    const href = URL.createObjectURL(blob);
    const a = doc.createElement('a');
    a.href = href;
    a.download = filename;
    doc.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(href), 0);
  }

  function mount(doc, model, storage) {
    assertModel(model);
    const controller = createController(model, { storage });
    let pendingPreview = null;
    let editId = '';
    const selected = new Set();

    const status = doc.getElementById('storage-status');
    const message = doc.getElementById('message');
    const report = doc.getElementById('import-report');
    const mappingBox = doc.getElementById('mapping-grid');
    const commitButton = doc.getElementById('commit-import');
    const tbody = doc.getElementById('accounts-body');
    const count = doc.getElementById('account-count');

    function announce(text, kind) {
      message.textContent = text || '';
      message.dataset.kind = kind || 'info';
    }

    function refreshStatus() {
      status.textContent = controller.getStatus();
      status.dataset.persistent = controller.bridge.persistent ? 'yes' : 'no';
    }

    function fillFilterOptions(state) {
      const fields = [
        ['filter-industry', state.accounts.map(a => a.industry)],
        ['filter-tag', state.accounts.flatMap(a => a.tags)],
        ['filter-stage', state.accounts.map(a => a.stage)]
      ];
      for (const [id, values] of fields) {
        const select = doc.getElementById(id);
        const keep = select.value;
        while (select.options.length > 1) select.remove(1);
        [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b)).forEach(value => {
          const opt = doc.createElement('option'); opt.value = value; opt.textContent = value; select.appendChild(opt);
        });
        if ([...select.options].some(o => o.value === keep)) select.value = keep;
      }
    }

    function renderSegments(state) {
      const select = doc.getElementById('segment-list');
      const keep = select.value;
      select.replaceChildren();
      const blank = doc.createElement('option'); blank.value = ''; blank.textContent = 'Saved segments'; select.appendChild(blank);
      state.segments.slice().sort((a, b) => a.name.localeCompare(b.name)).forEach((segment, index) => {
        const opt = doc.createElement('option');
        opt.value = String(state.segments.indexOf(segment));
        opt.textContent = segment.name;
        select.appendChild(opt);
      });
      if ([...select.options].some(o => o.value === keep)) select.value = keep;
    }

    function renderAccounts() {
      const state = controller.getState();
      fillFilterOptions(state);
      renderSegments(state);
      const accounts = controller.query(currentFilters(doc));
      const visibleIds = new Set(accounts.map(a => a.id));
      for (const id of [...selected]) if (!state.accounts.some(a => a.id === id)) selected.delete(id);
      tbody.replaceChildren();
      for (const account of accounts) {
        const tr = doc.createElement('tr');
        const selectCell = doc.createElement('td');
        const checkbox = doc.createElement('input');
        checkbox.type = 'checkbox'; checkbox.checked = selected.has(account.id); checkbox.setAttribute('aria-label', 'Select ' + account.company);
        checkbox.addEventListener('change', () => {
          if (checkbox.checked) selected.add(account.id);
          else selected.delete(account.id);
          doc.getElementById('merge-selected').disabled = [...selected].filter(id => visibleIds.has(id)).length < 2;
        });
        selectCell.appendChild(checkbox); tr.appendChild(selectCell);

        const companyCell = doc.createElement('td');
        companyCell.appendChild(textNode(doc, 'strong', account.company));
        if (account.domain) companyCell.appendChild(textNode(doc, 'div', account.domain, 'muted'));
        for (const source of account.sources || []) {
          const safe = controller.sourceHref(source);
          if (safe) {
            const a = textNode(doc, 'a', source, 'source-link'); a.href = safe; a.target = '_blank'; a.rel = 'noreferrer noopener'; companyCell.appendChild(a);
          } else companyCell.appendChild(textNode(doc, 'div', source, 'muted'));
        }
        tr.appendChild(companyCell);

        const contactsCell = doc.createElement('td');
        if (!account.contacts.length) contactsCell.appendChild(textNode(doc, 'span', 'No contact imported', 'muted'));
        account.contacts.forEach(contact => {
          const line = textNode(doc, 'div', [contact.name, contact.title, contact.email].filter(Boolean).join(' · ') || 'Unnamed contact');
          contactsCell.appendChild(line);
        });
        tr.appendChild(contactsCell);
        tr.appendChild(textNode(doc, 'td', account.stage || 'Research'));
        tr.appendChild(textNode(doc, 'td', account.tags.join(', ')));
        const actionCell = doc.createElement('td');
        actionCell.appendChild(button(doc, 'Edit', () => beginEdit(account.id), 'quiet'));
        tr.appendChild(actionCell);
        tbody.appendChild(tr);
      }
      count.textContent = `${accounts.length} shown · ${state.accounts.length} total`;
      doc.getElementById('merge-selected').disabled = [...selected].filter(id => visibleIds.has(id)).length < 2;
    }

    function beginEdit(id) {
      const account = controller.getState().accounts.find(a => a.id === id);
      if (!account) return;
      editId = id;
      doc.getElementById('edit-company').textContent = account.company;
      doc.getElementById('edit-stage').value = account.stage;
      doc.getElementById('edit-industry').value = account.industry;
      doc.getElementById('edit-location').value = account.location;
      doc.getElementById('edit-tags').value = account.tags.join(', ');
      doc.getElementById('edit-notes').value = account.notes;
      doc.getElementById('editor').hidden = false;
      doc.getElementById('edit-stage').focus();
    }

    function mappingFromUI() {
      const mapping = {};
      mappingBox.querySelectorAll('select[data-field]').forEach(select => { mapping[select.dataset.field] = select.value; });
      return Object.keys(mapping).length ? mapping : undefined;
    }

    function renderMapping(preview) {
      mappingBox.replaceChildren();
      for (const field of model.FIELDS || []) {
        const label = doc.createElement('label');
        label.appendChild(textNode(doc, 'span', field.replace(/(^|_)([a-z])/g, (_, p, c) => (p ? ' ' : '') + c.toUpperCase()), 'field-label'));
        const select = doc.createElement('select'); select.dataset.field = field;
        const blank = doc.createElement('option'); blank.value = ''; blank.textContent = 'Not mapped'; select.appendChild(blank);
        preview.headers.forEach(header => { const opt = doc.createElement('option'); opt.value = header; opt.textContent = header; select.appendChild(opt); });
        select.value = preview.mapping[field] || '';
        label.appendChild(select); mappingBox.appendChild(label);
      }
    }

    function renderReport(preview) {
      report.replaceChildren();
      const r = preview.report;
      report.appendChild(textNode(doc, 'div', `${r.rows} rows · ${r.created} new · ${r.merged} merged · ${r.unchanged} unchanged`, 'report-summary'));
      [...r.errors.map(x => ['Error', x]), ...r.warnings.map(x => ['Warning', x])].forEach(([kind, item]) => {
        report.appendChild(textNode(doc, 'div', `${kind} row ${item.row}: ${item.message}`, kind === 'Error' ? 'error' : 'warning'));
      });
      commitButton.disabled = r.errors.length > 0;
      commitButton.textContent = r.errors.length ? 'Fix errors before import' : 'Commit import';
    }

    async function csvText() {
      const file = doc.getElementById('csv-file').files[0];
      if (file) return { text: await file.text(), name: file.name };
      return { text: doc.getElementById('csv-text').value, name: doc.getElementById('import-name').value || 'Pasted CSV' };
    }

    async function doPreview() {
      try {
        const input = await csvText();
        if (!input.text.trim()) throw new Error('Choose a CSV file or paste CSV text first.');
        pendingPreview = controller.preview(input.text, input.name, mappingFromUI());
        renderMapping(pendingPreview); renderReport(pendingPreview);
        announce('Preview is isolated; nothing has been saved yet.');
      } catch (err) { pendingPreview = null; commitButton.disabled = true; announce(err.message, 'error'); }
    }

    function bindFilters() {
      ['filter-q', 'filter-industry', 'filter-tag', 'filter-stage', 'filter-email'].forEach(id => {
        doc.getElementById(id).addEventListener(id === 'filter-q' ? 'input' : 'change', renderAccounts);
      });
    }

    doc.getElementById('preview-import').addEventListener('click', doPreview);
    mappingBox.addEventListener('change', doPreview);
    commitButton.addEventListener('click', () => {
      try {
        controller.commit(pendingPreview); pendingPreview = null; mappingBox.replaceChildren(); report.replaceChildren(); commitButton.disabled = true;
        refreshStatus(); renderAccounts(); announce('Import committed. Repeat imports merge through the landed Fieldnote identity rules.');
      } catch (err) { announce(err.message, 'error'); }
    });

    doc.getElementById('merge-selected').addEventListener('click', () => {
      try { controller.merge([...selected]); selected.clear(); refreshStatus(); renderAccounts(); announce('Selected accounts merged; known domain aliases and contacts were preserved.'); }
      catch (err) { announce(err.message, 'error'); }
    });

    doc.getElementById('save-edit').addEventListener('click', () => {
      if (!editId) return;
      try {
        controller.update(editId, {
          stage: doc.getElementById('edit-stage').value,
          industry: doc.getElementById('edit-industry').value,
          location: doc.getElementById('edit-location').value,
          tags: doc.getElementById('edit-tags').value,
          notes: doc.getElementById('edit-notes').value
        });
        doc.getElementById('editor').hidden = true; editId = ''; refreshStatus(); renderAccounts(); announce('Account notes and workflow fields saved.');
      } catch (err) { announce(err.message, 'error'); }
    });
    doc.getElementById('cancel-edit').addEventListener('click', () => { doc.getElementById('editor').hidden = true; editId = ''; });

    bindFilters();
    doc.getElementById('clear-filters').addEventListener('click', () => {
      doc.getElementById('filter-q').value = ''; doc.getElementById('filter-industry').value = ''; doc.getElementById('filter-tag').value = '';
      doc.getElementById('filter-stage').value = ''; doc.getElementById('filter-email').checked = false; renderAccounts();
    });
    doc.getElementById('save-segment').addEventListener('click', () => {
      try { controller.saveSegment(doc.getElementById('segment-name').value, currentFilters(doc)); refreshStatus(); renderAccounts(); announce('Segment saved as a reusable filter.'); }
      catch (err) { announce(err.message, 'error'); }
    });
    doc.getElementById('segment-list').addEventListener('change', event => {
      if (event.target.value === '') return;
      const segment = controller.getState().segments[Number(event.target.value)]; if (!segment) return;
      const f = segment.filters;
      doc.getElementById('filter-q').value = f.q; doc.getElementById('filter-industry').value = f.industry; doc.getElementById('filter-tag').value = f.tag;
      doc.getElementById('filter-stage').value = f.stage; doc.getElementById('filter-email').checked = f.withEmail; renderAccounts();
    });

    doc.getElementById('export-csv').addEventListener('click', () => {
      download(doc, 'fieldnote-prospects.csv', controller.exportCSV(currentFilters(doc)), 'text/csv;charset=utf-8');
      announce('Exported the currently filtered segment as spreadsheet-safe CSV.');
    });
    doc.getElementById('export-backup').addEventListener('click', () => {
      download(doc, 'fieldnote-workspace.json', controller.backupText(), 'application/json;charset=utf-8');
      announce('Workspace backup downloaded. Keep customer data private.');
    });
    doc.getElementById('restore-backup').addEventListener('change', async event => {
      const file = event.target.files[0]; if (!file) return;
      try { controller.restoreText(await file.text()); selected.clear(); refreshStatus(); renderAccounts(); announce('Backup restored after model validation.'); }
      catch (err) { announce(err.message, 'error'); }
      finally { event.target.value = ''; }
    });
    doc.getElementById('reset-local').addEventListener('click', () => {
      if (!confirm('Delete this Fieldnote workspace from this browser? Export a backup first if you need it.')) return;
      controller.reset(); selected.clear(); refreshStatus(); renderAccounts(); announce('Local workspace reset. This does not delete downloaded or SQLite backups.');
    });

    refreshStatus(); renderAccounts(); announce('Ready. Imports and exports stay local unless you explicitly use the separate private SQLite backup panel.');
    return controller;
  }

  return { STORAGE_KEY, REQUIRED_MODEL_METHODS, StorageBridge, createController, currentFilters, mount };
});