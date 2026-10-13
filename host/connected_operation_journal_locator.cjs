'use strict';

const INDEX_SCHEMA = 'commons.connected_operation_journal_index/v1';
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const DEFAULTS = Object.freeze({max_entries: 10000, max_index_bytes: 8388608,
  max_command_bytes: 48000});

class OperationJournalLocatorError extends Error {
  constructor(message, progress, cause) {
    super(message);
    this.name = 'OperationJournalLocatorError';
    this.progress = {...progress};
    this.cause = cause;
  }
}

function utf8Bytes(text) {
  let bytes = 0;
  for (const char of text) {
    const cp = char.codePointAt(0);
    if (cp >= 0xd800 && cp <= 0xdfff) throw new TypeError('Path contains unpaired UTF-16');
    bytes += cp < 128 ? 1 : cp < 2048 ? 2 : cp < 65536 ? 3 : 4;
  }
  return bytes;
}

const pythonJson = value => 'json.loads(' + JSON.stringify(JSON.stringify(value)) + ')';
const validIdentity = value => object(value) && Number.isSafeInteger(value.file_bytes)
  && value.file_bytes >= 0 && ['device', 'inode', 'mtime_ns'].every(key =>
    typeof value[key] === 'string' && /^[0-9]+$/.test(value[key]));
const sameIdentity = (left, right) => validIdentity(left) && validIdentity(right)
  && ['device', 'inode', 'mtime_ns', 'file_bytes'].every(key => left[key] === right[key]);

/**
 * Explicit read-only observation of the highest completed index sequence
 * present at one stable local directory-listing boundary. Never resume an effect.
 */
