'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const app = require('./app.js');

function empty() {
  return { version: 1, nextId: 1, accounts: [], imports: [], segments: [] };
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

const model = {
  empty,
  clone,
  validateState(state) {
    if (!state || state.version !== 1 || !Array.isArray(state.accounts) ||
        !Array.isArray(state.imports) || !Array.isArray(state.segments)) {
      throw new Error('bad state');
    }
    return true;
  },
  safeURL() { return ''; },
  previewImport(state, text, options) {
    const next = clone(state);
    next.accounts.push({
      id: 'a' + next.nextId++,
      company: text,
      website: '',
      domain: '',
      domainAliases: [],
      industry: '',
      location: '',
      stage: 'Research',
      tags: [],
      notes: '',
      sources: [],
      contacts: [],
      conflicts: [],
      importFiles: [options.filename]
    });
    return {
      state: next,
      headers: ['Company'],
      mapping: { company: 'Company' },
      report: {
        filename: options.filename,
        rows: 1,
        created: 1,
        merged: 0,
        unchanged: 0,
        errors: [],
        warnings: []
      }
    };
  },
  commitImport(preview) {
    const next = clone(preview.state);
    next.imports.unshift({ ...preview.report, at: 'now' });
    return next;
  },
  mergeDuplicates(state) { return { state: clone(state), id: state.accounts[0]?.id }; },
  updateAccount(state, id, changes) {
    const next = clone(state);
    const account = next.accounts.find(item => item.id === id);
    if (!account) throw new Error('missing');
    Object.assign(account, changes);
    return next;
  },
  filterAccounts(state) { return clone(state.accounts); },
  exportCSV() { return 'company\r\n'; },
  saveSegment(state, name, filters) {
    const next = clone(state);
    next.segments.push({ name, filters: clone(filters || {}) });
    return next;
  }
};

function controller() {
  return app.createController(model, { storage: null });
}

function seedAccount(c) {
  c.commit(c.preview('Acme', 'seed.csv'));
  assert.equal(c.getState().accounts.length, 1);
}

test('preview cannot overwrite an account edit made after that preview', () => {
  const c = controller();
  seedAccount(c);
  const stale = c.preview('Later import', 'later.csv');

  c.update('a1', { notes: 'keep this newer edit' });

  assert.throws(() => c.commit(stale), /Preview is stale/);
  const current = c.getState();
  assert.equal(current.accounts.length, 1);
  assert.equal(current.accounts[0].notes, 'keep this newer edit');
  assert.equal(current.imports.length, 1);
});

test('preview becomes stale after segment state changes', () => {
  const c = controller();
  seedAccount(c);
  const stale = c.preview('Later import', 'later.csv');

  c.saveSegment('Focused', { q: 'Acme' });

  assert.throws(() => c.commit(stale), /Preview is stale/);
  assert.equal(c.getState().segments[0].name, 'Focused');
  assert.equal(c.getState().accounts.length, 1);
});

test('a successfully committed preview cannot be replayed', () => {
  const c = controller();
  const preview = c.preview('Acme', 'first.csv');

  c.commit(preview);

  assert.throws(() => c.commit(preview), /Preview is stale/);
  assert.equal(c.getState().accounts.length, 1);
  assert.equal(c.getState().imports.length, 1);
});

test('reset invalidates previews created from the prior workspace generation', () => {
  const c = controller();
  seedAccount(c);
  const stale = c.preview('Later import', 'later.csv');

  c.reset();

  assert.throws(() => c.commit(stale), /Preview is stale/);
  assert.deepEqual(c.getState(), empty());
});
