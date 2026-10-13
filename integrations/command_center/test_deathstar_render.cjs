'use strict';
// Deterministic render contracts for web/deathstar.js. Run in cloud CI.
// This DOM harness performs no browser, provider, timer, or network I/O.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const source = fs.readFileSync(
  process.env.DEATHSTAR_SOURCE || path.join(__dirname, 'web/deathstar.js'), 'utf8');
const NOW = '2026-09-13T00:00:00Z';
const clone = value => JSON.parse(JSON.stringify(value));
const flush = () => new Promise(resolve => setImmediate(resolve));

function snapshot(overrides = {}) {
  return {
    generated_at: NOW,
    work: {open: {fresh: 0, retained: 0, stale: 0, unknown: 0}, top_attention: []},
    sources: {fresh: 0, total: 0, coverage_debt_count: 0},
    throughput: {merged_prs: {'1h': 0, '24h': 0}},
    workers: {explicit_heartbeats: 0, liveness: {}},
    revenue: {observed_amounts: []},
    refresh: {request_budget: {observed_attempts: 0, deferred_reads: 0, scopes: []}},
    cache: {hit: false}, telemetry: {projection_ms: 0},
    ...overrides,
  };
}

function harness(initial = snapshot()) {
  const htmlWrites = [], requests = [], timers = new Map(), responses = [{body: initial}];
  let timerId = 0;
  class Element {
    constructor(tag) {
      this.tagName = tag; this.children = []; this.listeners = new Map();
      this.attributes = {}; this.disabled = false; this._text = '';
    }
    set textContent(value) { this._text = String(value); this.children = []; }
    get textContent() { return this._text + this.children.map(n => n.textContent).join(''); }
    set innerHTML(value) {
      htmlWrites.push(value); throw new Error('HTML parsing is not a text-rendering road');
    }
    insertAdjacentHTML(_position, value) {
      htmlWrites.push(value); throw new Error('HTML parsing is not a text-rendering road');
    }
    append(...nodes) { this.children.push(...nodes); }
    prepend(...nodes) { this.children.unshift(...nodes); }
    replaceChildren(...nodes) { this._text = ''; this.children = [...nodes]; }
    setAttribute(key, value) { this.attributes[key] = String(value); }
    addEventListener(name, callback) { this.listeners.set(name, callback); }
  }
  const root = new Element('main'), listeners = new Map();
  const document = {
    visibilityState: 'visible',
    querySelector: selector => selector === '#view-focus .main-column' ? root : null,
    createElement: tag => new Element(tag),
    createTextNode: value => { const n = new Element('#text'); n.textContent = value; return n; },
    addEventListener: (name, callback) => listeners.set(name, callback),
  };
  class Clock extends Date {
    constructor(...args) { super(...(args.length ? args : [NOW])); }
    static now() { return Date.parse(NOW); }
    toLocaleTimeString() { return this.toISOString().slice(11, 19) + ' UTC'; }
  }
  class Controller {
    constructor() { this.signal = {aborted: false}; }
    abort() { this.signal.aborted = true; }
  }
  const context = vm.createContext({
    document, Date: Clock, AbortController: Controller,
    setTimeout: (callback, delay) => { const id = ++timerId; timers.set(id, {callback, delay}); return id; },
    clearTimeout: id => timers.delete(id),
    fetch: async (url, options) => {
      requests.push({url, options});
      const response = responses.shift();
      assert.ok(response, 'Every fetch must have an explicitly queued response');
      if (response.error) throw response.error;
      if (response.promise) return response.promise;
      return {ok: response.status === undefined || response.status < 400,
        status: response.status || 200, json: async () => clone(response.body)};
    },
  });
  vm.runInContext(source, context, {filename: 'web/deathstar.js'});
  const card = root.children[0];
  assert.ok(card, 'The operation pulse is mounted');
  const status = card.children[1], body = card.children[2], button = card.children[3];
  const walk = node => [node, ...node.children.flatMap(walk)];
  return {
    root, card, status, body, button, requests, timers, htmlWrites, walk,
    ready: flush,
    queue: value => responses.push(value),
    async click() { button.listeners.get('click')(); await flush(); },
    async visibility(value) {
      document.visibilityState = value; listeners.get('visibilitychange')(); await flush();
    },
    async poll() {
      const due = [...timers].filter(([, value]) => value.delay === 30000);
      assert.equal(due.length, 1, 'Exactly one bounded poll is scheduled');
      const [id, value] = due[0]; timers.delete(id); value.callback(); await flush();
    },
  };
}

