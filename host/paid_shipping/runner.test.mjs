import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { gzipSync, gunzipSync } from 'node:zlib';
import { openState, putPrivateFile, runMonitor, serializeState, planStateFiles } from './runner.mjs';

test('SQLite state round-trips through private text snapshot', () => {
  const opened = openState();
  opened.sqlite.prepare(`INSERT INTO slack_shipping_cursors
    (channel,latest_ts,initialized,updated_at) VALUES ('C0BU51F1PL3','123.456',1,123)`).run();
  const snapshot = serializeState(opened.sqlite);
  assert.equal(JSON.parse(snapshot).version, 2);
  opened.sqlite.close();
  const restored = openState(snapshot);
  assert.equal(restored.sqlite.prepare('SELECT latest_ts FROM slack_shipping_cursors').get().latest_ts, '123.456');
  assert.equal(serializeState(restored.sqlite), snapshot);
  restored.sqlite.close();
});

test('legacy v1 loads and a raw state over 390 KB compresses without dropping rows', () => {
  const legacy = JSON.stringify({ version: 1, tables: { slack_shipping_state: [
    { key: 'legacy', value: 'retained', updated_at: 1 }
  ] } });
  const opened = openState(legacy);
  opened.sqlite.prepare('INSERT INTO slack_shipping_state (key,value,updated_at) VALUES (?,?,?)')
    .run('large', 'A'.repeat(450_000), 2);
  const snapshot = serializeState(opened.sqlite);
  opened.sqlite.close();
  assert.ok(snapshot.length < 390_000);
  const restored = openState(snapshot);
  assert.equal(restored.sqlite.prepare('SELECT value FROM slack_shipping_state WHERE key=?')
    .get('large').value.length, 450_000);
  assert.equal(restored.sqlite.prepare('SELECT value FROM slack_shipping_state WHERE key=?')
    .get('legacy').value, 'retained');
  restored.sqlite.close();
});

test('compressed state exceeding the bounded decode limit is rejected', () => {
  const oversized = gzipSync(Buffer.alloc(32 * 1024 * 1024 + 1));
  const envelope = JSON.stringify({ version: 2, codec: 'gzip+base64',
    raw_sha256: '0'.repeat(64), data: oversized.toString('base64') });
  assert.throws(() => openState(envelope), /state_decompression_invalid/u);
});

test('public state repository stops before Slack or private content reads', async () => {
  const originalFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async rawUrl => {
    requests.push(String(rawUrl));
    return Response.json({ private: false, visibility: 'public' });
  };
  try {
    await assert.rejects(runMonitor({ COMMONS_GITHUB_TOKEN: 'fixture', SLACK_BOT_TOKEN: 'fixture',
      TYPESAFE_API_KEY: 'fixture' }),
      /private_repository_required/u);
    assert.equal(requests.length, 1);
    assert.equal(new URL(requests[0]).pathname,
      '/repos/woahwhattheheck/commons-ship-enforcer');
  } finally { globalThis.fetch = originalFetch; }
});

