'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(process.argv[2] || 'operator_auth.js', 'utf8');
const NativeRequest = globalThis.Request;
const NativeHeaders = globalThis.Headers;

if (typeof NativeRequest !== 'function' || typeof NativeHeaders !== 'function') {
  throw new Error('WHATWG Request/Headers globals are required for operator auth transport tests');
}

function loadHarness(key = 'op-secret', options = {}) {
  const calls = [];
  const storage = new Map([['creator-desk.operator.v1', key]]);
  const baseUrl = 'https://creator.example/app';
  const documentBaseUrl = options.documentBaseUrl || baseUrl;

  class BrowserNode {
    constructor(baseURI) { this._baseURI = baseURI; }
    get baseURI() { return this._baseURI; }
  }

  function outboundRequest(input, init) {
    if (input instanceof NativeRequest) return new NativeRequest(input, init);
    return new NativeRequest(new URL(String(input), baseUrl), init);
  }

  async function originalFetch(input, init) {
    const outbound = outboundRequest(input, init);
    calls.push({input, init, outbound});
    return {status: 200, ok: true, json: async () => ({operator: true})};
  }

  const document = new BrowserNode(documentBaseUrl);
  document.addEventListener = () => {};
  document.querySelectorAll = () => [];
  document.getElementById = () => null;
  document.createElement = () => { throw new Error('DOM creation not expected in transport tests'); };

  const window = {fetch: originalFetch, Request: NativeRequest, Headers: NativeHeaders, URL, Node: BrowserNode};
  const context = {
    window,
    location: {origin: 'https://creator.example', href: baseUrl},
    localStorage: {
      getItem(name) { return storage.has(name) ? storage.get(name) : null; },
      setItem(name, value) { storage.set(name, value); },
      removeItem(name) { storage.delete(name); },
    },
    Headers: NativeHeaders,
    URL,
    document,
    console,
  };
  vm.createContext(context);
  vm.runInContext(source, context, {filename: 'operator_auth.js'});
  return {fetch: context.window.fetch, calls, Request: NativeRequest, Headers: NativeHeaders};
}

function authHeader(call) {
  const headers = call.init && call.init.headers;
  return headers && typeof headers.get === 'function' ? headers.get('authorization') : null;
}

test('same-origin protected relative and absolute requests receive bearer auth', async () => {
  const h = loadHarness();
  await h.fetch('/api/dashboard');
  await h.fetch('https://creator.example/workspace.sqlite3');
  assert.equal(authHeader(h.calls[0]), 'Bearer op-secret');
  assert.equal(authHeader(h.calls[1]), 'Bearer op-secret');
});

test('relative target resolves against document baseURI rather than location href', async () => {
  const h = loadHarness('op-secret', {documentBaseUrl: 'https://attacker.example/base/'});
  await h.fetch('../api/dashboard');
  assert.equal(h.calls[0].outbound.url, 'https://attacker.example/api/dashboard');
  assert.equal(authHeader(h.calls[0]), null);
  assert.equal(h.calls[0].outbound.headers.get('authorization'), null);
});

test('protocol-relative hostile origin never receives bearer auth', async () => {
  const h = loadHarness();
  await h.fetch('//attacker.example/api/dashboard');
  assert.equal(authHeader(h.calls[0]), null);
});

test('absolute hostile origin never receives bearer auth', async () => {
  const h = loadHarness();
  await h.fetch('https://attacker.example/api/dashboard', {headers: {'X-Caller': 'kept'}});
  assert.equal(authHeader(h.calls[0]), null);
  assert.equal(h.calls[0].init.headers['X-Caller'], 'kept');
});

test('same-origin public GET does not receive operator bearer auth', async () => {
  const h = loadHarness();
  await h.fetch('/api/catalog', {headers: {'X-Public': 'yes'}});
  assert.equal(authHeader(h.calls[0]), null);
  assert.equal(h.calls[0].init.headers['X-Public'], 'yes');
});

test('genuine same-origin protected Request keeps inherited native headers', async () => {
  const h = loadHarness();
  const request = new h.Request('https://creator.example/api/dashboard', {
    headers: {'X-Caller': 'kept'},
  });
  await h.fetch(request);
  assert.equal(authHeader(h.calls[0]), 'Bearer op-secret');
  assert.equal(h.calls[0].outbound.headers.get('x-caller'), 'kept');
});

test('explicit init headers remain authoritative while auth is added', async () => {
  const h = loadHarness();
  const request = new h.Request('https://creator.example/api/dashboard', {
    headers: {'X-Request': 'old'},
  });
  await h.fetch(request, {headers: {'X-Init': 'new'}});
  assert.equal(authHeader(h.calls[0]), 'Bearer op-secret');
  assert.equal(h.calls[0].outbound.headers.get('x-init'), 'new');
  assert.equal(h.calls[0].outbound.headers.get('x-request'), null);
});

