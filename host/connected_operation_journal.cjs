'use strict';

const RECORD_SCHEMA = 'commons.connected_operation_journal_record/v1';
const INDEX_SCHEMA = 'commons.connected_operation_journal_index/v1';
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const basename = value => typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9._-]{0,59}$/.test(value);
const digest = value => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
const keyLabel = value => typeof value === 'string' && value.length > 0 && value.length <= 2048;
const absoluteDirectory = value => typeof value === 'string' && value.startsWith('/')
  && !/^\/+$/ .test(value) && !value.includes('\0');

class OperationJournalError extends Error {
  constructor(message, progress, cause) {
    super(message);
    this.name = 'OperationJournalError';
    this.progress = {...progress};
    this.cause = cause;
  }
}

function hashJson(sha256Utf8, value) {
  const serialized = JSON.stringify(value);
  if (serialized === undefined) throw new TypeError('Journal value must serialize to JSON');
  const measured = sha256Utf8(serialized + '\n');
  if (!object(measured) || !Number.isSafeInteger(measured.bytes) || measured.bytes < 1
      || !digest(measured.sha256)) throw new TypeError('sha256Utf8 lacks exact JSON bytes/digest');
  return measured;
}

function receiptFor(receipt, name, path, measured) {
  if (!object(receipt) || receipt.status !== 'written' || receipt.name !== name
      || receipt.path !== path || receipt.file_bytes !== measured.bytes) {
    const error = new TypeError('Writer did not acknowledge the exact named JSON file/byte count');
    error.writer_receipt = receipt;
    throw error;
  }
  return {name, path, file_bytes: measured.bytes, sha256: measured.sha256};
}

/**
 * Fresh append-only retention backend for the existing operation recorder.
 * Supply the existing JSON writer and SHA256 helper. No provider dispatch,
 * credentials, filesystem enumeration, overwrite, retry, or implicit resume.
 */
function createOperationJournal(writer, sha256Utf8, options) {
  if (!object(writer) || typeof writer.write !== 'function'
      || !absoluteDirectory(writer.directory) || typeof sha256Utf8 !== 'function') {
    throw new TypeError('Supply a named JSON writer with directory and sha256Utf8');
  }
  if (!object(options)) throw new TypeError('options must be an object');
  for (const name of Object.keys(options)) {
    if (!['operation_id', 'prefix', 'max_records'].includes(name)) {
      throw new TypeError('Unknown operation journal option: ' + name);
    }
  }
  const operationId = options.operation_id, prefix = options.prefix;
  if (!keyLabel(operationId) || operationId.length > 256) {
    throw new TypeError('operation_id must be a nonempty label of at most 256 characters');
  }
  if (!basename(prefix)) throw new TypeError('prefix must be a plain basename of at most 60 characters');
  const maxRecords = options.max_records ?? 10000;
  if (!Number.isSafeInteger(maxRecords) || maxRecords < 1 || maxRecords > 100000) {
    throw new RangeError('max_records must be an integer in 1..100000');
  }
  const directory = writer.directory.replace(/\/+$/, '');
  let assigned = 0, acknowledged = 0, latestIndex = null, tail = Promise.resolve();
  const latest = new Map(), failures = [];

  function snapshot() {
    return {schema: 'commons.connected_operation_journal_snapshot/v1',
      operation_id: operationId, prefix, directory, assigned_records: assigned,
      acknowledged_updates: acknowledged, retained_keys: latest.size,
      latest_index: latestIndex ? {...latestIndex} : null,
      entries: Array.from(latest.values(), value => ({...value})),
      failures: failures.map(value => ({...value})),
      scope: 'this_fresh_instance; no_directory_enumeration_or_provider_assessment'};
  }

  function retain(key, value) {
    if (!keyLabel(key)) throw new TypeError('key must be a nonempty label of at most 2048 characters');
    if (assigned >= maxRecords) throw new RangeError('Operation journal exceeds max_records');
    // Freeze ordinary JSON semantics before any await, without mutating the raw input.
    const serialized = JSON.stringify(value);
    if (serialized === undefined) throw new TypeError('Retained value must serialize to JSON');
    const stableValue = JSON.parse(serialized), sequence = ++assigned;
    const suffix = String(sequence).padStart(6, '0');
    const recordName = prefix + '-r' + suffix, indexName = prefix + '-i' + suffix;
    const recordPath = directory + '/' + recordName + '.json';
    const indexPath = directory + '/' + indexName + '.json';
    const progress = {sequence, key, phase: 'write_record', record_name: recordName,
      index_name: indexName, record_write_acknowledged: false,
      index_write_acknowledged: false};
    const write = async () => {
      try {
        const record = {schema: RECORD_SCHEMA, operation_id: operationId,
          sequence, key, value: stableValue};
        const recordHash = hashJson(sha256Utf8, record);
        const recordReceipt = await writer.write(recordName, record);
        progress.record_receipt = recordReceipt;
        const locator = receiptFor(recordReceipt, recordName, recordPath, recordHash);
        progress.record_write_acknowledged = true;
        const entry = {key, sequence, record_name: locator.name, path: locator.path,
          file_bytes: locator.file_bytes, sha256: locator.sha256};
        const candidate = new Map(latest);
        candidate.set(key, entry);
        const index = {schema: INDEX_SCHEMA, operation_id: operationId, prefix,
          directory, index_name: indexName, last_sequence: sequence,
          acknowledged_updates: acknowledged + 1,
          retained_keys: candidate.size, max_records: maxRecords,
          entries: Array.from(candidate.values()),
          scope: 'this_fresh_instance; no_directory_enumeration_or_provider_assessment'};
        progress.phase = 'write_index';
        const indexHash = hashJson(sha256Utf8, index);
        const indexReceipt = await writer.write(indexName, index);
        progress.index_receipt = indexReceipt;
        const indexLocator = receiptFor(indexReceipt, indexName, indexPath, indexHash);
        progress.index_write_acknowledged = true;
        latest.set(key, entry);
        acknowledged++;
        latestIndex = {...indexLocator, operation_id: operationId, prefix, sequence};
        return {record: {...entry}, index: {...latestIndex}};
      } catch (error) {
        failures.push({sequence, key, phase: progress.phase, record_name: recordName,
          index_name: indexName, record_write_acknowledged: progress.record_write_acknowledged,
          index_write_acknowledged: progress.index_write_acknowledged});
        throw new OperationJournalError(error?.message ?? String(error), progress, error);
      }
    };
    const pending = tail.then(write, write);
    tail = pending.catch(() => {});
    return pending;
  }
  return {retain, snapshot, directory, prefix};
}

