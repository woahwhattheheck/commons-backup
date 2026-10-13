import test from 'node:test';
import assert from 'node:assert/strict';
import { browserNetworkRules, handleRequest, resolveScorerBase, runForm, scoreOptions, validateRequest, validateUrl } from './cua_s1_form.mjs';
import fixtureHandler from './cua_s1_fixture.mjs';

const input = { url: 'https://example.com/form', form_title: 'Contact',
  entities: [{ label: 'Name', value: 'Ada' }] };
const controls = [
  { index: 0, token: 'field-token', role: 'Edit', label: 'Name', value: '', checked: null, type: 'text', tag: 'input' },
  { index: 1, token: 'button-token', role: 'Button', label: 'Submit', value: '', checked: null, type: 'submit', tag: 'button' },
];

function fixture(selected = [0, 2]) {
  let closed = false;
  let value = '';
  let clicks = 0;
  let pinned = null;
  let requestHandler = null;
  const page = {
    setRequestInterception: async () => {},
    on: (event, handler) => { if (event === 'request') requestHandler = handler; },
    goto: async () => {},
    url: () => input.url,
    evaluate: async (fn, token) => {
      if (!token) return structuredClone(controls);
      const control = controls.find(item => item.token === token);
      return { count: 1, tag: control.tag, type: control.type, label: control.label,
        value: token === 'field-token' ? value : '', checked: null };
    },
    locator: selector => ({
      fill: async next => { assert.match(selector, /field-token/); value = next; },
      click: async () => { assert.match(selector, /button-token/); clicks++; },
    }),
  };
  const browser = { newPage: async () => page, close: async () => { closed = true; } };
  let n = 0;
  const score = async payload => {
    assert.match(payload.context, /TASK fill the form from the document, then submit/);
    assert.deepEqual(payload.options, scoreOptions(input.entities));
    const selected_index = selected[n++];
    return { selected_index, choices: payload.options.map((option, index) => ({ option,
      probability: index === selected_index ? 0.9 : 0.02 })) };
  };
  return { launch: async target => { pinned = target; return browser; },
    resolver: async () => [{ address: '93.184.215.14' }],
    score, get state() { return { closed, value, clicks }; },
    get pinned() { return pinned; },
    get requestHandler() { return requestHandler; }, page };
}

test('validates public target and exact model options', async () => {
  const fakeResolver = async () => [{ address: '8.8.8.8' }];
  assert.equal(await validateUrl(input.url, fakeResolver), input.url);
  await assert.rejects(validateUrl('http://127.0.0.1/admin'), /PRIVATE_URL/);
  await assert.rejects(validateUrl('http://example.com/admin', async () => [{ address: '10.0.0.1' }]), /PRIVATE_URL/);
  await assert.rejects(validateUrl('file:///etc/passwd'), /BAD_URL/);
  assert.deepEqual(scoreOptions(input.entities), ['fill Name: Ada', 'check', 'click', 'skip']);
  assert.equal(browserNetworkRules('example.com', '93.184.215.14'),
    '--host-resolver-rules=MAP example.com 93.184.215.14, MAP * ^NOTFOUND');
  assert.throws(() => browserNetworkRules('example.com', '127.0.0.1'), /PRIVATE_URL/);
  assert.throws(() => validateRequest({ ...input, entities: [input.entities[0], input.entities[0]] }), /BAD_ENTITIES/);
});

test('preview scores controls without browser mutations and closes browser', async () => {
  const f = fixture();
  const result = await runForm(input, f);
  assert.equal(result.executed, false);
  assert.equal(result.elements_scored, 2);
  assert.deepEqual(f.pinned, { href: input.url, host: 'example.com', pinnedAddress: '93.184.215.14' });
  assert.deepEqual(result.planned_actions.map(x => x.action), ['fill']);
  assert.deepEqual(f.state, { closed: true, value: '', clicks: 0 });
});

test('execute fills with independent readback, but submit needs explicit opt-in', async () => {
  const f = fixture();
  const result = await runForm({ ...input, execute: true }, f);
  assert.equal(result.execution_order[0].verified_value, true);
  assert.equal(result.submission_verified, false);
  assert.deepEqual(f.state, { closed: true, value: 'Ada', clicks: 0 });
});

