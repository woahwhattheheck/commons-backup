'use strict';

// Native exec bindings and the already-authorized exporter command belong to the caller.
// This module owns only the NEXT conversation for that one exporter session.
const SCHEMA = 'commons.file_chunk_export/v1';
const SHA256 = /^[0-9a-f]{64}$/;
const GIT_SHA = /^[0-9a-f]{40}$/;
const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
const digestMatches = (value, pattern) => typeof value === 'string' && pattern.test(value);

class FileChunkError extends Error {
  constructor(code, message, progress, cause) {
    super(message);
    this.name = 'FileChunkError';
    this.code = code;
    this.progress = progress;
    if (cause !== undefined) this.cause = cause;
  }
}

function object(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError(label + ' must be an object');
  }
  return value;
}

function integer(value, label, minimum, maximum) {
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    throw new TypeError(label + ' must be an integer in ' + minimum + '..' + maximum);
  }
  return value;
}

function nonempty(value, label) {
  if (typeof value !== 'string' || !value.trim()) throw new TypeError(label + ' is required');
  return value;
}

function validBase64(value, bytes) {
  if (typeof value !== 'string' || value.length !== 4 * Math.ceil(bytes / 3)) return false;
  const remainder = bytes % 3;
  const padding = remainder === 0 ? 0 : 3 - remainder;
  const end = value.length - padding;
  for (let i = 0; i < end; i += 1) {
    if (ALPHABET.indexOf(value[i]) < 0) return false;
  }
  for (let i = end; i < value.length; i += 1) if (value[i] !== '=') return false;
  if (padding === 2 && (ALPHABET.indexOf(value[end - 1]) & 15) !== 0) return false;
  if (padding === 1 && (ALPHABET.indexOf(value[end - 1]) & 3) !== 0) return false;
  return true;
}

