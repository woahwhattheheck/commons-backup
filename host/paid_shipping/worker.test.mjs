import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import worker, { tick } from './worker.mjs';
import { classifyThread, incidentNotice, incidentRefs, operatorNotice } from './rules.mjs';

const channels = ['C0BU51F1PL3', 'C0BTB4SUCP9', 'C0BVANHNB26'];
const actualNow = Date.now;
const baseTs = String(Math.floor(actualNow() / 1000) - 120);

function fixture() {
  let clock = actualNow();
  Date.now = () => clock;
  const sqlite = new DatabaseSync(':memory:');
  sqlite.exec(fs.readFileSync(new URL('./schema.sql', import.meta.url), 'utf8'));
  sqlite.exec(`CREATE TABLE incidents (id TEXT,op_id TEXT,reason TEXT,content TEXT,destination TEXT,email_status TEXT)`);
  let queryCount = 0;
  const DB = { prepare(sql) { return { bind(...args) {
    const stmt = sqlite.prepare(sql);
    return {
      first: async () => { queryCount++; return stmt.get(...args); },
      all: async () => { queryCount++; return { results: stmt.all(...args) }; },
      run: async () => { queryCount++; return { meta: { changes: stmt.run(...args).changes } }; }
    };
  } }; } };
  const env = { DB, SLACK_BOT_TOKEN: 'test-slack-token', GITHUB_TOKEN: 'test-github-token' };
  const roots = new Map(channels.map(c => [c, []]));
  const replies = new Map();
  const posts = [];
  const requests = [];
  let failPostAfterInsert = false;
  let rateLimitMethod = null;
  let forkUpstream = [];
  let historyPageSize = 1;
  globalThis.fetch = async (url, options = {}) => {
    requests.push(String(url));
    if (String(url).startsWith('https://api.github.com/')) {
      const path = String(url).replace('https://api.github.com', '');
      if (path === '/user') return options.headers.Authorization === 'Bearer test-secondary-token'
        ? Response.json({ id: 311286379 }) : Response.json({ message: 'Bad credentials' }, { status: 401 });
      if (path.includes('/pulls?')) return Response.json(forkUpstream);
      if (path.endsWith('/pulls/22')) return Response.json({ user: { id: 293286387 }, base: { repo: { fork: true } }, state: 'open', head: { repo: { owner: { login: 'woahwhattheheck' } }, ref: 'fix', sha: 'abc' } });
      if (path.endsWith('/pulls/23')) return Response.json({ user: { id: 311286379 }, base: { repo: { fork: true } }, state: 'open', head: { repo: { owner: { login: 'tokenjunkielabs' } }, ref: 'fix', sha: 'def' } });
      if (path.endsWith('/repos/other/repo/pulls/9')) return Response.json({ user: { id: 999 }, base: { repo: { fork: false } }, state: 'open' });
      if (path.endsWith('/repos/sponsor/repo/pulls/42')) return Response.json({ user: { id: 311286379 }, base: { repo: { fork: false } }, state: 'open' });
      if (path.endsWith('/repos/woahwhattheheck/ultimate-ai-platform')) return Response.json({ parent: { full_name: 'iyeanur6-cyber/ultimate-ai-platform' } });
      if (path.endsWith('/repos/tokenjunkielabs/ultimate-ai-platform')) return Response.json({ parent: { full_name: 'iyeanur6-cyber/ultimate-ai-platform' } });
      return Response.json({}, { status: 404 });
    }
    const method = new URL(String(url)).pathname.split('/').at(-1);
    if (method === rateLimitMethod) {
      rateLimitMethod = null;
      return new Response(null, { status: 429, headers: { 'Retry-After': '600' } });
    }
    const body = options.body ? JSON.parse(options.body) : Object.fromEntries(new URL(String(url)).searchParams);
    if (method === 'chat.postMessage') {
      const ts = String(Number(baseTs) + 1000 + posts.length) + '.000001';
      const message = { ts, text: body.text, bot_id: 'bot', metadata: body.metadata };
      posts.push({ ...body, ts });
      if (body.thread_ts) replies.get(`${body.channel}:${body.thread_ts}`).push(message);
      else roots.get(body.channel).push(message);
      if (failPostAfterInsert) { failPostAfterInsert = false; throw new Error('connection_lost'); }
      return Response.json({ ok: true, ts });
    }
    if (method === 'conversations.history') {
      const sorted = [...roots.get(body.channel)].filter(m => Number(m.ts) > Number(body.oldest || 0) &&
        (!body.latest || Number(m.ts) < Number(body.latest))).sort((a,b) => Number(b.ts)-Number(a.ts));
      const index = Number(body.cursor || 0);
      const slice = sorted.slice(index, index + historyPageSize);
      return Response.json({ ok: true, messages: slice, response_metadata: { next_cursor: index + historyPageSize < sorted.length ? String(index + historyPageSize) : '' } });
    }
    if (method === 'conversations.replies') {
      const sorted = replies.get(`${body.channel}:${body.ts}`) || [];
      const index = Number(body.cursor || 0);
      const slice = sorted.slice(index, index + 1);
      return Response.json({ ok: true, messages: slice, response_metadata: { next_cursor: index + 1 < sorted.length ? String(index + 1) : '' } });
    }
    throw new Error(`unexpected ${url}`);
  };
  return {
    sqlite, env, roots, replies, posts, requests,
    queryCount: () => queryCount,
    resetQueryCount() { queryCount = 0; },
    setHistoryPageSize(value) { historyPageSize = value; },
    advance(seconds) { clock += seconds * 1000; },
    add(channel, ts, text, threadTs) {
      const message = { ts, text, user: 'U123' };
      if (threadTs) replies.get(`${channel}:${threadTs}`).push(message);
      else { roots.get(channel).push(message); replies.set(`${channel}:${ts}`, [message]); }
      return message;
    },
    setPostConnectionLoss() { failPostAfterInsert = true; },
    setRateLimitOnce(method) { rateLimitMethod = method; },
    setForkUpstream(value) { forkUpstream = value; }
  };
}