function requireRecovered(result, locator) {
  if (!object(result) || result.status !== 'read' || !object(result.source)
      || result.source.complete_sha256_verified !== true || result.source.path !== locator.path
      || result.source.file_bytes !== locator.file_bytes || result.source.sha256 !== locator.sha256
      || !own(result, 'value')) {
    throw new TypeError('Recovered file does not match its retained exact locator/digest');
  }
}

function validEntry(entry, directory, prefix, lastSequence) {
  return object(entry) && keyLabel(entry.key) && Number.isSafeInteger(entry.sequence)
    && entry.sequence >= 1 && entry.sequence <= lastSequence
    && entry.record_name === prefix + '-r' + String(entry.sequence).padStart(6, '0')
    && entry.path === directory + '/' + entry.record_name + '.json'
    && Number.isSafeInteger(entry.file_bytes) && entry.file_bytes >= 1 && digest(entry.sha256);
}

/** Restore one selected recorded JSON value; never call or settle its provider. */
async function recoverOperationJournalEntry(reader, indexLocator, key) {
  const progress = {phase: 'validate_locator', key};
  try {
    if (!object(reader) || typeof reader.read !== 'function'
        || !absoluteDirectory(reader.directory) || !object(indexLocator)
        || !basename(indexLocator.prefix) || !keyLabel(indexLocator.operation_id)
        || !Number.isSafeInteger(indexLocator.sequence) || indexLocator.sequence < 1
        || indexLocator.sequence > 100000 || !digest(indexLocator.sha256)
        || !Number.isSafeInteger(indexLocator.file_bytes) || indexLocator.file_bytes < 1
        || !keyLabel(key)) throw new TypeError('Supply reader, complete known index locator and key');
    const directory = reader.directory.replace(/\/+$/, '');
    const expectedName = indexLocator.prefix + '-i' + String(indexLocator.sequence).padStart(6, '0');
    if (indexLocator.name !== expectedName || indexLocator.path !== directory + '/' + expectedName + '.json') {
      throw new TypeError('Index locator must identify the reader directory and exact sequence name');
    }
    progress.phase = 'read_index';
    const restoredIndex = await reader.read(indexLocator.name);
    requireRecovered(restoredIndex, indexLocator);
    const index = restoredIndex.value;
    if (!object(index) || index.schema !== INDEX_SCHEMA
        || index.operation_id !== indexLocator.operation_id || index.prefix !== indexLocator.prefix
        || index.directory !== directory || index.index_name !== expectedName
        || index.last_sequence !== indexLocator.sequence
        || !Number.isSafeInteger(index.max_records) || index.max_records < 1 || index.max_records > 100000
        || index.last_sequence > index.max_records || !Array.isArray(index.entries)
        || index.entries.length !== index.retained_keys || index.entries.length > index.max_records
        || !Number.isSafeInteger(index.acknowledged_updates) || index.acknowledged_updates < 1
        || index.acknowledged_updates > index.last_sequence) {
      throw new TypeError('Recovered index lacks complete matching journal metadata');
    }
    const seen = new Set();
    let selected;
    for (const entry of index.entries) {
      if (!validEntry(entry, directory, index.prefix, index.last_sequence) || seen.has(entry.key)) {
        throw new TypeError('Recovered index has invalid or duplicate key/locator metadata');
      }
      seen.add(entry.key);
      if (entry.key === key) selected = entry;
    }
    if (!selected) throw new TypeError('Selected key is absent from this retained index');
    progress.phase = 'read_record';
    progress.record_name = selected.record_name;
    const restoredRecord = await reader.read(selected.record_name);
    requireRecovered(restoredRecord, selected);
    const record = restoredRecord.value;
    if (!object(record) || record.schema !== RECORD_SCHEMA || record.operation_id !== index.operation_id
        || record.sequence !== selected.sequence || record.key !== key || !own(record, 'value')) {
      throw new TypeError('Recovered record differs from its indexed operation/key/sequence');
    }
    return {schema: 'commons.connected_operation_journal_recovery/v1',
      status: 'recovered', operation_id: index.operation_id, key, sequence: record.sequence,
      index_source: {...restoredIndex.source}, record_source: {...restoredRecord.source},
      value: record.value, scope: 'retained_json_only; provider_outcome_not_assessed'};
  } catch (error) {
    throw new OperationJournalError(error?.message ?? String(error), progress, error);
  }
}

module.exports = {createOperationJournal, recoverOperationJournalEntry, OperationJournalError};
