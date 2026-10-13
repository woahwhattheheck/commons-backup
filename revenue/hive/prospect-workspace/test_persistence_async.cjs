/* SPDX-License-Identifier: Apache-2.0 */
'use strict';
// Execute the complete shipped panel script. DOM, fetch and file-read boundaries
// are deterministic adapters; these tests do not claim a browser installation.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const source = fs.readFileSync(path.join(__dirname, 'persistence.js'), 'utf8');
const controlIds = ['save', 'download', 'refresh', 'erase', 'backup'];
const tick = () => new Promise(resolve => setImmediate(resolve));
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}
function harness() {
  const elements = Object.fromEntries([...controlIds, 'status'].map(id => [id, {
    disabled: id === 'save', textContent: '', files: [],
    click() { if (!this.disabled) return this.onclick(); },
  }]));
  const calls = [], downloads = [], confirmations = [];
  let sequence = 0;
  const context = {
    document: {
      getElementById: id => elements[id],
      createElement: () => ({click() { downloads.push(this); }, remove() {}}),
      body: {append() {}},
    },
    fetch(url, options = {}) {
      const task = deferred(); calls.push({url, options, ...task}); return task.promise;
    },
    crypto: {randomUUID: () => `operation-${++sequence}`},
    TextDecoder, Blob,
    URL: {createObjectURL: () => 'blob:test-backup', revokeObjectURL() {}},
    setTimeout: callback => { callback(); return 0; },
    confirm: message => { confirmations.push(message); return true; },
  };
  vm.runInNewContext(source, context, {filename: 'persistence.js'});
  return {
    elements, calls, downloads, confirmations,
    async respond(index, body, ok = true) {
      calls[index].resolve({ok, json: async () => body}); await tick();
    },
    async fail(index, message = 'connection interrupted') {
      calls[index].reject(new Error(message)); await tick();
    },
    choose(text, task) {
      const bytes = new TextEncoder().encode(text);
      elements.backup.files = [{name: 'workspace.json', size: bytes.length,
        arrayBuffer: () => task ? task.promise : Promise.resolve(bytes.buffer)}];
      return elements.backup.onchange();
    },
  };
}
async function ready() {
  const h = harness(); await h.respond(0, {revision: 7, present: true}); return h;
}
function allDisabled(h) {
  for (const id of controlIds) assert.equal(h.elements[id].disabled, true, id);
}
function request(h, index) { return JSON.parse(h.calls[index].options.body); }
const first = '{ "version": 1, "accounts": [] }\n';
const replacement = '{ "version": 1, "accounts": [{"company":"Example"}] }\n';

test('initial revision read exclusively owns controls', async () => {
  const h = harness(); allDisabled(h);
  h.elements.save.onclick(); await tick();
  h.elements.refresh.onclick(); h.elements.erase.onclick();
  h.elements.download.onclick(); await tick();
  assert.equal(h.calls.length, 1);
  assert.equal(h.confirmations.length, 0);
  await h.respond(0, {revision: 7, present: true});
  assert.equal(h.elements.backup.disabled, false);
  assert.equal(h.elements.save.disabled, true);
});

test('replacement file read disables Save before its first await', async () => {
  const h = await ready(); await h.choose(first);
  assert.equal(h.elements.save.disabled, false);
  const read = deferred(), selecting = h.choose(replacement, read);
  allDisabled(h);
  h.elements.save.click();
  assert.equal(h.calls.length, 1, 'a native-style click must not send deletion');
  read.resolve(new TextEncoder().encode(replacement).buffer); await selecting;
  assert.equal(h.elements.save.disabled, false);
  h.elements.save.click();
  assert.equal(request(h, 1).payload, replacement);
  await h.respond(1, {revision: 8, present: true});
});

test('direct handlers cannot write or refresh while a file is loading', async () => {
  const h = await ready(); await h.choose(first);
  const read = deferred(), selecting = h.choose(replacement, read);
  h.elements.save.onclick(); await tick();
  h.elements.refresh.onclick(); h.elements.erase.onclick();
  h.elements.download.onclick(); await tick();
  assert.equal(h.calls.length, 1);
  assert.equal(h.confirmations.length, 0);
  read.resolve(new TextEncoder().encode(replacement).buffer); await selecting;
});

test('ordinary Save without a selected file cannot become deletion', async () => {
  const h = await ready(); h.elements.save.onclick(); await tick();
  assert.equal(h.calls.length, 1);
  assert.match(h.elements.status.textContent, /Select.*backup/i);
});

