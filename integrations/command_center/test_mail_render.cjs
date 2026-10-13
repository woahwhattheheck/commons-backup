'use strict';
// Deterministic render contracts for web/mail.js. Run in cloud CI only.
// Fake DOM, clock, timers, and fetch: no browser, provider, or network I/O.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const source = fs.readFileSync(
  process.env.MAIL_SOURCE || path.join(__dirname, 'web/mail.js'), 'utf8');
const NOW = '2026-09-13T00:00:00Z';
const clone = value => JSON.parse(JSON.stringify(value));
const flush = () => new Promise(resolve => setImmediate(resolve));

function thread(overrides = {}) {
  return {
    title: 'A recorded conversation', account: 'team@example.test',
    observed_waiting_on: 'us', waiting_on: 'us', last_activity_at: NOW,
    message_count: 1, unread: false, assigned_owner: null, next_action: null,
    priority: null, due_at: null, overdue: false, url: null, record_refs: [],
    ...overrides,
  };
}

function snapshot(overrides = {}) {
  return {
    observed_at: NOW, sources: [], threads: [],
    pagination: {offset: 0, next_offset: null, matching_threads: 0},
    counts: {messages: 0, duplicate_records: 0},
    ...overrides,
  };
}

function page(offset, nextOffset, title = 'Page ' + offset) {
  return snapshot({threads: [thread({title})],
    pagination: {offset, next_offset: nextOffset, matching_threads: 201},
    counts: {messages: 201, duplicate_records: 0}});
}

function harness(initial = snapshot(), visibility = 'visible') {
  const htmlWrites = [], requests = [], unexpectedRequests = [], events = [];
  const timers = new Map(), responses = [{body: initial}];
  let timerId = 0;
  class Element {
    constructor(tag) {
      this.tagName = tag; this.children = []; this.listeners = new Map();
      this.attributes = {}; this.disabled = false; this._text = '';
    }
    set value(value) { this._value = String(value); }
    get value() { return this._value ?? (this.tagName === 'select' ? this.children[0]?.value : '') ?? ''; }
    set textContent(value) { this._text = String(value); this.children = []; }
    get textContent() { return this._text + this.children.map(n => n.textContent).join(''); }
    set innerHTML(value) { htmlWrites.push(value); throw new Error('Unexpected HTML parsing'); }
    insertAdjacentHTML(_position, value) { htmlWrites.push(value); throw new Error('Unexpected HTML parsing'); }
    append(...nodes) { this.children.push(...nodes); }
    prepend(...nodes) { this.children.unshift(...nodes); }
    replaceChildren(...nodes) { this._text = ''; this.children = [...nodes]; }
    setAttribute(key, value) { this.attributes[key] = String(value); }
    addEventListener(name, callback) { this.listeners.set(name, callback); }
  }
  const root = new Element('main'), listeners = new Map();
  const document = {
    visibilityState: visibility,
    getElementById: id => id === 'view-inbox' ? root : null,
    createElement: tag => new Element(tag),
    createTextNode: value => { const n = new Element('#text'); n.textContent = value; return n; },
    addEventListener: (name, callback) => listeners.set(name, callback),
  };
  class Clock extends Date {
    constructor(...args) { super(...(args.length ? args : [NOW])); }
    static now() { return Date.parse(NOW); }
    toLocaleString() { return this.toISOString(); }
  }
  class Controller {
    constructor() { this.signal = {aborted: false}; }
    abort() { this.signal.aborted = true; }
  }
  class Event {
    constructor(type, options = {}) { this.type = type; this.detail = options.detail; }
  }
  const context = vm.createContext({
    document, Date: Clock, URL, URLSearchParams, AbortController: Controller,
    CustomEvent: Event, window: {dispatchEvent: event => { events.push(event); return true; }},
    setTimeout: (callback, delay) => { const id = ++timerId; timers.set(id, {callback, delay}); return id; },
    clearTimeout: id => timers.delete(id),
    fetch: async (url, options) => {
      requests.push({url, options});
      const response = responses.shift();
      if (!response) {
        unexpectedRequests.push(url);
        throw new Error('Every fetch needs an explicitly queued response');
      }
      if (response.error) throw response.error;
      if (response.promise) return response.promise;
      return {ok: response.status === undefined || response.status < 400,
        status: response.status || 200, json: async () => clone(response.body)};
    },
  });
  vm.runInContext(source, context, {filename: 'web/mail.js'});
  const card = root.children[0];
  assert.equal(card?.id, 'deathstar-mail', 'The shared email tracker is mounted');
  const form = card.children[2], status = card.children[3], coverage = card.children[4];
  const rows = card.children[5], pages = card.children[6];
  const search = form.children[0], mode = form.children[1], refresh = form.children[2];
  const back = pages.children[0], next = pages.children[1];
  const walk = node => [node, ...node.children.flatMap(walk)];
  return {
    root, card, form, status, coverage, rows, search, mode, refresh, back, next,
    requests, unexpectedRequests, timers, htmlWrites, events, walk,
    ready: flush,
    queue: value => responses.push(value),
    params: () => {
      const url = new URL(requests.at(-1).url, 'https://command-center.example.test');
      assert.equal(url.pathname, '/api/mail');
      return Object.fromEntries(url.searchParams);
    },
    async click(button) {
      assert.equal(button.disabled, false, 'A disabled control cannot be clicked');
      button.listeners.get('click')(); await flush();
    },
    async submit(value = search.value) {
      search.value = value; let prevented = false;
      form.listeners.get('submit')({preventDefault: () => { prevented = true; }});
      assert.equal(prevented, true); await flush();
    },
    async change(value) { mode.value = value; mode.listeners.get('change')(); await flush(); },
    async visibility(value) {
      document.visibilityState = value; listeners.get('visibilitychange')(); await flush();
    },
    async poll() {
      const due = [...timers].filter(([, value]) => value.delay === 30000);
      assert.equal(due.length, 1, 'Exactly one bounded poll is scheduled');
      const [id, value] = due[0]; timers.delete(id); value.callback(); await flush();
    },
    assertReadOnly() {
      assert.deepEqual(unexpectedRequests, []);
      assert.ok(requests.every(r => r.url.startsWith('/api/mail?')));
      assert.ok(requests.every(r => r.options?.method === undefined || r.options.method === 'GET'));
      assert.ok(requests.every(r => r.options?.body === undefined));
    },
  };
}

