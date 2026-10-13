'use strict';

const {reconcileBeforePullCreate} = require('./connected_github_pr_preflight.cjs');
const {preparePublicationClaim, mutatePublicationClaims} = require('./connected_github_publication_claim.cjs');

// Caller supplies the already-discovered native bindings and authorized change.
// No filesystem, network client, credential lookup, or forced ref update. Source/publication
// writes are not replayed; optional publication-claim CAS conflicts re-read the claim file.
const ACTIONS = ['fetch', 'fetch_file', 'fetch_blob', 'create_blob', 'create_tree', 'create_commit',
  'create_branch', 'create_pull_request', 'merge_pull_request', 'create_file', 'update_file'];
const SHA = /^[0-9a-f]{40}$/;
const EMPTY_BLOB_SHA = 'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391';

class GitHubPublishError extends Error {
  constructor(message, progress, cause) {
    super(message);
    this.name = 'GitHubPublishError';
    this.progress = progress;
    this.cause = cause;
  }
}

function object(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError(`${label} must be an object`);
  }
  return value;
}

function text(value, label) {
  if (typeof value !== 'string' || !value.trim()) throw new TypeError(`${label} is required`);
  return value;
}

function branch(value, label) {
  text(value, label);
  if (value === '@' || value.startsWith('-') || value.startsWith('refs/')
      || /[\x00-\x20\x7f~^:?*\[\\]/.test(value) || value.includes('..') || value.includes('@{')
      || value.split('/').some(part => !part || part.startsWith('.') || part.endsWith('.') || part.endsWith('.lock'))) {
    throw new TypeError(`${label} must be a short Git branch name`);
  }
  return value;
}

function validateFiles(input, allowDeletions = false) {
  if (!Array.isArray(input.files) || !input.files.length) throw new TypeError('files must contain at least one source file');
  const paths = new Set();
  const files = input.files.map((file, index) => {
    object(file, `files[${index}]`);
    const path = text(file.path, `files[${index}].path`);
    if (path.includes('\\') || /[\x00-\x1f\x7f]/.test(path)
        || path.split('/').some(part => !part || part === '.' || part === '..')) {
      throw new TypeError(`Noncanonical repository path: ${path}`);
    }
    if (paths.has(path)) throw new TypeError(`Duplicate source path: ${path}`);
    paths.add(path);
    if (!Object.prototype.hasOwnProperty.call(file, 'expected_blob_sha')
        || (file.expected_blob_sha !== null && (typeof file.expected_blob_sha !== 'string' || !SHA.test(file.expected_blob_sha)))) {
      throw new TypeError(`Supply the observed expected_blob_sha, or null for a new file: ${path}`);
    }
    if (Object.prototype.hasOwnProperty.call(file, 'delete') && typeof file.delete !== 'boolean') {
      throw new TypeError(`delete must be boolean when supplied: ${path}`);
    }
    if (file.delete === true) {
      if (!allowDeletions) throw new TypeError(`Explicit deletion is supported only by the Contents publisher: ${path}`);
      if (file.expected_blob_sha === null) throw new TypeError(`Deletion requires the observed existing blob: ${path}`);
      if (['content', 'encoding', 'mode', 'expected_new_blob_sha'].some(key =>
        Object.prototype.hasOwnProperty.call(file, key))) {
        throw new TypeError(`Deletion does not accept content, encoding, mode or a new-blob pin: ${path}`);
      }
      return {...file, path, delete: true};
    }
    if (typeof file.content !== 'string') throw new TypeError(`content must be a string: ${path}`);
    const encoding = file.encoding ?? 'utf-8';
    if (!['utf-8', 'base64'].includes(encoding)) throw new TypeError(`Unsupported encoding: ${path}`);
    if (Object.prototype.hasOwnProperty.call(file, 'expected_new_blob_sha')
        && (typeof file.expected_new_blob_sha !== 'string' || !SHA.test(file.expected_new_blob_sha))) {
      throw new TypeError(`expected_new_blob_sha requires a lowercase Git SHA: ${path}`);
    }
    if (encoding === 'base64' && !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(file.content)) {
      throw new TypeError(`content must be padded base64 without whitespace: ${path}`);
    }
    if (encoding === 'utf-8') {
      for (let i = 0; i < file.content.length; i++) {
        const code = file.content.charCodeAt(i);
        if (code >= 0xd800 && code <= 0xdbff) {
          const next = file.content.charCodeAt(++i);
          if (!(next >= 0xdc00 && next <= 0xdfff)) throw new TypeError(`Unpaired Unicode surrogate: ${path}`);
        } else if (code >= 0xdc00 && code <= 0xdfff) throw new TypeError(`Unpaired Unicode surrogate: ${path}`);
      }
    }
    if (file.mode !== undefined && !['100644', '100755'].includes(file.mode)) {
      throw new TypeError(`Only regular-file modes are supported: ${path}`);
    }
    return {...file, path, encoding};
  });
  for (const path of paths) {
    const parts = path.split('/');
    while (parts.length > 1) {
      parts.pop();
      if (paths.has(parts.join('/'))) throw new TypeError(`A source file is also a parent directory: ${path}`);
    }
  }
  return files;
}

function validate(input, allowDeletions = false) {
  object(input, 'change');
  const repo = text(input.repository_full_name, 'repository_full_name');
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repo)
      || repo.split('/').some(part => part === '.' || part === '..')) {
    throw new TypeError('repository_full_name must be owner/repository');
  }
  const base = branch(input.base_branch ?? 'main', 'base_branch');
  const head = branch(input.branch_name, 'branch_name');
  if (base === head) throw new TypeError('branch_name must differ from base_branch');
  if (input.merge !== undefined && typeof input.merge !== 'boolean') throw new TypeError('merge must be boolean');
  const method = input.merge_method ?? 'merge';
  if (!['merge', 'squash', 'rebase'].includes(method)) throw new TypeError('unsupported merge_method');
  if (input.body !== undefined && typeof input.body !== 'string') throw new TypeError('body must be a string');
  const title = text(input.title, 'title');
  const message = text(input.commit_message ?? title, 'commit_message');
  const files = validateFiles(input, allowDeletions);
  return {repository_full_name: repo, base_branch: base, branch_name: head,
    title, body: input.body ?? '', commit_message: message, files,
    merge: input.merge === true, merge_method: method};
}

// Accept the observed direct connector envelope, not arbitrary payload.result fields.
function normalizeNativeEnvelope(result) {
  if (!result || typeof result !== 'object' || Array.isArray(result)
      || result.connector_name !== 'GitHub' || typeof result.action_name !== 'string'
      || !['result', 'error', 'error_code'].every(key =>
        Object.prototype.hasOwnProperty.call(result, key))) return result;
  const failed = result.error != null || result.error_data != null || result.error_code != null
    || result.json_rpc_error_code != null || result.error_http_status_code != null;
  if (!failed) return {structuredContent: result.result ?? null};
  const data = result.error_data && typeof result.error_data === 'object'
    && !Array.isArray(result.error_data) ? result.error_data : {};
  return {isError: true, structuredContent: {
    error_code: result.error_code,
    error_data: {...data,
      status: result.error_http_status_code ?? data.status,
      headers: result.error_http_headers ?? data.headers},
  }};
}

function inspectToolError(action, result) {
  const nativeResponse = result;
  result = normalizeNativeEnvelope(result);
  if (!result || typeof result !== 'object' || result.isError !== true) return null;
  const structured = result.structuredContent;
  const data = structured && typeof structured === 'object' ? structured.error_data : undefined;
  const status = data && /^[1-5][0-9]{2}$/.test(String(data.status))
    ? Number(data.status) : null;
  // Evidence paths address the supplied native response, never a reconstructed envelope.
  const directEnvelope = nativeResponse !== result;
  const providerMessage = directEnvelope ? nativeResponse.error_data?.message : data?.message;
  const messagePath = directEnvelope ? 'error_data.message' : 'structuredContent.error_data.message';
  const connectorError = directEnvelope ? nativeResponse.error : structured?.error;
  const connectorPath = directEnvelope ? 'error' : 'structuredContent.error';
  const evidence = {};
  const details = {
    action,
    error_code: 'native_tool_error',
    http_status: status,
    message: action + ' returned a native tool error'
      + (status === null ? '' : ' (GitHub HTTP ' + status + ')'),
  };
  if (typeof structured?.error_code === 'string'
      && /^[A-Z0-9_]{1,64}$/.test(structured.error_code)) {
    details.connector_error_code = structured.error_code;
  }
  // Only this explicit provider sentence classifies a secondary limit.
  // Other 403s, absent timing and arbitrary body text establish no limit kind.
  if (typeof providerMessage === 'string' && providerMessage.length <= 8192
      && providerMessage.startsWith('You have exceeded a secondary rate limit.')) {
    details.rate_limit_kind = 'secondary';
    evidence.rate_limit_kind = {source_path: messagePath, source_range: [0,41],
      format: 'github_secondary_limit_sentence'};
    const support = /please include the request ID ([0-9A-F]{1,16}(?::[0-9A-F]{1,16}){4})\.$/.exec(providerMessage);
    if (support) {
      const start = support.index + 'please include the request ID '.length;
      details.github_request_id = support[1];
      evidence.github_request_id = {source_path: messagePath,
        source_range: [start,start + support[1].length], format: 'github_support_request_id'};
    }
  }
  const metadata = [data?.headers, data, structured?.headers, structured,
    result.headers, result].filter(value => value && typeof value === 'object' && !Array.isArray(value))
    .map(value => Object.fromEntries(Object.entries(value).map(([key, item]) => [key.toLowerCase(), item])));
  const number = value => {
    if (typeof value === 'string' && /^\d+(?:\.\d+)?$/.test(value.trim())) value = Number(value.trim());
    return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : undefined;
  };
  const integer = value => {
    const parsed = number(value);
    return Number.isSafeInteger(parsed) ? parsed : undefined;
  };
  const first = (keys, normalize) => {
    for (const fields of metadata) {
      for (const key of keys) {
        const value = normalize(fields[key]);
        if (value !== undefined) return value;
      }
    }
  };
  const retryAfter = value => {
    if (number(value) !== undefined) return typeof value === 'string' ? value.trim() : value;
    if (typeof value !== 'string') return undefined;
    const header = value.trim();
    if (/^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4} \d{2}:\d{2}:\d{2} GMT$/.test(header)
        && Number.isFinite(Date.parse(header)) && new Date(header).toUTCString() === header) return header;
  };
  const retrySeconds = first(['retry_after_seconds'], number);
  const retry = first(['retry-after', 'retry_after'], retryAfter);
  if (retrySeconds !== undefined) details.retry_after_seconds = retrySeconds;
  if (retry !== undefined || retrySeconds !== undefined) details.retry_after = retry ?? retrySeconds;
  for (const [field, keys, normalize] of [
    ['rate_limit_remaining', ['x-ratelimit-remaining', 'rate_limit_remaining'], integer],
    ['rate_limit_reset', ['x-ratelimit-reset', 'rate_limit_reset'], integer],
    ['rate_limit_resource', ['x-ratelimit-resource', 'rate_limit_resource'],
      value => typeof value === 'string' && /^[a-z][a-z0-9_]{0,63}$/.test(value) ? value : undefined],
  ]) {
    const value = first(keys, normalize);
    if (value !== undefined) details[field] = value;
  }
  if (status === 405 && data.message === 'Base branch was modified. Review and try the merge again.') {
    details.error_code = 'base_branch_modified';
    details.message = action + ' was refused because the base branch moved; '
      + 'read the current PR and base before continuing the same merge';
  } else if (Array.isArray(result.content) && result.content.some(block =>
    block?.type === 'text' && typeof block.text === 'string'
    && /\bTransport closed\b/.test(block.text.slice(-1024)))) {
    details.error_code = 'transport_closed';
    details.message = action + ' returned no usable result because its transport closed; '
      + 'reconcile provider state before retrying a write';
  }
  // Add status evidence only after existing error-code classification. In particular,
  // a transport_closed error keeps its old null-status/cache behavior.
  if (details.error_code === 'native_tool_error' && status === null
      && typeof connectorError === 'string') {
    const prefix = /^GitHub API error (403): \{/.exec(connectorError.slice(0,24));
    if (prefix) {
      details.http_status = 403;
      details.message = action + ' returned a native tool error (GitHub HTTP 403)';
      evidence.http_status = {source_path: connectorPath, source_range: [17,20],
        format: 'github_connector_error_prefix'};
    }
  }
  if (Object.keys(evidence).length) details.provider_evidence = evidence;
  return details;
}

function unpack(result, action) {
  const nativeResponse = result;
  result = normalizeNativeEnvelope(result);
  object(result, `${action} response`);
  if (result.isError) {
    const details = inspectToolError(action, nativeResponse);
    const error = new Error(details?.message ?? action + ' returned a tool error');
    if (details) error.tool_error = details;
    throw error;
  }
  if (result.structuredContent !== undefined) return object(result.structuredContent, `${action} payload`);
  if (Array.isArray(result.content)) {
    for (const block of result.content) {
      if (block.type !== 'text') continue;
      try { return object(JSON.parse(block.text), `${action} payload`); } catch (_) { /* Try the next native block. */ }
    }
    throw new Error(`${action} did not return a readable object`);
  }
  return result;
}

function sha(value, label) {
  if (typeof value !== 'string' || !SHA.test(value)) throw new Error(`${label} did not return a Git SHA`);
  return value;
}

function checkNewBlobPin(file, source) {
  if (source.expected_new_blob_sha === undefined) return;
  file.expected_new_blob_sha = source.expected_new_blob_sha;
  file.source_pin_matches = file.blob_sha === source.expected_new_blob_sha;
  if (!file.source_pin_matches) {
    throw new Error(`New source blob mismatch: ${file.path}; expected ${source.expected_new_blob_sha}, observed ${file.blob_sha}`);
  }
}

function isMissingFileResponse(response) {
  response = normalizeNativeEnvelope(response);
  const payload = response?.structuredContent;
  return response?.isError === true && payload?.error_code === 'NOT_FOUND'
    && [404, '404'].includes(payload.error_data?.status)
    && payload.error_data?.message === 'Not Found';
}

// Decode whole retained objects locally; no caller-reported leaf or mode is evidence.
const MAX_RETAINED_TREE_BYTES = 16 * 1024 * 1024;
const MAX_RETAINED_TREE_ENTRIES = 200000;

function retainedTreeBytes(encoded, remaining) {
  if (typeof encoded !== 'string' || encoded.length % 4
      || encoded.length > 4 * Math.ceil(remaining / 3)) {
    throw new TypeError('Retained tree bytes require bounded, padded base64');
  }
  const padding = encoded.endsWith('==') ? 2 : encoded.endsWith('=') ? 1 : 0;
  const length = encoded.length / 4 * 3 - padding;
  if (length > remaining || length < 0) throw new TypeError('Retained tree byte bound exceeded');
  const raw = new Uint8Array(length);
  const digit = code => code >= 65 && code <= 90 ? code - 65
    : code >= 97 && code <= 122 ? code - 71
      : code >= 48 && code <= 57 ? code + 4 : code === 43 ? 62 : code === 47 ? 63 : -1;
  for (let i = 0, out = 0; i < encoded.length; i += 4) {
    const a = digit(encoded.charCodeAt(i)), b = digit(encoded.charCodeAt(i + 1));
    const last = i + 4 === encoded.length;
    const c = last && padding === 2 ? 0 : digit(encoded.charCodeAt(i + 2));
    const d = last && padding ? 0 : digit(encoded.charCodeAt(i + 3));
    if (a < 0 || b < 0 || c < 0 || d < 0
        || (last && padding === 2 && (encoded[i + 2] !== '=' || (b & 15)))
        || (last && padding && (encoded[i + 3] !== '=' || (padding === 1 && (c & 3))))) {
      throw new TypeError('Retained tree bytes require canonical base64');
    }
    if (out < length) raw[out++] = (a << 2) | (b >>> 4);
    if (out < length) raw[out++] = (b << 4) | (c >>> 2);
    if (out < length) raw[out++] = (c << 6) | d;
  }
  return raw;
}