async function collectFileChunks(bindings, request, options = {}) {
  object(bindings, 'bindings');
  object(request, 'request');
  object(options, 'options');
  const hasCommand = Object.prototype.hasOwnProperty.call(request, 'command');
  const hasStart = Object.prototype.hasOwnProperty.call(request, 'start_result');
  if (hasCommand === hasStart) throw new TypeError('Provide exactly one command or start_result');
  if (hasCommand) nonempty(request.command, 'command');
  else object(request.start_result, 'start_result');
  const file = nonempty(request.file, 'file');
  if (typeof bindings.write_stdin !== 'function'
      || (hasCommand && typeof bindings.exec_command !== 'function')) {
    throw new TypeError('Native exec_command/write_stdin bindings are required');
  }
  if (request.workdir !== undefined) nonempty(request.workdir, 'workdir');
  const maxBytes = integer(request.max_bytes ?? 33554432, 'max_bytes', 0, Number.MAX_SAFE_INTEGER);
  const maxParts = integer(request.max_parts ?? 4096, 'max_parts', 0, 100000);
  const timeoutMs = integer(request.timeout_ms ?? 120000, 'timeout_ms', 1, 3600000);
  const maxPolls = integer(request.max_polls ?? 64, 'max_polls', 0, 4096);
  const outputTokens = integer(request.max_output_tokens ?? 300000, 'max_output_tokens', 1000, 300000);
  const responseChars = integer(request.max_response_chars ?? 1048576, 'max_response_chars', 1000, 2097152);
  const lineChars = integer(request.max_line_chars ?? 900000, 'max_line_chars', 1000, 1048576);
  const preambleChars = integer(request.max_preamble_chars ?? 8192, 'max_preamble_chars', 0, 65536);
  const yieldMs = integer(request.yield_time_ms ?? 1000, 'yield_time_ms', 250, 1000);
  if (request.expected_bytes !== undefined) integer(request.expected_bytes, 'expected_bytes', 0, maxBytes);
  if (request.expected_sha256 !== undefined && !digestMatches(request.expected_sha256, SHA256)) {
    throw new TypeError('expected_sha256 must be a lowercase SHA-256');
  }
  if (request.expected_git_blob_sha1 !== undefined && !digestMatches(request.expected_git_blob_sha1, GIT_SHA)) {
    throw new TypeError('expected_git_blob_sha1 must be a lowercase Git blob SHA-1');
  }
  for (const callback of ['onProgress', 'onResponse']) {
    if (options[callback] !== undefined && typeof options[callback] !== 'function') {
      throw new TypeError(callback + ' must be a function');
    }
  }

  const deadline = Date.now() + timeoutMs;
  const encodedParts = [];
  const partMetadata = [];
  const state = {
    stage: 'starting', file, session_id: null, exit_code: null, calls: 0, polls: 0,
    parts_received: 0, bytes_received: 0, next_offset: 0,
    manifest: null, completion: null, preamble: '', callback_errors: [], cleanup: null
  };
  let buffer = '';
  let waitingForPart = false;
  let sentOffset = null;

  function snapshot() {
    return {
      stage: state.stage, file: state.file, session_id: state.session_id,
      exit_code: state.exit_code, calls: state.calls, polls: state.polls,
      parts_received: state.parts_received, bytes_received: state.bytes_received,
      next_offset: state.next_offset, manifest: state.manifest,
      completion: state.completion, callback_errors: state.callback_errors.slice(),
      cleanup: state.cleanup
    };
  }

  async function progress() {
    if (!options.onProgress) return;
    try { await options.onProgress(snapshot()); }
    catch (error) { state.callback_errors.push(String(error).slice(0, 512)); }
  }

  function fail(code, message) {
    throw new FileChunkError(code, message, snapshot());
  }

  function checkDeadline() {
    if (Date.now() >= deadline) fail('DEADLINE', 'The declared conversation deadline elapsed');
  }

  function sameIdentity(record) {
    const m = state.manifest;
    return record.schema === SCHEMA && record.file === m.file
      && record.file_bytes === m.file_bytes && record.sha256 === m.sha256
      && record.git_blob_sha1 === m.git_blob_sha1;
  }

  function preamble(line) {
    if (state.preamble.length + line.length + 1 > preambleChars) {
      fail('PREAMBLE_LIMIT', 'Startup output exceeded max_preamble_chars');
    }
    state.preamble += line + '\n';
  }

  function recordLine(line) {
    if (!line.trim()) return;
    if (line.length > lineChars) fail('LINE_LIMIT', 'A record exceeded max_line_chars');
    let record;
    try { record = JSON.parse(line); }
    catch (error) {
      if (!state.manifest) { preamble(line); return; }
      fail('INVALID_JSON', 'Exporter output was not a complete JSON record');
    }
    if (!record || typeof record !== 'object' || Array.isArray(record) || record.schema !== SCHEMA) {
      if (!state.manifest) { preamble(line); return; }
      fail('UNEXPECTED_OUTPUT', 'Unexpected output after the exporter manifest');
    }
    if (record.kind === 'error') {
      fail(typeof record.code === 'string' ? record.code : 'EXPORTER_ERROR',
        typeof record.message === 'string' ? record.message : 'The exporter reported an error');
    }
    if (record.kind === 'manifest') {
      if (state.manifest) fail('DUPLICATE_MANIFEST', 'The exporter emitted more than one manifest');
      if (record.file !== file
          || !Number.isSafeInteger(record.file_bytes) || record.file_bytes < 0 || record.file_bytes > maxBytes
          || !Number.isSafeInteger(record.chunk_bytes) || record.chunk_bytes < 3
          || record.chunk_bytes > 524286 || record.chunk_bytes % 3 !== 0
          || !Number.isSafeInteger(record.part_count) || record.part_count < 0
          || record.part_count > maxParts
          || record.part_count !== Math.ceil(record.file_bytes / record.chunk_bytes)
          || !digestMatches(record.sha256, SHA256) || !digestMatches(record.git_blob_sha1, GIT_SHA)
          || record.next_offset !== (record.part_count ? 0 : null)) {
        fail('MANIFEST_MISMATCH', 'The manifest violates the requested file or transfer limits');
      }
      if ((request.expected_bytes !== undefined && record.file_bytes !== request.expected_bytes)
          || (request.expected_sha256 !== undefined && record.sha256 !== request.expected_sha256)
          || (request.expected_git_blob_sha1 !== undefined && record.git_blob_sha1 !== request.expected_git_blob_sha1)) {
        fail('PIN_MISMATCH', 'The manifest does not match the supplied source pins');
      }
      state.manifest = record;
      state.next_offset = record.part_count ? 0 : null;
      state.stage = 'manifest';
      return;
    }
    if (!state.manifest) fail('MISSING_MANIFEST', 'A protocol record arrived before its manifest');
    if (state.completion) fail('AFTER_COMPLETION', 'A protocol record arrived after completion');
    if (record.kind === 'source-part') {
      const m = state.manifest;
      const end = Math.min(m.file_bytes, state.bytes_received + m.chunk_bytes);
      if (!waitingForPart || sentOffset !== state.bytes_received || !sameIdentity(record)
          || record.part_index !== state.parts_received || record.part_count !== m.part_count
          || record.start !== state.bytes_received || record.end !== end
          || end <= record.start || !digestMatches(record.chunk_sha256, SHA256)
          || record.next_offset !== (end < m.file_bytes ? end : null)
          || !validBase64(record.base64, end - record.start)) {
        fail('PART_MISMATCH', 'A part was unsolicited, noncontiguous, malformed, or differently pinned');
      }
      encodedParts.push(record.base64);
      partMetadata.push({
        part_index: record.part_index, start: record.start, end: record.end,
        chunk_sha256: record.chunk_sha256
      });
      state.parts_received += 1;
      state.bytes_received = end;
      state.next_offset = record.next_offset;
      waitingForPart = false;
      state.stage = 'part';
      return;
    }
    if (record.kind === 'complete') {
      if (waitingForPart || !sameIdentity(record)
          || state.parts_received !== state.manifest.part_count
          || record.parts !== state.parts_received
          || record.transferred_bytes !== state.bytes_received
          || state.bytes_received !== state.manifest.file_bytes) {
        fail('COMPLETION_MISMATCH', 'The completion does not cover the exact manifest bytes and parts');
      }
      state.completion = record;
      state.stage = 'waiting_for_exit';
      return;
    }
    fail('UNEXPECTED_RECORD', 'The exporter emitted an unknown protocol record');
  }

  async function receive(result, operation) {
    object(result, 'native result');
    if (result.session_id !== undefined) {
      integer(result.session_id, 'session_id', 1, Number.MAX_SAFE_INTEGER);
      if (state.session_id !== null && state.session_id !== result.session_id) {
        fail('SESSION_CHANGED', 'The native response changed the exporter session');
      }
      state.session_id = result.session_id;
    }
    if (result.exit_code !== undefined) {
      if (!Number.isInteger(result.exit_code)) fail('INVALID_EXIT', 'The native exit code is invalid');
      state.exit_code = result.exit_code;
    }
    if (typeof result.output !== 'string' || result.output.length > responseChars) {
      fail('RESPONSE_LIMIT', 'Native output is missing or exceeds max_response_chars');
    }
    if (options.onResponse) await options.onResponse(result, { operation, call: state.calls });
    buffer += result.output;
    let split;
    while ((split = buffer.indexOf('\n')) !== -1) {
      let line = buffer.slice(0, split); buffer = buffer.slice(split + 1);
      if (line.endsWith('\r')) line = line.slice(0, -1);
      recordLine(line);
    }
    if (buffer.length > lineChars) fail('LINE_LIMIT', 'An unfinished record exceeded max_line_chars');
    if (state.exit_code !== null && buffer) {
      const tail = buffer; buffer = ''; recordLine(tail);
    }
    await progress();
  }

  async function read(chars, operation) {
    checkDeadline();
    if (state.session_id === null || state.exit_code !== null) {
      fail('SESSION_CLOSED', 'No live exporter session remains');
    }
    if (!chars) {
      if (state.polls >= maxPolls) fail('POLL_LIMIT', 'The declared empty-read budget was exhausted');
      state.polls += 1;
    }
    state.calls += 1;
    const result = await bindings.write_stdin({
      session_id: state.session_id, chars, yield_time_ms: yieldMs, max_output_tokens: outputTokens
    });
    await receive(result, operation);
  }

  async function closeOwnedSession() {
    if (state.session_id === null || state.exit_code !== null) return;
    state.cleanup = { attempted: true, session_id: state.session_id, exit_code: null };
    try {
      for (let attempt = 0; attempt < 3; attempt += 1) {
        const result = await bindings.write_stdin({
          session_id: state.session_id, chars: attempt === 0 ? '\u0003' : '',
          yield_time_ms: yieldMs, max_output_tokens: 2000
        });
        if (result.exit_code !== undefined) {
          state.exit_code = result.exit_code; state.cleanup.exit_code = result.exit_code; break;
        }
      }
      state.cleanup.session_closed = state.exit_code !== null;
    } catch (error) {
      state.cleanup.error = String(error).slice(0, 512);
      state.cleanup.session_closed = false;
    }
  }

  try {
    checkDeadline();
    if (hasCommand) {
      state.calls += 1;
      const args = {
        cmd: request.command, login: false, tty: true,
        yield_time_ms: yieldMs, max_output_tokens: outputTokens
      };
      if (request.workdir !== undefined) args.workdir = request.workdir;
      await receive(await bindings.exec_command(args), 'start');
    } else {
      await receive(request.start_result, 'adopt_start');
    }
    while (!state.manifest && state.exit_code === null) await read('', 'await_manifest');
    if (!state.manifest) {
      if (state.exit_code === 0) fail('MISSING_MANIFEST', 'The command exited successfully without a manifest');
      state.stage = 'exited_before_manifest';
      await progress();
      return {
        status: 'exited_before_manifest', exit_code: state.exit_code,
        startup_output: state.preamble, progress: snapshot()
      };
    }
    while (state.parts_received < state.manifest.part_count) {
      if (state.exit_code !== null) fail('EARLY_EXIT', 'The exporter exited before all requested parts arrived');
      waitingForPart = true; sentOffset = state.bytes_received; state.stage = 'requesting_part';
      await read('NEXT ' + sentOffset + '\n', 'next');
      while (waitingForPart && state.exit_code === null) await read('', 'await_part');
      if (waitingForPart) fail('EARLY_EXIT', 'The exporter exited before its requested part arrived');
    }
    while (state.exit_code === null) {
      await read('', 'await_completion_or_exit');
    }
    if (!state.completion) fail('MISSING_COMPLETION', 'The exporter exited without a complete transfer');
    if (state.exit_code !== 0) fail('EXPORT_EXIT', 'The exporter did not exit successfully');
    const base64 = encodedParts.join('');
    if (!validBase64(base64, state.bytes_received)) fail('CONTENT_LENGTH', 'Joined base64 does not match the complete byte count');
    state.stage = 'complete';
    await progress();
    return {
      status: 'complete', manifest: state.manifest, completion: state.completion,
      base64, parts: partMetadata, exit_code: 0, startup_output: state.preamble,
      source_pins_matched: {
        bytes: request.expected_bytes !== undefined,
        sha256: request.expected_sha256 !== undefined,
        git_blob_sha1: request.expected_git_blob_sha1 !== undefined
      },
      validation: 'protocol_ranges_canonical_base64_reported_pins_completion_and_zero_exit',
      content_hashes: 'reported_by_exporter', progress: snapshot()
    };
  } catch (error) {
    await closeOwnedSession();
    state.stage = 'error';
    await progress();
    const code = error instanceof FileChunkError ? error.code : 'NATIVE_OR_CALLBACK_ERROR';
    throw new FileChunkError(code, error.message || String(error), snapshot(), error);
  }
}

module.exports = { FileChunkError, collectFileChunks };