test('zero observations remain numeric zero, with unknown worker and money coverage', async () => {
  const h = harness(); await h.ready();
  assert.match(h.body.textContent, /0 current open; 0 retained \/ stale \/ unknown/);
  assert.match(h.body.textContent, /0 fresh sources of 0/);
  assert.match(h.body.textContent, /0 in 1h; 0 in 24h/);
  assert.match(h.body.textContent, /0 observed attempts; 0 deferred reads/);
  assert.match(h.body.textContent, /No explicit heartbeat coverage/);
  assert.match(h.body.textContent, /No typed payment records loaded/);
  assert.doesNotMatch(h.body.textContent, /undefined|NaN/);
  assert.match(h.status.textContent, /Shared snapshot 00:00:00 UTC/);
  assert.equal(h.button.disabled, false);
  assert.deepEqual(h.requests.map(r => r.url), ['/api/summary']);
});

test('failed refresh retains the same last-good rows and labels them unavailable and retained', async () => {
  const h = harness(snapshot({work: {open: {fresh: 3, retained: 2, stale: 1, unknown: 0},
    top_attention: [{id: 'keep', title: 'Keep this observation', freshness: 'fresh',
      status: 'open', next_action: 'Read the existing receipt'}]}}));
  await h.ready();
  const children = [...h.body.children], previous = h.body.textContent;
  for (const failure of [{error: new Error('Fixture offline')}, {status: 503}]) {
    h.queue(failure); await h.click();
    assert.equal(h.body.textContent, previous);
    assert.equal(h.body.children.length, children.length);
    children.forEach((node, index) => assert.equal(h.body.children[index], node,
      'Last-good DOM nodes survive the failed fetch'));
    assert.match(h.status.textContent, /unavailable/i);
    assert.match(h.status.textContent, /Prior displayed observations are retained/i);
    assert.doesNotMatch(h.status.textContent, /^Shared snapshot/);
    assert.equal(h.button.disabled, false);
  }
  h.queue({body: snapshot()}); await h.click();
  assert.match(h.status.textContent, /^Shared snapshot/);
  assert.doesNotMatch(h.body.textContent, /Keep this observation/);
});

test('provider and work strings render literally without HTML parsing', async () => {
  const payload = '<img src=x onerror="globalThis.compromised=true">';
  const h = harness(snapshot({
    work: {open: {fresh: 0, retained: 1, stale: 0, unknown: 0}, top_attention: [
      {id: 'literal', title: payload, freshness: 'retained', status: 'open',
        next_action: '<script>globalThis.compromised=true</script>'}]},
    refresh: {request_budget: {observed_attempts: 0, deferred_reads: 1, scopes: [
      {scope: payload, retry_remaining_seconds: 10, retry_not_before: NOW}]}},
  }));
  await h.ready();
  assert.ok(h.body.textContent.includes(payload));
  assert.ok(h.body.textContent.includes('<script>globalThis.compromised=true</script>'));
  assert.deepEqual(h.htmlWrites, []);
  assert.equal(h.walk(h.root).filter(n => ['img', 'script', 'iframe'].includes(n.tagName)).length, 0);
  assert.match(h.status.textContent, /^Shared snapshot/);
});

test('hidden tabs make no polling requests and resume one poll when visible', async () => {
  const h = harness(); await h.ready();
  assert.equal(h.requests.length, 1);
  await h.visibility('hidden');
  await h.poll();
  assert.equal(h.requests.length, 1, 'A due hidden-tab timer performs no fetch');
  assert.equal(h.timers.size, 0, 'A hidden-tab wake does not perpetuate polling');
  h.queue({body: snapshot()}); await h.visibility('visible');
  assert.equal(h.requests.length, 2, 'Visibility resumes one immediate read');
  h.queue({body: snapshot()}); await h.poll();
  assert.equal(h.requests.length, 3);
  assert.equal([...h.timers.values()].filter(t => t.delay === 30000).length, 1);
  assert.ok(h.requests.every(r => r.url === '/api/summary'));
});


test('malformed status metadata cannot replace last-good summary rows', async () => {
  const h = harness(snapshot({work: {open: {fresh: 1, retained: 0, stale: 0, unknown: 0},
    top_attention: [{id: 'keep', title: 'Keep the last-good summary', freshness: 'fresh',
      status: 'open', next_action: 'Read the existing receipt'}]}}));
  await h.ready();
  const children = [...h.body.children], previous = h.body.textContent;
  for (const missing of ['cache', 'telemetry']) {
    const malformed = snapshot();
    delete malformed[missing];
    h.queue({body: malformed}); await h.click();
    assert.match(h.status.textContent, /unavailable/i);
    assert.match(h.status.textContent, /Prior displayed observations are retained/i);
    assert.equal(h.body.textContent, previous);
    assert.equal(h.body.children.length, children.length);
    children.forEach((node, index) => assert.equal(h.body.children[index], node,
      'Invalid status metadata must fail before any visible body replacement'));
    assert.equal(h.button.disabled, false);
  }
  h.queue({body: snapshot()}); await h.click();
  assert.match(h.status.textContent, /^Shared snapshot/);
  assert.doesNotMatch(h.body.textContent, /Keep the last-good summary/);
});