// SHA-1 over Git's "tree <byte-length>\\0" framing, usable without Node imports.
function retainedTreeSHA(raw) {
  const header = 'tree ' + raw.length + '\0';
  const length = header.length + raw.length;
  const padded = Math.ceil((length + 9) / 64) * 64;
  const bytes = new Uint8Array(padded);
  for (let i = 0; i < header.length; i++) bytes[i] = header.charCodeAt(i);
  bytes.set(raw, header.length);
  bytes[length] = 128;
  // Retained objects are bounded to 16 MiB, so the bit length fits in 32 bits.
  for (let i = 0; i < 4; i++) bytes[padded - 1 - i] = (length * 8) >>> (i * 8) & 255;
  const words = new Int32Array(80);
  let h0 = 0x67452301, h1 = 0xefcdab89, h2 = 0x98badcfe, h3 = 0x10325476, h4 = 0xc3d2e1f0;
  for (let offset = 0; offset < padded; offset += 64) {
    for (let i = 0; i < 16; i++) {
      const at = offset + i * 4;
      words[i] = bytes[at] << 24 | bytes[at + 1] << 16 | bytes[at + 2] << 8 | bytes[at + 3];
    }
    for (let i = 16; i < 80; i++) {
      const value = words[i - 3] ^ words[i - 8] ^ words[i - 14] ^ words[i - 16];
      words[i] = value << 1 | value >>> 31;
    }
    let a = h0, b = h1, c = h2, d = h3, e = h4;
    // Fixed round groups avoid choosing the same function/constant per word.
    for (let i = 0; i < 20; i++) {
      const next = ((a << 5 | a >>> 27) + ((b & c) | (~b & d)) + e + 0x5a827999 + words[i]) | 0;
      e = d; d = c; c = b << 30 | b >>> 2; b = a; a = next;
    }
    for (let i = 20; i < 40; i++) {
      const next = ((a << 5 | a >>> 27) + (b ^ c ^ d) + e + 0x6ed9eba1 + words[i]) | 0;
      e = d; d = c; c = b << 30 | b >>> 2; b = a; a = next;
    }
    for (let i = 40; i < 60; i++) {
      const next = ((a << 5 | a >>> 27) + ((b & c) | (b & d) | (c & d)) + e + 0x8f1bbcdc + words[i]) | 0;
      e = d; d = c; c = b << 30 | b >>> 2; b = a; a = next;
    }
    for (let i = 60; i < 80; i++) {
      const next = ((a << 5 | a >>> 27) + (b ^ c ^ d) + e + 0xca62c1d6 + words[i]) | 0;
      e = d; d = c; c = b << 30 | b >>> 2; b = a; a = next;
    }
    h0 = (h0 + a) | 0; h1 = (h1 + b) | 0; h2 = (h2 + c) | 0; h3 = (h3 + d) | 0; h4 = (h4 + e) | 0;
  }
  return [h0, h1, h2, h3, h4].map(value => (value >>> 0).toString(16).padStart(8, '0')).join('');
}

function parseRetainedTree(raw, expectedSHA) {
  if (retainedTreeSHA(raw) !== expectedSHA) throw new Error('Retained tree bytes do not match their Git object SHA');
  const types = {'40000': 'tree', '100644': 'blob', '100755': 'blob', '120000': 'blob', '160000': 'commit'};
  const entries = [], names = new Set();
  let previous, previousDirectory;
  const orderByte = (name, directory, index) => index < name.length ? name[index]
    : index === name.length && directory ? 47 : -1;
  for (let at = 0; at < raw.length;) {
    const space = raw.indexOf(32, at), nul = raw.indexOf(0, space + 1);
    if (space < at || space - at > 6 || nul < space + 2 || nul + 21 > raw.length) {
      throw new Error('Incomplete or malformed retained tree record');
    }
    const mode = String.fromCharCode(...raw.subarray(at, space));
    if (!Object.prototype.hasOwnProperty.call(types, mode)) throw new Error('Unsupported retained tree mode');
    const name = raw.subarray(space + 1, nul);
    let path;
    try { path = decodeURIComponent(Array.from(name, value => '%' + value.toString(16).padStart(2, '0')).join('')); }
    catch (_) { throw new Error('Retained tree names must be strict UTF-8'); }
    if (!path || path.includes('/') || path === '.' || path === '..' || names.has(path)) {
      throw new Error('Invalid or duplicate retained tree name');
    }
    const directory = mode === '40000';
    if (previous) {
      let i = 0, left, right;
      do {
        left = orderByte(previous, previousDirectory, i);
        right = orderByte(name, directory, i++);
      } while (left === right && left !== -1);
      if (left >= right) throw new Error('Retained tree records are not in canonical Git order');
    }
    names.add(path);
    entries.push({path, mode: directory ? '040000' : mode, type: types[mode],
      sha: Array.from(raw.subarray(nul + 1, nul + 21), value => value.toString(16).padStart(2, '0')).join('')});
    if (entries.length > MAX_RETAINED_TREE_ENTRIES) throw new Error('Retained tree entry bound exceeded');
    previous = name; previousDirectory = directory; at = nul + 21;
  }
  return entries;
}


// Local postimage prediction uses only whole, native-bound preimage trees.
// Existing parser/framer supplies SHA-1 identity; no provider reads happen here.
const MAX_LOCAL_TREE_OBJECTS = 256;
const MAX_LOCAL_TREE_TOTAL_BYTES = 64 * 1024 * 1024;

function encodeTreeName(name) {
  if (typeof name !== 'string' || !name || name === '.' || name === '..'
      || name.includes('/') || name.includes('\0') || name.length > 4096) {
    throw new Error('Local tree identity requires bounded immediate entry names');
  }
  // encodeURIComponent rejects unpaired surrogates and emits strict UTF-8.
  const encoded = encodeURIComponent(name), bytes = [];
  for (let at = 0; at < encoded.length; at++) {
    if (encoded[at] === '%') {
      bytes.push(parseInt(encoded.slice(at + 1, at + 3), 16)); at += 2;
    } else bytes.push(encoded.charCodeAt(at));
  }
  if (bytes.length > 4096) throw new Error('Local tree name exceeds 4096 UTF-8 bytes');
  return Uint8Array.from(bytes);
}

function serializeTreeEntries(entries, budget) {
  if (!Array.isArray(entries) || entries.length > MAX_RETAINED_TREE_ENTRIES) {
    throw new Error('Local tree entry bound exceeded');
  }
  const types = {'40000': 'tree', '100644': 'blob', '100755': 'blob',
    '120000': 'blob', '160000': 'commit'};
  const names = new Set(), prepared = [];
  let length = 0;
  for (const entry of entries) {
    object(entry, 'Local tree entry');
    const mode = entry.mode === '040000' ? '40000' : entry.mode;
    if (typeof mode !== 'string' || !Object.prototype.hasOwnProperty.call(types, mode)
        || entry.type !== types[mode]) {
      throw new Error('Unsupported local tree entry mode/type');
    }
    const name = encodeTreeName(entry.path);
    if (names.has(entry.path)) throw new Error('Duplicate local tree entry name');
    names.add(entry.path);
    const objectSHA = sha(entry.sha, 'Local tree entry');
    length += mode.length + 1 + name.length + 1 + 20;
    if (length > MAX_RETAINED_TREE_BYTES) throw new Error('Local tree body exceeds 16 MiB');
    prepared.push({mode, name, objectSHA, directory: mode === '40000'});
  }
  if (length > MAX_LOCAL_TREE_TOTAL_BYTES - budget.body_bytes) {
    throw new Error('Local tree aggregate body bound exceeded');
  }
  budget.body_bytes += length;
  // Git compares name bytes, using '/' for a tree and NUL for a non-tree
  // at the end of a name. JavaScript string/locale sorting is not equivalent.
  prepared.sort((left, right) => {
    const common = Math.min(left.name.length, right.name.length);
    for (let i = 0; i < common; i++) {
      if (left.name[i] !== right.name[i]) return left.name[i] - right.name[i];
    }
    const a = common < left.name.length ? left.name[common] : left.directory ? 47 : 0;
    const b = common < right.name.length ? right.name[common] : right.directory ? 47 : 0;
    return a - b;
  });
  const raw = new Uint8Array(length);
  let at = 0;
  for (const entry of prepared) {
    for (let i = 0; i < entry.mode.length; i++) raw[at++] = entry.mode.charCodeAt(i);
    raw[at++] = 32;
    raw.set(entry.name, at); at += entry.name.length;
    raw[at++] = 0;
    for (let i = 0; i < 40; i += 2) raw[at++] = parseInt(entry.objectSHA.slice(i, i + 2), 16);
  }
  return raw;
}

function prepareInlineTreeIdentity(snapshots, baseTreeSHA, files, verification) {
  if (!(snapshots instanceof Map) || !snapshots.has('')) {
    throw new Error('Local tree identity needs the complete native-bound base root');
  }
  const budget = {body_bytes: 0}, nodes = new Map();
  const addNode = (path, node) => {
    if (nodes.size >= MAX_LOCAL_TREE_OBJECTS) throw new Error('Local tree directory bound exceeded');
    nodes.set(path, node);
  };
  // Parse creates independent entry objects per path even when two base
  // directories share the same tree SHA. Cached native arrays are never edited.
  for (const [path, snapshot] of snapshots) {
    const raw = serializeTreeEntries(snapshot.tree, budget);
    verification.body_bytes_encoded = budget.body_bytes;
    const entries = parseRetainedTree(raw, sha(snapshot.tree_sha, 'Base tree snapshot'));
    addNode(path, {original_sha: snapshot.tree_sha,
      entries: new Map(entries.map(entry => [entry.path, {...entry}]))});
    verification.base_trees.push({path, tree_sha: snapshot.tree_sha,
      bytes: raw.length, entries: entries.length, git_object_sha_verified: true});
  }
  if (nodes.get('').original_sha !== baseTreeSHA) throw new Error('Local base root identity differs');
  for (const [path, node] of nodes) {
    if (!path) continue;
    const slash = path.lastIndexOf('/');
    const parent = slash < 0 ? '' : path.slice(0, slash);
    const name = path.slice(slash + 1), entry = nodes.get(parent)?.entries.get(name);
    if (!entry || entry.type !== 'tree' || entry.sha !== node.original_sha) {
      throw new Error('Local base tree is not bound through its complete parent: ' + path);
    }
  }
  for (const file of files) {
    const parts = file.path.split('/');
    let parentPath = '';
    for (let i = 0; i < parts.length - 1; i++) {
      const name = parts[i], parent = nodes.get(parentPath);
      if (!parent) throw new Error('Complete local parent tree is unavailable: ' + parentPath);
      const path = parentPath ? parentPath + '/' + name : name;
      const entry = parent.entries.get(name);
      if (entry) {
        if (entry.type !== 'tree' || !nodes.has(path)) {
          throw new Error('Local directory is not completely observed: ' + path);
        }
      } else {
        // Absence is established by this whole parent's verified entry set.
        addNode(path, {original_sha: null, entries: new Map()});
        parent.entries.set(name, {path: name, mode: '040000', type: 'tree', sha: null});
      }
      parentPath = path;
    }
    const parent = nodes.get(parentPath), name = parts[parts.length - 1];
    const existing = parent.entries.get(name);
    if (existing && (existing.type !== 'blob' || !['100644', '100755'].includes(existing.mode))) {
      throw new Error('Local changed leaf is not a regular file: ' + file.path);
    }
    parent.entries.set(name, {path: name, mode: file.mode, type: 'blob',
      sha: sha(file.expected_new_blob_sha, 'Pinned inline source')});
  }
  const paths = [...nodes.keys()].sort((left, right) =>
    (right ? right.split('/').length : 0) - (left ? left.split('/').length : 0));
  for (const path of paths) {
    const node = nodes.get(path);
    const raw = serializeTreeEntries([...node.entries.values()], budget);
    verification.body_bytes_encoded = budget.body_bytes;
    const treeSHA = retainedTreeSHA(raw);
    verification.computed_trees.push({path, previous_tree_sha: node.original_sha,
      tree_sha: treeSHA, bytes: raw.length, entries: node.entries.size});
    if (path) {
      const slash = path.lastIndexOf('/');
      const parent = slash < 0 ? '' : path.slice(0, slash);
      const name = path.slice(slash + 1);
      nodes.get(parent).entries.set(name, {path: name, mode: '040000', type: 'tree', sha: treeSHA});
    } else verification.expected_tree_sha = treeSHA;
  }
  return sha(verification.expected_tree_sha, 'Predicted created tree');
}

function validateRetainedTrees(input, files) {
  const trees = new Map();
  if (input === undefined) return trees;
  if (!Array.isArray(input) || input.length > 16) throw new TypeError('retained_trees must contain at most 16 whole trees');
  let remaining = MAX_RETAINED_TREE_BYTES;
  for (const source of input) {
    object(source, 'retained tree');
    if (Object.keys(source).some(key => !['path', 'tree_sha', 'raw_base64'].includes(key))) {
      throw new TypeError('Retained trees accept only path, tree_sha and raw_base64');
    }
    const path = source.path;
    if (typeof path !== 'string' || path.includes('\\') || /[\x00-\x1f\x7f]/.test(path)
        || (path && path.split('/').some(part => !part || part === '.' || part === '..'))
        || !files.some(file => path === '' || file.path.startsWith(path + '/'))) {
      throw new TypeError('Retained tree path must be a canonical parent of a changed file');
    }
    if (trees.has(path)) throw new TypeError('Duplicate retained tree path');
    const treeSHA = sha(source.tree_sha, 'Retained tree');
    const raw = retainedTreeBytes(source.raw_base64, remaining);
    remaining -= raw.length;
    trees.set(path, {tree_sha: treeSHA, bytes: raw.length,
      tree: parseRetainedTree(raw, treeSHA), consumed: false});
  }
  return trees;
}

function requireRetainedTreesConsumed(trees) {
  for (const [path, tree] of trees) {
    if (!tree.consumed) throw new Error('The native parent traversal did not reach retained tree: ' + (path || '/'));
  }
}