test('submit is narrowly gated and receipt does not claim submission success', async () => {
  const f = fixture();
  const result = await runForm({ ...input, execute: true, submit: true }, f);
  assert.equal(result.execution_order.at(-1).status, 'click_delivered');
  assert.equal(result.execution_order.at(-1).submitted, 'unknown');
  assert.equal(result.submission_verified, false);
  assert.equal(f.state.clicks, 1);
});

test('changed target fails before any action and closes browser', async () => {
  const f = fixture();
  f.page.url = () => 'https://elsewhere.example/form';
  await assert.rejects(runForm({ ...input, execute: true }, f), /TARGET_CHANGED/);
  assert.deepEqual(f.state, { closed: true, value: '', clicks: 0 });
});

test('incomplete plan cannot mutate a form', async () => {
  const f = fixture([3, 2]);
  await assert.rejects(runForm({ ...input, execute: true }, f), /INCOMPLETE_PLAN/);
  assert.deepEqual(f.state, { closed: true, value: '', clicks: 0 });
});

test('browser blocks cross-origin requests after pinning the target host', async () => {
  const f = fixture();
  await runForm(input, f);
  let aborted = false;
  await f.requestHandler({ url: () => 'http://127.0.0.1/internal',
    abort: () => { aborted = true; }, continue: () => { throw new Error('continued'); } });
  assert.equal(aborted, true);
});

test('HTTP handler returns typed failure for private URL', async () => {
  const result = await handleRequest({ method: 'POST', url: 'https://service.example/api/cua_s1_form',
    text: async () => JSON.stringify({ ...input, url: 'http://127.0.0.1/' }) }, fixture());
  assert.equal(result.status, 400);
  assert.equal(result.body.error.code, 'PRIVATE_URL');
});

test('hosted fixture has one labeled field and no submission control', () => {
  const headers = {};
  const response = { setHeader: (key, value) => { headers[key] = value; },
    status(code) { this.statusCode = code; return this; },
    send(body) { this.body = body; return this; } };
  fixtureHandler({ method: 'GET' }, response);
  assert.equal(response.statusCode, 200);
  assert.match(headers['content-type'], /text\/html/);
  assert.match(response.body, /<label for="cua-name">Name<\/label>/);
  assert.match(response.body, /<input id="cua-name"/);
  assert.doesNotMatch(response.body, /<button|type="submit"/);
});

test('resolveScorerBase prefers production alias and Web Headers.get', () => {
  const req = { url: '/cua-s1/form' };
  assert.equal(resolveScorerBase(req, {
    COMMONS_CUA_SCORER_BASE: 'https://scorer.example/',
    VERCEL_URL: 'deploy.vercel.app',
  }), 'https://scorer.example');
  assert.equal(resolveScorerBase(req, {
    VERCEL_PROJECT_PRODUCTION_URL: 'commons-spark-mcp.vercel.app',
    VERCEL_URL: 'deploy.vercel.app',
  }), 'https://commons-spark-mcp.vercel.app');
  const webHeaders = { get(name) {
    const key = String(name).toLowerCase();
    if (key === 'x-forwarded-host') return 'commons-spark-mcp.vercel.app';
    if (key === 'x-forwarded-proto') return 'https';
    return null;
  } };
  assert.equal(resolveScorerBase({ url: '/cua-s1/form', headers: webHeaders }, {
    VERCEL_URL: 'deploy.vercel.app',
  }), 'https://commons-spark-mcp.vercel.app');
  assert.equal(resolveScorerBase(req, {
    VERCEL: '1', VERCEL_URL: 'deploy.vercel.app',
  }), 'https://commons-spark-mcp.vercel.app');
  assert.equal(resolveScorerBase({
    url: '/cua-s1/form',
    headers: { host: 'commons-spark-mcp.vercel.app', 'x-forwarded-proto': 'https' },
  }, { VERCEL_URL: 'deploy.vercel.app' }), 'https://commons-spark-mcp.vercel.app');
});
