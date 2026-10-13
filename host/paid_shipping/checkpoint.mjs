import { createHash } from 'node:crypto';
import { gzipSync, gunzipSync } from 'node:zlib';

export const STATE_PATH = 'paid-work/shipping-state.json';
const STATE_DIR = 'paid-work/shipping-state';
const SHARD_THREADS = 200;
const MAX_RAW_STATE_BYTES = 32 * 1024 * 1024;
const MAX_FILE_BYTES = 390_000;
const sha256 = value => createHash('sha256').update(value).digest('hex');
const rawJson = value => Buffer.from(JSON.stringify(value) + '\n', 'utf8');

export function decodeVersion2(state) {
  const hex = state.codec === 'gzip+hex';
  const b64 = state.codec === 'gzip+base64';
  if ((!hex && !b64) || typeof state.data !== 'string' ||
    !/^[a-f0-9]{64}$/u.test(state.raw_sha256 || '') ||
    (b64 && !/^[A-Za-z0-9+/]*={0,2}$/u.test(state.data)) ||
    (hex && !/^[0-9a-f]*$/u.test(state.data))) throw new Error('state_schema_invalid');
  let raw;
  try {
    raw = gunzipSync(Buffer.from(state.data, hex ? 'hex' : 'base64'),
      { maxOutputLength: MAX_RAW_STATE_BYTES });
  } catch { throw new Error('state_decompression_invalid'); }
  if (sha256(raw) !== state.raw_sha256) throw new Error('state_checksum_invalid');
  return raw;
}

function envelope(raw, encoding) {
  if (raw.length > MAX_RAW_STATE_BYTES) throw new Error('state_raw_too_large');
  return JSON.stringify({ version: 2, codec: `gzip+${encoding}`, raw_sha256: sha256(raw),
    data: gzipSync(raw, { level: 9 }).toString(encoding) }) + '\n';
}

export function serializeTables(tables) {
  return envelope(rawJson({ version: 1, tables }), 'base64');
}

export function planTables(tables) {
  if (rawJson({ version: 1, tables }).length > MAX_RAW_STATE_BYTES)
    throw new Error('state_raw_too_large');
  const threads = tables.slack_shipping_threads;
  if (threads.length <= SHARD_THREADS) {
    return { mode: 'single', files: [{ path: STATE_PATH, text: serializeTables(tables) }] };
  }
  const files = [];
  const names = [];
  let totalBytes = 0;
  function shard(prefix, value) {
    const raw = rawJson(value);
    totalBytes += raw.length;
    if (totalBytes > MAX_RAW_STATE_BYTES) throw new Error('state_raw_too_large');
    const text = envelope(raw, 'hex');
    // Bind the name to the exact stored bytes, including compression. A new
    // generation never changes any file still referenced by the old index.
    const name = `${prefix}-${sha256(text)}.json`;
    files.push({ path: `${STATE_DIR}/${name}`, text });
    return name;
  }
  for (let index = 0; index < threads.length; index += SHARD_THREADS) {
    names.push(shard(`threads-${String(names.length).padStart(4, '0')}`, {
      version: 1, table: 'slack_shipping_threads', rows: threads.slice(index, index + SHARD_THREADS)
    }));
  }
  const rest = shard('rest', { version: 1, tables: { ...tables, slack_shipping_threads: [] } });
  files.push({ path: STATE_PATH, text: JSON.stringify({ version: 4,
    codec: 'shard-gzip+hex', shards: names, rest, thread_count: threads.length }) + '\n' });
  return { mode: 'sharded', files };
}

/** Read one index snapshot. The callback reads files, never changes the index. */
export async function materializeCheckpoint(text, readFile) {
  const state = JSON.parse(text);
  if (state.version !== 3 && state.version !== 4) return text;
  const immutable = state.version === 4;
  if (state.codec !== 'shard-gzip+hex' || !Array.isArray(state.shards) ||
    typeof state.rest !== 'string' || !Number.isSafeInteger(state.thread_count) || state.thread_count < 0 ||
    new Set(state.shards).size !== state.shards.length) throw new Error('state_schema_invalid');
  let totalBytes = 0;
  async function readPart(name, pattern) {
    if (typeof name !== 'string') throw new Error('state_schema_invalid');
    const match = pattern.exec(name);
    if (!match) throw new Error('state_schema_invalid');
    const file = await readFile(`${STATE_DIR}/${name}`);
    if (!file) throw new Error('state_shard_missing');
    if (immutable && sha256(file.text) !== match[1]) throw new Error('state_shard_checksum_invalid');
    const raw = decodeVersion2(JSON.parse(file.text));
    totalBytes += raw.length;
    if (totalBytes > MAX_RAW_STATE_BYTES) throw new Error('state_raw_too_large');
    return JSON.parse(raw.toString('utf8'));
  }
  const threads = [];
  for (const name of state.shards) {
    const part = await readPart(name, immutable
      ? /^threads-\d{4,}-([a-f0-9]{64})\.json$/u : /^threads-\d{4}\.json$/u);
    if (part.version !== 1 || part.table !== 'slack_shipping_threads' || !Array.isArray(part.rows))
      throw new Error('state_schema_invalid');
    for (const row of part.rows) threads.push(row);
  }
  if (threads.length !== state.thread_count) throw new Error('state_thread_count_invalid');
  const rest = await readPart(state.rest, immutable ? /^rest-([a-f0-9]{64})\.json$/u : /^rest\.json$/u);
  if (rest.version !== 1 || !rest.tables || typeof rest.tables !== 'object' || Array.isArray(rest.tables))
    throw new Error('state_schema_invalid');
  rest.tables.slack_shipping_threads = threads;
  const result = JSON.stringify(rest);
  if (Buffer.byteLength(result, 'utf8') > MAX_RAW_STATE_BYTES) throw new Error('state_raw_too_large');
  return result;
}

/** Stage immutable files, then replace the index with its ORIGINAL Contents SHA.
 * Publisher holds/errors propagate unchanged. Never refresh that SHA to win a
 * race, overwrite a shard, or delete old files while a reader may need them.
 */
export async function persistCheckpoint(plan, stored, readFile, putFile) {
  const index = plan.files.find(file => file.path === STATE_PATH);
  if (!index) throw new Error('state_index_missing');
  // Discover a size failure before staging any part of a new checkpoint.
  if (plan.files.some(file => Buffer.byteLength(file.text, 'utf8') > MAX_FILE_BYTES))
    throw new Error('private_file_too_large');
  for (const file of plan.files) {
    if (file.path === STATE_PATH) continue;
    const prev = await readFile(file.path);
    if (prev) {
      if (prev.text !== file.text) throw new Error('state_shard_conflict');
      continue;
    }
    await putFile(file.path, file.text);
  }
  if (index.text !== stored.text) await putFile(STATE_PATH, index.text, stored.sha);
}