/** Resolve exact entries from native trees or independently verified whole bytes. */
function baseFileReader({api, repository_full_name, commitSha, treeSha,
  fetchJSON, readPreimage, progress, treeLabel, retainedTrees = new Map(), treeSnapshots}) {
  const trees = new Map();
  const unavailable = new Map();
  const remember = (path, current, entries) => {
    if (treeSnapshots) {
      if (entries.length > MAX_RETAINED_TREE_ENTRIES) throw new Error('Local tree entry bound exceeded');
      const saved = treeSnapshots.get(path);
      if (saved) {
        if (saved.tree_sha !== current) throw new Error('Local tree snapshot identity changed');
        return entries;
      }
      if (treeSnapshots.size >= MAX_LOCAL_TREE_OBJECTS) {
        throw new Error('Local tree directory bound exceeded');
      }
      treeSnapshots.set(path, {tree_sha: current, tree: entries.map(entry => ({...entry}))});
    }
    return entries;
  };
  const tree = async (current, parentPath) => {
    const retained = retainedTrees.get(parentPath);
    if (retained) {
      if (retained.tree_sha !== current) {
        throw new Error('Retained tree does not match the native parent at: ' + (parentPath || '/'));
      }
      if (!retained.consumed) {
        retained.consumed = true;
        (progress.retained_tree_preimages ??= []).push({path: parentPath,
          base_commit_sha: commitSha, parent_tree_sha: current, bytes: retained.bytes,
          entries: retained.tree.length, git_object_sha_verified: true});
      }
      return remember(parentPath, current, retained.tree);
    }
    if (unavailable.has(current)) throw unavailable.get(current);
    if (!trees.has(current)) {
      let data;
      try { data = await fetchJSON(`${api}/git/trees/${current}`); }
      catch (error) {
        if (error.tool_error?.error_code === 'transport_closed'
            && error.tool_error.http_status === null) unavailable.set(current, error);
        throw error;
      }
      if (data.sha !== current || !Array.isArray(data.tree) || data.truncated !== false) {
        const error = new Error(`The ${treeLabel} tree could not be read completely: ${current}`);
        if (data.sha === current && Array.isArray(data.tree) && data.truncated === true) {
          error.truncated_tree = true;
          unavailable.set(current, error);
        }
        throw error;
      }
      trees.set(current, data.tree);
    }
    return remember(parentPath, current, trees.get(current));
  };
  return async (path, expectedBlob) => {
    let current = treeSha;
    const parts = path.split('/');
    for (let index = 0; index < parts.length; index++) {
      const parentPath = parts.slice(0, index).join('/');
      let entries;
      try { entries = await tree(current, parentPath); }
      catch (error) {
        if (retainedTrees.has(parentPath)) throw error;
        // The successful prefix reads must already establish the immediate parent.
        if (index === 0 || index !== parts.length - 1 || !unavailable.has(current)
            || typeof readPreimage !== 'function') throw error;
        const request = {repository_full_name, path, ref: commitSha, encoding: 'utf-8',
          start_line: 1, end_line: 1};
        const record = {path, base_commit_sha: commitSha, parent_tree_sha: current,
          reason: error.truncated_tree ? 'truncated_tree' : 'transport_closed',
          ...(error.tool_error ? {tree_error: error.tool_error} : {}),
          request, outcome: 'pending'};
        (progress.preimage_fallbacks ??= []).push(record);
        let response;
        try { response = await readPreimage(request); }
        catch (readError) {
          record.outcome = 'unavailable';
          if (readError.tool_error) record.tool_error = readError.tool_error;
          throw readError;
        }
        if (response.absent) {
          Object.assign(record, {outcome: 'absent', observed_blob_sha: null,
            http_status: 404, connector_error_code: 'NOT_FOUND'});
          return null;
        }
        const data = response.data;
        record.outcome = 'unavailable';
        if (data.display_url !== `https://github.com/${repository_full_name}/blob/${commitSha}/${path}`) {
          throw new Error(`File precheck did not identify the exact immutable path: ${path}`);
        }
        const observed = sha(data.sha, 'Existing file precheck');
        Object.assign(record, {outcome: 'existing_blob', observed_blob_sha: observed,
          file_type_observed: false, mode_observed: false});
        // A differing blob proves a version conflict without assuming type or mode.
        if (observed !== expectedBlob) return {sha: observed};
        throw new Error(`The existing path's Git type and mode are unavailable: ${path}; a caller-selected mode cannot replace the unreadable tree`);
      }
      const item = entries.find(entry => entry.path === parts[index]);
      if (!item) return null;
      if (index === parts.length - 1) return item;
      if (item.type !== 'tree') throw new Error(`A parent path is not a directory: ${path}`);
      current = sha(item.sha, 'Parent tree');
    }
  };
}

function inspectReadback(file, source, data) {
  if (source.encoding === 'utf-8') {
    const observed = sha(data.sha, 'Published text blob');
    const expected = source.expected_new_blob_sha ?? null;
    // Large-file metadata can retain the blob SHA while omitting the body.
    if (typeof data.content !== 'string' || (data.content === '' && observed !== EMPTY_BLOB_SHA)) {
      return {path: file.path, expected_blob_sha: expected, observed_blob_sha: observed,
        content_matches: null, content_available: false, matches: false,
        error_code: 'readback_content_unavailable'};
    }
    const contentMatches = data.content === source.content;
    const matches = contentMatches && (expected === null || observed === expected);
    if (matches) file.blob_sha = observed;
    return {path: file.path, expected_blob_sha: expected, observed_blob_sha: observed,
      content_matches: contentMatches, matches};
  }
  return {path: file.path, expected_blob_sha: file.blob_sha, observed_blob_sha: data.sha,
    matches: data.sha === file.blob_sha};
}

/** Recover omitted text with one optional read of the observed immutable blob. */
async function resolveReadback(file, source, data, readBlob) {
  const initial = inspectReadback(file, source, data);
  if (initial.error_code !== 'readback_content_unavailable' || typeof readBlob !== 'function') {
    return initial;
  }
  let blob;
  try {
    blob = await readBlob(initial.observed_blob_sha);
  } catch (error) {
    return {...initial, blob_readback_attempted: true,
      blob_readback_error: String(error?.message ?? error),
      ...(error?.tool_error ? {tool_error: error.tool_error} : {})};
  }
  return {...inspectReadback(file, source, {
    sha: initial.observed_blob_sha, content: blob?.content,
  }), blob_readback_attempted: true, readback_source: 'blob', file_content_available: false};
}

function readbackLimit(options) {
  const limit = options.readback_concurrency === undefined ? 4 : options.readback_concurrency;
  if (!Number.isSafeInteger(limit) || limit < 1) {
    throw new TypeError('readback_concurrency must be a positive safe integer');
  }
  return limit;
}

/** Keep each settled outcome in input order while bounding independent reads. */
async function settleReadbacks(items, read, limit) {
  const outcomes = new Array(items.length);
  let nextIndex = 0;
  const worker = async () => {
    while (nextIndex < items.length) {
      const index = nextIndex++;
      try {
        outcomes[index] = {status: 'fulfilled', value: await read(items[index], index)};
      } catch (reason) {
        outcomes[index] = {status: 'rejected', reason};
      }
    }
  };
  await Promise.all(Array.from({length: Math.min(limit, items.length)}, worker));
  return outcomes;
}

/** Optional bounded wall-clock attribution around native binding settlement only. */
function actionTimer(options, progress) {
  if (options.action_timing !== undefined && typeof options.action_timing !== 'boolean') {
    throw new TypeError('action_timing must be boolean');
  }
  if (options.action_timing !== true) return null;
  const summary = {clock: 'Date.now', unit: 'milliseconds',
    scope: 'native_binding_settlement', monotonic: false, recording_errors: 0, actions: {}};
  progress.action_timing = summary;
  const sample = () => {
    try {
      const value = Date.now();
      return Number.isFinite(value) ? value : null;
    } catch (_) { return null; }
  };
  return async (action, invoke) => {
    const started = sample();
    let returned = false;
    try {
      const result = await invoke();
      returned = true;
      return result;
    } finally {
      // Metrics must not replace a native response or the original binding error.
      const ended = sample();
      try {
        const record = summary.actions[action] ??= {count: 0, returned: 0, threw: 0,
          timed_count: 0, unavailable_samples: 0, negative_samples: 0,
          total_ms: 0, min_ms: null, max_ms: null};
        record.count++;
        record[returned ? 'returned' : 'threw']++;
        const elapsed = started === null || ended === null ? null : ended - started;
        if (elapsed === null || !Number.isFinite(elapsed)) {
          record.unavailable_samples++;
        } else {
          record.timed_count++;
          if (elapsed < 0) record.negative_samples++;
          record.total_ms += elapsed;
          record.min_ms = record.min_ms === null ? elapsed : Math.min(record.min_ms, elapsed);
          record.max_ms = record.max_ms === null ? elapsed : Math.max(record.max_ms, elapsed);
        }
      } catch (_) {
        try { summary.recording_errors++; } catch (_) { /* Best effort only. */ }
      }
    }
  };
}

