'use strict';

const DEFAULTS = Object.freeze({max_file_bytes: 8388608, chunk_bytes: 4096,
  concurrency: 4, max_command_bytes: 48000});
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);

class ExecJsonReaderError extends Error {
  constructor(message, progress, cause) {
    super(message);
    this.name = 'ExecJsonReaderError';
    this.progress = {...progress};
    this.cause = cause;
  }
}

function utf8Bytes(text) {
  let count = 0;
  for (const char of text) {
    const cp = char.codePointAt(0);
    count += cp < 128 ? 1 : cp < 2048 ? 2 : cp < 65536 ? 3 : 4;
  }
  return count;
}

// Values become Python JSON expressions in a quoted heredoc, never shell syntax.
const pythonJson = value => 'json.loads(' + JSON.stringify(JSON.stringify(value)) + ')';
const command = program => "python3 - <<'CONNECTED_EXEC_JSON_READER_PY'\n" +
  'from pathlib import Path\nimport json, os, stat, hashlib, base64\n' + program +
  '\nCONNECTED_EXEC_JSON_READER_PY';
const stamp = 'def identity(value):\n' +
  '    return {"device": str(value.st_dev), "inode": str(value.st_ino), ' +
  '"mtime_ns": str(value.st_mtime_ns), "file_bytes": value.st_size}\n';

function base64Bytes(value) {
  if (typeof value !== 'string' ||
      !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value)) {
    throw new TypeError('Chunk lacks complete base64');
  }
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  const bytes = new Uint8Array(value.length / 4 * 3 -
    (value.endsWith('==') ? 2 : value.endsWith('=') ? 1 : 0));
  let at = 0;
  for (let index = 0; index < value.length; index += 4) {
    const a = alphabet.indexOf(value[index]), b = alphabet.indexOf(value[index + 1]);
    const c = alphabet.indexOf(value[index + 2]), d = alphabet.indexOf(value[index + 3]);
    bytes[at++] = (a << 2) | (b >> 4);
    if (c >= 0) bytes[at++] = ((b & 15) << 4) | (c >> 2);
    if (d >= 0) bytes[at++] = ((c & 3) << 6) | d;
  }
  return bytes;
}

function utf8Text(bytes) {
  const parts = [];
  let part = '';
  for (let index = 0; index < bytes.length;) {
    const first = bytes[index++];
    let cp, extra, minimum;
    if (first < 128) { cp = first; extra = 0; minimum = 0; }
    else if (first >= 0xc2 && first <= 0xdf) { cp = first & 31; extra = 1; minimum = 128; }
    else if (first >= 0xe0 && first <= 0xef) { cp = first & 15; extra = 2; minimum = 2048; }
    else if (first >= 0xf0 && first <= 0xf4) { cp = first & 7; extra = 3; minimum = 65536; }
    else throw new TypeError('Journal bytes are not valid UTF-8');
    if (index + extra > bytes.length) throw new TypeError('Journal ends within a UTF-8 code point');
    for (let next = 0; next < extra; next++) {
      const value = bytes[index++];
      if (value < 128 || value > 191) throw new TypeError('Invalid UTF-8 continuation byte');
      cp = (cp << 6) | (value & 63);
    }
    if (cp < minimum || cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff)) {
      throw new TypeError('Journal bytes contain an invalid UTF-8 code point');
    }
    part += String.fromCodePoint(cp);
    if (part.length >= 8192) { parts.push(part); part = ''; }
  }
  if (part) parts.push(part);
  return parts.join('');
}

/**
 * Restore one complete named cloud JSON file through supplied execution.
 * sha256Utf8 is the existing helper returning {bytes, sha256}; no provider
 * operation, file write, credential acquisition, retry or implicit resume.
 */