test('initial mail read is bounded and zero observations remain zero', async () => {
  const h = harness(); await h.ready();
  assert.deepEqual(h.params(), {limit: '100', offset: '0', q: '', mode: 'all'});
  assert.match(h.status.textContent, /0 shown of 0 matching threads/);
  assert.match(h.status.textContent, /0 observed messages.*0 duplicate records combined/);
  assert.match(h.coverage.textContent, /No email source loaded yet/);
  assert.match(h.rows.textContent, /No matching threads/);
  assert.doesNotMatch(h.card.textContent, /undefined|NaN/);
  assert.equal(h.back.disabled, true); assert.equal(h.next.disabled, true);
  assert.equal(h.refresh.disabled, false); h.assertReadOnly();
});

test('filters reset paging and next/previous use the shared API pagination', async () => {
  const h = harness(page(0, 100)); await h.ready();
  h.queue({body: page(100, 200)}); await h.click(h.next);
  assert.deepEqual(h.params(), {limit: '100', offset: '100', q: '', mode: 'all'});
  h.queue({body: page(0, 100)}); await h.click(h.back);
  assert.equal(h.params().offset, '0');
  h.queue({body: page(100, 200)}); await h.click(h.next);
  h.queue({body: page(0, 100)}); await h.change('waiting_on_us');
  assert.deepEqual(h.params(), {limit: '100', offset: '0', q: '', mode: 'waiting_on_us'});
  h.queue({body: page(100, 200)}); await h.click(h.next);
  const query = 'invoice + receipt & account@example.test';
  h.queue({body: snapshot()}); await h.submit(query);
  assert.deepEqual(h.params(), {limit: '100', offset: '0', q: query, mode: 'waiting_on_us'});
  for (const mode of ['waiting_on_them', 'unread', 'overdue', 'unknown', 'all']) {
    h.queue({body: snapshot()}); await h.change(mode);
    assert.deepEqual(h.params(), {limit: '100', offset: '0', q: query, mode});
  }
  assert.equal(h.next.disabled, true); h.assertReadOnly();
});

