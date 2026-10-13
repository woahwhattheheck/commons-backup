'use strict';

// Caller supplies an authorized execution binding and an isolated local directory.
// No provider call, credential acquisition, effect retry, or implicit resume.
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const DEFAULTS = {max_command_bytes: 48000, chunk_chars: 16000,
  concurrency: 4, max_serialized_chars: 8388608};

class ExecJsonJournalError extends Error {
  constructor(message, progress, cause) {
    super(message);
    this.name = 'ExecJsonJournalError';
    this.progress = {...progress};
    this.cause = cause;
  }
}

function utf8Bytes(text) {
  let bytes = 0;
  for (const character of text) {
    const point = character.codePointAt(0);
    bytes += point < 128 ? 1 : point < 2048 ? 2 : point < 65536 ? 3 : 4;
  }
  return bytes;
}

// This is a Python JSON expression inside a quoted heredoc, not shell escaping.
const pythonJson = value => 'json.loads(' + JSON.stringify(JSON.stringify(value)) + ')';
const command = program => "python3 - <<'CONNECTED_EXEC_JSON_JOURNAL_PY'\n" +
  'from pathlib import Path\nimport json, os\n' + program +
  '\nCONNECTED_EXEC_JSON_JOURNAL_PY';

function createExecJsonJournal(execCommand, options) {
  if (typeof execCommand !== 'function') throw new TypeError('Supply execCommand');
  if (!options || typeof options !== 'object' || Array.isArray(options)) {
    throw new TypeError('options must be an object');
  }
  for (const key of Object.keys(options)) {
    if (key !== 'directory' && !own(DEFAULTS, key)) throw new TypeError('Unsupported option: ' + key);
  }
  const directory = options.directory;
  if (typeof directory !== 'string' || !directory.startsWith('/') || /^\/+$/ .test(directory) ||
      directory.includes('\0') || utf8Bytes(directory) > 4096) {
    throw new TypeError('directory must be a bounded absolute local path');
  }
  const limits = {...DEFAULTS};
  const bounds = {max_command_bytes: [8192, 60000], chunk_chars: [1, 24000],
    concurrency: [1, 8], max_serialized_chars: [1, 67108864]};
  for (const key of Object.keys(DEFAULTS)) {
    if (!own(options, key)) continue;
    const value = options[key], [min, max] = bounds[key];
    if (!Number.isSafeInteger(value) || value < min || value > max) {
      throw new RangeError(key + ' must be an integer from ' + min + ' to ' + max);
    }
    limits[key] = value;
  }
  const active = new Set();

  async function write(name, value) {
    if (typeof name !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$/.test(name)) {
      throw new TypeError('name must be a bounded plain basename');
    }
    if (active.has(name)) throw new TypeError('This name is already active');
    const serialized = JSON.stringify(value);
    if (serialized === undefined) throw new TypeError('value must serialize to JSON');
    if (serialized.length > limits.max_serialized_chars) throw new RangeError('JSON exceeds max_serialized_chars');
    const root = directory.replace(/\/+$/, '');
    const path = root + '/' + name + '.json';
    const pending = root + '/.' + name + '.pending';
    const progress = {status: 'incomplete', stage: 'prepare', name, path,
      pending_directory: pending, serialized_chars: serialized.length,
      chunks: 0, commands: 0, largest_command_bytes: 0};
    const bounded = cmd => {
      const bytes = utf8Bytes(cmd);
      if (bytes > limits.max_command_bytes) throw new RangeError('Command exceeds max_command_bytes');
      return {cmd, bytes};
    };
    const prefix = 'pending = Path(' + pythonJson(pending) + ')\n';
    const prepared = bounded(command(
      'base = Path(' + pythonJson(root) + ')\nbase.mkdir(parents=True, exist_ok=True)\n' +
      'target = Path(' + pythonJson(path) + ')\n' +
      'if target.exists(): raise FileExistsError("Journal destination already exists")\n' +
      prefix + 'pending.mkdir()'));
    const planned = [];
    for (let start = 0; start < serialized.length;) {
      let end = Math.min(serialized.length, start + limits.chunk_chars);
      let selected;
      while (!selected) {
        if (end < serialized.length && serialized.charCodeAt(end - 1) >= 0xd800 &&
            serialized.charCodeAt(end - 1) <= 0xdbff && serialized.charCodeAt(end) >= 0xdc00 &&
            serialized.charCodeAt(end) <= 0xdfff) end--;
        if (end <= start) throw new RangeError('Command bound cannot accommodate the next code point');
        const part = String(planned.length).padStart(6, '0') + '.part';
        const cmd = command(prefix + '(pending / ' + pythonJson(part) + ').write_text(' +
          pythonJson(serialized.slice(start, end)) + ', encoding="utf-8")');
        if (utf8Bytes(cmd) <= limits.max_command_bytes) selected = bounded(cmd);
        else end = start + Math.floor((end - start) / 2);
      }
      planned.push(selected);
      start = end;
    }
    progress.chunks = planned.length;
    const completed = bounded(command(prefix +
      'target = Path(' + pythonJson(path) + ')\n' +
      'parts = [pending / ("%06d.part" % index) for index in range(' + planned.length + ')]\n' +
      'data = "".join(part.read_text(encoding="utf-8") for part in parts)\njson.loads(data)\n' +
      'temporary = pending / "assembled.json"\n' +
      'with temporary.open("x", encoding="utf-8", newline="") as output:\n' +
      '    output.write(data + "\\n")\n    output.flush()\n    os.fsync(output.fileno())\n' +
      'os.replace(temporary, target)\n' +
      '# Cleanup failures do not invalidate the already atomically installed journal.\n' +
      'for part in parts:\n    try: part.unlink()\n    except OSError: pass\n' +
      'try: pending.rmdir()\nexcept OSError: pass'));
    const run = async ({cmd, bytes}) => {
      progress.commands++;
      progress.largest_command_bytes = Math.max(progress.largest_command_bytes, bytes);
      const result = await execCommand({cmd, shell: 'bash', login: false,
        max_output_tokens: 200, yield_time_ms: 10000});
      if (!result || result.exit_code !== 0 || result.session_id !== undefined) {
        const error = new Error('Local journal command did not confirm completion');
        error.execution_result = result;
        throw error;
      }
    };
    active.add(name);
    try {
      await run(prepared);
      progress.stage = 'write_chunks';
      for (let offset = 0; offset < planned.length; offset += limits.concurrency) {
        const settled = await Promise.allSettled(planned.slice(offset, offset + limits.concurrency).map(run));
        const failure = settled.find(result => result.status === 'rejected');
        if (failure) throw failure.reason;
      }
      progress.stage = 'assemble';
      await run(completed);
      return {...progress, status: 'written', stage: 'complete',
        file_bytes: utf8Bytes(serialized) + 1};
    } catch (error) {
      throw new ExecJsonJournalError(error.message || String(error), progress, error);
    } finally {
      active.delete(name);
    }
  }

  return {write, directory, limits: {...limits}};
}

module.exports = {createExecJsonJournal, ExecJsonJournalError};