test('rules require bounty completion and preserve own upstream, required tests and unrelated demos', () => {
  assert.equal(classifyThread([{ text: 'Product demo shipped in private workspace.' }]), null);
  assert.equal(classifyThread([{ text: 'Bounty assignment application submitted; sponsor-required tests are next.' }]), null);
  assert.equal(classifyThread([{ text: 'Bounty work is not done; the internal packet is incomplete.' }]), null);
  assert.equal(classifyThread([{ text: 'Bounty fix done in internal packet.' }, { text: 'Correction: this is not done yet.' }]), null);
  assert.equal(classifyThread([{ text: 'Bounty fix shipped: https://github.com/iyeanur6-cyber/ultimate-ai-platform/pull/42' }]), null);
  assert.equal(classifyThread([{ text: 'Bounty fix done in internal packet.' }])?.code, 'packet_only');
  assert.equal(classifyThread([{ text: 'Bounty fix done in internal packet.', bot_id: 'peer-bot' }])?.code, 'packet_only');
  assert.equal(classifyThread([{ text: 'Bounty work shipped in fork-only https://github.com/woahwhattheheck/ultimate-ai-platform/pull/22' }])?.code, 'fork_only');
  assert.equal(classifyThread([{ text: 'Bounty upstream PR publication returned 403.' }])?.code, 'upstream_403');
});