function createExecJsonReader(execCommand, sha256Utf8, options) {
  if (typeof execCommand !== 'function' || typeof sha256Utf8 !== 'function') {
    throw new TypeError('Supply execCommand and sha256Utf8');
  }
  if (!object(options)) throw new TypeError('options must be an object');
  for (const key of Object.keys(options)) {
    if (key !== 'directory' && !own(DEFAULTS, key)) throw new TypeError('Unsupported option: ' + key);
  }
  const directory = options.directory;
  if (typeof directory !== 'string' || !directory.startsWith('/') ||
      /^\/+$/ .test(directory) || directory.includes('\0') || utf8Bytes(directory) > 4096) {
    throw new TypeError('directory must be a bounded absolute local path');
  }
  const limits = {...DEFAULTS}, bounds = {
    max_file_bytes: [1, 67108864], chunk_bytes: [1024, 8192],
    concurrency: [1, 8], max_command_bytes: [8192, 60000]
  };
  for (const key of Object.keys(DEFAULTS)) {
    if (!own(options, key)) continue;
    const value = options[key], [min, max] = bounds[key];
    if (!Number.isSafeInteger(value) || value < min || value > max) {
      throw new RangeError(key + ' must be an integer from ' + min + ' to ' + max);
    }
    limits[key] = value;
  }

  async function read(name) {
    if (typeof name !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$/.test(name)) {
      throw new TypeError('name must be a bounded plain basename');
    }
    const path = directory.replace(/\/+$/, '') + '/' + name + '.json';
    const progress = {status: 'incomplete', stage: 'read_metadata', path, commands: 0,
      chunks: 0, bytes_received: 0, largest_command_bytes: 0};
    const run = async (program, maxOutputTokens) => {
      const cmd = command(program), size = utf8Bytes(cmd);
      if (size > limits.max_command_bytes) throw new RangeError('Command exceeds max_command_bytes');
      progress.commands++;
      progress.largest_command_bytes = Math.max(progress.largest_command_bytes, size);
      const response = await execCommand({cmd, shell: 'bash', login: false,
        max_output_tokens: maxOutputTokens, yield_time_ms: 10000});
      if (!response || response.exit_code !== 0 || response.session_id !== undefined ||
          typeof response.output !== 'string') {
        const error = new Error('Local read command did not confirm completed output');
        error.execution_result = response;
        throw error;
      }
      try { return JSON.parse(response.output); }
      catch (cause) {
        const error = new Error('Local read output is not complete JSON');
        error.execution_result = response;
        error.cause = cause;
        throw error;
      }
    };
    try {
      const header = await run(stamp + 'path = Path(' + pythonJson(path) + ')\n' +
        'with path.open("rb") as source:\n' +
        '    before = os.fstat(source.fileno())\n' +
        '    if not stat.S_ISREG(before.st_mode): raise TypeError("Journal is not a regular file")\n' +
        '    if before.st_size > ' + limits.max_file_bytes + ': raise ValueError("Journal exceeds max_file_bytes")\n' +
        '    digest = hashlib.sha256()\n' +
        '    for block in iter(lambda: source.read(65536), b""): digest.update(block)\n' +
        '    after = os.fstat(source.fileno())\n' +
        '    if identity(before) != identity(after): raise ValueError("Journal changed during metadata read")\n' +
        'print(json.dumps({"identity": identity(before), "sha256": digest.hexdigest()}))', 1000);
      if (!object(header) || !object(header.identity) || !/^[0-9a-f]{64}$/.test(header.sha256 ?? '') ||
          !Number.isSafeInteger(header.identity.file_bytes) || header.identity.file_bytes < 0 ||
          header.identity.file_bytes > limits.max_file_bytes ||
          ['device', 'inode', 'mtime_ns'].some(key =>
            typeof header.identity[key] !== 'string' || !/^[0-9]+$/.test(header.identity[key]))) {
        throw new TypeError('Read metadata lacks complete file identity');
      }
      Object.assign(progress, {file_bytes: header.identity.file_bytes,
        file_identity: header.identity, source_sha256: header.sha256, stage: 'read_chunks'});
      const bytes = new Uint8Array(header.identity.file_bytes);
      const count = Math.ceil(bytes.length / limits.chunk_bytes);
      progress.chunks = count;
      for (let start = 0; start < count; start += limits.concurrency) {
        const tasks = Array.from({length: Math.min(limits.concurrency, count - start)}, (_, index) => {
          const offset = (start + index) * limits.chunk_bytes;
          const length = Math.min(limits.chunk_bytes, bytes.length - offset);
          return {offset, length};
        });
        const settled = await Promise.allSettled(tasks.map(async task => {
          const value = await run(stamp + 'path = Path(' + pythonJson(path) + ')\n' +
            'expected = ' + pythonJson(header.identity) + '\n' +
            'with path.open("rb") as source:\n' +
            '    before = os.fstat(source.fileno())\n' +
            '    if identity(before) != expected: raise ValueError("Journal identity changed")\n' +
            '    source.seek(' + task.offset + ')\n    data = source.read(' + task.length + ')\n' +
            '    after = os.fstat(source.fileno())\n' +
            '    if identity(after) != expected or len(data) != ' + task.length +
            ': raise ValueError("Journal changed during chunk read")\n' +
            'print(json.dumps({"offset": ' + task.offset + ', "bytes": len(data), ' +
            '"data_base64": base64.b64encode(data).decode("ascii")}))',
          Math.ceil(limits.chunk_bytes * 4 / 3) + 1500);
          if (!object(value) || value.offset !== task.offset || value.bytes !== task.length) {
            throw new TypeError('Chunk does not identify the requested byte range');
          }
          const part = base64Bytes(value.data_base64);
          if (part.length !== task.length) throw new TypeError('Decoded chunk byte count differs');
          return {offset: task.offset, bytes: part};
        }));
        const failure = settled.find(item => item.status === 'rejected');
        if (failure) throw failure.reason;
        for (const result of settled) {
          bytes.set(result.value.bytes, result.value.offset);
          progress.bytes_received += result.value.bytes.length;
        }
      }
      progress.stage = 'verify';
      const text = utf8Text(bytes), computed = sha256Utf8(text);
      if (!object(computed) || computed.bytes !== bytes.length || computed.sha256 !== header.sha256) {
        throw new TypeError('Reconstructed journal does not match the observed complete SHA256');
      }
      progress.stage = 'parse';
      const value = JSON.parse(text);
      return {schema: 'commons.connected_exec_json_reader/v1', status: 'read',
        source: {path, file_bytes: bytes.length, identity: header.identity,
          sha256: header.sha256, complete_sha256_verified: true},
        stats: {commands: progress.commands, chunks: count,
          largest_command_bytes: progress.largest_command_bytes},
        json_text: text, value};
    } catch (error) {
      throw new ExecJsonReaderError(error?.message ?? String(error), progress, error);
    }
  }
  return {read, directory, limits: {...limits}};
}

module.exports = {createExecJsonReader, ExecJsonReaderError};