/** Publish regular-file changes through native GitHub tools, optionally merge. */
async function publishGitHubChange(tools, change, options = {}) {
  const progress = {status: 'incomplete', stage: 'validate', calls: {}, files: [], progress_callback_errors: []};
  let lastResponse;
  let announce = async () => {};
  let publicationClaimConfig = null;
  let publicationClaimActive = false;
  let releasePublicationClaim = async () => {};
  try {
    const spec = validate(change);
    publicationClaimConfig = preparePublicationClaim(options.publication_claims, spec);
    if (publicationClaimConfig) progress.publication_claim = {status: 'prepared',
      holder: publicationClaimConfig.holder, ledger_repository_full_name: publicationClaimConfig.ledger_repository_full_name,
      paths: publicationClaimConfig.paths};
    if (options.inline_pinned_utf8 !== undefined && typeof options.inline_pinned_utf8 !== 'boolean') {
      throw new TypeError('inline_pinned_utf8 must be boolean');
    }
    const inlinePinnedPaths = new Set(options.inline_pinned_utf8 === true
      ? spec.files.filter(file => file.encoding === 'utf-8'
        && file.expected_new_blob_sha !== undefined).map(file => file.path) : []);
    if (options.inline_pinned_utf8 === true) progress.inline_pinned_utf8 = true;
    if (options.inline_tree_identity !== undefined && typeof options.inline_tree_identity !== 'boolean') {
      throw new TypeError('inline_tree_identity must be boolean');
    }
    const localTreeIdentity = options.inline_tree_identity === true;
    if (localTreeIdentity && (options.inline_pinned_utf8 !== true
        || inlinePinnedPaths.size !== spec.files.length)) {
      throw new TypeError('inline_tree_identity requires inline_pinned_utf8 and a new blob pin on every UTF-8 file');
    }
    const treeSnapshots = localTreeIdentity ? new Map() : undefined;
    if (localTreeIdentity) progress.inline_tree_identity = true;
    const readbackConcurrency = readbackLimit(options);
    const retainedTrees = validateRetainedTrees(options.retained_trees, spec.files);
    progress.readback_concurrency = readbackConcurrency;
    const sourceByPath = new Map(spec.files.map(file => [file.path, file]));
    const repository_full_name = spec.repository_full_name;
    Object.assign(progress, {repository_full_name, base_branch: spec.base_branch, branch_name: spec.branch_name});
    const bindings = Object.fromEntries(ACTIONS.map(action => [action,
      options.bindings?.[action] ?? `mcp__codex_apps__github_${action}`]));
    const required = ACTIONS.filter(action => action !== 'fetch_blob'
      && (action !== 'merge_pull_request' || spec.merge)
      && (!['create_file', 'update_file'].includes(action) || publicationClaimConfig)
      && (action !== 'create_blob' || spec.files.some(file =>
        file.encoding === 'base64'
          || (file.expected_new_blob_sha !== undefined && !inlinePinnedPaths.has(file.path)))));
    for (const action of required) {
      if (typeof tools?.[bindings[action]] !== 'function') {
        throw new Error(`Binding not present: ${bindings[action]}. Repeat discovery alongside independent work.`);
      }
    }
    announce = async () => {
      if (typeof options.onProgress !== 'function') return;
      try { await options.onProgress(JSON.parse(JSON.stringify(progress))); }
      catch (error) { progress.progress_callback_errors.push(String(error.message ?? error)); }
    };
    const timeAction = actionTimer(options, progress);
    const call = async (action, args) => {
      progress.calls[action] = (progress.calls[action] ?? 0) + 1;
      lastResponse = undefined;
      lastResponse = timeAction
        ? await timeAction(action, () => tools[bindings[action]](args))
        : await tools[bindings[action]](args);
      return unpack(lastResponse, action);
    };
    const fetchJSON = async url => {
      const payload = await call('fetch', {url});
      return typeof payload.content === 'string' ? object(JSON.parse(payload.content), 'GitHub resource') : payload;
    };
    const readPreimage = async args => {
      try { return {data: await call('fetch_file', args)}; }
      catch (error) {
        if (isMissingFileResponse(lastResponse)) return {absent: true};
        throw error;
      }
    };
    const takePublicationClaim = async () => {
      if (!publicationClaimConfig) return null;
      progress.stage = 'take_publication_claims';
      const result = await mutatePublicationClaims({fetchJSON, readFile: readPreimage, call,
        config: publicationClaimConfig, action: 'take'});
      progress.publication_claim = result;
      publicationClaimActive = result.status === 'ACQUIRED';
      await announce();
      return result;
    };
    releasePublicationClaim = async reason => {
      if (!publicationClaimConfig || !publicationClaimActive) return null;
      const previousStage = progress.stage;
      try {
        progress.stage = 'release_publication_claims';
        const result = await mutatePublicationClaims({fetchJSON, readFile: readPreimage, call,
          config: publicationClaimConfig, action: 'release'});
        progress.publication_claim_release = {...result, reason};
        if (result.status === 'RELEASED' || result.status === 'ALREADY_RELEASED') publicationClaimActive = false;
        return result;
      } catch (claimError) {
        progress.publication_claim_release = {status: 'RELEASE_FAILED', reason,
          error: String(claimError?.message ?? claimError)};
        return null;
      } finally {
        progress.stage = previousStage;
        await announce();
      }
    };
    const api = `https://api.github.com/repos/${repository_full_name}`;
    progress.stage = 'read_base';
    const base = await fetchJSON(`${api}/branches/${encodeURIComponent(spec.base_branch)}`);
    progress.base_commit_sha = sha(base.commit?.sha, 'Base branch');
    progress.base_tree_sha = sha(base.commit?.commit?.tree?.sha, 'Base tree');
    const existingFile = baseFileReader({api, repository_full_name,
      commitSha: progress.base_commit_sha, treeSha: progress.base_tree_sha,
      fetchJSON, readPreimage: localTreeIdentity ? undefined : readPreimage,
      progress, treeLabel: 'base', retainedTrees, treeSnapshots});
    progress.stage = 'check_file_versions';
    for (const file of spec.files) {
      const existing = await existingFile(file.path, file.expected_blob_sha);
      if ((existing?.sha ?? null) !== file.expected_blob_sha) {
        throw new Error(`Base file changed: ${file.path}; expected ${file.expected_blob_sha ?? 'absent'}, observed ${existing?.sha ?? 'absent'}`);
      }
      if (existing && (existing.type !== 'blob' || !['100644', '100755'].includes(existing.mode))) {
        throw new Error(`The existing path is not a regular file: ${file.path}`);
      }
      progress.files.push({path: file.path, previous_blob_sha: existing?.sha ?? null,
        previous_mode: existing?.mode ?? null, mode: file.mode ?? existing?.mode ?? '100644',
        ...(file.expected_new_blob_sha === undefined ? {} : {
          expected_new_blob_sha: file.expected_new_blob_sha, source_pin_matches: null})});
    }
    requireRetainedTreesConsumed(retainedTrees);
    await announce();
    progress.stage = 'create_blobs';
    const createdBlobs = {'utf-8': new Map(), base64: new Map()};
    for (let index = 0; index < spec.files.length; index++) {
      const file = spec.files[index];
      if (file.encoding === 'utf-8'
          && (file.expected_new_blob_sha === undefined || inlinePinnedPaths.has(file.path))) continue;
      const blobs = createdBlobs[file.encoding];
      let blobSha = blobs.get(file.content);
      if (blobSha === undefined) {
        const data = await call('create_blob', {repository_full_name, content: file.content, encoding: file.encoding});
        blobSha = sha(data.sha, 'Created blob');
        blobs.set(file.content, blobSha);
      }
      progress.files[index].blob_sha = blobSha;
      checkNewBlobPin(progress.files[index], file);
      await announce();
    }
    const candidates = progress.files.filter(file => file.blob_sha === undefined
      || file.blob_sha !== file.previous_blob_sha || file.mode !== file.previous_mode);
    if (!candidates.length) {
      progress.status = 'no_source_changes'; progress.stage = 'complete';
      await announce(); return progress;
    }
    if (localTreeIdentity) {
      progress.stage = 'prepare_inline_tree_identity';
      const verification = {method: 'local_git_tree_identity',
        base_commit_sha: progress.base_commit_sha, base_tree_sha: progress.base_tree_sha,
        expected_tree_sha: null, tree_sha: null, tree_identity_matches: null,
        fetch_calls: 0, base_trees: [], computed_trees: [], body_bytes_encoded: 0,
        limits: {directories: MAX_LOCAL_TREE_OBJECTS, entries_per_tree: MAX_RETAINED_TREE_ENTRIES,
          bytes_per_tree: MAX_RETAINED_TREE_BYTES, total_body_bytes: MAX_LOCAL_TREE_TOTAL_BYTES,
          name_utf8_bytes: 4096}, checked_paths: [], complete: false};
      progress.inline_tree_verification = verification;
      prepareInlineTreeIdentity(treeSnapshots, progress.base_tree_sha, candidates, verification);
      await announce();
    }
    progress.stage = 'create_tree';
    const createdTree = await call('create_tree', {repository_full_name, base_tree_sha: progress.base_tree_sha,
      tree_elements: candidates.map(file => {
        const source = sourceByPath.get(file.path);
        return {path: file.path, mode: file.mode, type: 'blob',
          ...(file.blob_sha === undefined ? {content: source.content} : {sha: file.blob_sha})};
      })});
    progress.tree_sha = sha(createdTree.sha, 'Created tree');
    await announce();
    if (localTreeIdentity) {
      progress.stage = 'check_inline_tree_identity';
      const verification = progress.inline_tree_verification;
      verification.tree_sha = progress.tree_sha;
      verification.tree_identity_matches = progress.tree_sha === verification.expected_tree_sha;
      if (!verification.tree_identity_matches) {
        throw new Error('Created tree SHA differs from the exact local pinned postimage');
      }
      for (const file of progress.files) {
        file.blob_sha = file.expected_new_blob_sha;
        checkNewBlobPin(file, sourceByPath.get(file.path));
        verification.checked_paths.push(file.path);
      }
      verification.complete = true;
      await announce();
    } else if (inlinePinnedPaths.size) {
      progress.stage = 'check_inline_source_pins';
      const verification = {tree_sha: progress.tree_sha, fetch_calls: 0,
        checked_paths: [], complete: false};
      progress.inline_tree_verification = verification;
      // Read only the newly created tree. No commit or file fallback exists yet.
      const inlineFile = baseFileReader({api, repository_full_name,
        commitSha: null, treeSha: progress.tree_sha, progress, treeLabel: 'created',
        fetchJSON: async url => {
          verification.fetch_calls++;
          return fetchJSON(url);
        }});
      for (const file of progress.files) {
        if (!inlinePinnedPaths.has(file.path)) continue;
        const existing = await inlineFile(file.path, file.expected_new_blob_sha);
        if (!existing || existing.type !== 'blob' || existing.mode !== file.mode) {
          throw new Error(`Created tree path/type/mode mismatch: ${file.path}`);
        }
        file.blob_sha = sha(existing.sha, 'Created inline text blob');
        checkNewBlobPin(file, sourceByPath.get(file.path));
        verification.checked_paths.push(file.path);
      }
      verification.complete = true;
      await announce();
    }
    if (progress.tree_sha === progress.base_tree_sha) {
      for (const file of progress.files) file.blob_sha = file.previous_blob_sha;
      progress.status = 'no_source_changes'; progress.stage = 'complete';
      await announce(); return progress;
    }
    progress.stage = 'create_commit';
    const commit = await call('create_commit', {repository_full_name, parent_sha: progress.base_commit_sha,
      tree_sha: progress.tree_sha, message: spec.commit_message});
    progress.commit_sha = sha(commit.sha, 'Created commit');
    await announce();
    const claim = await takePublicationClaim();
    if (claim && claim.status !== 'ACQUIRED') {
      progress.status = claim.status === 'HELD_BY_PEER' ? 'publication_claim_held' : 'publication_claim_retry_required';
      progress.stage = 'complete';
      await announce();
      return progress;
    }
    progress.stage = 'create_branch';
    const createdBranch = await call('create_branch', {repository_full_name, branch_name: spec.branch_name, sha: progress.commit_sha});
    if (createdBranch.branch !== spec.branch_name && createdBranch.ref !== `refs/heads/${spec.branch_name}`) {
      throw new Error('The branch response does not identify the requested branch');
    }
    if (createdBranch.object?.sha && createdBranch.object.sha !== progress.commit_sha) {
      throw new Error('The branch response does not identify the created commit');
    }
    progress.branch_created = true;
    await announce();
    progress.stage = 'reconcile_before_pr_create';
    progress.pr_create_reconciliation = await reconcileBeforePullCreate({
      fetchJSON, repository: repository_full_name, baseBranch: spec.base_branch,
      branchName: spec.branch_name, expectedHead: progress.commit_sha,
      initialBaseHead: progress.base_commit_sha,
      files: progress.files.map(file => ({path: file.path, blob_sha: file.blob_sha}))
    });
    await announce();
    if (progress.pr_create_reconciliation) {
      progress.publication_status = progress.pr_create_reconciliation.status;
      progress.status = progress.pr_create_reconciliation.status === 'EXISTING_BRANCH_CONFLICT'
        ? 'reconciliation_hold' : 'reconciled';
      await releasePublicationClaim('preflight_reconciled');
      progress.stage = 'complete';
      await announce();
      return progress;
    }
    progress.stage = 'create_pull_request';
    const pr = await call('create_pull_request', {repository_full_name, head: spec.branch_name,
      base: spec.base_branch, title: spec.title, body: spec.body});
    progress.pull_request = {number: pr.number, url: pr.url ?? pr.display_url, head_sha: pr.head_sha};
    if (!Number.isInteger(pr.number) || pr.number < 1 || pr.head_sha !== progress.commit_sha) {
      throw new Error('The returned pull request does not identify the created commit');
    }
    progress.publication_status = 'pull_request_open';
    await releasePublicationClaim('pull_request_open');
    await announce();
    if (spec.merge) {
      progress.stage = 'check_current_base';
      const currentBase = await fetchJSON(`${api}/branches/${encodeURIComponent(spec.base_branch)}`);
      progress.current_base_commit_sha = sha(currentBase.commit?.sha, 'Current pre-merge base');
      progress.current_base_tree_sha = sha(currentBase.commit?.commit?.tree?.sha, 'Current pre-merge tree');
      if (progress.current_base_commit_sha !== progress.base_commit_sha) {
        // Reuse verified bytes only after binding them to this current native parent.
        const currentRetainedTrees = new Map(Array.from(retainedTrees, ([path, tree]) =>
          [path, {...tree, consumed: false}]));
        const currentFile = baseFileReader({api, repository_full_name,
          commitSha: progress.current_base_commit_sha, treeSha: progress.current_base_tree_sha,
          fetchJSON, readPreimage, progress, treeLabel: 'current base',
          retainedTrees: currentRetainedTrees});
        for (const file of progress.files) {
          const existing = await currentFile(file.path, file.previous_blob_sha);
          if ((existing?.sha ?? null) !== file.previous_blob_sha
              || (existing?.mode ?? null) !== file.previous_mode
              || (existing && existing.type !== 'blob')) {
            throw new Error(`Base file changed: ${file.path}; read the current source and compose deliberately`);
          }
        }
        requireRetainedTreesConsumed(currentRetainedTrees);
      }
      progress.current_preimages_verified = true;
      await announce();
      progress.stage = 'merge_pull_request';
      const merged = await call('merge_pull_request', {repository_full_name, pr_number: pr.number,
        expected_head_sha: progress.commit_sha, merge_method: spec.merge_method});
      progress.merge_result = merged;
      if (merged.merged !== true) throw new Error('GitHub did not report a completed merge');
      progress.publication_status = 'merged';
      progress.merge_sha = sha(merged.sha, 'Merge');
      await announce();
    }
    progress.stage = 'readback';
    progress.readback_ref = progress.merge_sha ?? progress.commit_sha;
    const readBlob = typeof tools?.[bindings.fetch_blob] === 'function'
      ? blob_sha => call('fetch_blob', {repository_full_name, blob_sha}) : undefined;
    // Bound independent reads; inspect every outcome before reporting completion.
    const reads = await settleReadbacks(candidates, async file => {
      const source = sourceByPath.get(file.path);
      const data = await call('fetch_file', {repository_full_name, path: file.path,
        ref: progress.readback_ref, encoding: source.encoding});
      return resolveReadback(file, source, data, readBlob);
    }, readbackConcurrency);
    progress.readback = reads.map((read, index) => read.status === 'fulfilled' ? read.value
      : {path: candidates[index].path, matches: false, error: String(read.reason?.message ?? read.reason),
        ...(read.reason?.tool_error ? {tool_error: read.reason.tool_error} : {})});
    const unavailable = progress.readback.some(read => read.error_code === 'readback_content_unavailable');
    progress.readback_status = unavailable ? 'content_unavailable'
      : progress.readback.some(read => !read.matches) ? 'incomplete' : 'complete';
    if (unavailable) throw new Error('Published source content was not returned; finish readback at readback_ref without repeating publication');
    if (progress.readback.some(read => !read.matches)) throw new Error('One or more published source readbacks did not match');
    progress.status = spec.merge ? 'merged' : 'pull_request_open';
    progress.stage = 'complete';
    await announce();
    return progress;
  } catch (error) {
    if (error.tool_error) progress.tool_error = error.tool_error;
    const explicitProviderRejection = Number.isInteger(error.tool_error?.http_status)
      && error.tool_error.http_status >= 400 && error.tool_error.http_status < 500
      && error.tool_error.error_code !== 'transport_closed';
    const knownNoUncertainCreate = progress.stage !== 'create_pull_request'
      || progress.pull_request !== undefined || explicitProviderRejection;
    if (publicationClaimActive && knownNoUncertainCreate) {
      await releasePublicationClaim('known_failure');
    } else if (publicationClaimActive) {
      progress.publication_claim_release = {status: 'RETAINED_FOR_RECONCILIATION',
        reason: 'uncertain_create_pull_request'};
    }
    await announce();
    const failure = new GitHubPublishError(String(error.message ?? error), progress, error);
    if (error.tool_error) failure.tool_error = error.tool_error;
    failure.response = lastResponse;
    throw failure;
  }
}

/** Explicitly finish a known publication's merge without replaying its creation. */
async function continueGitHubMerge(tools, change, previousProgress, options = {}) {
  const progress = {operation: 'merge_continuation', status: 'incomplete', stage: 'validate',
    calls: {}, files: [], progress_callback_errors: []};
  let lastResponse;
  let announce = async () => {};
  try {
    const spec = validate(change);
    const readbackConcurrency = readbackLimit(options);
    const retainedTrees = validateRetainedTrees(options.retained_trees, spec.files);
    progress.readback_concurrency = readbackConcurrency;
    if (!spec.merge) throw new TypeError('Set merge: true for this explicit merge continuation');
    const saved = object(previousProgress, 'previousProgress');
    for (const key of ['repository_full_name', 'base_branch', 'branch_name']) {
      if (saved[key] !== spec[key]) throw new Error(`Retained publication differs from change: ${key}`);
      progress[key] = spec[key];
    }
    for (const key of ['base_commit_sha', 'base_tree_sha', 'tree_sha', 'commit_sha']) {
      progress[key] = sha(saved[key], `Retained ${key}`);
    }
    const retainedPR = object(saved.pull_request, 'Retained pull_request');
    if (!Number.isInteger(retainedPR.number) || retainedPR.number < 1
        || retainedPR.head_sha !== progress.commit_sha) {
      throw new Error('Retain the confirmed pull request number and original head SHA');
    }
    progress.pull_request = {number: retainedPR.number, url: retainedPR.url, head_sha: progress.commit_sha};
    if (!Array.isArray(saved.files)) throw new TypeError('Retain the publication file versions');
    const savedFiles = new Map(saved.files.map(file => [object(file, 'Retained file').path, file]));
    if (savedFiles.size !== spec.files.length || saved.files.length !== spec.files.length) {
      throw new Error('Retained file paths differ from the original prepared change');
    }
    for (const source of spec.files) {
      const file = savedFiles.get(source.path);
      if (!file || file.previous_blob_sha !== source.expected_blob_sha
          || (file.previous_blob_sha === null ? file.previous_mode !== null
            : !['100644', '100755'].includes(file.previous_mode))
          || file.mode !== (source.mode ?? file.previous_mode ?? '100644')) {
        throw new Error(`Retained file version or mode differs from change: ${source.path}`);
      }
      const record = {path: source.path, previous_blob_sha: file.previous_blob_sha,
        previous_mode: file.previous_mode, mode: file.mode};
      if (file.expected_new_blob_sha !== undefined
          && file.expected_new_blob_sha !== source.expected_new_blob_sha) {
        throw new Error(`Retained source pin differs from change: ${source.path}`);
      }
      if (source.encoding === 'base64' || source.expected_new_blob_sha !== undefined) {
        record.blob_sha = sha(file.blob_sha, source.encoding === 'base64' ? 'Retained binary blob' : 'Retained text blob');
      }
      progress.files.push(record);
      checkNewBlobPin(record, source);
    }
    const repository_full_name = spec.repository_full_name;
    const actions = ['fetch', 'fetch_file', 'fetch_blob', 'merge_pull_request'];
    const bindings = Object.fromEntries(actions.map(action => [action,
      options.bindings?.[action] ?? `mcp__codex_apps__github_${action}`]));
    const requireBinding = action => {
      if (typeof tools?.[bindings[action]] !== 'function') {
        throw new Error(`Binding not present: ${bindings[action]}. Repeat discovery alongside independent work.`);
      }
    };
    requireBinding('fetch');
    requireBinding('fetch_file');
    announce = async () => {
      if (typeof options.onProgress !== 'function') return;
      try { await options.onProgress(JSON.parse(JSON.stringify(progress))); }
      catch (error) { progress.progress_callback_errors.push(String(error.message ?? error)); }
    };
    const timeAction = actionTimer(options, progress);
    const call = async (action, args) => {
      progress.calls[action] = (progress.calls[action] ?? 0) + 1;
      lastResponse = undefined;
      lastResponse = timeAction
        ? await timeAction(action, () => tools[bindings[action]](args))
        : await tools[bindings[action]](args);
      return unpack(lastResponse, action);
    };
    const fetchJSON = async url => {
      const payload = await call('fetch', {url});
      return typeof payload.content === 'string' ? object(JSON.parse(payload.content), 'GitHub resource') : payload;
    };
    const readPreimage = async args => {
      try { return {data: await call('fetch_file', args)}; }
      catch (error) {
        if (isMissingFileResponse(lastResponse)) return {absent: true};
        throw error;
      }
    };
    progress.stage = 'read_pull_request';
    const pr = await fetchJSON(`https://api.github.com/repos/${repository_full_name}/pulls/${retainedPR.number}`);
    if (pr.number !== retainedPR.number || pr.base?.ref !== spec.base_branch || pr.head?.ref !== spec.branch_name
        || typeof pr.head?.repo?.full_name !== 'string'
        || pr.head.repo.full_name.toLowerCase() !== repository_full_name.toLowerCase()
        || pr.head.sha !== progress.commit_sha) {
      throw new Error('The current pull request differs from the retained repository, branches, or head');
    }
    progress.pull_request.url = pr.html_url ?? retainedPR.url;
    if (pr.merged === true) {
      progress.publication_status = 'merged';
      progress.merge_sha = sha(pr.merge_commit_sha, 'Existing merge');
      progress.merge_skipped = 'already_merged';
      await announce();
    } else {
      if (pr.merged !== false || pr.state !== 'open') throw new Error('The pull request is not open or confirmed merged');
      progress.publication_status = 'pull_request_open';
      await announce();
      requireBinding('fetch');
      requireBinding('merge_pull_request');
      const api = `https://api.github.com/repos/${repository_full_name}`;
      progress.stage = 'read_base';
      const base = await fetchJSON(`${api}/branches/${encodeURIComponent(spec.base_branch)}`);
      progress.current_base_commit_sha = sha(base.commit?.sha, 'Current base branch');
      progress.current_base_tree_sha = sha(base.commit?.commit?.tree?.sha, 'Current base tree');
      const existingFile = baseFileReader({api, repository_full_name,
        commitSha: progress.current_base_commit_sha, treeSha: progress.current_base_tree_sha,
        fetchJSON, readPreimage, progress, treeLabel: 'current base', retainedTrees});
      progress.stage = 'check_file_versions';
      for (const file of progress.files) {
        const existing = await existingFile(file.path, file.previous_blob_sha);
        if ((existing?.sha ?? null) !== file.previous_blob_sha
            || (existing?.mode ?? null) !== file.previous_mode
            || (existing && existing.type !== 'blob')) {
          throw new Error(`Base file changed: ${file.path}; read the current source and compose deliberately`);
        }
      }
      requireRetainedTreesConsumed(retainedTrees);
      await announce();
      progress.stage = 'merge_pull_request';
      const merged = await call('merge_pull_request', {repository_full_name, pr_number: retainedPR.number,
        expected_head_sha: progress.commit_sha, merge_method: spec.merge_method});
      progress.merge_result = merged;
      if (merged.merged !== true) throw new Error('GitHub did not report a completed merge');
      progress.publication_status = 'merged';
      progress.merge_sha = sha(merged.sha, 'Merge');
      await announce();
    }
    progress.stage = 'readback';
    progress.readback_ref = progress.merge_sha;
    const readBlob = typeof tools?.[bindings.fetch_blob] === 'function'
      ? blob_sha => call('fetch_blob', {repository_full_name, blob_sha}) : undefined;
    const reads = await settleReadbacks(progress.files, async (file, index) => {
      const source = spec.files[index];
      const data = await call('fetch_file', {repository_full_name, path: file.path,
        ref: progress.readback_ref, encoding: source.encoding});
      return resolveReadback(file, source, data, readBlob);
    }, readbackConcurrency);
    progress.readback = reads.map((read, index) => read.status === 'fulfilled' ? read.value
      : {path: progress.files[index].path, matches: false, error: String(read.reason?.message ?? read.reason),
        ...(read.reason?.tool_error ? {tool_error: read.reason.tool_error} : {})});
    const unavailable = progress.readback.some(read => read.error_code === 'readback_content_unavailable');
    progress.readback_status = unavailable ? 'content_unavailable'
      : progress.readback.some(read => !read.matches) ? 'incomplete' : 'complete';
    if (unavailable) throw new Error('Merged source content was not returned; finish readback without repeating publication');
    if (progress.readback.some(read => !read.matches)) throw new Error('One or more merged source readbacks did not match');
    progress.status = 'merged';
    progress.stage = 'complete';
    await announce();
    return progress;
  } catch (error) {
    if (error.tool_error) progress.tool_error = error.tool_error;
    await announce();
    const failure = new GitHubPublishError(String(error.message ?? error), progress, error);
    if (error.tool_error) failure.tool_error = error.tool_error;
    failure.response = lastResponse;
    throw failure;
  }
}