test('failed reads retain exact last-good DOM, restore paging, and roll back requested offset', async () => {
  const initial = page(0, 100);
  initial.sources = [{id: 'email-a', current: true, account: 'team@example.test',
    last_good_observed_at: NOW, coverage: {complete: true}, sync_mode: 'cached'}];
  const h = harness(initial); await h.ready();
  const second = page(100, 200, 'Keep the displayed second page'); second.sources = initial.sources;
  h.queue({body: second}); await h.click(h.next);
  const rowNodes = [...h.rows.children], sourceNodes = [...h.coverage.children];
  const rowText = h.rows.textContent, sourceText = h.coverage.textContent;
  for (const failure of [{error: new Error('Fixture offline')}, {status: 503},
    {body: {threads: null, pagination: {}, counts: {}}}]) {
    h.queue(failure); await h.click(h.next);
    assert.equal(h.params().offset, '200', 'Retry starts from the displayed page, not the failed request');
    assert.equal(h.rows.textContent, rowText); assert.equal(h.coverage.textContent, sourceText);
    assert.equal(h.rows.children.length, rowNodes.length);
    assert.equal(h.coverage.children.length, sourceNodes.length);
    rowNodes.forEach((node, index) => assert.equal(h.rows.children[index], node));
    sourceNodes.forEach((node, index) => assert.equal(h.coverage.children[index], node));
    assert.match(h.status.textContent, /Email view unavailable/);
    assert.match(h.status.textContent, /Last displayed observations retained; sync freshness is not advanced/);
    assert.equal(h.back.disabled, false); assert.equal(h.next.disabled, false);
    assert.equal(h.refresh.disabled, false);
  }
  h.queue({body: page(0, 100)}); await h.click(h.back);
  assert.equal(h.params().offset, '0', 'Previous is relative to last displayed offset 100, not failed offset 200');
  assert.doesNotMatch(h.status.textContent, /unavailable/);
  assert.doesNotMatch(h.rows.textContent, /Keep the displayed second page/);
  h.assertReadOnly();
});

test('only absolute credential-free HTTPS originals become links', async () => {
  const urls = [null, '', '/relative', 'not a URL', 'http://example.test/mail',
    'javascript:void(0)', 'data:text/plain,mail', 'file:///mail',
    'https://user:password@example.test/mail', 'https://user@example.test/mail',
    'https://mail.example.test/message?id=abc#thread'];
  const h = harness(snapshot({threads: urls.map((url, index) => thread({title: String(index), url}))}));
  await h.ready();
  h.rows.children.forEach((row, index) => {
    const anchors = h.walk(row).filter(n => n.tagName === 'a');
    assert.equal(anchors.length, index === urls.length - 1 ? 1 : 0, 'URL case ' + index);
    if (anchors.length) {
      assert.equal(anchors[0].href, urls[index]); assert.equal(anchors[0].target, '_blank');
      assert.equal(anchors[0].rel, 'noopener noreferrer');
    }
  });
  assert.doesNotMatch(h.status.textContent, /unavailable/); h.assertReadOnly();
});

test('provider and directive strings remain literal text and priority zero stays visible', async () => {
  const literal = '<strong data-source="mail">literal & record</strong>';
  const h = harness(snapshot({
    sources: [{id: 'email-a', account: literal, current: false,
      last_good_observed_at: NOW, coverage: {complete: false}, sync_mode: '<em>partial</em>'}],
    threads: [thread({title: literal, account: literal, assigned_owner: '<b>Owner</b>',
      next_action: '<i>Recorded action</i>', priority: 0, waiting_on: 'unknown',
      observed_waiting_on: 'them'})],
  }));
  await h.ready();
  assert.ok(h.rows.textContent.includes(literal)); assert.ok(h.coverage.textContent.includes(literal));
  assert.ok(h.rows.textContent.includes('<b>Owner</b>'));
  assert.ok(h.rows.textContent.includes('<i>Recorded action</i>'));
  assert.match(h.rows.textContent, /Priority: 0/);
  assert.match(h.rows.textContent, /not current or complete enough to call waiting/);
  assert.match(h.coverage.textContent, /stale \/ unknown.*partial coverage/);
  assert.deepEqual(h.htmlWrites, []);
  assert.equal(h.walk(h.root).filter(n => ['b', 'i', 'em', 'script', 'img', 'iframe'].includes(n.tagName)).length, 0);
  assert.doesNotMatch(h.status.textContent, /unavailable/); h.assertReadOnly();
});

test('hidden documents neither start nor perpetuate mail polling, then resume once', async () => {
  const initiallyHidden = harness(snapshot(), 'hidden'); await initiallyHidden.ready();
  assert.equal(initiallyHidden.requests.length, 0); assert.equal(initiallyHidden.timers.size, 0);
  await initiallyHidden.visibility('visible');
  assert.equal(initiallyHidden.requests.length, 1); initiallyHidden.assertReadOnly();

  const h = harness(); await h.ready();
  await h.visibility('hidden'); await h.poll();
  assert.equal(h.requests.length, 1, 'A due hidden-document timer performs no fetch');
  assert.equal(h.timers.size, 0, 'A hidden wake schedules no replacement timer');
  h.queue({body: snapshot()}); await h.visibility('visible');
  assert.equal(h.requests.length, 2);
  h.queue({body: snapshot()}); await h.poll();
  assert.equal(h.requests.length, 3);
  assert.equal([...h.timers.values()].filter(t => t.delay === 30000).length, 1);
  h.assertReadOnly();
});

