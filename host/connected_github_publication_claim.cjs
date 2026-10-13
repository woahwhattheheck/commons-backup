'use strict';

const crypto = require('node:crypto');

const SCHEMA = 'commons-publication-claims/v1';
const HOLDINGS_BRANCH = 'state/claims';
const DEFAULT_LEDGER = 'woahwhattheheck/commons';
const REPO = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const MAX_PATHS = 64;
const MAX_LEASES = 64;

function text(value, label, maxBytes = 256) {
  if (typeof value !== 'string') throw new TypeError(label + ' must be text');
  const out = value.normalize('NFKC').trim();
  if (!out || /[\x00-\x1f\x7f]/.test(out) || Buffer.byteLength(out, 'utf8') > maxBytes) {
    throw new TypeError(label + ' is invalid');
  }
  return out;
}

function repo(value, label) {
  const out = text(value, label, 200).toLowerCase();
  if (!REPO.test(out)) throw new TypeError(label + ' must be owner/repository');
  return out;
}

function publicationKey(targetRepository, baseBranch, branchName) {
  const digest = crypto.createHash('sha256').update([
    targetRepository.toLowerCase(), baseBranch, branchName,
  ].join('\0')).digest('hex').slice(0, 32);
  return 'pubset-' + digest;
}

function preparePublicationClaim(value, spec) {
  if (value === undefined || value === false) return null;
  if (!spec || typeof spec !== 'object') throw new TypeError('publication claim requires a prepared change');
  const input = value === true ? {} : value;
  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    throw new TypeError('publication_claims must be boolean or an object');
  }
  const allowed = new Set(['ledger_repository_full_name', 'holder', 'ttl_s', 'issue_key']);
  for (const key of Object.keys(input)) {
    if (!allowed.has(key)) throw new TypeError('Unknown publication claim option: ' + key);
  }
  const targetRepository = repo(spec.repository_full_name, 'repository_full_name');
  const ledgerRepository = repo(input.ledger_repository_full_name ?? DEFAULT_LEDGER,
    'ledger_repository_full_name');
  const baseBranch = text(spec.base_branch, 'base_branch', 240);
  const branchName = text(spec.branch_name, 'branch_name', 240);
  const holder = input.holder === undefined ? 'publisher-' + crypto.randomUUID()
    : text(input.holder, 'publication claim holder', 200);
  const ttl = input.ttl_s === undefined ? 900 : input.ttl_s;
  if (!Number.isSafeInteger(ttl) || ttl < 30 || ttl > 7200) {
    throw new TypeError('publication claim ttl_s must be an integer from 30 to 7200');
  }
  const issueKey = input.issue_key === undefined ? null : text(input.issue_key, 'issue_key', 160);
  if (!Array.isArray(spec.files) || spec.files.length === 0 || spec.files.length > MAX_PATHS) {
    throw new TypeError('publication claims support 1 to ' + MAX_PATHS + ' paths');
  }
  const seen = new Set();
  const paths = spec.files.map(file => {
    const path = text(file?.path, 'publication path', 1024);
    if (seen.has(path)) throw new TypeError('duplicate publication claim path: ' + path);
    seen.add(path);
    return path;
  }).sort();
  const key = publicationKey(targetRepository, baseBranch, branchName);
  return {ledger_repository_full_name: ledgerRepository, holdings_branch: HOLDINGS_BRANCH,
    target_repository_full_name: targetRepository, base_branch: baseBranch,
    branch_name: branchName, holder, ttl_s: ttl, issue_key: issueKey, paths, key,
    file_path: 'publication-claims/' + key + '.json'};
}

function nowISO(now) {
  const ms = now === undefined ? Date.now() : now;
  if (!Number.isFinite(ms) || ms < 0) throw new TypeError('publication claim clock is invalid');
  return {ms, text: new Date(ms).toISOString().replace(/\.\d{3}Z$/, 'Z')};
}

function leaseLive(lease, nowMs) {
  if (!lease || typeof lease !== 'object' || Array.isArray(lease)
      || !Number.isSafeInteger(lease.ttl_s) || lease.ttl_s < 1 || lease.ttl_s > 7200) return false;
  const stamp = Date.parse(lease.heartbeat_at || lease.taken_at || '');
  if (!Number.isFinite(stamp)) return false;
  return nowMs - stamp <= lease.ttl_s * 1000;
}