function validateContribution(input) {
  object(input, 'change');
  const result = {};
  for (const key of ['repository_full_name', 'pull_request_repository_full_name']) {
    const value = text(input[key], key);
    if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(value)
        || value.split('/').some(part => part === '.' || part === '..')) {
      throw new TypeError(key + ' must be owner/repository');
    }
    result[key] = value;
  }
  if (!Number.isSafeInteger(input.pull_request_number) || input.pull_request_number < 1) {
    throw new TypeError('pull_request_number must identify the existing pull request');
  }
  for (const key of ['merge', 'merge_method', 'title', 'body', 'force']) {
    if (input[key] !== undefined) throw new TypeError(key + ' is not part of a contribution advancement');
  }
  return {...result, pull_request_number: input.pull_request_number,
    branch_name: branch(input.branch_name, 'branch_name'),
    base_branch: branch(input.base_branch, 'base_branch'),
    expected_head_sha: sha(input.expected_head_sha, 'expected_head_sha'),
    expected_base_sha: sha(input.expected_base_sha, 'expected_base_sha'),
    commit_message: text(input.commit_message, 'commit_message'), files: validateFiles(input)};
}

function contributionPR(pr, spec) {
  if (pr.number !== spec.pull_request_number || pr.head?.ref !== spec.branch_name
      || pr.base?.ref !== spec.base_branch
      || pr.head?.repo?.full_name?.toLowerCase() !== spec.repository_full_name.toLowerCase()
      || pr.base?.repo?.full_name?.toLowerCase() !== spec.pull_request_repository_full_name.toLowerCase()
      || !['open', 'closed'].includes(pr.state) || typeof pr.merged !== 'boolean') {
    throw new Error('The pull request differs from the specified repositories or branches');
  }
  return {number: pr.number, url: pr.html_url,
    head_sha: sha(pr.head.sha, 'PR head'), base_sha: sha(pr.base.sha, 'PR base'),
    state: pr.state, merged: pr.merged, author_login: pr.user?.login ?? null};
}

function requireContributionHead(pr, spec) {
  if (pr.state !== 'open' || pr.merged !== false || pr.head_sha !== spec.expected_head_sha
      || pr.base_sha !== spec.expected_base_sha) {
    throw new Error('The open contribution head or base changed; reconcile the original PR before publishing');
  }
}

function completeContributionTree(data, expected) {
  if (data.sha !== expected || data.truncated !== false || !Array.isArray(data.tree)) {
    throw new Error('The contribution tree was not returned completely: ' + expected);
  }
  const entries = new Map();
  for (const entry of data.tree) {
    if (!entry || typeof entry.path !== 'string'
        || entry.path.split('/').some(part => !part || part === '.' || part === '..')
        || entries.has(entry.path) || !['blob', 'tree', 'commit'].includes(entry.type)
        || typeof entry.mode !== 'string' || !/^[0-7]{6}$/.test(entry.mode)) {
      throw new Error('The contribution tree contains an invalid or duplicate entry');
    }
    sha(entry.sha, 'Contribution tree entry');
    entries.set(entry.path, entry);
  }
  for (const path of entries.keys()) {
    const parts = path.split('/');
    while (parts.length > 1) {
      parts.pop();
      if (entries.get(parts.join('/'))?.type !== 'tree') {
        throw new Error('The contribution tree omitted a parent directory: ' + path);
      }
    }
  }
  return entries;
}

function contributionFiles(spec, parentEntries) {
  return spec.files.map(source => {
    const before = parentEntries.get(source.path);
    if ((before?.sha ?? null) !== source.expected_blob_sha) {
      throw new Error('Contribution file changed: ' + source.path);
    }
    if (before && (before.type !== 'blob' || !['100644', '100755'].includes(before.mode))) {
      throw new Error('The contribution path is not a regular file: ' + source.path);
    }
    const parts = source.path.split('/');
    while (parts.length > 1) {
      parts.pop();
      const parent = parentEntries.get(parts.join('/'));
      if (parent && parent.type !== 'tree') {
        throw new Error('A contribution parent path is not a directory: ' + source.path);
      }
    }
    return {path: source.path, previous_blob_sha: before?.sha ?? null,
      previous_mode: before?.mode ?? null, mode: source.mode ?? before?.mode ?? '100644',
      ...(source.expected_new_blob_sha === undefined ? {} : {
        expected_new_blob_sha: source.expected_new_blob_sha, source_pin_matches: null})};
  });
}

function compareContributionTrees(before, after, files, sources) {
  const targetPaths = new Set(files.map(file => file.path));
  const parentPaths = new Set();
  for (const path of targetPaths) {
    const parts = path.split('/');
    while (parts.length > 1) { parts.pop(); parentPaths.add(parts.join('/')); }
  }
  const same = (a, b) => a?.sha === b?.sha && a?.type === b?.type && a?.mode === b?.mode;
  let unchangedLeaves = 0;
  for (const path of new Set([...before.keys(), ...after.keys()])) {
    if (targetPaths.has(path)) continue;
    const a = before.get(path), b = after.get(path);
    if (parentPaths.has(path)) {
      if ((a && (a.type !== 'tree' || a.mode !== '040000'))
          || b?.type !== 'tree' || b.mode !== '040000') {
        throw new Error('A prepared parent directory changed type or mode: ' + path);
      }
    } else if (!same(a, b)) {
      throw new Error('An unrequested contribution path changed: ' + path);
    }
    if (a && a.type !== 'tree') unchangedLeaves++;
  }
  const changedPaths = [];
  for (let index = 0; index < files.length; index++) {
    const file = files[index], entry = after.get(file.path);
    if (!entry || entry.type !== 'blob' || entry.mode !== file.mode
        || (file.blob_sha !== undefined && entry.sha !== file.blob_sha)) {
      throw new Error('The prepared contribution file has a different blob or mode: ' + file.path);
    }
    file.blob_sha = entry.sha;
    checkNewBlobPin(file, sources[index]);
    if (!same(before.get(file.path), entry)) changedPaths.push(file.path);
  }
  return {complete: true, unchanged_leaf_count: unchangedLeaves, changed_paths: changedPaths};
}

async function contributionOperation(tools, change, options, readOnly, previousProgress) {
  const progress = {operation: readOnly ? 'contribution_reconciliation' : 'contribution_advance',
    status: 'incomplete', stage: 'validate', publication_status: 'not_updated',
    calls: {}, files: [], progress_callback_errors: []};
  let lastResponse;
  let announce = async () => {};
  try {
    const spec = validateContribution(change);
    const readbackConcurrency = readbackLimit(options);
    progress.readback_concurrency = readbackConcurrency;
    const deferHeadObservation = readOnly ? undefined : options.defer_head_observation;
    if (deferHeadObservation !== undefined && typeof deferHeadObservation !== 'boolean') {
      throw new TypeError('defer_head_observation must be a boolean');
    }
    const identityKeys = ['repository_full_name', 'pull_request_repository_full_name',
      'pull_request_number', 'branch_name', 'base_branch', 'expected_head_sha', 'expected_base_sha'];
    for (const key of identityKeys) progress[key] = spec[key];
    progress.parent_commit_sha = spec.expected_head_sha;
    let saved;
    if (readOnly) {
      saved = object(previousProgress, 'previousProgress');
      if (!['contribution_advance', 'contribution_reconciliation'].includes(saved.operation)) {
        throw new Error('Retain the existing contribution operation, not a new-PR publication');
      }
      for (const key of identityKeys) {
        if (saved[key] !== spec[key]) throw new Error('Retained contribution differs from change: ' + key);
      }
      if (saved.parent_commit_sha !== spec.expected_head_sha) throw new Error('Retained contribution parent changed');
      for (const key of ['parent_tree_sha', 'tree_sha', 'commit_sha']) {
        progress[key] = sha(saved[key], 'Retained ' + key);
      }
      if (!Array.isArray(saved.files) || saved.files.length !== spec.files.length) {
        throw new Error('Retain all contribution file versions');
      }
      progress.previous_publication_status = saved.publication_status;
      progress.previous_ref_update_state = saved.ref_update_state ?? null;
      progress.publication_status = 'unreconciled';
    }
    const actions = ['fetch', 'fetch_file', 'fetch_blob',
      ...(readOnly ? [] : ['create_blob', 'create_tree', 'create_commit', 'update_ref'])];
    const bindings = Object.fromEntries(actions.map(action => [action,
      options.bindings?.[action] ?? 'mcp__codex_apps__github_' + action]));
    for (const action of actions) {
      if (action === 'fetch_blob' || (action === 'create_blob' && !spec.files.some(file =>
        file.encoding === 'base64' || file.expected_new_blob_sha !== undefined))) continue;
      if (typeof tools?.[bindings[action]] !== 'function') {
        throw new Error('Binding not present: ' + bindings[action] + '. Repeat discovery alongside independent work.');
      }
    }
    announce = async () => {
      if (typeof options.onProgress !== 'function') return;
      try { await options.onProgress(JSON.parse(JSON.stringify(progress))); }
      catch (error) { progress.progress_callback_errors.push(String(error.message ?? error)); }
    };
    const timeAction = actionTimer(options, progress);
    const call = async (action, args) => {
      progress.calls[action] = (progress.calls[action] ?? 0) + 1;
      let response;
      try {
        lastResponse = undefined;
        response = timeAction
          ? await timeAction(action, () => tools[bindings[action]](args))
          : await tools[bindings[action]](args);
        lastResponse = response;
        return unpack(response, action);
      } catch (error) {
        if (response !== undefined) error.response = response;
        throw error;
      }
    };
    const fetchJSON = async url => {
      const payload = await call('fetch', {url});
      return typeof payload.content === 'string' ? object(JSON.parse(payload.content), 'GitHub resource') : payload;
    };
    const repository_full_name = spec.repository_full_name;
    const api = 'https://api.github.com/repos/' + repository_full_name;
    const prURL = 'https://api.github.com/repos/' + spec.pull_request_repository_full_name
      + '/pulls/' + spec.pull_request_number;
    const refURL = api + '/git/ref/heads/' + spec.branch_name.split('/').map(encodeURIComponent).join('/');
    const observe = async label => {
      const outcomes = await Promise.allSettled([fetchJSON(prURL), fetchJSON(refURL)]);
      const record = {stage: label};
      for (let index = 0; index < outcomes.length; index++) {
        if (outcomes[index].status === 'rejected') {
          const error = outcomes[index].reason;
          record[index === 0 ? 'pull_request_error' : 'ref_error'] = {
            message: String(error?.message ?? error),
            ...(error?.tool_error ? {tool_error: error.tool_error} : {})};
        }
      }
      (progress.observations ??= []).push(record);
      const failure = outcomes.find(outcome => outcome.status === 'rejected');
      if (failure) throw failure.reason;
      record.pull_request = contributionPR(outcomes[0].value, spec);
      const ref = outcomes[1].value;
      if (ref.ref !== 'refs/heads/' + spec.branch_name || ref.object?.type !== 'commit') {
        throw new Error('The reference response does not identify the existing branch');
      }
      record.ref_sha = sha(ref.object.sha, 'Contribution branch ref');
      record.base_changed = record.pull_request.base_sha !== spec.expected_base_sha;
      return record;
    };
    if (!readOnly) {
      progress.stage = 'read_pull_request';
      progress.pull_request = contributionPR(await fetchJSON(prURL), spec);
      requireContributionHead(progress.pull_request, spec);
    }
    progress.stage = 'read_parent';
    const parent = await fetchJSON(api + '/git/commits/' + spec.expected_head_sha);
    if (parent.sha !== spec.expected_head_sha) throw new Error('The contribution parent identity changed');
    const parentTree = sha(parent.tree?.sha, 'Contribution parent tree');
    if (readOnly && parentTree !== progress.parent_tree_sha) throw new Error('Retained contribution parent tree changed');
    progress.parent_tree_sha = parentTree;
    const before = completeContributionTree(await fetchJSON(api + '/git/trees/' + parentTree + '?recursive=1'), parentTree);
    progress.stage = 'check_file_versions';
    progress.files = contributionFiles(spec, before);
    if (readOnly) {
      const retained = new Map(saved.files.map(file => [object(file, 'Retained file').path, file]));
      if (retained.size !== progress.files.length) throw new Error('Retained contribution paths differ');
      for (let index = 0; index < progress.files.length; index++) {
        const file = progress.files[index], source = spec.files[index], old = retained.get(file.path);
        if (!old || ['previous_blob_sha', 'previous_mode', 'mode'].some(key => old[key] !== file[key])
            || (old.expected_new_blob_sha !== undefined && old.expected_new_blob_sha !== source.expected_new_blob_sha)) {
          throw new Error('Retained contribution file or pin changed: ' + file.path);
        }
        if (old.blob_sha !== undefined) file.blob_sha = sha(old.blob_sha, 'Retained contribution blob');
        if (source.encoding === 'base64' || source.expected_new_blob_sha !== undefined) {
          sha(file.blob_sha, 'Retained source identity');
          checkNewBlobPin(file, source);
        }
      }
    }
    await announce();
    if (!readOnly) {
      progress.stage = 'create_blobs';
      const createdBlobs = {'utf-8': new Map(), base64: new Map()};
      for (let index = 0; index < spec.files.length; index++) {
        const source = spec.files[index], file = progress.files[index];
        if (source.encoding === 'utf-8' && source.expected_new_blob_sha === undefined) continue;
        const blobs = createdBlobs[source.encoding];
        let blobSha = blobs.get(source.content);
        if (blobSha === undefined) {
          const blob = await call('create_blob', {repository_full_name, content: source.content, encoding: source.encoding});
          blobSha = sha(blob.sha, 'Created contribution blob');
          blobs.set(source.content, blobSha);
        }
        file.blob_sha = blobSha;
        checkNewBlobPin(file, source);
        await announce();
      }
      const candidates = progress.files.filter(file => file.blob_sha === undefined
        || file.blob_sha !== file.previous_blob_sha || file.mode !== file.previous_mode);
      if (!candidates.length) {
        progress.status = 'no_source_changes'; progress.stage = 'complete';
        await announce(); return progress;
      }
      progress.stage = 'create_tree';
      const sources = new Map(spec.files.map(source => [source.path, source]));
      const tree = await call('create_tree', {repository_full_name, base_tree_sha: parentTree,
        tree_elements: candidates.map(file => ({path: file.path, mode: file.mode, type: 'blob',
          ...(file.blob_sha === undefined ? {content: sources.get(file.path).content} : {sha: file.blob_sha})}))});
      progress.tree_sha = sha(tree.sha, 'Created contribution tree');
      await announce();
      if (progress.tree_sha === parentTree) {
        for (const file of progress.files) file.blob_sha = file.previous_blob_sha;
        progress.status = 'no_source_changes'; progress.stage = 'complete';
        await announce(); return progress;
      }
      progress.stage = 'create_commit';
      const commit = await call('create_commit', {repository_full_name, parent_sha: spec.expected_head_sha,
        tree_sha: progress.tree_sha, message: spec.commit_message});
      progress.commit_sha = sha(commit.sha, 'Created contribution commit');
      await announce();
    }
    progress.stage = 'verify_commit';
    const created = await fetchJSON(api + '/git/commits/' + progress.commit_sha);
    if (created.sha !== progress.commit_sha || created.tree?.sha !== progress.tree_sha
        || !Array.isArray(created.parents) || created.parents.length !== 1
        || created.parents[0].sha !== spec.expected_head_sha || created.message !== spec.commit_message) {
      throw new Error('The prepared commit differs from its sole parent, tree or message');
    }
    const after = completeContributionTree(
      await fetchJSON(api + '/git/trees/' + progress.tree_sha + '?recursive=1'), progress.tree_sha);
    progress.tree_comparison = compareContributionTrees(before, after, progress.files, spec.files);
    progress.commit_verified = true;
    progress.stage = 'readback';
    progress.readback_ref = progress.commit_sha;
    const readBlob = typeof tools?.[bindings.fetch_blob] === 'function'
      ? blob_sha => call('fetch_blob', {repository_full_name, blob_sha}) : undefined;
    const reads = await settleReadbacks(progress.files, async (file, index) => {
      const source = {...spec.files[index], expected_new_blob_sha: file.blob_sha};
      const data = await call('fetch_file', {repository_full_name, path: file.path,
        ref: progress.readback_ref, encoding: source.encoding});
      return resolveReadback(file, source, data, readBlob);
    }, readbackConcurrency);
    progress.readback = reads.map((read, index) => read.status === 'fulfilled' ? read.value
      : {path: progress.files[index].path, matches: false, error: String(read.reason?.message ?? read.reason),
        ...(read.reason?.tool_error ? {tool_error: read.reason.tool_error} : {})});
    progress.readback_status = progress.readback.some(row => row.error_code === 'readback_content_unavailable')
      ? 'content_unavailable' : progress.readback.some(row => !row.matches) ? 'incomplete' : 'complete';
    await announce();
    if (progress.readback_status !== 'complete') {
      throw new Error('Prepared contribution source readback is incomplete; retain this commit without repeating publication');
    }
    if (!readOnly) {
      progress.stage = 'check_current_head';
      const current = await observe(progress.stage);
      requireContributionHead(current.pull_request, spec);
      if (current.ref_sha !== spec.expected_head_sha) throw new Error('The existing contribution branch moved');
      progress.stage = 'update_ref';
      progress.ref_update_state = 'unknown';
      progress.publication_status = 'unknown';
      progress.ref_update_request = {repository_full_name, branch_name: spec.branch_name,
        sha: progress.commit_sha, force: false};
      await announce();
      const updated = await call('update_ref', progress.ref_update_request);
      if (updated.success !== true) throw new Error('The ref writer did not confirm its update; reconcile before any continuation');
      progress.ref_update_state = 'confirmed';
      progress.publication_status = 'update_confirmed';
      await announce();
      if (deferHeadObservation === true) {
        progress.status = 'contribution_head_observation_pending';
        progress.stage = 'head_observation_deferred';
        progress.head_observation_status = 'deferred';
        progress.head_observation_target = {
          repository_full_name: spec.repository_full_name,
          pull_request_repository_full_name: spec.pull_request_repository_full_name,
          pull_request_number: spec.pull_request_number,
          branch_name: spec.branch_name,
          base_branch: spec.base_branch,
          expected_commit_sha: progress.commit_sha,
          expected_base_sha: spec.expected_base_sha};
        await announce();
        return progress;
      }
    }
    progress.stage = 'read_current_head';
    const current = await observe(progress.stage);
    progress.pull_request = current.pull_request;
    if (current.ref_sha === progress.commit_sha && current.pull_request.head_sha === progress.commit_sha) {
      progress.publication_status = 'updated';
      progress.ref_update_state = 'observed_updated';
      progress.status = 'contribution_branch_updated';
    } else if (readOnly && current.ref_sha === spec.expected_head_sha
        && current.pull_request.head_sha === spec.expected_head_sha) {
      progress.publication_status = 'previous_head_observed';
      progress.ref_update_state = 'observed_previous';
      progress.status = 'contribution_branch_not_updated';
    } else {
      progress.ref_update_state = 'not_converged';
      throw new Error('The current branch and PR do not both identify the prepared commit; retain the observations and do not repeat the write');
    }
    progress.stage = 'complete';
    await announce();
    return progress;
  } catch (error) {
    if (error.tool_error) progress.tool_error = error.tool_error;
    await announce();
    const failure = new GitHubPublishError(String(error.message ?? error), progress, error);
    if (error.tool_error) failure.tool_error = error.tool_error;
    failure.response = error.response ?? lastResponse;
    throw failure;
  }
}