test('forged Request-like url cannot smuggle bearer to string-coerced hostile target', async () => {
  const h = loadHarness();
  const forged = {
    url: 'https://creator.example/api/dashboard',
    headers: new h.Headers({'X-Caller': 'forged'}),
    toString() { return 'https://attacker.example/steal'; },
  };
  await h.fetch(forged);
  assert.equal(h.calls[0].outbound.url, 'https://attacker.example/steal');
  assert.equal(authHeader(h.calls[0]), null);
  assert.equal(h.calls[0].outbound.headers.get('authorization'), null);
});

test('stateful non-Request coercion is consumed once and bound to dispatched target', async () => {
  const h = loadHarness();
  let coercions = 0;
  const forged = {
    toString() {
      coercions += 1;
      return coercions === 1
        ? 'https://creator.example/api/dashboard'
        : 'https://attacker.example/steal';
    },
  };
  await h.fetch(forged);
  assert.equal(coercions, 1);
  assert.equal(h.calls[0].outbound.url, 'https://creator.example/api/dashboard');
  assert.equal(authHeader(h.calls[0]), 'Bearer op-secret');
  assert.equal(h.calls[0].outbound.headers.get('authorization'), 'Bearer op-secret');
});

test('native Request own url shadow cannot smuggle bearer across its internal target', async () => {
  const h = loadHarness();
  const request = new h.Request('https://attacker.example/steal', {
    headers: {'X-Internal': 'kept'},
  });
  Object.defineProperty(request, 'url', {
    value: 'https://creator.example/api/dashboard',
    configurable: true,
  });

  assert.equal(request.url, 'https://creator.example/api/dashboard');
  await h.fetch(request);

  assert.equal(h.calls[0].outbound.url, 'https://attacker.example/steal');
  assert.equal(authHeader(h.calls[0]), null);
  assert.equal(h.calls[0].outbound.headers.get('authorization'), null);
  assert.equal(h.calls[0].outbound.headers.get('x-internal'), 'kept');
});

test('native Request own headers shadow cannot replace inherited internal headers', async () => {
  const h = loadHarness();
  const request = new h.Request('https://creator.example/api/dashboard', {
    headers: {'X-Internal': 'kept'},
  });
  Object.defineProperty(request, 'headers', {
    value: new h.Headers({'X-Shadow': 'forged'}),
    configurable: true,
  });

  await h.fetch(request);

  assert.equal(authHeader(h.calls[0]), 'Bearer op-secret');
  assert.equal(h.calls[0].outbound.headers.get('x-internal'), 'kept');
  assert.equal(h.calls[0].outbound.headers.get('x-shadow'), null);
});

test('native Request url getter call shadow cannot redirect classification', async () => {
  const h = loadHarness();
  const request = new h.Request('https://attacker.example/steal');
  Object.defineProperty(request, 'url', {
    value: 'https://creator.example/api/dashboard',
    configurable: true,
  });
  const urlGetter = Object.getOwnPropertyDescriptor(h.Request.prototype, 'url').get;
  const priorCall = Object.getOwnPropertyDescriptor(urlGetter, 'call');
  try {
    Object.defineProperty(urlGetter, 'call', {
      value(input) { return input.url; },
      configurable: true,
    });
    await h.fetch(request);
  } finally {
    if (priorCall) Object.defineProperty(urlGetter, 'call', priorCall);
    else delete urlGetter.call;
  }

  assert.equal(h.calls[0].outbound.url, 'https://attacker.example/steal');
  assert.equal(authHeader(h.calls[0]), null);
  assert.equal(h.calls[0].outbound.headers.get('authorization'), null);
});

test('native Request headers getter call shadow cannot forge inherited headers', async () => {
  const h = loadHarness();
  const request = new h.Request('https://creator.example/api/dashboard', {
    headers: {'X-Internal': 'kept'},
  });
  Object.defineProperty(request, 'headers', {
    value: new h.Headers({'X-Shadow': 'forged'}),
    configurable: true,
  });
  const headersGetter = Object.getOwnPropertyDescriptor(h.Request.prototype, 'headers').get;
  const priorCall = Object.getOwnPropertyDescriptor(headersGetter, 'call');
  try {
    Object.defineProperty(headersGetter, 'call', {
      value(input) { return input.headers; },
      configurable: true,
    });
    await h.fetch(request);
  } finally {
    if (priorCall) Object.defineProperty(headersGetter, 'call', priorCall);
    else delete headersGetter.call;
  }

  assert.equal(authHeader(h.calls[0]), 'Bearer op-secret');
  assert.equal(h.calls[0].outbound.headers.get('x-internal'), 'kept');
  assert.equal(h.calls[0].outbound.headers.get('x-shadow'), null);
});