test('incident matching extracts exact structured target and operator text contains no caller prose', () => {
  assert.deepEqual(incidentRefs(JSON.stringify({ repo_full_name: 'owner/repo', pr_number: 42 })), ['owner/repo#42']);
  assert.deepEqual(incidentRefs(JSON.stringify({ owner: 'owner', repo: 'repo', issue_number: 7 })), ['owner/repo#7', 'owner/repo!7']);
  assert.deepEqual(incidentRefs(JSON.stringify({ repository_full_name: 'owner/repo', pr_number: 9 })), ['owner/repo#9']);
  const text = operatorNotice({ reason_code: 'git_publication_inspection_unavailable', tool_name: 'github_create_pull_request', repository: 'owner/repo', issue_number: 42 });
  assert.match(text, /owner\/repo#42/);
  assert.match(text, /configured named Git remote and local publication inspection/);
  const held = operatorNotice({ reason_code: 'incident_held', tool_name: 'github_create_pull_request', repository: 'owner/repo' });
  assert.match(held, /Bryce handles any external incident statement/u);
  assert.match(held, /Do not retry by rephrasing or switching accounts/u);
  assert.match(held, /email process; delivery may still be pending/u);
  const smoke = operatorNotice({ reason_code: 'monitor_transport_check', tool_name: 'monitor', operation_id: 'smoke-1' });
  assert.match(smoke, /operational transport check/u);
  assert.match(smoke, /No action needed/u);
  assert.doesNotMatch(smoke, /Publication route blocked/u);
  assert.match(incidentNotice({ id: 'id', op_id: 'op', reason: 'blocked_incident', destination: '{}', email_status: 'accepted' }), /email was accepted for Bryce/);
  assert.doesNotMatch(incidentNotice({ id: 'id', op_id: 'op', reason: 'blocked_incident', destination: '{}', email_status: 'pending' }), /email was accepted for Bryce/);
});

test('live tick keeps typed analysis while the chat route returns a private hold', async () => {
  const f = fixture();
  f.env.TYPESAFE_API_KEY = 'test-jev-token';
  const slackFetch = globalThis.fetch;
  const jevStates = [];
  globalThis.fetch = async (url, options) => {
    if (String(url) === 'https://api.typesafe.ai/v1/systemone') {
      const input = JSON.parse(options.body);
      jevStates.push(input.state);
      assert.equal(input.model, 'jev-latest');
      assert.equal(options.headers.Authorization, 'Bearer test-jev-token');
      return Response.json({ answers: { next_action: { type: 'choice', choice: 'submit_own_patch' } },
        usage: { input_tokens: 27 } });
    }
    return slackFetch(url, options);
  };
  await tick(f.env);
  f.advance(10);
  f.add(channels[0], String(Number(baseTs) + 120) + '.000001', 'Bounty fix done in internal packet.');
  const result = await tick(f.env);
  assert.equal(result.jev.calls, 1);
  assert.equal(result.jev.input_tokens, 27);
  assert.equal(result.jev.status, 'ok');
  assert.equal(jevStates.length, 1);
  assert.match(jevStates[0], /Bounty fix done in internal packet/u);
  assert.equal(f.posts.length, 0);
  assert.equal(result.delivered.code, 'outbound_sender_identity_unverified');
  assert.equal(result.delivered.delivered, false);
  assert.equal(result.delivered.incident, false);
  assert.deepEqual(result.delivered.matched_fields, []);
  assert.deepEqual(result.delivered.matched_terms, []);
  assert.match(result.delivered.private_instruction, /Return this result privately/u);
  assert.equal(f.sqlite.prepare('SELECT COUNT(*) AS n FROM slack_shipping_outbox').get().n, 0);
  assert.equal(f.requests.filter(url => new URL(url).pathname.endsWith('/chat.postMessage')).length, 0);
});

test('JEV API error is explicit while the fallback remains local', async () => {
  const f = fixture();
  f.env.TYPESAFE_API_KEY = 'test-jev-token';
  const slackFetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => String(url) === 'https://api.typesafe.ai/v1/systemone'
    ? Response.json({ error: 'unavailable' }, { status: 503 }) : slackFetch(url, options);
  await tick(f.env);
  f.advance(10);
  f.add(channels[0], String(Number(baseTs) + 120) + '.000001', 'Bounty fix done in internal packet.');
  const result = await tick(f.env);
  assert.equal(result.jev.calls, 1);
  assert.equal(result.jev.errors, 1);
  assert.equal(result.jev.status, 'degraded_static_fallback');
  assert.equal(f.posts.length, 0);
  assert.equal(result.delivered.code, 'outbound_sender_identity_unverified');
  assert.equal(result.delivered.delivered, false);
  assert.equal(f.sqlite.prepare('SELECT COUNT(*) AS n FROM slack_shipping_outbox').get().n, 0);
  assert.equal(f.requests.filter(url => new URL(url).pathname.endsWith('/chat.postMessage')).length, 0);
});

test('baseline and paginated analysis remain read-only with no queued notices', async () => {
  const f = fixture();
  f.add(channels[0], baseTs + '.000001', 'Bounty fix done in internal packet.');
  await tick(f.env);
  assert.equal(f.posts.length, 0);
  f.advance(10);
  f.add(channels[0], String(Number(baseTs) + 120) + '.000001', 'Bounty fix done in internal packet for issue two.');
  f.add(channels[0], String(Number(baseTs) + 121) + '.000001', 'Bounty fix done in internal packet for issue three.');
  const paged = await tick(f.env);
  assert.equal(paged.channels[0].more, true);
  await tick(f.env);
  assert.equal(f.posts.length, 0);
  assert.ok(f.requests.filter(url => new URL(url).pathname.endsWith('/conversations.history')).length > channels.length);
  await tick(f.env);
  assert.equal(f.posts.length, 0);
  assert.equal(f.sqlite.prepare('SELECT COUNT(*) AS n FROM slack_shipping_outbox').get().n, 0);
  assert.equal(f.requests.filter(url => new URL(url).pathname.endsWith('/chat.postMessage')).length, 0);
});

test('fork proof analysis cannot queue or post a notice', async () => {
  const f = fixture();
  await tick(f.env);
  f.advance(10);
  const root = String(Number(baseTs) + 120) + '.000001';
  f.add(channels[1], root, 'Bounty work shipped in fork-only https://github.com/woahwhattheheck/ultimate-ai-platform/pull/22');
  f.setForkUpstream([{ user: { id: 293286387 }, state: 'open', head: { sha: 'abc', ref: 'fix' } }]);
  await tick(f.env);
  assert.equal(f.posts.length, 0);
  f.add(channels[1], String(Number(baseTs) + 121) + '.000001', 'Still only the fork PR.', root);
  f.setForkUpstream([]);
  await tick(f.env);
  await tick(f.env);
  await tick(f.env);
  assert.equal(f.posts.length, 0);
  assert.equal(f.sqlite.prepare('SELECT COUNT(*) AS n FROM slack_shipping_outbox').get().n, 0);
  assert.equal(f.requests.filter(url => new URL(url).pathname.endsWith('/chat.postMessage')).length, 0);
});

test('claimant and owner pull-request analysis cannot queue a notice', async () => {
  const f = fixture();
  await tick(f.env);
  f.advance(10);
  const first = String(Number(baseTs) + 120) + '.000001';
  f.add(channels[1], first, 'Bounty fix shipped in fork-only https://github.com/tokenjunkielabs/ultimate-ai-platform/pull/23; a competing PR is https://github.com/other/repo/pull/9');
  await tick(f.env);
  assert.equal(f.posts.length, 0);
  const second = String(Number(baseTs) + 121) + '.000001';
  f.add(channels[1], second, 'Bounty fix shipped in fork-only https://github.com/tokenjunkielabs/ultimate-ai-platform/pull/23; our upstream is https://github.com/sponsor/repo/pull/42');
  await tick(f.env);
  await tick(f.env);
  assert.equal(f.posts.length, 0);
  assert.equal(f.sqlite.prepare('SELECT COUNT(*) AS n FROM slack_shipping_outbox').get().n, 0);
  assert.equal(f.requests.filter(url => new URL(url).pathname.endsWith('/chat.postMessage')).length, 0);
});

test('legacy delivery backlog is terminally held without provider access', async () => {
  const f = fixture();
  const insert = f.sqlite.prepare(`INSERT INTO slack_shipping_outbox
    (id,channel,kind,body,state,created_at,updated_at) VALUES (?,?,?,?,?,?,?)`);
  for (const [index, state] of ['pending', 'sending', 'uncertain', 'accepted'].entries()) {
    insert.run(`legacy-${index}`, channels[0], 'legacy', 'private body', state, Number(baseTs), Number(baseTs));
  }
  const result = await tick(f.env);
  const states = Object.fromEntries(f.sqlite.prepare(
    'SELECT id,state FROM slack_shipping_outbox ORDER BY id'
  ).all().map(row => [row.id, row.state]));
  assert.deepEqual(states, {
    'legacy-0': 'held',
    'legacy-1': 'held',
    'legacy-2': 'held',
    'legacy-3': 'accepted'
  });
  assert.equal(result.delivered.held, 3);
  assert.equal(result.delivered.accepted, 0);
  assert.equal(result.delivered.code, 'outbound_sender_identity_unverified');
  assert.equal(result.delivered.delivered, false);
  assert.equal(result.delivered.incident, false);
  assert.equal(f.posts.length, 0);
  assert.equal(f.requests.filter(url => new URL(url).pathname.endsWith('/chat.postMessage')).length, 0);
});

test('operator endpoint returns a private hold and creates no fallback record', async () => {
  const f = fixture();
  const id = 'a'.repeat(64);
  const url = 'https://commons-shipping-enforcer.tjlabs-publisher.workers.dev/v1/operator-notice';
  const auth = { Authorization: 'Bearer test-github-token' };
  const body = { notice_id: id, reason_code: 'git_publication_inspection_unavailable', tool_name: 'github_create_pull_request', operation_id: 'op-123', repository: 'owner/repo', issue_number: 42 };
  const invalid = await worker.fetch(new Request(url, { method: 'POST', headers: auth, body: JSON.stringify({ ...body, draft: 'private draft' }) }), f.env);
  assert.equal(invalid.status, 400);
  const unauthorized = await worker.fetch(new Request(url, { method: 'POST', body: JSON.stringify(body) }), f.env);
  assert.equal(unauthorized.status, 401);
  for (const headers of [auth, auth, { Authorization: 'Bearer test-secondary-token' }]) {
    const held = await worker.fetch(new Request(url, { method: 'POST', headers, body: JSON.stringify(body) }), f.env);
    assert.equal(held.status, 409);
    const decision = await held.json();
    assert.equal(decision.accepted, false);
    assert.equal(decision.notice_id, id);
    assert.equal(decision.code, 'outbound_sender_identity_unverified');
    assert.equal(decision.delivered, false);
    assert.equal(decision.incident, false);
    assert.deepEqual(decision.matched_fields, []);
    assert.deepEqual(decision.matched_terms, []);
    assert.match(decision.private_instruction, /Return this result privately/u);
  }
  assert.equal(f.sqlite.prepare('SELECT COUNT(*) AS n FROM slack_shipping_operator_notices').get().n, 0);
  assert.equal(f.sqlite.prepare('SELECT COUNT(*) AS n FROM slack_shipping_outbox').get().n, 0);
  await tick(f.env);
  assert.equal(f.posts.length, 0);
  assert.equal(f.requests.filter(requestUrl => new URL(requestUrl).pathname.endsWith('/chat.postMessage')).length, 0);
  const health = await worker.fetch(new Request('https://example.test/health'), f.env);
  const healthBody = await health.json();
  assert.equal(healthBody.mode, 'read_only');
  assert.equal(healthBody.slack_writes, false);
  assert.equal(healthBody.outbound.delivered, false);
});

test('new incidents advance locally without creating an outward fallback', async () => {
  const f = fixture();
  const ts = baseTs + '.000001';
  f.add(channels[2], ts, 'Our bounty PR https://github.com/owner/repo/pull/42 needs checks.');
  f.sqlite.prepare(`INSERT INTO incidents VALUES (?,?,?,?,?,?)`).run('old','old-op','blocked_incident','secret draft','{"repo_full_name":"owner/repo","pr_number":42}','sent');
  await tick(f.env);
  assert.equal(f.posts.length, 0);
  f.sqlite.prepare(`INSERT INTO incidents VALUES (?,?,?,?,?,?)`).run('new','new-op','blocked_incident','private incident body','{"repo_full_name":"owner/repo","pr_number":42}','pending');
  const result = await tick(f.env);
  assert.equal(result.incidents.queued, 0);
  assert.equal(result.incidents.held, 1);
  assert.equal(result.incidents.hold.delivered, false);
  assert.equal(result.incidents.hold.incident, false);
  assert.equal(f.posts.length, 0);
  assert.equal(f.sqlite.prepare('SELECT COUNT(*) AS n FROM slack_shipping_outbox').get().n, 0);
  assert.equal(f.requests.filter(url => new URL(url).pathname.endsWith('/chat.postMessage')).length, 0);
});

test('large read slices stay within the query budget and create no fallback queue', async () => {
  const f = fixture();
  f.setHistoryPageSize(100);
  await tick(f.env);
  f.advance(10);
  for (const channel of channels) for (let i = 0; i < 100; i++) {
    f.add(channel, `${Number(baseTs) + 120}.${String(i + 1).padStart(6, '0')}`,
      `Bounty issue ${i} fix done in internal packet.`);
  }
  for (let i = 0; i < 3; i++) f.sqlite.prepare('INSERT INTO incidents VALUES (?,?,?,?,?,?)').run(
    `inc-${i}`, `op-${i}`, 'blocked_incident', 'private content',
    JSON.stringify({ owner: 'owner', repo: 'repo', issue_number: i + 1 }), 'sent');
  for (let i = 0; i < 2; i++) f.sqlite.prepare(`INSERT INTO slack_shipping_operator_notices
    (notice_id,reason_code,tool_name,repository,issue_number,created_at) VALUES (?,?,?,?,?,?)`).run(
    String(i + 1).repeat(64), 'git_publication_inspection_unavailable', 'github_create_pull_request',
    'owner/repo', i + 1, Number(baseTs));
  f.resetQueryCount();
  const result = await tick(f.env);
  assert.ok(result.channels.every(channel => channel.queued === 100));
  assert.equal(f.sqlite.prepare('SELECT COUNT(*) AS n FROM slack_shipping_threads').get().n, 300);
  assert.equal(result.threads.pages, 4);
  assert.equal(result.incidents.queued, 0);
  assert.equal(result.incidents.held, 3);
  assert.equal(result.operators.queued, 0);
  assert.equal(result.operators.held, 2);
  assert.equal(f.posts.length, 0);
  assert.equal(f.sqlite.prepare('SELECT COUNT(*) AS n FROM slack_shipping_outbox').get().n, 0);
  assert.ok(f.queryCount() <= 47, `D1 query budget: ${f.queryCount()}`);
  assert.ok(f.sqlite.prepare('SELECT COUNT(*) AS n FROM slack_shipping_threads WHERE signature=\'\'').get().n >= 296);
  assert.equal(f.requests.filter(url => new URL(url).pathname.endsWith('/chat.postMessage')).length, 0);
});

test('new active work gets priority while a baseline slot advances each minute', async () => {
  const f = fixture();
  f.setHistoryPageSize(100);
  for (let i = 0; i < 7; i++) f.add(channels[0],
    `${Number(baseTs) + i}.${String(i + 1).padStart(6, '0')}`,
    `Bounty issue ${i} still in internal packet.`);
  await tick(f.env);
  assert.equal(f.sqlite.prepare('SELECT COUNT(*) AS n FROM slack_shipping_threads WHERE baseline=1').get().n, 6);
  f.advance(10);
  const hotTs = `${Number(baseTs) + 120}.000001`;
  f.add(channels[1], hotTs, 'Bounty fix done in internal packet.');
  const result = await tick(f.env);
  assert.ok(result.threads.pages >= 2 && result.threads.pages <= 4);
  assert.equal(f.sqlite.prepare('SELECT baseline FROM slack_shipping_threads WHERE channel=? AND root_ts=?').get(channels[1], hotTs).baseline, 0);
  assert.equal(f.sqlite.prepare('SELECT COUNT(*) AS n FROM slack_shipping_threads WHERE baseline=1').get().n, 5);
});

test('free runner clears a large baseline slice and discovers new work during paginated history', async () => {
  const f = fixture();
  f.env.FREE_ACTIONS = true;
  f.setHistoryPageSize(100);
  for (let i = 1; i <= 258; i++)
    f.add(channels[0], `${baseTs}.${String(i).padStart(6, '0')}`, `Bounty issue context ${i}.`);
  const first = await tick(f.env);
  assert.equal(first.channels[0].queued, 100);
  assert.equal(first.threads.pages, 100);
  assert.equal(f.sqlite.prepare('SELECT COUNT(*) AS n FROM slack_shipping_threads WHERE baseline=1').get().n, 0);
  assert.equal(f.posts.length, 0);
  f.advance(10);
  const newRoot = `${Number(baseTs) + 120}.000001`;
  f.add(channels[0], newRoot, 'Bounty fix done in internal packet.');
  const second = await tick(f.env);
  assert.equal(second.channels[0].recent.queued, 1);
  assert.equal(second.threads.pages, 120);
  const hot = f.sqlite.prepare('SELECT baseline,signature FROM slack_shipping_threads WHERE channel=? AND root_ts=?')
    .get(channels[0], newRoot);
  assert.equal(hot.baseline, 0);
  assert.notEqual(hot.signature, '');
  assert.equal(second.delivered.code, 'outbound_sender_identity_unverified');
  assert.equal(second.delivered.delivered, false);
  assert.equal(f.posts.length, 0);
  assert.equal(f.sqlite.prepare('SELECT COUNT(*) AS n FROM slack_shipping_outbox').get().n, 0);
  assert.equal(f.requests.filter(url => new URL(url).pathname.endsWith('/chat.postMessage')).length, 0);
});

test('free runner persists Slack Retry-After and defers without consuming the thread cursor', async () => {
  const f = fixture();
  f.env.FREE_ACTIONS = true;
  f.add(channels[0], `${baseTs}.000001`, 'Bounty issue context.');
  f.setRateLimitOnce('conversations.replies');
  const first = await tick(f.env);
  assert.equal(first.threads.rate_limited, true);
  assert.equal(first.threads.pages, 0);
  const retry = f.sqlite.prepare('SELECT value FROM slack_shipping_state WHERE key=?')
    .get('slack_retry:conversations.replies');
  assert.ok(Number(retry.value) > Date.now());
  assert.equal(f.sqlite.prepare('SELECT signature FROM slack_shipping_threads').get().signature, '');
  const calls = f.requests.filter(u => new URL(u).pathname.endsWith('/conversations.replies')).length;
  await tick({ ...f.env, SLACK_COOLDOWNS: undefined });
  assert.equal(f.requests.filter(u => new URL(u).pathname.endsWith('/conversations.replies')).length, calls);
});

test('free runner stops thread scanning at elapsed-time budget and retains backlog', async () => {
  const f = fixture();
  f.env.FREE_ACTIONS = true;
  f.setHistoryPageSize(100);
  for (let i = 1; i <= 100; i++)
    f.add(channels[0], `${baseTs}.${String(i).padStart(6, '0')}`, `Bounty issue context ${i}.`);
  const fetchBefore = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    if (new URL(String(url)).pathname.endsWith('/conversations.replies')) f.advance(10);
    return fetchBefore(url, options);
  };
  let result;
  try { result = await tick(f.env); }
  finally { globalThis.fetch = fetchBefore; }
  assert.ok(result.threads.pages > 0 && result.threads.pages < 100);
  assert.equal(result.threads.deadline_reached, true);
  assert.ok(f.sqlite.prepare('SELECT COUNT(*) AS n FROM slack_shipping_threads WHERE baseline=1').get().n > 0);
});