/** Add one nonforce, sole-parent commit to the original open contribution PR. */
async function advanceGitHubContribution(tools, change, options = {}) {
  return contributionOperation(tools, change, options, false);
}

/** Read a retained contribution's source and current refs without any writes. */
async function reconcileGitHubContribution(tools, change, previousProgress, options = {}) {
  return contributionOperation(tools, change, options, true, previousProgress);
}


function validateContributionHeadTarget(input) {
  object(input, 'head observation target');
  const keys = ['repository_full_name', 'pull_request_repository_full_name',
    'pull_request_number', 'branch_name', 'base_branch',
    'expected_commit_sha', 'expected_base_sha'];
  for (const key of Object.keys(input)) {
    if (!keys.includes(key)) throw new TypeError('Unsupported head observation field: ' + key);
  }
  const result = {};
  for (const key of ['repository_full_name', 'pull_request_repository_full_name']) {
    const value = text(input[key], key);
    if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(value)
        || value.split('/').some(part => part === '.' || part === '..')) {
      throw new TypeError(key + ' must be owner/repository');
    }
    result[key] = value;
  }
  if (!Number.isSafeInteger(input.pull_request_number) || input.pull_request_number < 1) {
    throw new TypeError('pull_request_number must identify the existing pull request');
  }
  return {...result, pull_request_number: input.pull_request_number,
    branch_name: branch(input.branch_name, 'branch_name'),
    base_branch: branch(input.base_branch, 'base_branch'),
    expected_commit_sha: sha(input.expected_commit_sha, 'expected_commit_sha'),
    expected_base_sha: sha(input.expected_base_sha, 'expected_base_sha')};
}

/** Observe two current head resources; never verify source or repeat a write. */
async function observeGitHubContributionHead(tools, target, options = {}) {
  const progress = {operation: 'contribution_head_observation', status: 'incomplete',
    stage: 'validate', source_verification: 'not_performed',
    publication_verification: 'not_performed', snapshot: false, writes: 0,
    calls: {}, requests: {}, responses: {}, observations: {}, errors: {},
    expected_head_observed: null, heads_agree: null, base_changed: null,
    progress_callback_errors: []};
  let announce = async () => {};
  try {
    const spec = validateContributionHeadTarget(target);
    object(options, 'head observation options');
    for (const key of Object.keys(options)) {
      if (!['bindings', 'onProgress'].includes(key)) {
        throw new TypeError('Unsupported head observation option: ' + key);
      }
    }
    if (options.bindings !== undefined) {
      object(options.bindings, 'head observation bindings');
      for (const key of Object.keys(options.bindings)) {
        if (key !== 'fetch') throw new TypeError('Only the fetch binding is used for head observation');
      }
    }
    const binding = text(options.bindings?.fetch ?? 'mcp__codex_apps__github_fetch', 'fetch binding');
    if (typeof tools?.[binding] !== 'function') {
      throw new Error('Binding not present: ' + binding + '. Repeat discovery alongside independent work.');
    }
    if (options.onProgress !== undefined && typeof options.onProgress !== 'function') {
      throw new TypeError('onProgress must be a function');
    }
    progress.target = spec;
    announce = async () => {
      if (options.onProgress === undefined) return;
      try { await options.onProgress(JSON.parse(JSON.stringify(progress))); }
      catch (error) { progress.progress_callback_errors.push(String(error.message ?? error)); }
    };
    progress.requests.pull_request = {url: 'https://api.github.com/repos/'
      + spec.pull_request_repository_full_name + '/pulls/' + spec.pull_request_number};
    progress.requests.branch_ref = {url: 'https://api.github.com/repos/'
      + spec.repository_full_name + '/git/ref/heads/'
      + spec.branch_name.split('/').map(encodeURIComponent).join('/')};
    progress.stage = 'read_current_head';
    await announce();
    const names = ['pull_request', 'branch_ref'];
    const outcomes = await Promise.allSettled(names.map(async name => {
      progress.calls.fetch = (progress.calls.fetch ?? 0) + 1;
      const response = await tools[binding](progress.requests[name]);
      progress.responses[name] = response;
      const payload = unpack(response, 'fetch');
      const data = typeof payload.content === 'string'
        ? object(JSON.parse(payload.content), 'GitHub resource') : object(payload, 'GitHub resource');
      if (name === 'pull_request') return contributionPR(data, spec);
      if (data.ref !== 'refs/heads/' + spec.branch_name || data.object?.type !== 'commit') {
        throw new Error('The reference response does not identify the requested branch');
      }
      return {ref: data.ref, type: 'commit', sha: sha(data.object.sha, 'Contribution branch ref')};
    }));
    for (let index = 0; index < outcomes.length; index++) {
      const name = names[index], outcome = outcomes[index];
      if (outcome.status === 'fulfilled') {
        progress.observations[name] = outcome.value;
      } else {
        const error = outcome.reason;
        progress.errors[name] = {message: String(error?.message ?? error),
          ...(error?.tool_error ? {tool_error: error.tool_error} : {})};
      }
    }
    if (progress.observations.pull_request) {
      progress.base_changed = progress.observations.pull_request.base_sha !== spec.expected_base_sha;
    }
    if (Object.keys(progress.errors).length === 0) {
      const pr = progress.observations.pull_request;
      const ref = progress.observations.branch_ref;
      progress.heads_agree = pr.head_sha === ref.sha;
      progress.expected_head_observed = pr.head_sha === spec.expected_commit_sha
        && ref.sha === spec.expected_commit_sha;
      progress.status = progress.expected_head_observed ? 'expected_head_observed' : 'not_converged';
    }
    progress.stage = 'complete';
    await announce();
    return progress;
  } catch (error) {
    progress.error = String(error.message ?? error);
    await announce();
    throw new GitHubPublishError(progress.error, progress, error);
  }
}