async function observeOperationJournalLocator(execCommand, reader, options) {
  const progress = {phase: 'validate', provider_operations: 0};
  try {
    if (typeof execCommand !== 'function' || !object(reader) || typeof reader.read !== 'function'
        || !object(options)) throw new TypeError('Supply execCommand, existing reader and options');
    for (const key of Object.keys(options)) {
      if (key !== 'prefix' && !own(DEFAULTS, key)) throw new TypeError('Unknown locator option: ' + key);
    }
    const prefix = options.prefix, directory = reader.directory?.replace(/\/+$/, '');
    if (typeof prefix !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,59}$/.test(prefix)
        || typeof directory !== 'string' || !directory.startsWith('/') || directory === '/'
        || directory.includes('\0') || utf8Bytes(directory) > 4096) {
      throw new TypeError('Supply a plain prefix and bounded absolute reader directory');
    }
    const limits = {...DEFAULTS}, bounds = {max_entries: [1, 1000000],
      max_index_bytes: [1, 67108864], max_command_bytes: [8192, 60000]};
    for (const key of Object.keys(DEFAULTS)) {
      if (!own(options, key)) continue;
      const value = options[key], [min, max] = bounds[key];
      if (!Number.isSafeInteger(value) || value < min || value > max) {
        throw new RangeError(key + ' must be an integer from ' + min + ' to ' + max);
      }
      limits[key] = value;
    }
    progress.directory = directory;
    progress.prefix = prefix;
    const program = [
      'from pathlib import Path',
      'import json, os, stat, hashlib, re',
      'def identity(value):',
      '    return {"device": str(value.st_dev), "inode": str(value.st_ino), "mtime_ns": str(value.st_mtime_ns), "file_bytes": value.st_size}',
      'root = Path(' + pythonJson(directory) + ')',
      'prefix = ' + pythonJson(prefix),
      'before_directory = os.stat(root)',
      'if not stat.S_ISDIR(before_directory.st_mode): raise TypeError("Journal directory is not a directory")',
      'pattern = re.compile(re.escape(prefix) + r"-i([0-9]{6})\\.json\\Z")',
      'entries = 0',
      'candidates = 0',
      'selected = None',
      'with os.scandir(root) as listing:',
      '    for entry in listing:',
      '        entries += 1',
      '        if entries > ' + limits.max_entries + ': raise ValueError("Directory exceeds max_entries")',
      '        match = pattern.fullmatch(entry.name)',
      '        if match is None: continue',
      '        sequence = int(match.group(1))',
      '        if sequence < 1 or sequence > 100000: raise ValueError("Matching index sequence is outside producer bounds")',
      '        observed = entry.stat(follow_symlinks=False)',
      '        if not stat.S_ISREG(observed.st_mode): raise TypeError("Matching index is not a regular file")',
      '        candidates += 1',
      '        if selected is None or sequence > selected["sequence"]:',
      '            selected = {"name": entry.name[:-5], "sequence": sequence, "identity": identity(observed)}',
      'if selected is None: raise ValueError("No completed matching journal index observed")',
      'path = root / (selected["name"] + ".json")',
      'with path.open("rb") as source:',
      '    before_file = os.fstat(source.fileno())',
      '    if identity(before_file) != selected["identity"]: raise ValueError("Selected index changed after listing")',
      '    if before_file.st_size > ' + limits.max_index_bytes + ': raise ValueError("Index exceeds max_index_bytes")',
      '    digest = hashlib.sha256()',
      '    for block in iter(lambda: source.read(65536), b""): digest.update(block)',
      '    after_file = os.fstat(source.fileno())',
      '    if identity(before_file) != identity(after_file): raise ValueError("Index changed during digest observation")',
      'after_directory = os.stat(root)',
      'if identity(before_directory) != identity(after_directory): raise ValueError("Journal directory changed during observation")',
      'print(json.dumps({"name": selected["name"], "sequence": selected["sequence"], "path": str(path),',
      '    "identity": selected["identity"], "sha256": digest.hexdigest(), "directory_identity": identity(before_directory),',
      '    "directory_entries": entries, "matching_indexes": candidates}))'
    ].join('\n');
    const cmd = "python3 - <<'CONNECTED_OPERATION_JOURNAL_LOCATOR_PY'\n" + program +
      '\nCONNECTED_OPERATION_JOURNAL_LOCATOR_PY';
    const commandBytes = utf8Bytes(cmd);
    if (commandBytes > limits.max_command_bytes) throw new RangeError('Complete command exceeds max_command_bytes');
    progress.phase = 'observe_directory';
    progress.command_bytes = commandBytes;
    const execution = await execCommand({cmd, shell: 'bash', login: false,
      max_output_tokens: 5000, yield_time_ms: 10000});
    if (!object(execution) || execution.exit_code !== 0 || execution.session_id !== undefined
        || typeof execution.output !== 'string') {
      const error = new Error('Directory observation did not return completed output');
      error.execution_result = execution;
      throw error;
    }
    let observed;
    try { observed = JSON.parse(execution.output); }
    catch (cause) {
      const error = new Error('Directory observation lacks complete JSON output');
      error.execution_result = execution;
      error.cause = cause;
      throw error;
    }
    if (!object(observed) || !Number.isSafeInteger(observed.sequence)
        || observed.sequence < 1 || observed.sequence > 100000
        || observed.name !== prefix + '-i' + String(observed.sequence).padStart(6, '0')
        || observed.path !== directory + '/' + observed.name + '.json'
        || !validIdentity(observed.identity) || observed.identity.file_bytes > limits.max_index_bytes
        || !validIdentity(observed.directory_identity) || !/^[0-9a-f]{64}$/.test(observed.sha256 ?? '')
        || !Number.isSafeInteger(observed.directory_entries) || observed.directory_entries < 1
        || observed.directory_entries > limits.max_entries || !Number.isSafeInteger(observed.matching_indexes)
        || observed.matching_indexes < 1 || observed.matching_indexes > observed.directory_entries) {
      throw new TypeError('Directory observation lacks exact bounded locator/coverage metadata');
    }
    progress.phase = 'read_index';
    progress.observed = observed;
    const restored = await reader.read(observed.name);
    if (!object(restored) || restored.status !== 'read' || !object(restored.source)
        || restored.source.path !== observed.path || restored.source.file_bytes !== observed.identity.file_bytes
        || restored.source.sha256 !== observed.sha256 || restored.source.complete_sha256_verified !== true
        || !sameIdentity(restored.source.identity, observed.identity)) {
      throw new TypeError('Restored index differs from the observed complete file identity/digest');
    }
    const index = restored.value;
    if (!object(index) || index.schema !== INDEX_SCHEMA || index.prefix !== prefix
        || index.directory !== directory || index.index_name !== observed.name
        || index.last_sequence !== observed.sequence || typeof index.operation_id !== 'string'
        || index.operation_id.length < 1 || index.operation_id.length > 256) {
      throw new TypeError('Observed index lacks matching operation journal metadata');
    }
    return {schema: 'commons.connected_operation_journal_locator/v1', status: 'observed',
      index_locator: {name: observed.name, path: observed.path,
        file_bytes: observed.identity.file_bytes, sha256: observed.sha256,
        operation_id: index.operation_id, prefix, sequence: observed.sequence},
      observation: observed, command_bytes: commandBytes,
      scope: 'highest_matching_sequence_at_stable_local_listing; producer_acknowledgement_and_provider_outcome_not_assessed',
      execution_response: execution, retained_index: restored};
  } catch (error) {
    throw new OperationJournalLocatorError(error?.message ?? String(error), progress, error);
  }
}

module.exports = {observeOperationJournalLocator, OperationJournalLocatorError};
