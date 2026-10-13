'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const integrity = require('./integrity.js');

function clone(value) { return JSON.parse(JSON.stringify(value)); }
function empty() { return { version: 1, nextId: 1, accounts: [], imports: [], segments: [] }; }
function makeModel() {
  return {
    empty,
    clone,
    validateState(state) {
      if (!state || state.version !== 1 || !Array.isArray(state.accounts) || !Array.isArray(state.imports) || !Array.isArray(state.segments)) throw new Error('bad state');
      return true;
    },
    safeURL(value) { return /^https?:\/\//.test(String(value)) ? String(value) : ''; },
    previewImport(state, _text, options) {
      const next = clone(state);
      next.accounts.push({ id: 'a' + next.nextId++, company: options.filename || 'Acme' });
      return { state: next, report: { rows: 1, created: 1, merged: 0, unchanged: 0, errors: [], warnings: [] } };
    },
    commitImport(preview) { return clone(preview.state); },
    mergeDuplicates(state, ids) { const next = clone(state); next.accounts = next.accounts.filter(account => ids.includes(account.id)).slice(0, 1); return { state: next }; },
    updateAccount(state, id, changes) { const next = clone(state); Object.assign(next.accounts.find(account => account.id === id), changes); return next; },
    filterAccounts(state) { return clone(state.accounts); },
    exportCSV(accounts) { return accounts.map(account => account.company).join('\n'); },
    saveSegment(state, name, filters) { const next = clone(state); next.segments.push({ name, filters: { q: filters.q || '', industry: filters.industry || '', tag: filters.tag || '', stage: filters.stage || '', withEmail: Boolean(filters.withEmail) } }); return next; }
  };
}
function makeStorage(initial) {
  let value = initial === undefined ? null : initial;
  return { getItem() { return value; }, setItem(_key, next) { value = next; }, removeItem() { value = null; }, value: () => value };
}
function makeBaseApi() {
  class StorageBridge {
    constructor(storage, key = 'fieldnote.workspace.v1') { this.storage = storage; this.key = key; this.persistent = Boolean(storage); this.writeBlocked = false; this.status = 'Local browser storage ready.'; }
    load(model) { const raw = this.storage && this.storage.getItem(this.key); if (!raw) return { state: model.empty(), status: this.status }; const parsed = JSON.parse(raw); model.validateState(parsed); return { state: model.clone(parsed), status: this.status }; }
    persist(model, state) { model.validateState(state); if (!this.storage || this.writeBlocked) return false; this.storage.setItem(this.key, JSON.stringify(state)); return true; }
    clear() { if (this.storage) this.storage.removeItem(this.key); this.writeBlocked = false; return true; }
  }
  function createController(model, options = {}) {
    const bridge = new StorageBridge(options.storage || null);
    let state = bridge.load(model).state;
    function replace(next) { model.validateState(next); state = model.clone(next); bridge.persist(model, state); return model.clone(state); }
    return {
      bridge,
      getState: () => model.clone(state),
      getStatus: () => bridge.status,
      preview: (text, filename, mapping) => model.previewImport(state, text, { filename, mapping }),
      commit(preview) { if (preview.report.errors.length) throw new Error('errors'); return replace(model.commitImport(preview)); },
      merge(ids) { return replace(model.mergeDuplicates(state, ids).state); },
      update(id, changes) { return replace(model.updateAccount(state, id, changes)); },
      query(filters) { return model.filterAccounts(state, filters); },
      saveSegment(name, filters) { return replace(model.saveSegment(state, name, filters)); },
      exportCSV(filters) { return model.exportCSV(model.filterAccounts(state, filters)); },
      restoreText(text) { const parsed = JSON.parse(text); model.validateState(parsed); bridge.writeBlocked = false; return replace(parsed); },
      reset() { state = model.empty(); bridge.clear(); return model.clone(state); }
    };
  }
  return { StorageBridge, createController, mount() { throw new Error('not used'); } };
}

test('present empty-string localStorage is corrupt, write-blocked, and left untouched', () => {
  const api = makeBaseApi(); integrity.install(api, globalThis);
  const backing = makeStorage('');
  const controller = api.createController(makeModel(), { storage: backing });
  assert.equal(controller.bridge.writeBlocked, true);
  assert.match(controller.getStatus(), /left untouched/i);
  controller.saveSegment('Memory only', { q: '' });
  assert.equal(backing.value(), '');
});

test('install leaves stale-preview ownership with the app controller', () => {
  const api = makeBaseApi();
  const originalCreateController = api.createController;
  integrity.install(api, globalThis);
  assert.equal(api.createController, originalCreateController);
  const controller = api.createController(makeModel(), { storage: makeStorage() });
  assert.equal(Object.prototype.hasOwnProperty.call(controller, 'integrityRevision'), false);
  assert.equal(Object.prototype.hasOwnProperty.call(integrity, 'decorateController'), false);
});

function fakeSelect(value = '') {
  return { value, options: [{ value: '' }], appendChild(option) { this.options.push(option); } };
}
function fakeDocument() {
  const elements = {
    'filter-q': { id: 'filter-q', value: '' },
    'filter-industry': Object.assign(fakeSelect(), { id: 'filter-industry' }),
    'filter-tag': Object.assign(fakeSelect(), { id: 'filter-tag' }),
    'filter-stage': Object.assign(fakeSelect(), { id: 'filter-stage' }),
    'filter-email': { id: 'filter-email', checked: false },
    'segment-list': Object.assign(fakeSelect('0'), { id: 'segment-list' }),
    'clear-filters': { id: 'clear-filters' }
  };
  const listeners = { change: [], input: [], click: [] };
  const checked = [];
  return {
    elements,
    checked,
    getElementById(id) { return elements[id] || null; },
    createElement() { return { value: '', textContent: '' }; },
    addEventListener(type, listener) { listeners[type].push(listener); },
    querySelectorAll() { return checked; },
    emit(type, target) { for (const listener of listeners[type]) listener({ target }); }
  };
}

test('saved segment filters remain authoritative after their taxonomy value disappears', () => {
  const doc = fakeDocument();
  let seenQuery = null;
  let seenExport = null;
  const controller = {
    getState: () => ({ segments: [{ name: 'Old stage', filters: { q: '', industry: 'Manufacturing', tag: 'priority', stage: 'Qualified', withEmail: true } }] }),
    query(filters) { seenQuery = clone(filters); return []; },
    exportCSV(filters) { seenExport = clone(filters); return 'csv'; },
    merge(ids) { return ids; },
    restoreText() {},
    reset() {}
  };
  integrity.attachUiIntegrity(doc, controller);
  doc.emit('change', doc.elements['segment-list']);
  assert.deepEqual(controller.query({ q: '', industry: '', tag: '', stage: '', withEmail: false }), []);
  assert.deepEqual(seenQuery, { q: '', industry: 'Manufacturing', tag: 'priority', stage: 'Qualified', withEmail: true });
  controller.exportCSV({ q: '', industry: '', tag: '', stage: '', withEmail: false });
  assert.deepEqual(seenExport, seenQuery);
  assert.equal(doc.elements['filter-industry'].value, 'Manufacturing');
  assert.ok(doc.elements['filter-industry'].options.some(option => option.value === 'Manufacturing'));
  doc.elements['filter-stage'].value = 'Research';
  doc.emit('change', doc.elements['filter-stage']);
  controller.query({ q: '', industry: '', tag: '', stage: 'Research', withEmail: false });
  assert.equal(seenQuery.stage, 'Research');
});

test('destructive merge is restricted to currently visible account ids', () => {
  const doc = fakeDocument();
  let merged = null;
  const controller = {
    getState: () => ({ segments: [] }),
    query() { return [{ id: 'a1' }, { id: 'a2' }]; },
    exportCSV() { return ''; },
    merge(ids) { merged = ids; return ids; },
    restoreText() {},
    reset() {}
  };
  integrity.attachUiIntegrity(doc, controller);
  controller.merge(['hidden', 'a2', 'a1', 'a2']);
  assert.deepEqual(merged, ['a2', 'a1']);
  assert.throws(() => controller.merge(['hidden', 'a1']), /two visible accounts/i);
});

test('filter transitions clear visible selections before the original UI can hide them', () => {
  const doc = fakeDocument();
  let clicks = 0;
  doc.checked.push({ click() { clicks++; } }, { click() { clicks++; } });
  const controller = { getState: () => ({ segments: [] }), query: () => [], exportCSV: () => '', merge: ids => ids, restoreText() {}, reset() {} };
  integrity.attachUiIntegrity(doc, controller);
  doc.emit('change', doc.elements['filter-industry']);
  assert.equal(clicks, 2);
});

test('index loads integrity shim after app and before the body closes', () => {
  const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
  const appPosition = html.indexOf('<script src="app.js"></script>');
  const integrityPosition = html.indexOf('<script src="integrity.js"></script>');
  const bodyPosition = html.indexOf('</body>');
  assert.ok(appPosition > 0 && integrityPosition > appPosition && bodyPosition > integrityPosition);
});

test('integrity shim contains no network-send primitive', () => {
  const source = fs.readFileSync(path.join(__dirname, 'integrity.js'), 'utf8');
  assert.doesNotMatch(source, /\bfetch\s*\(|XMLHttpRequest|WebSocket|sendBeacon/);
});