/** Publish UTF-8 content through explicit serial native Contents calls; no Git-mode claim. */
async function publishGitHubContentsChange(tools, change, options = {}) {
  const progress = {operation: 'contents_publication', status: 'incomplete',
    stage: 'validate', calls: {}, files: [], serial_writes: [],
    progress_callback_errors: [], mode_verification: 'not_performed',
    whole_tree_verification: 'not_performed', pending_write: null};
  let lastResponse;
  let announce = async () => {};
  let publicationClaimConfig = null;
  let publicationClaimActive = false;
  let releasePublicationClaim = async () => {};
  try {
    const spec = validate(change, true);
    publicationClaimConfig = preparePublicationClaim(options.publication_claims, spec);
    if (publicationClaimConfig) progress.publication_claim = {status: 'prepared',
      holder: publicationClaimConfig.holder, ledger_repository_full_name: publicationClaimConfig.ledger_repository_full_name,
      paths: publicationClaimConfig.paths};
    if (spec.files.length > 300) throw new TypeError('Contents publication supports at most 300 file paths');
    if (spec.files.some(file => file.delete !== true && (file.encoding !== 'utf-8' || file.mode !== undefined))) {
      throw new TypeError('Contents publication accepts UTF-8 content or explicit deletion, without caller-selected Git modes');
    }
    if (options.retained_trees !== undefined) {
      throw new TypeError('retained_trees belongs to the Git Trees publisher, not Contents publication');
    }
    const saved = options.resume_created_branch;
    if (saved !== undefined) {
      object(saved, 'resume_created_branch');
      if (saved.operation !== 'contents_publication' || saved.branch_created !== true
          || saved.pending_write !== null || !Array.isArray(saved.serial_writes) || saved.serial_writes.length
          || saved.pull_request !== undefined || saved.publication_status !== undefined
          || saved.commit_sha !== saved.base_commit_sha) {
        throw new TypeError('Resume only a confirmed branch creation before any Contents or PR write');
      }
      sha(saved.base_commit_sha, 'Retained Contents base');
      for (const key of ['repository_full_name', 'base_branch', 'branch_name']) {
        if (saved[key] !== spec[key]) throw new Error('Retained branch differs from change: ' + key);
      }
      if (!Array.isArray(saved.files) || saved.files.length !== spec.files.length
          || saved.files.some((file, index) => file.path !== spec.files[index].path
            || file.previous_blob_sha !== spec.files[index].expected_blob_sha
            || (file.delete === true) !== (spec.files[index].delete === true)
            || file.expected_new_blob_sha !== spec.files[index].expected_new_blob_sha)) {
        throw new Error('Retained branch file preimages or source pins differ from the prepared change');
      }
      progress.resumed_branch_creation = true;
    }
    const readbackConcurrency = readbackLimit(options);
    progress.readback_concurrency = readbackConcurrency;
    const repository_full_name = spec.repository_full_name;
    Object.assign(progress, {repository_full_name, base_branch: spec.base_branch, branch_name: spec.branch_name});
    const actions = ['fetch', 'fetch_file', 'fetch_blob', 'create_branch',
      'create_file', 'update_file', 'delete_file', 'create_pull_request', 'merge_pull_request'];
    const bindings = Object.fromEntries(actions.map(action => [action,
      options.bindings?.[action] ?? 'mcp__codex_apps__github_' + action]));
    const required = actions.filter(action => action !== 'fetch_blob'
      && (action !== 'create_branch' || saved === undefined)
      && (action !== 'merge_pull_request' || spec.merge)
      && (action !== 'create_file' || publicationClaimConfig
        || spec.files.some(file => file.delete !== true && file.expected_blob_sha === null))
      && (action !== 'update_file' || publicationClaimConfig
        || spec.files.some(file => file.delete !== true && file.expected_blob_sha !== null))
      && (action !== 'delete_file' || spec.files.some(file => file.delete === true)));
    for (const action of required) {
      if (typeof tools?.[bindings[action]] !== 'function') {
        throw new Error('Binding not present: ' + bindings[action] + '. Repeat discovery alongside independent work.');
      }
    }
    announce = async () => {
      if (typeof options.onProgress !== 'function') return;
      try { await options.onProgress(JSON.parse(JSON.stringify(progress))); }
      catch (error) { progress.progress_callback_errors.push(String(error.message ?? error)); }
    };
    const timeAction = actionTimer(options, progress);
    const call = async (action, args) => {
      progress.calls[action] = (progress.calls[action] ?? 0) + 1;
      lastResponse = undefined;
      const response = timeAction
        ? await timeAction(action, () => tools[bindings[action]](args))
        : await tools[bindings[action]](args);
      lastResponse = response;
      try { return unpack(response, action); }
      catch (error) { error.native_response = response; throw error; }
    };
    const write = async (action, args, context) => {
      progress.pending_write = {action, ...context, state: 'calling'};
      await announce();
      const result = await call(action, args);
      progress.pending_write.state = 'response_received';
      await announce();
      return result;
    };
    const fetchJSON = async url => {
      const payload = await call('fetch', {url});
      return typeof payload.content === 'string' ? object(JSON.parse(payload.content), 'GitHub resource') : payload;
    };
    const readClaimFile = async args => {
      try { return {data: await call('fetch_file', args)}; }
      catch (error) {
        if (isMissingFileResponse(error.native_response ?? lastResponse)) return {absent: true};
        throw error;
      }
    };
    const takePublicationClaim = async () => {
      if (!publicationClaimConfig) return null;
      progress.stage = 'take_publication_claims';
      const result = await mutatePublicationClaims({fetchJSON, readFile: readClaimFile, call,
        config: publicationClaimConfig, action: 'take'});
      progress.publication_claim = result;
      publicationClaimActive = result.status === 'ACQUIRED';
      await announce();
      return result;
    };
    releasePublicationClaim = async reason => {
      if (!publicationClaimConfig || !publicationClaimActive) return null;
      const previousStage = progress.stage;
      try {
        progress.stage = 'release_publication_claims';
        const result = await mutatePublicationClaims({fetchJSON, readFile: readClaimFile, call,
          config: publicationClaimConfig, action: 'release'});
        progress.publication_claim_release = {...result, reason};
        if (result.status === 'RELEASED' || result.status === 'ALREADY_RELEASED') publicationClaimActive = false;
        return result;
      } catch (claimError) {
        progress.publication_claim_release = {status: 'RELEASE_FAILED', reason,
          error: String(claimError?.message ?? claimError)};
        return null;
      } finally {
        progress.stage = previousStage;
        await announce();
      }
    };
    const readBlob = typeof tools?.[bindings.fetch_blob] === 'function'
      ? blob_sha => call('fetch_blob', {repository_full_name, blob_sha}) : undefined;
    const api = 'https://api.github.com/repos/' + repository_full_name;
    const refURL = name => api + '/git/ref/heads/' + name.split('/').map(encodeURIComponent).join('/');
    const branchURL = refURL(spec.branch_name);
    const requireBranchHead = async expected => {
      const current = await fetchJSON(branchURL);
      if (current.ref !== 'refs/heads/' + spec.branch_name) throw new Error('Contents ref response identifies a different branch');
      const observed = sha(current.object?.sha, 'Contents branch head');
      progress.observed_branch_sha = observed;
      if (observed !== expected) throw new Error('Contents branch moved; reconcile it before another write');
    };
    const readDeletedPath = async (path, ref) => {
      try {
        const data = await call('fetch_file', {repository_full_name, path, ref, encoding: 'utf-8'});
        return {path, expected_absent: true, observed_absent: false,
          observed_blob_sha: sha(data.sha, 'Deleted path readback'), matches: false};
      } catch (error) {
        // Use this read's own response: final file reads may complete concurrently.
        if (!isMissingFileResponse(error.native_response)) throw error;
        return {path, expected_absent: true, observed_absent: true,
          observed_blob_sha: null, http_status: 404, connector_error_code: 'NOT_FOUND', matches: true};
      }
    };
    progress.stage = 'read_base';
    const base = await fetchJSON(refURL(spec.base_branch));
    if (base.ref !== 'refs/heads/' + spec.base_branch) throw new Error('Contents base ref response identifies a different branch');
    progress.initial_current_base_sha = sha(base.object?.sha, 'Current Contents base');
    progress.base_commit_sha = saved === undefined ? progress.initial_current_base_sha : saved.base_commit_sha;
    progress.stage = 'check_file_versions';
    for (const source of spec.files) {
      let existing;
      try {
        existing = await call('fetch_file', {repository_full_name, path: source.path,
          ref: progress.base_commit_sha, encoding: 'utf-8'});
      } catch (error) {
        if (!isMissingFileResponse(error.native_response)) throw error;
        existing = null;
      }
      const observed = existing === null ? null : sha(existing.sha, 'Contents preimage blob');
      if (observed !== source.expected_blob_sha) {
        throw new Error('Base file changed: ' + source.path + '; expected '
          + (source.expected_blob_sha ?? 'absent') + ', observed ' + (observed ?? 'absent'));
      }
      const file = {path: source.path, previous_blob_sha: observed, write_required: true};
      if (source.delete === true) file.delete = true;
      if (source.expected_new_blob_sha !== undefined) file.expected_new_blob_sha = source.expected_new_blob_sha;
      // A positive Contents response is a blob/content observation, not Git-mode or symlink proof.
      // Skip only a complete exact-content match; omitted preimage text is not an empty file.
      if (source.delete !== true && existing !== null && typeof existing.content === 'string'
          && (existing.content !== '' || observed === EMPTY_BLOB_SHA)
          && existing.content === source.content) {
        file.blob_sha = observed;
        checkNewBlobPin(file, source);
        file.write_required = false;
      }
      progress.files.push(file);
    }
    await announce();
    const candidates = progress.files.filter(file => file.write_required);
    if (!candidates.length) {
      progress.status = 'no_source_changes'; progress.stage = 'complete';
      await announce(); return progress;
    }
    const sourceByPath = new Map(spec.files.map(file => [file.path, file]));
    const claim = await takePublicationClaim();
    if (claim && claim.status !== 'ACQUIRED') {
      progress.status = claim.status === 'HELD_BY_PEER' ? 'publication_claim_held' : 'publication_claim_retry_required';
      progress.stage = 'complete';
      await announce();
      return progress;
    }
    progress.stage = 'create_branch';
    if (saved === undefined) {
      const created = await write('create_branch', {repository_full_name,
        branch_name: spec.branch_name, sha: progress.base_commit_sha},
      {expected_commit_sha: progress.base_commit_sha});
      if (created.branch !== spec.branch_name && created.ref !== 'refs/heads/' + spec.branch_name) {
        throw new Error('The branch response does not identify the requested branch');
      }
      if (created.object?.sha && created.object.sha !== progress.base_commit_sha) {
        throw new Error('The branch response does not identify the observed base');
      }
      progress.branch_creation = 'performed';
      progress.pending_write = null;
    } else {
      progress.branch_creation = 'retained';
    }
    progress.branch_created = true;
    progress.commit_sha = progress.base_commit_sha;
    await announce();
    await requireBranchHead(progress.commit_sha);
    for (const file of candidates) {
      const source = sourceByPath.get(file.path);
      const parent = progress.commit_sha;
      const action = file.delete === true ? 'delete_file'
        : file.previous_blob_sha === null ? 'create_file' : 'update_file';
      progress.stage = 'write_contents';
      const result = await write(action, {repository_full_name, branch: spec.branch_name,
        path: file.path, message: spec.commit_message,
        ...(file.delete === true ? {} : {content: source.content}),
        ...(action === 'create_file' ? {} : {sha: file.previous_blob_sha})},
      {path: file.path, expected_parent_sha: parent, previous_blob_sha: file.previous_blob_sha});
      const commitSHA = sha(result.commit_sha, 'Contents commit');
      const record = {action, path: file.path, parent_sha: parent, commit_sha: commitSHA, verified: false};
      progress.serial_writes.push(record);
      progress.commit_sha = commitSHA;
      if (action === 'update_file') record.response_blob_sha = sha(result.content_sha, 'Contents updated blob');
      progress.pending_write = null;
      await announce();
      progress.stage = 'check_contents_commit';
      const commit = await fetchJSON(api + '/commits/' + commitSHA + '?per_page=2&page=1');
      if (commit.sha !== commitSHA || !Array.isArray(commit.parents) || commit.parents.length !== 1
          || commit.parents[0].sha !== parent) {
        throw new Error('Contents commit has an unexpected parent; reconcile the branch before another write');
      }
      const changed = commit.files;
      const expectedStatus = file.delete === true ? 'removed' : action === 'create_file' ? 'added' : 'modified';
      if (!Array.isArray(changed) || changed.length !== 1 || changed[0].filename !== file.path
          || changed[0].status !== expectedStatus || changed[0].previous_filename !== undefined) {
        throw new Error('Contents commit does not contain exactly the intended path and change kind');
      }
      if (file.delete === true) {
        record.removed_blob_sha = sha(changed[0].sha, 'Contents removed-file blob');
        if (record.removed_blob_sha !== file.previous_blob_sha) {
          throw new Error('Contents deletion removed a different preimage blob');
        }
        record.readback = await readDeletedPath(file.path, commitSHA);
        if (!record.readback.matches) {
          throw new Error('Deleted path is still present at its Contents commit; reconcile without replaying the deletion');
        }
        file.blob_sha = null;
      } else {
        record.commit_blob_sha = sha(changed[0].sha, 'Contents changed-file blob');
        if (record.response_blob_sha !== undefined && record.response_blob_sha !== record.commit_blob_sha) {
          throw new Error('Contents response and commit disagree on the updated blob');
        }
        const data = await call('fetch_file', {repository_full_name, path: file.path,
          ref: commitSHA, encoding: 'utf-8'});
        record.readback = await resolveReadback(file, source, data, readBlob);
        if (!record.readback.matches || file.blob_sha !== record.commit_blob_sha) {
          throw new Error('Contents commit source readback did not match; finish reconciliation without replaying the write');
        }
        checkNewBlobPin(file, source);
      }
      await requireBranchHead(commitSHA);
      record.verified = true;
      await announce();
    }
    progress.stage = 'check_aggregate_paths';
    // The sole-parent, sole-path chain above establishes complete serial lineage.
    // The comparison independently binds the aggregate paths and final blobs.
    const comparison = await fetchJSON(api + '/compare/' + progress.base_commit_sha
      + '...' + progress.commit_sha + '?per_page=1&page=1');
    const expectedPaths = new Map(candidates.map(file => [file.path, file]));
    if (comparison.status !== 'ahead' || comparison.total_commits !== candidates.length
        || comparison.ahead_by !== candidates.length || comparison.behind_by !== 0
        || comparison.base_commit?.sha !== progress.base_commit_sha
        || comparison.merge_base_commit?.sha !== progress.base_commit_sha
        || !Array.isArray(comparison.files) || comparison.files.length !== candidates.length) {
      throw new Error('Contents aggregate comparison does not match the retained serial change');
    }
    const observedPaths = new Set();
    for (const changed of comparison.files) {
      const expected = expectedPaths.get(changed.filename);
      if (!expected || observedPaths.has(changed.filename)
          || changed.sha !== (expected.delete === true ? expected.previous_blob_sha : expected.blob_sha)
          || changed.status !== (expected.delete === true ? 'removed' : expected.previous_blob_sha === null ? 'added' : 'modified')
          || changed.previous_filename !== undefined) {
        throw new Error('Contents aggregate paths or final blobs differ from the prepared change');
      }
      observedPaths.add(changed.filename);
    }
    progress.aggregate_paths_verified = true;
    await requireBranchHead(progress.commit_sha);
    await announce();
    progress.stage = 'reconcile_before_pr_create';
    progress.pr_create_reconciliation = await reconcileBeforePullCreate({
      fetchJSON, repository: repository_full_name, baseBranch: spec.base_branch,
      branchName: spec.branch_name, expectedHead: progress.commit_sha,
      initialBaseHead: progress.base_commit_sha,
      files: progress.files.map(file => ({path: file.path, blob_sha: file.blob_sha}))
    });
    await announce();
    if (progress.pr_create_reconciliation) {
      progress.publication_status = progress.pr_create_reconciliation.status;
      progress.status = progress.pr_create_reconciliation.status === 'EXISTING_BRANCH_CONFLICT'
        ? 'reconciliation_hold' : 'reconciled';
      await releasePublicationClaim('preflight_reconciled');
      progress.stage = 'complete';
      await announce();
      return progress;
    }
    progress.stage = 'create_pull_request';
    const pr = await write('create_pull_request', {repository_full_name,
      head: spec.branch_name, base: spec.base_branch, title: spec.title, body: spec.body},
    {expected_head_sha: progress.commit_sha});
    progress.pull_request = {number: pr.number, url: pr.url ?? pr.display_url, head_sha: pr.head_sha};
    if (!Number.isInteger(pr.number) || pr.number < 1 || pr.head_sha !== progress.commit_sha) {
      throw new Error('The returned pull request does not identify the prepared Contents head');
    }
    progress.pending_write = null;
    progress.publication_status = 'pull_request_open';
    await releasePublicationClaim('pull_request_open');
    await announce();
    if (spec.merge) {
      progress.stage = 'check_current_base';
      const currentBase = await fetchJSON(refURL(spec.base_branch));
      if (currentBase.ref !== 'refs/heads/' + spec.base_branch) throw new Error('Current base ref identifies a different branch');
      progress.current_base_commit_sha = sha(currentBase.object?.sha, 'Current pre-merge base');
      if (progress.current_base_commit_sha !== progress.base_commit_sha) {
        for (const file of progress.files) {
          let current;
          try {
            current = await call('fetch_file', {repository_full_name, path: file.path,
              ref: progress.current_base_commit_sha, encoding: 'utf-8'});
          } catch (error) {
            if (!isMissingFileResponse(error.native_response)) throw error;
            current = null;
          }
          const observed = current === null ? null : sha(current.sha, 'Current pre-merge file');
          if (observed !== file.previous_blob_sha) {
            throw new Error('Current base file changed: ' + file.path + '; compose deliberately before merging this PR');
          }
        }
      }
      progress.current_preimages_verified = true;
      await announce();
      progress.stage = 'merge_pull_request';
      const merged = await write('merge_pull_request', {repository_full_name, pr_number: pr.number,
        expected_head_sha: progress.commit_sha, merge_method: spec.merge_method},
      {pr_number: pr.number, expected_head_sha: progress.commit_sha});
      progress.merge_result = merged;
      if (merged.merged !== true) throw new Error('GitHub did not report a completed merge');
      progress.merge_sha = sha(merged.sha, 'Contents merge');
      progress.pending_write = null;
      progress.publication_status = 'merged';
      await announce();
    }
    progress.stage = 'readback';
    progress.readback_ref = progress.merge_sha ?? progress.commit_sha;
    const reads = await settleReadbacks(progress.files, async file => {
      if (file.delete === true) {
        return {...await readDeletedPath(file.path, progress.readback_ref), removed_blob_sha: file.previous_blob_sha};
      }
      const source = sourceByPath.get(file.path);
      const data = await call('fetch_file', {repository_full_name, path: file.path,
        ref: progress.readback_ref, encoding: 'utf-8'});
      const readback = await resolveReadback({...file}, source, data, readBlob);
      return {...readback, commit_blob_sha: file.blob_sha,
        matches: readback.matches && readback.observed_blob_sha === file.blob_sha};
    }, readbackConcurrency);
    progress.readback = reads.map((read, index) => read.status === 'fulfilled' ? read.value
      : {path: progress.files[index].path, matches: false, error: String(read.reason?.message ?? read.reason),
        ...(read.reason?.tool_error ? {tool_error: read.reason.tool_error} : {})});
    const unavailable = progress.readback.some(read => read.error_code === 'readback_content_unavailable');
    progress.readback_status = unavailable ? 'content_unavailable'
      : progress.readback.some(read => !read.matches) ? 'incomplete' : 'complete';
    if (progress.readback_status !== 'complete') {
      throw new Error('Published Contents readback is incomplete; reconcile at readback_ref without repeating publication');
    }
    progress.status = spec.merge ? 'merged' : 'pull_request_open';
    progress.stage = 'complete';
    await announce();
    return progress;
  } catch (error) {
    if (error.tool_error) progress.tool_error = error.tool_error;
    progress.reconciliation_required = progress.branch_created === true || progress.pending_write !== null;
    const explicitProviderRejection = Number.isInteger(error.tool_error?.http_status)
      && error.tool_error.http_status >= 400 && error.tool_error.http_status < 500
      && error.tool_error.error_code !== 'transport_closed';
    const uncertainCreate = progress.pending_write?.action === 'create_pull_request'
      && progress.pending_write?.state === 'calling' && progress.pull_request === undefined
      && !explicitProviderRejection;
    if (publicationClaimActive && !uncertainCreate) {
      await releasePublicationClaim('known_failure');
    } else if (publicationClaimActive) {
      progress.publication_claim_release = {status: 'RETAINED_FOR_RECONCILIATION',
        reason: 'uncertain_create_pull_request'};
    }
    await announce();
    const failure = new GitHubPublishError(String(error.message ?? error), progress, error);
    if (error.tool_error) failure.tool_error = error.tool_error;
    failure.response = lastResponse;
    throw failure;
  }
}