function parseRecord(observed, config) {
  if (observed?.absent) {
    return {sha: null, record: {schema: SCHEMA, key: config.key,
      repository: config.target_repository_full_name, base_branch: config.base_branch,
      branch_name: config.branch_name, leases: []}};
  }
  const data = observed?.data;
  if (!data || typeof data !== 'object' || typeof data.content !== 'string'
      || typeof data.sha !== 'string' || !/^[0-9a-f]{40}$/.test(data.sha)) {
    throw new Error('Publication claim file lacks exact UTF-8/blob identity');
  }
  let record;
  try { record = JSON.parse(data.content); }
  catch (_) { throw new Error('Publication claim file is not valid JSON'); }
  if (!record || typeof record !== 'object' || Array.isArray(record)
      || record.schema !== SCHEMA || record.key !== config.key
      || record.repository !== config.target_repository_full_name
      || record.base_branch !== config.base_branch || record.branch_name !== config.branch_name
      || !Array.isArray(record.leases) || record.leases.length > MAX_LEASES) {
    throw new Error('Publication claim file has incompatible metadata');
  }
  return {sha: data.sha, record};
}

function overlap(left, right) {
  const wanted = new Set(left);
  return right.filter(path => wanted.has(path));
}

function retryableConflict(error) {
  const status = error?.tool_error?.http_status;
  return status === 409 || status === 422 || /sha.*match|already exists|conflict|reference.*moved/i.test(String(error?.message || error));
}

async function mutatePublicationClaims({readFile, call, config, action, attempts = 3, now}) {
  if (!config) return {status: 'DISABLED'};
  if (!['take', 'release'].includes(action)) throw new TypeError('unsupported publication claim action');
  if (typeof readFile !== 'function' || typeof call !== 'function') {
    throw new TypeError('publication claim I/O callbacks are required');
  }
  if (!Number.isSafeInteger(attempts) || attempts < 1 || attempts > 5) {
    throw new TypeError('publication claim attempts must be from 1 to 5');
  }
  for (let attempt = 1; attempt <= attempts; attempt++) {
    const clock = nowISO(now === undefined ? undefined : now);
    const observed = await readFile({repository_full_name: config.ledger_repository_full_name,
      path: config.file_path, ref: config.holdings_branch, encoding: 'utf-8'});
    const {sha, record} = parseRecord(observed, config);
    const live = record.leases.filter(lease => leaseLive(lease, clock.ms));
    const own = live.find(lease => lease.holder === config.holder);
    if (action === 'take') {
      const conflicts = [];
      for (const lease of live) {
        if (lease.holder === config.holder) continue;
        const shared = overlap(config.paths, Array.isArray(lease.paths) ? lease.paths : []);
        if (shared.length) conflicts.push({holder: lease.holder, paths: shared,
          heartbeat_at: lease.heartbeat_at, ttl_s: lease.ttl_s, issue_key: lease.issue_key ?? null});
      }
      if (conflicts.length) {
        return {status: 'HELD_BY_PEER', holder: config.holder, conflicts,
          file_sha: sha, provider_writes: 0};
      }
      if (!own && live.length >= MAX_LEASES) {
        throw new RangeError('Publication claim file has too many live disjoint leases');
      }
      const lease = {holder: config.holder, paths: config.paths, heartbeat_at: clock.text,
        ttl_s: config.ttl_s, ...(config.issue_key ? {issue_key: config.issue_key} : {})};
      lease.taken_at = own?.taken_at ?? clock.text;
      record.leases = [...live.filter(row => row.holder !== config.holder), lease];
    } else {
      if (!own) return {status: 'ALREADY_RELEASED', holder: config.holder,
        file_sha: sha, provider_writes: 0};
      record.leases = live.filter(row => row.holder !== config.holder);
    }
    const content = JSON.stringify(record, null, 2) + '\n';
    try {
      let result;
      if (sha === null) {
        result = await call('create_file', {repository_full_name: config.ledger_repository_full_name,
          path: config.file_path, branch: config.holdings_branch, content,
          message: action + ' publication paths for ' + config.branch_name});
      } else {
        result = await call('update_file', {repository_full_name: config.ledger_repository_full_name,
          path: config.file_path, branch: config.holdings_branch, content, sha,
          message: action + ' publication paths for ' + config.branch_name});
      }
      return {status: action === 'take' ? 'ACQUIRED' : 'RELEASED', holder: config.holder,
        paths: config.paths, file_path: config.file_path, previous_file_sha: sha,
        content_sha: result?.content_sha ?? null, commit_sha: result?.commit_sha ?? null,
        attempt, provider_writes: 1, live_leases: record.leases.length};
    } catch (error) {
      if (!retryableConflict(error) || attempt === attempts) throw error;
    }
  }
  return {status: 'RACE_RETRY_REQUIRED', holder: config.holder, provider_writes: null};
}

module.exports = {preparePublicationClaim, mutatePublicationClaims, publicationKey, leaseLive};