test('runner persists private state and reports held notices without Slack writes', async () => {
  const originalFetch = globalThis.fetch;
  const env = { COMMONS_GITHUB_TOKEN: 'fixture-github', SLACK_BOT_TOKEN: 'fixture-slack', TYPESAFE_API_KEY: 'fixture-jev' };
  const statePath = '/repos/woahwhattheheck/commons-ship-enforcer/contents/paid-work/shipping-state.json';
  const noticeId = 'a'.repeat(64);
  const noticePath = `paid-work/shipping-operator-notices/${noticeId}.json`;
  const notice = { notice_id: noticeId, reason_code: 'git_publication_inspection_unavailable',
    tool_name: 'gh', operation_id: 'ship-test-1' };
  const files = new Map([[noticePath, JSON.stringify(notice)]]);
  const shas = new Map([[noticePath, '1'.repeat(40)]]);
  const writes = [];
  const posts = [];
  const requests = [];
  globalThis.fetch = async (rawUrl, options = {}) => {
    const url = new URL(String(rawUrl));
    requests.push({ path: url.pathname, method: options.method || 'GET' });
    if (url.hostname === 'api.github.com' && url.pathname ===
      '/repos/woahwhattheheck/commons-ship-enforcer')
      return Response.json({ private: true, visibility: 'private' });
    if (url.hostname === 'api.github.com' && url.pathname.includes('/contents/')) {
      const path = url.pathname.replace('/repos/woahwhattheheck/commons-ship-enforcer/contents/', '');
      if (!files.has(path)) return Response.json({ message: 'Not Found' }, { status: 404 });
      return Response.json({ type: 'file', sha: shas.get(path),
        content: Buffer.from(files.get(path)).toString('base64') });
    }
    if (url.hostname === 'api.github.com' && url.pathname.endsWith('/git/trees/main'))
      return Response.json({ truncated: false, tree: [{ type: 'blob', path: noticePath }] });
    if (url.hostname === 'account-publisher.tjlabs-publisher.workers.dev') {
      assert.equal(options.headers['User-Agent'], 'Commons-Shipping-Enforcer/1.0');
      const input = JSON.parse(options.body);
      assert.equal(input.operation, 'file.put');
      assert.equal(input.args.path, 'paid-work/shipping-state.json');
      assert.equal(input.args.sha, shas.get(input.args.path));
      files.set(input.args.path, Buffer.from(input.args.content, 'base64').toString('utf8'));
      shas.set(input.args.path, String(writes.length + 2).repeat(40));
      writes.push(input.operation_id);
      return Response.json({ allow: true, receipt: { commit: { oid: 'b'.repeat(40) } } });
    }
    if (url.hostname === 'slack.com') {
      const method = url.pathname.split('/').at(-1);
      if (method === 'conversations.history' || method === 'conversations.replies') {
        assert.equal(options.method, 'GET');
        return Response.json({ ok: true, messages: posts.map((p, i) => ({ ts: `${i + 1}.000001`,
          text: p.text, metadata: p.metadata })), response_metadata: { next_cursor: '' } });
      }
      if (method === 'chat.postMessage') {
        assert.equal(options.method, 'POST');
        posts.push(JSON.parse(options.body));
        return Response.json({ ok: true, ts: '1.000001' });
      }
    }
    throw new Error(`unexpected ${url.pathname}`);
  };
  try {
    const first = await runMonitor(env);
    assert.equal(first.imported, 1);
    assert.equal(first.mode, 'read_only');
    assert.equal(first.slack_writes, false);
    assert.equal(first.delivered, 0);
    assert.equal(first.delivery_error, null);
    assert.equal(first.delivery_code, 'outbound_sender_identity_unverified');
    assert.equal(first.delivery_held, 0);
    assert.equal(first.operator_held, 1);
    assert.equal(first.incident_held, 0);
    assert.equal(posts.length, 0);
    assert.equal(writes.length, 2); // initial private snapshot, then CAS update
    assert.ok(requests.filter(r => r.path.endsWith('/conversations.history')).every(r => r.method === 'GET'));
    const second = await runMonitor(env);
    assert.equal(second.imported, 0);
    assert.equal(second.delivered, 0);
    assert.equal(second.operator_held, 1);
    assert.equal(second.delivery_code, 'outbound_sender_identity_unverified');
    assert.equal(posts.length, 0);
    assert.equal(requests.filter(r => r.path.endsWith('/chat.postMessage')).length, 0);
  } finally { globalThis.fetch = originalFetch; }
});

test('publisher 403 surfaces reason_code and does not retry a held publication', async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (rawUrl, options = {}) => {
    calls.push({ url: String(rawUrl), body: options.body, accept: options.headers.Accept });
    return Response.json({ allow: false, reason_code: 'invalid_candidate' }, { status: 403 });
  };
  try {
    await assert.rejects(
      putPrivateFile({ COMMONS_GITHUB_TOKEN: 'fixture' }, 'paid-work/shipping-state.json', '{"ok":true}\n'),
      /publisher_state_invalid_candidate/u);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].accept, 'application/json');
    assert.equal(JSON.parse(calls[0].body).operation, 'file.put');
  } finally { globalThis.fetch = originalFetch; }
});

test('publisher HTML 403 is named publisher_state_403', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response('<html>denied</html>', {
    status: 403, headers: { 'Content-Type': 'text/html' }
  });
  try {
    await assert.rejects(
      putPrivateFile({ COMMONS_GITHUB_TOKEN: 'fixture' }, 'paid-work/shipping-state.json', '{"ok":true}\n'),
      /publisher_state_403/u);
  } finally { globalThis.fetch = originalFetch; }
});