/**
 * Recover selected regular UTF-8 files from observed immutable Git source.
 * No writer, PR reconstruction, retry, or inference of whole-operation custody.
 */
async function recoverGitHubFiles(tools, input, options = {}) {
  object(input, 'recovery input');
  object(options, 'recovery options');
  const allowed = ['repository_full_name', 'operation_id', 'commit_sha',
    'branch_name', 'expected_head_sha', 'files'];
  if (Object.keys(input).some(key => !allowed.includes(key))) {
    throw new TypeError('Unsupported recovery input field');
  }
  if (Object.keys(options).some(key => !['bindings', 'git_blob_identity', 'limits'].includes(key))) {
    throw new TypeError('Unsupported recovery option');
  }
  const repository = text(input.repository_full_name, 'repository_full_name');
  if (repository.length > 200 || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository)
      || repository.split('/').some(part => part === '.' || part === '..')) {
    throw new TypeError('repository_full_name must be owner/repository');
  }
  const operationId = text(input.operation_id, 'operation_id');
  if (operationId.length > 160 || !/^[A-Za-z0-9_.:-]+$/.test(operationId)) {
    throw new TypeError('operation_id must be a bounded stable identifier');
  }
  const byBranch = input.branch_name !== undefined;
  if (byBranch) {
    branch(input.branch_name, 'branch_name');
    if (input.branch_name.length > 255 || input.commit_sha !== undefined) {
      throw new TypeError('Choose an immutable commit or a bounded branch with expected head');
    }
    sha(input.expected_head_sha, 'expected_head_sha');
  } else {
    sha(input.commit_sha, 'commit_sha');
    if (input.expected_head_sha !== undefined) throw new TypeError('expected_head_sha requires branch_name');
  }
  if (!Array.isArray(input.files) || input.files.length < 1 || input.files.length > 64) {
    throw new TypeError('Recovery requires 1 to 64 explicitly selected files');
  }
  const seen = new Set();
  const files = [];
  for (let index = 0; index < input.files.length; index++) {
    if (!Object.prototype.hasOwnProperty.call(input.files, index)) throw new TypeError('files must be dense');
    const item = object(input.files[index], 'recovery file');
    if (Object.keys(item).some(key => !['path', 'expected_blob_sha'].includes(key))) {
      throw new TypeError('Recovery files accept only path and optional expected_blob_sha');
    }
    const path = text(item.path, 'recovery path');
    if (path.length > 1024 || path.includes('\\') || /[\x00-\x1f\x7f]/.test(path)
        || path.split('/').some(part => !part || part === '.' || part === '..')) {
      throw new TypeError('Noncanonical or oversized recovery path: ' + path);
    }
    if (seen.has(path)) throw new TypeError('Duplicate recovery path: ' + path);
    seen.add(path);
    if (item.expected_blob_sha !== undefined) sha(item.expected_blob_sha, 'expected_blob_sha');
    files.push({path, ...(item.expected_blob_sha === undefined ? {} : {expected_blob_sha: item.expected_blob_sha})});
  }
  for (const path of seen) {
    const parts = path.split('/');
    while (parts.length > 1) {
      parts.pop();
      if (seen.has(parts.join('/'))) throw new TypeError('A selected file is also a parent directory');
    }
  }
  const defaults = {max_calls: 128, max_file_bytes: 2097152, max_total_bytes: 8388608,
    max_metadata_chars: 2097152, max_tree_entries: 10000, max_elapsed_ms: 60000};
  const maxima = {max_calls: 512, max_file_bytes: 16777216, max_total_bytes: 67108864,
    max_metadata_chars: 8388608, max_tree_entries: 100000, max_elapsed_ms: 300000};
  const supplied = options.limits === undefined ? {} : object(options.limits, 'limits');
  if (Object.keys(supplied).some(key => !Object.prototype.hasOwnProperty.call(defaults, key))) {
    throw new TypeError('Unsupported recovery limit');
  }
  const limits = {...defaults, ...supplied};
  for (const [key, value] of Object.entries(limits)) {
    if (!Number.isSafeInteger(value) || value < 1 || value > maxima[key]) {
      throw new TypeError('Recovery limit out of range: ' + key);
    }
  }
  const customBindings = options.bindings === undefined ? {} : object(options.bindings, 'bindings');
  if (Object.keys(customBindings).some(key => !['fetch', 'fetch_file'].includes(key))) {
    throw new TypeError('Recovery accepts only read bindings fetch and fetch_file');
  }
  const bindings = {};
  for (const action of ['fetch', 'fetch_file']) {
    bindings[action] = customBindings[action] ?? 'mcp__codex_apps__github_' + action;
    if (typeof bindings[action] !== 'string' || typeof tools?.[bindings[action]] !== 'function') {
      throw new TypeError('Recovery binding not present: ' + action);
    }
  }
  let identity = options.git_blob_identity;
  if (identity === undefined && typeof require === 'function') {
    identity = require('./connected_git_blob_identity.cjs').gitBlobIdentity;
  }
  if (typeof identity !== 'function') {
    throw new TypeError('Supply the verified gitBlobIdentity function in options.git_blob_identity');
  }

  const requestedCommit = input.commit_sha;
  const requestedBranch = input.branch_name;
  const expectedHead = input.expected_head_sha;
  const start = Date.now();
  const result = {operation: 'source_recovery', operation_id: operationId,
    operation_id_provenance: 'caller_supplied', repository_full_name: repository,
    status: 'incomplete', stage: 'resolve_commit', writes: 0, snapshot: false,
    publication_verification: 'not_performed', execution_verification: 'not_performed',
    whole_operation_custody: 'not_inferred', limits: {...limits},
    calls: {fetch: 0, fetch_file: 0}, reads: [], files: files.map(file => ({...file, status: 'pending'})),
    recovered_files: 0, recovered_bytes: 0, metadata_chars: 0, tree_entries: 0,
    preimage_fallbacks: []};
  const fail = (code, message) => { const error = new Error(message); error.code = code; return error; };
  const describe = error => ({code: error?.code ?? 'RECOVERY_READ_FAILED',
    message: String(error?.message ?? error), ...(error?.tool_error ? {tool_error: error.tool_error} : {})});
  const checkTime = () => {
    if (Date.now() - start > limits.max_elapsed_ms) {
      throw fail('RECOVERY_TIME_LIMIT', 'Recovery elapsed-time limit reached; no further reads');
    }
  };
  let lastReadError;
  const call = async (action, args) => {
    checkTime();
    if (result.reads.length >= limits.max_calls) throw fail('RECOVERY_CALL_LIMIT', 'Recovery call limit reached');
    const record = {action, args: {...args}, outcome: 'calling'};
    result.reads.push(record);
    result.calls[action]++;
    lastReadError = undefined;
    try {
      const response = await tools[bindings[action]](args);
      record.response = response; // Preserve each exact envelope before decoding.
      const payload = unpack(response, action);
      record.outcome = 'received';
      checkTime();
      return payload;
    } catch (error) {
      record.thrown = error;
      lastReadError = error instanceof Error ? error : new Error(String(error?.message ?? error));
      if (error?.tool_error) lastReadError.tool_error = error.tool_error;
      if (error?.code) lastReadError.code = error.code;
      record.outcome = 'error';
      record.error = describe(error);
      throw lastReadError;
    }
  };
  const api = 'https://api.github.com/repos/' + repository;
  const trees = new Map();
  const fetchJSON = async url => {
    const payload = await call('fetch', {url});
    const serialized = typeof payload.content === 'string' ? payload.content : JSON.stringify(payload);
    if (serialized.length > limits.max_metadata_chars - result.metadata_chars) {
      throw fail('RECOVERY_METADATA_LIMIT', 'Recovery metadata character limit reached');
    }
    result.metadata_chars += serialized.length;
    const data = typeof payload.content === 'string'
      ? object(JSON.parse(payload.content), 'GitHub recovery resource') : payload;
    if (url.startsWith(api + '/git/trees/')) {
      const expected = url.slice((api + '/git/trees/').length);
      if (data.sha !== expected || !Array.isArray(data.tree) || data.truncated !== false) {
        throw fail('RECOVERY_INCOMPLETE_TREE', 'Recovery requires a complete identified parent tree');
      }
      if (data.tree.length > limits.max_tree_entries - result.tree_entries) {
        throw fail('RECOVERY_TREE_LIMIT', 'Recovery tree-entry limit reached');
      }
      const names = new Set();
      const types = {'100644': 'blob', '100755': 'blob', '120000': 'blob', '040000': 'tree', '160000': 'commit'};
      for (let i = 0; i < data.tree.length; i++) {
        const entry = data.tree[i];
        if (!entry || typeof entry.path !== 'string' || !entry.path || entry.path.includes('/')
            || entry.path.includes('\\') || /[\x00-\x1f\x7f]/.test(entry.path)
            || ['.', '..'].includes(entry.path) || names.has(entry.path)
            || !Object.prototype.hasOwnProperty.call(types, entry.mode) || types[entry.mode] !== entry.type
            || typeof entry.sha !== 'string' || !SHA.test(entry.sha)
            || (entry.size !== undefined && (!Number.isSafeInteger(entry.size) || entry.size < 0))) {
          throw fail('RECOVERY_INVALID_TREE', 'Invalid or duplicate native Git tree entry');
        }
        names.add(entry.path);
      }
      result.tree_entries += data.tree.length;
      trees.set(expected, data.tree);
    }
    return data;
  };
  let currentFile;
  try {
    let commitSha = requestedCommit;
    if (byBranch) {
      const ref = await fetchJSON(api + '/git/ref/heads/' + requestedBranch.split('/').map(encodeURIComponent).join('/'));
      if (ref.ref !== 'refs/heads/' + requestedBranch || ref.object?.type !== 'commit') {
        throw fail('RECOVERY_BRANCH_IDENTITY', 'The native ref does not identify the requested commit branch');
      }
      commitSha = sha(ref.object.sha, 'Observed recovery head');
      result.branch_observation = {branch_name: requestedBranch,
        expected_head_sha: expectedHead, observed_head_sha: commitSha};
      if (commitSha !== expectedHead) {
        throw fail('RECOVERY_HEAD_CHANGED', 'The branch differs from the expected head; no source files were read');
      }
    }
    result.commit_sha = commitSha;
    const commit = await fetchJSON(api + '/git/commits/' + commitSha);
    if (commit.sha !== commitSha || !Array.isArray(commit.parents) || commit.parents.length > 64) {
      throw fail('RECOVERY_COMMIT_IDENTITY', 'The native commit does not identify the requested commit and bounded parents');
    }
    const parents = [];
    for (let i = 0; i < commit.parents.length; i++) {
      parents.push(sha(commit.parents[i]?.sha, 'Recovery parent commit'));
    }
    result.commit = {sha: commitSha, parent_shas: parents, tree_sha: sha(commit.tree?.sha, 'Recovery root tree')};
    const readEntry = baseFileReader({api, repository_full_name: repository,
      commitSha, treeSha: result.commit.tree_sha, fetchJSON, progress: result, treeLabel: 'recovery',
      // An omitted parent tree cannot establish an existing file's Git mode.
      // Keep the original read failure and perform no one-line Contents fallback.
      readPreimage: async () => { throw lastReadError
        ?? fail('RECOVERY_MODE_UNAVAILABLE', 'No complete parent tree; recovery does not infer a Git mode'); }});
    for (const file of result.files) {
      currentFile = file;
      result.stage = 'read_path';
      checkTime();
      const entry = await readEntry(file.path, file.expected_blob_sha);
      const components = file.path.split('/');
      let treeSha = result.commit.tree_sha;
      file.tree_path = [];
      for (let i = 0; i < components.length; i++) {
        const found = trees.get(treeSha)?.find(item => item.path === components[i]);
        file.tree_path.push({directory_path: components.slice(0, i).join('/'),
          tree_sha: treeSha, entry: found ? {path: found.path, mode: found.mode, type: found.type, sha: found.sha} : null});
        if (!found || i === components.length - 1) break;
        treeSha = found.sha;
      }
      if (!entry) {
        file.status = 'absent';
        throw fail('RECOVERY_PATH_ABSENT', 'Selected path is absent from the observed complete tree: ' + file.path);
      }
      Object.assign(file, {blob_sha: entry.sha, mode: entry.mode, type: entry.type});
      if (entry.type !== 'blob' || !['100644', '100755'].includes(entry.mode)) {
        throw fail('RECOVERY_UNSUPPORTED_FILE', 'Recovery supports regular files only: ' + file.path);
      }
      if (file.expected_blob_sha !== undefined && entry.sha !== file.expected_blob_sha) {
        throw fail('RECOVERY_BLOB_CHANGED', 'Selected path differs from the expected blob: ' + file.path);
      }
      if (entry.size !== undefined) {
        file.observed_size = entry.size;
        if (entry.size > limits.max_file_bytes || entry.size > limits.max_total_bytes - result.recovered_bytes) {
          throw fail('RECOVERY_BYTE_LIMIT', 'Observed file size exceeds recovery byte budget: ' + file.path);
        }
      }
      result.stage = 'read_content';
      const data = await call('fetch_file', {repository_full_name: repository,
        path: file.path, ref: commitSha, encoding: 'utf-8'});
      if (data.sha !== entry.sha || (data.encoding !== undefined && data.encoding !== 'utf-8')) {
        throw fail('RECOVERY_CONTENT_IDENTITY', 'File response differs from the observed UTF-8 blob: ' + file.path);
      }
      if (typeof data.content !== 'string' || (data.content === '' && entry.sha !== EMPTY_BLOB_SHA)) {
        throw fail('RECOVERY_CONTENT_UNAVAILABLE', 'Complete source text was not returned: ' + file.path);
      }
      // UTF-16 length is a lower bound on UTF-8 bytes for valid Unicode.
      if (data.content.length > limits.max_file_bytes || data.content.length > limits.max_total_bytes - result.recovered_bytes) {
        throw fail('RECOVERY_BYTE_LIMIT', 'Returned source exceeds recovery byte budget: ' + file.path);
      }
      const measured = identity(data.content);
      if (!measured || !Number.isSafeInteger(measured.bytes) || measured.bytes < 0
          || measured.git_blob_sha !== entry.sha
          || (entry.size !== undefined && measured.bytes !== entry.size)) {
        throw fail('RECOVERY_BLOB_MISMATCH', 'Complete source bytes do not match the observed Git blob: ' + file.path);
      }
      if (measured.bytes > limits.max_file_bytes || measured.bytes > limits.max_total_bytes - result.recovered_bytes) {
        throw fail('RECOVERY_BYTE_LIMIT', 'Measured source exceeds recovery byte budget: ' + file.path);
      }
      checkTime();
      Object.assign(file, {status: 'recovered', encoding: 'utf-8', content: data.content,
        bytes: measured.bytes, git_blob_sha_verified: true, commit_sha: commitSha});
      result.recovered_files++;
      result.recovered_bytes += measured.bytes;
      currentFile = undefined;
    }
    result.status = 'recovered';
    result.stage = 'complete';
  } catch (error) {
    result.error = describe(error);
    if (currentFile) {
      if (currentFile.status === 'pending') currentFile.status = 'failed';
      currentFile.error = result.error;
    }
  }
  result.elapsed_ms = Date.now() - start;
  result.coverage = {requested_files: files.length, recovered_files: result.recovered_files,
    pending_paths: result.files.filter(file => file.status === 'pending').map(file => file.path),
    all_selected_files_recovered: result.recovered_files === files.length,
    repository_scope: 'caller_selected_paths_only'};
  return result;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {GitHubPublishError, publishGitHubChange, publishGitHubContentsChange, continueGitHubMerge,
    advanceGitHubContribution, reconcileGitHubContribution, observeGitHubContributionHead,
    inspectReadback, resolveReadback, inspectToolError, recoverGitHubFiles};
}