test('manage dispatches the exact directive or fallback source/item without making a write', async () => {
  const directive = {source_id: 'mail-source-B', item_id: 'message-id-42'};
  const fallback = {source_id: 'mail-source-A', item_id: 'message-id-42'};
  const ignored = {source_id: 'other-source', item_id: 'other-message'};
  const h = harness(snapshot({threads: [
    thread({directive_ref: directive, record_refs: [fallback]}),
    thread({record_refs: [fallback, ignored]}), thread(),
  ]}));
  await h.ready();
  const buttons = h.rows.children.map(row => h.walk(row).filter(n => n.tagName === 'button'));
  assert.deepEqual(buttons.map(row => row.length), [1, 1, 0]);
  await h.click(buttons[0][0]); await h.click(buttons[1][0]);
  assert.deepEqual(h.events.map(event => event.type), ['commons-open-work', 'commons-open-work']);
  assert.deepEqual(clone(h.events.map(event => event.detail)), [directive, fallback]);
  assert.equal(h.requests.length, 1, 'Management is a local selection event, not a provider or write operation');
  h.assertReadOnly();
});

test('an old failed poll cannot overwrite a newer queued mode or search reset', async () => {
  for (const control of ['mode', 'search']) {
    const h = harness(page(0, 100)); await h.ready();
    h.queue({body: page(100, 200)}); await h.click(h.next);
    let rejectOld;
    h.queue({promise: new Promise((_resolve, reject) => { rejectOld = reject; })});
    await h.poll();
    assert.equal(h.requests.length, 3);
    assert.equal(h.params().offset, '100');
    if (control === 'mode') await h.change('unread');
    else await h.submit('new matching thread');
    assert.equal(h.requests.length, 3, 'The new filter is queued behind the in-flight read');
    const filtered = snapshot({threads: [thread({title: 'First matching result'})],
      pagination: {offset: 0, next_offset: null, matching_threads: 1},
      counts: {messages: 1, duplicate_records: 0}});
    h.queue({body: filtered});
    rejectOld(new Error('The old page poll failed'));
    await h.ready();
    assert.equal(h.requests.length, 4, 'Exactly one queued filter read starts');
    assert.deepEqual(h.params(), {limit: '100', offset: '0',
      q: control === 'search' ? 'new matching thread' : '',
      mode: control === 'mode' ? 'unread' : 'all'});
    assert.match(h.rows.textContent, /First matching result/);
    assert.equal(h.back.disabled, true); assert.equal(h.next.disabled, true);
    assert.doesNotMatch(h.status.textContent, /unavailable/);
    h.assertReadOnly();
  }
});

test('an old successful poll cannot render after a newer mode or search reset', async () => {
  for (const control of ['mode', 'search']) {
    const h = harness(page(0, 100, 'Stable last-good result')); await h.ready();
    let resolveOld;
    h.queue({promise: new Promise(resolve => { resolveOld = resolve; })});
    await h.poll();
    assert.equal(h.requests.length, 2);
    if (control === 'mode') await h.change('unread');
    else await h.submit('new matching thread');
    assert.equal(h.requests.length, 2, 'The new filter is queued behind the in-flight read');

    let resolveFiltered;
    h.queue({promise: new Promise(resolve => { resolveFiltered = resolve; })});
    const obsolete = page(0, 100, 'OBSOLETE successful response');
    resolveOld({ok: true, status: 200, json: async () => clone(obsolete)});
    await h.ready();
    assert.equal(h.requests.length, 3, 'Exactly one queued filter read starts after the stale success');
    assert.deepEqual(h.params(), {limit: '100', offset: '0',
      q: control === 'search' ? 'new matching thread' : '',
      mode: control === 'mode' ? 'unread' : 'all'});
    assert.match(h.rows.textContent, /Stable last-good result/);
    assert.doesNotMatch(h.rows.textContent, /OBSOLETE successful response/,
      'An obsolete successful payload must never replace the displayed rows');

    const filtered = snapshot({threads: [thread({title: 'Current filtered result'})],
      pagination: {offset: 0, next_offset: null, matching_threads: 1},
      counts: {messages: 1, duplicate_records: 0}});
    resolveFiltered({ok: true, status: 200, json: async () => clone(filtered)});
    await h.ready();
    assert.match(h.rows.textContent, /Current filtered result/);
    assert.doesNotMatch(h.rows.textContent, /OBSOLETE successful response/);
    assert.equal(h.back.disabled, true); assert.equal(h.next.disabled, true);
    assert.doesNotMatch(h.status.textContent, /unavailable/);
    h.assertReadOnly();
  }
});