test('clearing or rejecting a file leaves Save disabled and controls usable', async () => {
  const h = await ready(); await h.choose(first);
  h.elements.backup.files = []; await h.elements.backup.onchange();
  assert.equal(h.elements.save.disabled, true);
  await h.choose('[]');
  assert.equal(h.elements.save.disabled, true);
  assert.equal(h.elements.refresh.disabled, false);
  const read = deferred(), selecting = h.choose(first, read);
  read.reject(new Error('file unavailable')); await selecting;
  assert.match(h.elements.status.textContent, /file unavailable/);
  assert.equal(h.elements.save.disabled, true);
  assert.equal(h.elements.backup.disabled, false);
  assert.equal(h.calls.length, 1);
});

test('manual revision refresh blocks concurrent operations and uses new revision', async () => {
  const h = await ready(); await h.choose(first);
  h.elements.refresh.click(); allDisabled(h);
  h.elements.save.onclick(); await tick(); h.elements.refresh.onclick();
  assert.equal(h.calls.length, 2);
  await h.respond(1, {revision: 12, present: true});
  h.elements.save.click();
  assert.equal(request(h, 2).expected_revision, 12);
  assert.equal(request(h, 2).payload, first);
  await h.respond(2, {revision: 13, present: true});
});

test('failed revision refresh releases controls without changing selected bytes', async () => {
  const h = await ready(); await h.choose(first);
  h.elements.refresh.click(); await h.fail(1);
  assert.equal(h.elements.backup.disabled, false);
  assert.equal(h.elements.save.disabled, false);
  h.elements.save.click();
  assert.equal(request(h, 2).payload, first);
  assert.equal(request(h, 2).expected_revision, 7);
  await h.respond(2, {revision: 8, present: true});
});

test('in-flight save ignores reentrant clicks and retains exact retry request', async () => {
  const h = await ready(); await h.choose(first);
  h.elements.save.click(); allDisabled(h);
  const original = h.calls[1].options.body;
  h.elements.save.onclick(); await tick(); h.elements.refresh.onclick();
  h.elements.download.onclick(); await tick(); h.elements.erase.onclick();
  await h.choose(replacement);
  assert.equal(h.calls.length, 2);
  assert.equal(h.confirmations.length, 0);
  await h.fail(1);
  assert.equal(h.elements.save.textContent, 'Retry pending operation');
  h.elements.save.click();
  assert.equal(h.calls[2].options.body, original);
  await h.respond(2, {revision: 8, present: true});
  assert.equal(h.elements.save.textContent, 'Save to SQLite');
});

test('download is exclusive and never writes or changes revision', async () => {
  const h = await ready(); await h.choose(first);
  h.elements.download.click(); allDisabled(h);
  h.elements.save.onclick(); await tick(); h.elements.refresh.onclick();
  h.elements.download.onclick(); await tick();
  assert.equal(h.calls.length, 2);
  await h.respond(1, {revision: 11, present: true, payload: replacement});
  assert.equal(h.downloads[0].download, 'hive-prospect-backup-r11.json');
  h.elements.save.click();
  assert.equal(request(h, 2).expected_revision, 7);
  assert.equal(request(h, 2).payload, first);
  await h.respond(2, {revision: 8, present: true});
});

test('explicit deletion and interrupted deletion retry still send null exactly once per attempt', async () => {
  const h = await ready(); h.elements.erase.click();
  assert.equal(h.confirmations.length, 1);
  assert.equal(request(h, 1).payload, null);
  const original = h.calls[1].options.body;
  await h.fail(1);
  assert.equal(h.elements.save.disabled, false);
  h.elements.save.click();
  assert.equal(h.calls[2].options.body, original);
  await h.respond(2, {revision: 8, present: false});
  assert.equal(h.elements.save.disabled, true);
});

test('explicitly discarded retry reloads revision before the next write', async () => {
  const h = await ready(); await h.choose(first);
  h.elements.save.click(); await h.respond(1, {error: 'revision conflict'}, false);
  h.elements.refresh.click(); allDisabled(h);
  assert.equal(h.confirmations.length, 1);
  await h.respond(2, {revision: 9, present: true});
  h.elements.save.click();
  assert.notEqual(request(h, 3).operation_id, request(h, 1).operation_id);
  assert.equal(request(h, 3).expected_revision, 9);
  assert.equal(request(h, 3).payload, first);
  await h.respond(3, {revision: 10, present: true});
});