test('RESOURCE_BUSY retries the same payload then writes', async () => {
  const originalFetch = globalThis.fetch;
  const originalTimeout = globalThis.setTimeout;
  const delays = [];
  globalThis.setTimeout = (fn, ms) => {
    delays.push(ms);
    return originalTimeout(fn, 0);
  };
  const calls = [];
  globalThis.fetch = async (rawUrl, options = {}) => {
    const body = JSON.parse(options.body);
    calls.push(body.operation_id);
    if (calls.length === 1)
      return Response.json({ error: 'RESOURCE_BUSY' }, { status: 409 });
    return Response.json({ allow: true, receipt: { commit: { oid: 'b'.repeat(40) } } });
  };
  try {
    const oid = await putPrivateFile({ COMMONS_GITHUB_TOKEN: 'fixture' },
      'paid-work/shipping-state.json', '{"ok":true}\n', 'a'.repeat(40));
    assert.equal(oid, 'b'.repeat(40));
    assert.equal(calls.length, 2);
    assert.equal(calls[0], calls[1]);
    assert.deepEqual(delays, [1000]);
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.setTimeout = originalTimeout;
  }
});

test('more than 200 thread rows become gzip+hex shards of at most 200', () => {
  const opened = openState();
  const insert = opened.sqlite.prepare(`INSERT INTO slack_shipping_threads
    (channel,root_ts,latest_ts,refs,signature,baseline,active,updated_at)
    VALUES (?,?,?,?,?,?,?,?)`);
  for (let i = 1; i <= 201; i++) {
    insert.run('C0BU51F1PL3', `${i}.000001`, `${i}.000009`, `woahwhattheheck/commons#${i}`,
      'ab'.repeat(32), 0, 1, i);
  }
  const boundary = openState();
  const one = boundary.sqlite.prepare(`INSERT INTO slack_shipping_threads
    (channel,root_ts,latest_ts,refs,signature,baseline,active,updated_at)
    VALUES (?,?,?,?,?,?,?,?)`);
  for (let i = 1; i <= 200; i++) one.run('C0BU51F1PL3', `${i}.000001`, `${i}.000009`, '[]', 'c'.repeat(64), 1, 1, i);
  const single = planStateFiles(boundary.sqlite);
  assert.equal(single.mode, 'single');
  assert.equal(single.files.length, 1);
  assert.equal(single.files[0].path, 'paid-work/shipping-state.json');
  assert.equal(JSON.parse(single.files[0].text).codec, 'gzip+base64');
  boundary.sqlite.close();

  const plan = planStateFiles(opened.sqlite);
  opened.sqlite.close();
  assert.equal(plan.mode, 'sharded');
  const threads = plan.files.filter(file => file.path.includes('/threads-'));
  assert.equal(threads.length, 2);
  let rows = [];
  for (const file of threads) {
    const envelope = JSON.parse(file.text);
    assert.equal(envelope.version, 2);
    assert.equal(envelope.codec, 'gzip+hex');
    assert.match(envelope.data, /^[0-9a-f]+$/u);
    assert.ok(file.text.length < 390_000);
    const part = JSON.parse(gunzipSync(Buffer.from(envelope.data, 'hex')).toString('utf8'));
    assert.ok(part.rows.length > 0 && part.rows.length <= 200);
    rows.push(...part.rows);
  }
  assert.equal(rows.length, 201);
  assert.equal(rows[200].refs, 'woahwhattheheck/commons#201');
  const index = JSON.parse(plan.files.at(-1).text);
  const restEnvelope = JSON.parse(plan.files.find(file => file.path.endsWith(`/${index.rest}`)).text);
  assert.equal(restEnvelope.codec, 'gzip+hex');
  const rest = JSON.parse(gunzipSync(Buffer.from(restEnvelope.data, 'hex')).toString('utf8'));
  rest.tables.slack_shipping_threads = rows;
  assert.equal(index.version, 4);
  assert.equal(index.thread_count, 201);
  assert.deepEqual(index.shards, threads.map((file, i) =>
    `threads-${String(i).padStart(4, '0')}-${createHash('sha256').update(file.text).digest('hex')}.json`));
  const restored = openState(JSON.stringify(rest));
  assert.equal(restored.sqlite.prepare('SELECT COUNT(*) AS n FROM slack_shipping_threads').get().n, 201);
  assert.equal(restored.sqlite.prepare('SELECT refs FROM slack_shipping_threads WHERE root_ts=?').get('201.000001').refs,
    'woahwhattheheck/commons#201');
  restored.sqlite.close();
});
