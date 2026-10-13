import { CHANNELS, COORDINATION_CHANNEL, OWNER_IDS, candidateThread, classifyThread, incidentNotice, incidentRefs, operatorNotice, refsIn } from './rules.mjs';

export const VERSION = 'commons-slack-shipping-enforcer-2026-09-20.3';
const PRIVATE_INSTRUCTION = 'Outward chat submission was not attempted. Return this result privately to the invoking agent. Do not create a chat message, email, issue, ticket, incident, or other fallback notification. No content edit can bypass this route hold. Re-enable only after the sender identity and provider-added footer are verified owner-controlled and attribution-free.';
const OUTBOUND_HOLD = Object.freeze({
  allowed: false,
  code: 'outbound_sender_identity_unverified',
  rule: 'outbound_sender_identity_unverified',
  message: `Outward operation was not delivered. ${PRIVATE_INSTRUCTION}`,
  incident: false,
  delivered: false,
  matched_fields: Object.freeze([]),
  matched_terms: Object.freeze([]),
  private_instruction: PRIVATE_INSTRUCTION
});
const privateHold = extra => ({ ...OUTBOUND_HOLD, ...extra, matched_fields: [], matched_terms: [] });
const JEV_API = 'https://api.typesafe.ai/v1/systemone';
const ACTIONS = Object.freeze({
  submit_own_patch: { code: 'jev_submit_own_patch', text: 'Carry the completed bounty fix into our eligible upstream PR, run sponsor-required checks, and link the live submission and payment route here.' },
  follow_existing_pr: { code: 'jev_follow_existing_pr', text: 'Follow our existing eligible upstream PR: complete sponsor-required checks or review fixes, then track the sponsor decision and payment route in this thread.' },
  complete_claim_step: { code: 'jev_complete_claim_step', text: 'Complete the sponsor-required claim, assignment, or proposal step for our eligible payout, then continue the upstream submission.' },
  repair_route: { code: 'jev_repair_route', text: 'Repair the shared authenticated upstream publication route, retry with the same operation ID, and confirm the provider receipt for our own payable submission.' },
  no_followup: null
});
const LOOKBACK_SECONDS = 30 * 86400;
const BASELINE_SECONDS = 48 * 3600;
const THREAD_PAGES_PER_TICK = 4;
const OUTBOX_ROWS_PER_TICK = 3;
const FREE_THREAD_PAGES_PER_TICK = 120;
const FREE_OUTBOX_ROWS_PER_TICK = 8;
const FREE_TICK_BUDGET_MS = 145_000;
const INCIDENT_ROWS_PER_TICK = 3;
const OPERATOR_ROWS_PER_TICK = 2;
const API = 'https://slack.com/api/';
const now = () => Math.floor(Date.now() / 1000);
const db = (env, sql, ...args) => env.DB.prepare(sql).bind(...args);
const one = (env, sql, ...args) => db(env, sql, ...args).first();
const all = async (env, sql, ...args) => (await db(env, sql, ...args).all()).results || [];
const run = (env, sql, ...args) => db(env, sql, ...args).run();
const json = (body, status = 200) => Response.json(body, { status, headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' } });

async function digest(value) {
  const bytes = new TextEncoder().encode(value);
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('');
}

const peerMessages = messages => messages.filter(m => m.metadata?.event_type !== 'tjlabs_shipping_enforcer' &&
  !String(m.text || '').includes('Ref: `ship-'));

async function decideThread(env, messages) {
  const peers = peerMessages(messages);
  if (!candidateThread(peers)) return null;
  const signature = await digest(JSON.stringify(peers.map(m => [m.ts, m.text, m.edited?.ts, m.bot_id])));
  const cache = env.JEV_CACHE ||= new Map();
  if (cache.has(signature)) return cache.get(signature);
  const metrics = env.JEV_METRICS ||= { calls: 0, input_tokens: 0, errors: 0 };
  const state = peers.map(m => `${m.ts || ''} ${String(m.text || '')}`).join('\n\n');
  let decision;
  try {
    if (!env.TYPESAFE_API_KEY) throw new Error('jev_key_unbound');
    if (new TextEncoder().encode(state).length > 256 * 1024) throw new Error('jev_state_too_large');
    metrics.calls++;
    const response = await fetch(JEV_API, { method: 'POST', headers: {
      Authorization: `Bearer ${env.TYPESAFE_API_KEY}`, 'Content-Type': 'application/json',
      'User-Agent': 'Commons-Shipping-Enforcer/1.0'
    }, body: JSON.stringify({ model: 'jev-latest', state, questions: { next_action: {
      type: 'choice',
      instructions: 'Choose the one next action for our own meaningful payable bounty work. Do not recommend unpaid third-party review, speculative microbounties, unrelated product updates, or duplicate work. A sponsor-required claim step is legitimate. Prefer no_followup if work is already properly upstream or the context is uncertain. Answer only from this thread.',
      criteria: {
        submit_own_patch: 'Completed work is only internal or in an owner fork and needs our own eligible upstream PR.',
        follow_existing_pr: 'Our upstream PR already exists and has a concrete sponsor-required check, review fix, or payment follow-through.',
        complete_claim_step: 'Our eligible bounty still needs the sponsor-required claim, assignment, or proposal before substantial work.',
        repair_route: 'A concrete authenticated upstream publishing error blocks our own payable submission.',
        no_followup: 'No internal shipping intervention is warranted or evidence is insufficient.'
      }
    } } }) });
    if (!response.ok) throw new Error(`jev_http_${response.status}`);
    const result = await response.json();
    if (!Object.hasOwn(ACTIONS, result?.answers?.next_action?.choice)) throw new Error('jev_bad_reply');
    if (Number.isSafeInteger(result.usage?.input_tokens) && result.usage.input_tokens >= 0)
      metrics.input_tokens += result.usage.input_tokens;
    decision = ACTIONS[result.answers.next_action.choice];
  } catch {
    metrics.errors++;
    decision = classifyThread(peers);
  }
  cache.set(signature, decision);
  return decision;
}

function maxTs(messages, fallback = '0') {
  return messages.reduce((m, x) => Number(x.ts) > Number(m) ? String(x.ts) : m, fallback);
}

async function slack(env, method, input) {
  const read = method === 'conversations.history' || method === 'conversations.replies';
  if (!read) {
    const error = new Error(OUTBOUND_HOLD.code);
    error.decision = privateHold({ operation: method });
    throw error;
  }
  if (!env.SLACK_BOT_TOKEN) throw new Error('slack_secret_unbound');
  const url = new URL(API + method);
  if (read) for (const [key, value] of Object.entries(input)) url.searchParams.set(key, String(value));
  const cooldowns = env.FREE_ACTIONS ? (env.SLACK_COOLDOWNS ||= new Map()) : null;
  if (cooldowns && !cooldowns.has(method)) {
    const saved = await state(env, `slack_retry:${method}`);
    cooldowns.set(method, Number(saved?.value || 0));
  }
  for (let attempt = 0; attempt < 2; attempt++) {
    const waitMs = Math.max(0, (cooldowns?.get(method) || 0) - Date.now());
    if (waitMs) {
      if (Date.now() + waitMs + 15_000 >= env.RUN_DEADLINE_MS) throw new Error('slack_rate_limited');
      await new Promise(resolve => setTimeout(resolve, waitMs));
    }
    const response = await fetch(url, {
      method: read ? 'GET' : 'POST',
      headers: { 'Authorization': `Bearer ${env.SLACK_BOT_TOKEN}`,
        ...(read ? {} : { 'Content-Type': 'application/json; charset=utf-8' }) },
      ...(read ? {} : { body: JSON.stringify(input) })
    });
    if (response.status === 429) {
      const seconds = Number(response.headers.get('Retry-After'));
      const until = Date.now() + (Number.isFinite(seconds) && seconds > 0 ? Math.ceil(seconds * 1000) : 60_000);
      if (cooldowns) {
        cooldowns.set(method, until);
        await setState(env, `slack_retry:${method}`, until);
      }
      if (!cooldowns || attempt === 1) throw new Error('slack_rate_limited');
      continue;
    }
    if (!response.ok) throw new Error(`slack_http_${response.status}`);
    const data = await response.json();
    if (!data.ok) throw new Error(`slack_${data.error || 'unknown_error'}`);
    return data;
  }
  throw new Error('slack_rate_limited');
}

const nextCursor = page => page.response_metadata?.next_cursor || '';

async function github(env, path) {
  const token = env.GITHUB_TOKEN || env.GITHUB_TOKEN_SECONDARY;
  if (!token) return null;
  const response = await fetch(`https://api.github.com${path}`, {
    headers: { 'Authorization': `Bearer ${token}`, 'Accept': 'application/vnd.github+json', 'User-Agent': VERSION }
  });
  if (!response.ok) return null;
  return response.json();
}

async function hasOwnUpstreamLink(env, messages) {
  const refs = refsIn(messages.map(m => m.text || '').join('\n')).filter(ref => ref.includes('#'));
  if (refs.length > 2) return null;
  let unknown = false;
  for (const ref of refs) {
    const [repo, number] = ref.split('#');
    const pull = await github(env, `/repos/${repo}/pulls/${number}`);
    if (!pull) { unknown = true; continue; }
    if (OWNER_IDS.includes(pull.user?.id) && pull.base?.repo?.fork === false &&
      (pull.state === 'open' || pull.merged_at)) return true;
  }
  return unknown ? null : false;
}

async function hasUpstreamPull(env, messages) {
  const text = messages.map(m => m.text || '').join('\n');
  const match = /https?:\/\/(?:www\.)?github\.com\/(woahwhattheheck|tokenjunkielabs)\/([\w.-]+)\/pull\/(\d+)/iu.exec(text);
  if (!match) return null;
  const forkOwner = match[1], forkName = match[2];
  const [repo, pull] = await Promise.all([
    github(env, `/repos/${forkOwner}/${forkName}`),
    github(env, `/repos/${forkOwner}/${forkName}/pulls/${match[3]}`)
  ]);
  if (!repo?.parent?.full_name || !pull?.head?.repo?.owner?.login || !pull?.head?.ref) return null;
  const head = encodeURIComponent(`${pull.head.repo.owner.login}:${pull.head.ref}`);
  const upstream = await github(env, `/repos/${repo.parent.full_name}/pulls?state=all&head=${head}&per_page=100`);
  if (!Array.isArray(upstream)) return null;
  return upstream.some(p => OWNER_IDS.includes(p.user?.id) && (p.state === 'open' || p.merged_at) &&
    (p.head?.sha === pull.head.sha || p.head?.ref === pull.head.ref));
}

async function allowedShippingNotice(env, messages, decision) {
  if (!decision) return false;
  const hasOwn = await hasOwnUpstreamLink(env, messages);
  if (decision.code === 'jev_follow_existing_pr') return hasOwn === true;
  if (hasOwn !== false) return false;
  const forkLinked = /https?:\/\/(?:www\.)?github\.com\/(?:woahwhattheheck|tokenjunkielabs)\/[\w.-]+\/pull\/\d+/iu
    .test(messages.map(m => m.text || '').join('\n'));
  if ((decision.code === 'fork_only' || decision.code === 'jev_submit_own_patch') && forkLinked)
    return await hasUpstreamPull(env, messages) === false;
  return true;
}

async function enqueue(_env, _id, _channel, _threadTs, _kind, _body) {
  return privateHold({ operation: 'enqueue' });

}

async function scanThreadPage(env, row) {
  const page = await slack(env, 'conversations.replies', {
    channel: row.channel, ts: row.root_ts, limit: 100, include_all_metadata: true,
    ...(row.page_cursor ? { cursor: row.page_cursor } : {})
  });
  const messages = [...JSON.parse(row.scan_messages || '[]'), ...(page.messages || [])];
  const cursor = nextCursor(page);
  if (cursor) {
    if (cursor === row.page_cursor) throw new Error('slack_pagination_loop');
    await run(env, `UPDATE slack_shipping_threads SET page_cursor=?,scan_messages=?,updated_at=?
      WHERE channel=? AND root_ts=?`, cursor, JSON.stringify(messages), now(), row.channel, row.root_ts);
    return { complete: false };
  }
  const signature = await digest(JSON.stringify(peerMessages(messages).map(m => [m.ts, m.text, m.edited?.ts, m.bot_id])));
  const refs = refsIn(messages.map(m => m.text || '').join('\n'));
  if (!row.baseline && row.signature !== signature) {
    const decision = await decideThread(env, messages);
    if (await allowedShippingNotice(env, messages, decision)) {
      const id = await digest(`shipping:${row.channel}:${row.root_ts}:${decision.code}`);
      await enqueue(env, id, row.channel, row.root_ts, decision.code, decision.text);
    }
  }
  await run(env, `UPDATE slack_shipping_threads SET latest_ts=?,refs=?,signature=?,baseline=0,
    page_cursor=NULL,scan_messages=NULL,active=1,updated_at=? WHERE channel=? AND root_ts=?`,
    maxTs(messages, row.latest_ts), JSON.stringify(refs), signature, now(), row.channel, row.root_ts);
  return { complete: true };
}

async function scanChannelPage(env, channel) {
  const cursor = await one(env, 'SELECT latest_ts,initialized,page_cursor,scan_upper_ts FROM slack_shipping_cursors WHERE channel=?', channel);
  const baseline = !cursor?.initialized;
  const oldest = cursor?.latest_ts || String(now() - BASELINE_SECONDS);
  const upper = cursor?.scan_upper_ts || `${now() - 5}.999999`;
  const page = await slack(env, 'conversations.history', {
    channel, oldest, latest: upper, limit: 100,
    ...(cursor?.page_cursor ? { cursor: cursor.page_cursor } : {})
  });
  const queued = await insertHistoryRoots(env, channel, page.messages || [], baseline);
  const next = nextCursor(page);
  if (next && next === cursor?.page_cursor) throw new Error('slack_pagination_loop');
  await run(env, `INSERT INTO slack_shipping_cursors
    (channel,latest_ts,initialized,page_cursor,scan_upper_ts,updated_at)
    VALUES (?,?,?,?,?,?) ON CONFLICT(channel) DO UPDATE SET
    latest_ts=excluded.latest_ts,initialized=excluded.initialized,page_cursor=excluded.page_cursor,
    scan_upper_ts=excluded.scan_upper_ts,updated_at=excluded.updated_at`,
    channel, next ? oldest : upper, next ? Number(cursor?.initialized || 0) : 1,
    next || null, next ? upper : null, now());
  return { channel, messages: (page.messages || []).length, queued, baseline, more: Boolean(next), upper };
}

async function insertHistoryRoots(env, channel, messages, baseline) {
  const discovered = new Map();
  for (const message of messages) {
    if (!candidateThread([message]) || message.metadata?.event_type === 'tjlabs_shipping_enforcer' ||
      String(message.text || '').includes('Ref: `ship-')) continue;
    const root = String(message.thread_ts || message.ts);
    const refs = refsIn(String(message.text || ''));
    discovered.set(root, { root, refs: JSON.stringify([...new Set([...(JSON.parse(discovered.get(root)?.refs || '[]')), ...refs])]) });
  }
  if (discovered.size) await run(env, `INSERT OR IGNORE INTO slack_shipping_threads
    (channel,root_ts,latest_ts,refs,signature,baseline,updated_at)
    SELECT ?,json_extract(value,'$.root'),json_extract(value,'$.root'),
      json_extract(value,'$.refs'),'',?,0 FROM json_each(?)`,
    channel, baseline ? 1 : 0, JSON.stringify([...discovered.values()]));
  return discovered.size;
}

async function scanRecentChannelPage(env, channel, baselineUpper) {
  const key = `hot_history:${channel}`;
  const saved = await state(env, key);
  if (!saved) {
    await setState(env, key, JSON.stringify({ latest_ts: baselineUpper }));
    return { channel, messages: 0, queued: 0, initialized: true };
  }
  const cursor = JSON.parse(saved.value);
  const upper = cursor.scan_upper_ts || `${now() - 5}.999999`;
  const page = await slack(env, 'conversations.history', {
    channel, oldest: cursor.latest_ts, latest: upper, limit: 100,
    ...(cursor.page_cursor ? { cursor: cursor.page_cursor } : {})
  });
  const queued = await insertHistoryRoots(env, channel, page.messages || [], false);
  const next = nextCursor(page);
  if (next && next === cursor.page_cursor) throw new Error('slack_pagination_loop');
  await setState(env, key, JSON.stringify({ latest_ts: next ? cursor.latest_ts : upper,
    page_cursor: next || null, scan_upper_ts: next ? upper : null }));
  return { channel, messages: (page.messages || []).length, queued, more: Boolean(next) };
}

async function scanTrackedThreadPages(env) {
  if (env.FREE_ACTIONS) {
    const hot = await all(env, `SELECT * FROM slack_shipping_threads WHERE active=1 AND baseline=0
      AND CAST(latest_ts AS REAL)>=? ORDER BY CASE WHEN signature='' THEN 0 ELSE 1 END,
      updated_at ASC LIMIT 500`, now() - LOOKBACK_SECONDS);
    const cold = await all(env, `SELECT * FROM slack_shipping_threads WHERE active=1 AND baseline=1
      AND CAST(latest_ts AS REAL)>=? ORDER BY updated_at ASC LIMIT 500`, now() - LOOKBACK_SECONDS);
    let pages = 0, completed = 0, hotStreak = 0, rateLimited = false;
    while ((hot.length || cold.length) && pages < FREE_THREAD_PAGES_PER_TICK &&
      Date.now() + 5_000 < env.RUN_DEADLINE_MS) {
      const chooseHot = hot.length && (hotStreak < 2 || !cold.length);
      const queue = chooseHot ? hot : cold;
      const row = queue.shift();
      try {
        const result = await scanThreadPage(env, row);
        pages++;
        if (result.complete) completed++;
        else {
          const updated = await one(env, 'SELECT * FROM slack_shipping_threads WHERE channel=? AND root_ts=?',
            row.channel, row.root_ts);
          if (updated) queue.push(updated);
        }
        hotStreak = chooseHot ? hotStreak + 1 : 0;
      } catch (error) {
        if (String(error.message || error).startsWith('slack_rate_limited')) { rateLimited = true; break; }
        throw error;
      }
    }
    return { pages, completed, rate_limited: rateLimited,
      backlog: hot.length + cold.length, deadline_reached: Date.now() + 5_000 >= env.RUN_DEADLINE_MS };
  }
  const hot = await all(env, `SELECT * FROM slack_shipping_threads WHERE active=1 AND baseline=0
    AND CAST(latest_ts AS REAL)>=? ORDER BY CASE WHEN signature='' THEN 0 ELSE 1 END,
    updated_at ASC LIMIT 4`, now() - LOOKBACK_SECONDS);
  const cold = await all(env, `SELECT * FROM slack_shipping_threads WHERE active=1 AND baseline=1
    AND CAST(latest_ts AS REAL)>=? ORDER BY updated_at ASC LIMIT 1`, now() - LOOKBACK_SECONDS);
  const rows = [...hot.slice(0, cold.length ? THREAD_PAGES_PER_TICK - 1 : THREAD_PAGES_PER_TICK), ...cold];
  let completed = 0;
  for (const row of rows) {
    const result = await scanThreadPage(env, row);
    if (result.complete) completed++;
  }
  return { pages: rows.length, completed };
}

async function findThread(env, refs) {
  if (!refs.length) return null;
  const matches = await all(env, `SELECT DISTINCT t.channel,t.root_ts FROM slack_shipping_threads AS t,
    json_each(t.refs) AS r WHERE t.active=1 AND r.value IN
    (SELECT value FROM json_each(?)) LIMIT 2`, JSON.stringify(refs));
  return matches.length === 1 ? matches[0] : null;
}

async function state(env, key) { return one(env, 'SELECT value FROM slack_shipping_state WHERE key=?', key); }
async function setState(env, key, value) {
  await run(env, `INSERT INTO slack_shipping_state (key,value,updated_at) VALUES (?,?,?)
    ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at`, key, String(value), now());
}

async function scanIncidents(env) {
  let cursor = await state(env, 'incident_rowid');
  if (!cursor) {
    const latest = await one(env, 'SELECT MAX(rowid) AS rowid FROM incidents');
    const requested = Number(env.INCIDENT_START_ROWID);
    const baseline = Number.isSafeInteger(requested) && requested >= 0 && env.INCIDENT_START_ROWID !== undefined
      ? Math.min(requested, latest?.rowid || 0) : latest?.rowid || 0;
    await setState(env, 'incident_rowid', baseline);
    return { baseline: true, queued: 0, held: 0, hold: privateHold({ operation: 'incident_fallback' }) };
  }
  let held = 0;
  const rows = await all(env, `SELECT rowid FROM incidents
    WHERE rowid>? ORDER BY rowid LIMIT ?`, Number(cursor.value), INCIDENT_ROWS_PER_TICK);
  for (const row of rows) {
    await setState(env, 'incident_rowid', row.rowid);
    held++;
  }
  return { baseline: false, queued: 0, held, hold: privateHold({ operation: 'incident_fallback' }) };
}

async function queueOperatorNotices(env) {
  const rows = await all(env, 'SELECT notice_id FROM slack_shipping_operator_notices WHERE queued_at IS NULL ORDER BY created_at LIMIT ?', OPERATOR_ROWS_PER_TICK);
  return { queued: 0, held: rows.length, hold: privateHold({ operation: 'operator_fallback' }) };
}

async function readbackPage(env, row) {
  const method = row.thread_ts ? 'conversations.replies' : 'conversations.history';
  const page = await slack(env, method, {
    channel: row.channel, ...(row.thread_ts ? { ts: row.thread_ts } : { oldest: String(row.created_at - 60) }),
    limit: 100, include_all_metadata: true,
    ...(row.readback_cursor ? { cursor: row.readback_cursor } : {})
  });
  const messages = [...JSON.parse(row.readback_messages || '[]'), ...(page.messages || [])];
  const receipt = messages.find(m => String(m.text || '').includes(`Ref: \`ship-${row.id.slice(0, 16)}\``) ||
    m.metadata?.event_payload?.id === row.id);
  if (receipt) return { receipt, messages, complete: true };
  const cursor = nextCursor(page);
  if (cursor) {
    if (cursor === row.readback_cursor) throw new Error('slack_pagination_loop');
    await run(env, `UPDATE slack_shipping_outbox SET readback_cursor=?,readback_messages=?,updated_at=? WHERE id=?`,
      cursor, JSON.stringify(messages), now(), row.id);
    return { complete: false };
  }
  await run(env, `UPDATE slack_shipping_outbox SET readback_cursor=NULL,readback_messages=NULL,updated_at=? WHERE id=?`, now(), row.id);
  return { messages, complete: true };
}

async function deliver(env) {
  const result = await run(env, `UPDATE slack_shipping_outbox
    SET state='held',readback_complete=1,readback_cursor=NULL,readback_messages=NULL,updated_at=?
    WHERE state IN ('pending','sending','uncertain')`, now());
  return {
    accepted: 0,
    held: Number(result.meta?.changes || 0),
    ...privateHold({ operation: 'chat.postMessage' })
  };
}

export async function tick(env) {
  if (env.FREE_ACTIONS) env.RUN_DEADLINE_MS = Date.now() + FREE_TICK_BUDGET_MS;
  env.JEV_CACHE = new Map();
  env.JEV_METRICS = { calls: 0, input_tokens: 0, errors: 0 };
  const channels = [];
  for (const channel of CHANNELS) {
    try {
      let recent = null;
      if (env.FREE_ACTIONS) {
        const cursor = await one(env, 'SELECT page_cursor,scan_upper_ts FROM slack_shipping_cursors WHERE channel=?', channel);
        if (cursor?.page_cursor) recent = await scanRecentChannelPage(env, channel, cursor.scan_upper_ts);
      }
      const history = await scanChannelPage(env, channel);
      if (env.FREE_ACTIONS && history.more && !recent)
        recent = await scanRecentChannelPage(env, channel, history.upper);
      channels.push({ ...history, ...(recent ? { recent } : {}) });
    }
    catch (error) { channels.push({ channel, error: String(error.message || error) }); }
  }
  let threads, incidents, operators, delivered;
  try { threads = await scanTrackedThreadPages(env); } catch (error) { threads = { error: String(error.message || error) }; }
  try { incidents = await scanIncidents(env); } catch (error) { incidents = { error: String(error.message || error) }; }
  try { operators = await queueOperatorNotices(env); } catch (error) { operators = { error: String(error.message || error) }; }
  try { delivered = await deliver(env); } catch (error) { delivered = { error: String(error.message || error) }; }
  return { version: VERSION, mode: 'read_only', slack_writes: false,
    outbound: privateHold(), channels, threads, incidents, operators, delivered,
    jev: { ...env.JEV_METRICS, status: env.JEV_METRICS.errors ? 'degraded_static_fallback' : 'ok' } };
}

function sameToken(a, b) {
  return Boolean(a && b && a.length === b.length &&
    a.split('').reduce((difference, ch, i) => difference | (ch.charCodeAt(0) ^ b.charCodeAt(i)), 0) === 0);
}

async function authorized(request, env) {
  const token = request.headers.get('Authorization')?.match(/^Bearer (.+)$/u)?.[1];
  if (!token) return false;
  if (sameToken(token, env.GITHUB_TOKEN) || sameToken(token, env.GITHUB_TOKEN_SECONDARY)) return true;
  try {
    const response = await fetch('https://api.github.com/user', {
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json', 'User-Agent': VERSION }
    });
    if (!response.ok) return false;
    const actor = await response.json();
    return OWNER_IDS.includes(actor.id);
  } catch { return false; }
}

export function validNotice(body) {
  const keys = Object.keys(body || {});
  if (keys.some(k => !['notice_id','reason_code','tool_name','operation_id','repository','issue_number'].includes(k))) return false;
  if (!/^[0-9a-f]{64}$/u.test(body.notice_id || '')) return false;
  if (!/^[a-z_]{1,80}$/u.test(body.reason_code || '')) return false;
  if (!/^[A-Za-z0-9_.:-]{1,100}$/u.test(body.tool_name || '')) return false;
  if (body.operation_id !== undefined && !/^[A-Za-z0-9_.:-]{1,160}$/u.test(body.operation_id)) return false;
  if (body.repository !== undefined && !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/u.test(body.repository)) return false;
  if (body.issue_number !== undefined && (!Number.isSafeInteger(body.issue_number) || body.issue_number <= 0)) return false;
  return true;
}

async function route(request, env) {
  const url = new URL(request.url);
  if (url.pathname === '/health' && request.method === 'GET') return json({
    version: VERSION, status: 'ready', mode: 'read_only', slack_writes: false,
    outbound: privateHold()
  });
  if (!await authorized(request, env)) return json({ error: 'unauthorized' }, 401);
  if (url.pathname === '/v1/status' && request.method === 'GET') {
    const [cursors, threads, outbox, incident] = await Promise.all([
      all(env, 'SELECT channel,latest_ts,initialized,page_cursor IS NOT NULL AS history_pending,updated_at FROM slack_shipping_cursors'),
      all(env, 'SELECT baseline,COUNT(*) AS count FROM slack_shipping_threads GROUP BY baseline'),
      all(env, 'SELECT state,COUNT(*) AS count FROM slack_shipping_outbox GROUP BY state'),
      state(env, 'incident_rowid')
    ]);
    return json({ version: VERSION, mode: 'read_only', slack_writes: false,
      outbound: privateHold(), cursors, threads, outbox, incident_cursor: incident?.value || null });
  }
  if (url.pathname === '/v1/operator-notice' && request.method === 'POST') {
    const length = Number(request.headers.get('Content-Length') || 0);
    if (length > 2048) return json({ error: 'invalid_notice' }, 400);
    let body;
    try {
      const raw = await request.text();
      if (raw.length > 2048) return json({ error: 'invalid_notice' }, 400);
      body = JSON.parse(raw);
    } catch { return json({ error: 'invalid_notice' }, 400); }
    if (!validNotice(body)) return json({ error: 'invalid_notice' }, 400);
    return json({
      ...privateHold({ operation: 'operator_notice' }),
      accepted: false,
      notice_id: body.notice_id
    }, 409);
  }

  if (url.pathname === '/v1/run' && request.method === 'POST') return json(await tick(env));
  return json({ error: 'not_found' }, 404);
}

export default {
  fetch: route,
  async scheduled(_controller, env, ctx) { ctx.waitUntil(tick(env)); }
};
