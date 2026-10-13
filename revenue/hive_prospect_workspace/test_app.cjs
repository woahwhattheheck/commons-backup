'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const app = require('./app.js');

function empty() { return { version: 1, nextId: 1, accounts: [], imports: [], segments: [] }; }
function clone(v) { return JSON.parse(JSON.stringify(v)); }
function validateState(s) {
  if (!s || s.version !== 1 || !Array.isArray(s.accounts) || !Array.isArray(s.imports) || !Array.isArray(s.segments)) throw new Error('bad state');
  return true;
}
const calls = [];
const model = {
  empty, clone, validateState,
  safeURL(value) { try { const u = new URL(String(value)); return ['http:', 'https:'].includes(u.protocol) ? u.href : ''; } catch { return ''; } },
  previewImport(state, text, options) {
    calls.push(['previewImport', text, clone(options)]);
    const next = clone(state);
    next.accounts.push({ id: 'a' + next.nextId++, company: 'Acme', website: 'https://acme.example/', domain: 'acme.example', domainAliases: [], industry: '', location: '', stage: 'Research', tags: [], notes: '', sources: ['https://source.example/acme'], contacts: [{ name: 'Jordan', email: 'j@acme.example', title: 'Ops', sources: [] }], conflicts: [], importFiles: [options.filename] });
    return { state: next, headers: ['Company'], mapping: { company: 'Company' }, report: { filename: options.filename, rows: 1, created: 1, merged: 0, unchanged: 0, errors: text === 'bad' ? [{ row: 2, message: 'bad' }] : [], warnings: [] } };
  },
  commitImport(preview) { const s = clone(preview.state); s.imports.unshift({ ...preview.report, at: 'now' }); return s; },
  mergeDuplicates(state, ids) { calls.push(['mergeDuplicates', ids]); const s = clone(state); s.accounts = s.accounts.filter((_, i) => i === 0); return { state: s, id: s.accounts[0] && s.accounts[0].id }; },
  updateAccount(state, id, changes) { const s = clone(state); const a = s.accounts.find(x => x.id === id); if (!a) throw new Error('missing'); Object.assign(a, changes); return s; },
  filterAccounts(state, filters) { calls.push(['filterAccounts', clone(filters)]); return state.accounts.filter(a => !filters.q || a.company.toLowerCase().includes(String(filters.q).toLowerCase())); },
  exportCSV(accounts) { return 'company\r\n' + accounts.map(a => a.company).join('\r\n') + '\r\n'; },
  saveSegment(state, name, filters) { const s = clone(state); s.segments.push({ name, filters: { q: filters.q || '', industry: filters.industry || '', tag: filters.tag || '', stage: filters.stage || '', withEmail: Boolean(filters.withEmail) } }); return s; }
};

function storage(initial) {
  let value = initial == null ? null : initial;
  return {
    getItem() { return value; },
    setItem(_k, v) { value = v; },
    removeItem() { value = null; },
    value: () => value
  };
}

function controller(initial) { return app.createController(model, { storage: storage(initial) }); }

test('declares the exact landed model methods it needs', () => {
  for (const name of app.REQUIRED_MODEL_METHODS) assert.equal(typeof model[name], 'function');
});

test('loads an empty workspace when local storage is empty', () => {
  assert.deepEqual(controller().getState(), empty());
});

test('loads and validates an existing browser workspace', () => {
  const s = empty(); s.segments.push({ name: 'Keep', filters: { q: '', industry: '', tag: '', stage: '', withEmail: false } });
  assert.equal(controller(JSON.stringify(s)).getState().segments[0].name, 'Keep');
});

test('invalid saved JSON is left untouched and does not become trusted state', () => {
  const backing = storage('{bad json');
  const c = app.createController(model, { storage: backing });
  assert.deepEqual(c.getState(), empty());
  assert.equal(backing.value(), '{bad json');
  assert.match(c.getStatus(), /left untouched/i);
});


test('invalid saved JSON cannot be overwritten by ordinary memory edits', () => {
  const backing = storage('{bad json');
  const c = app.createController(model, { storage: backing });
  c.commit(c.preview('ok', 'memory.csv'));
  assert.equal(c.getState().accounts.length, 1);
  assert.equal(backing.value(), '{bad json');
  assert.equal(c.bridge.writeBlocked, true);
});

test('explicit validated restore may replace previously invalid saved bytes', () => {
  const backing = storage('{bad json');
  const c = app.createController(model, { storage: backing });
  const restored = empty();
  restored.segments.push({ name: 'Recovered', filters: { q: '', industry: '', tag: '', stage: '', withEmail: false } });
  c.restoreText(JSON.stringify(restored));
  assert.equal(JSON.parse(backing.value()).segments[0].name, 'Recovered');
  assert.equal(c.bridge.writeBlocked, false);
});

test('storage read failure falls back to memory without throwing', () => {
  const backing = { getItem() { throw new Error('SecurityError'); } };
  const c = app.createController(model, { storage: backing });
  assert.deepEqual(c.getState(), empty());
  assert.equal(c.bridge.persistent, false);
  assert.match(c.getStatus(), /Memory only/i);
});

test('storage write failure retains the newly committed workspace in memory', () => {
  const backing = { getItem() { return null; }, setItem() { throw new Error('Quota'); }, removeItem() {} };
  const c = app.createController(model, { storage: backing });
  const p = c.preview('ok', 'agency.csv');
  const committed = c.commit(p);
  assert.equal(committed.accounts.length, 1);
  assert.equal(c.getState().accounts.length, 1);
  assert.equal(c.bridge.persistent, false);
});

test('preview passes the customer filename and optional mapping to model.js', () => {
  calls.length = 0;
  const c = controller();
  c.preview('ok', 'accounts.csv', { company: 'Company' });
  assert.deepEqual(calls[0], ['previewImport', 'ok', { filename: 'accounts.csv', mapping: { company: 'Company' } }]);
});

test('commit refuses partial imports when preview has row errors', () => {
  const c = controller();
  const p = c.preview('bad', 'accounts.csv');
  assert.throws(() => c.commit(p), /Fix all import errors/);
  assert.equal(c.getState().accounts.length, 0);
});

test('clean preview commits and persists through the landed model contract', () => {
  const backing = storage();
  const c = app.createController(model, { storage: backing });
  c.commit(c.preview('ok', 'accounts.csv'));
  assert.equal(c.getState().accounts[0].company, 'Acme');
  assert.equal(JSON.parse(backing.value()).imports.length, 1);
});

test('account edits, segments, filters and CSV export delegate to model.js', () => {
  calls.length = 0;
  const c = controller();
  c.commit(c.preview('ok', 'accounts.csv'));
  c.update('a1', { stage: 'Qualified', notes: 'Owner supplied' });
  c.saveSegment('Qualified', { q: 'acme', stage: 'Qualified' });
  assert.equal(c.getState().accounts[0].stage, 'Qualified');
  assert.equal(c.getState().segments[0].name, 'Qualified');
  assert.match(c.exportCSV({ q: 'acme' }), /Acme/);
  assert.ok(calls.some(x => x[0] === 'filterAccounts'));
});

test('manual duplicate merge delegates selected ids and preserves one state', () => {
  calls.length = 0;
  const c = controller();
  c.commit(c.preview('ok', 'one.csv'));
  const s = c.getState();
  s.accounts.push({ ...clone(s.accounts[0]), id: 'a2', company: 'Acme duplicate' }); s.nextId = 3;
  c.restoreText(JSON.stringify(s));
  c.merge(['a1', 'a2']);
  assert.deepEqual(calls.find(x => x[0] === 'mergeDuplicates'), ['mergeDuplicates', ['a1', 'a2']]);
  assert.equal(c.getState().accounts.length, 1);
});

test('backup restore is validated before replacing live state', () => {
  const c = controller();
  c.commit(c.preview('ok', 'one.csv'));
  const before = c.backupText();
  assert.throws(() => c.restoreText('{"version":99}'), /bad state/);
  assert.equal(c.backupText(), before);
  const clean = empty(); clean.segments.push({ name: 'Restored', filters: { q: '', industry: '', tag: '', stage: '', withEmail: false } });
  c.restoreText(JSON.stringify(clean));
  assert.equal(c.getState().segments[0].name, 'Restored');
});

test('reset removes browser state and resets memory', () => {
  const backing = storage();
  const c = app.createController(model, { storage: backing });
  c.commit(c.preview('ok', 'one.csv'));
  c.reset();
  assert.deepEqual(c.getState(), empty());
  assert.equal(backing.value(), null);
});

test('source links allow only model-approved HTTP(S) destinations', () => {
  const c = controller();
  assert.equal(c.sourceHref('javascript:alert(1)'), '');
  assert.equal(c.sourceHref('https://source.example/a'), 'https://source.example/a');
});

test('index loads landed model before app and has no remote scripts or form action', () => {
  const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
  const modelPos = html.indexOf('<script src="model.js"></script>');
  const appPos = html.indexOf('<script src="app.js"></script>');
  assert.ok(modelPos > 0 && appPos > modelPos);
  assert.doesNotMatch(html, /<script[^>]+https?:\/\//i);
  assert.doesNotMatch(html, /<form\b[^>]*\baction=/i);
  for (const id of ['preview-import','commit-import','filter-q','merge-selected','export-csv','export-backup','restore-backup','reset-local']) {
    assert.match(html, new RegExp(`id=["']${id}["']`));
  }
});

test('app source has no fetch, XHR, websocket, beacon or external-send primitive', () => {
  const source = fs.readFileSync(path.join(__dirname, 'app.js'), 'utf8');
  assert.doesNotMatch(source, /\bfetch\s*\(/);
  assert.doesNotMatch(source, /XMLHttpRequest|WebSocket|sendBeacon/);
});
