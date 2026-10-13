'use strict';

// Caller-owned private custody only. No discovery, transport, retry or routing.
const MAX_CALLS = 1000;
const MAX_REQUEST_NODES = 100000;
const MAX_REQUEST_CHARS = 16 * 1024 * 1024;
const MAX_REQUEST_DEPTH = 64;
const MAX_ERROR_CHARS = 2048;
const MAX_CAUSE_DEPTH = 3;

function object(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError(label + ' must be an object');
  }
  return value;
}

function label(value, field, limit) {
  if (typeof value !== 'string' || !value.trim() || value.length > limit
      || /[\x00-\x1f\x7f]/.test(value)) {
    throw new TypeError(field + ' must be bounded nonempty text without control characters');
  }
  return value;
}

// Copy the actual binding arguments before awaiting retention. Reject values
// JSON would silently drop or coerce; never mutate the caller's original object.
function requestSnapshot(input) {
  let nodes = 0;
  let chars = 0;
  const active = new Set();
  function charge(length) {
    chars += length;
    if (chars > MAX_REQUEST_CHARS) throw new RangeError('Request text bound exceeded');
  }
  function copy(value, depth) {
    if (++nodes > MAX_REQUEST_NODES || depth > MAX_REQUEST_DEPTH) {
      throw new RangeError('Request structure bound exceeded');
    }
    if (value === null || typeof value === 'boolean') return value;
    if (typeof value === 'string') { charge(value.length); return value; }
    if (typeof value === 'number') {
      if (!Number.isFinite(value) || Object.is(value, -0)) {
        throw new TypeError('Request numbers must be finite JSON values without negative zero');
      }
      return value;
    }
    if (!value || typeof value !== 'object') {
      throw new TypeError('Request values must be plain JSON; undefined is not silently omitted');
    }
    if (active.has(value)) throw new TypeError('Request contains a cycle');
    const array = Array.isArray(value);
    const proto = Object.getPrototypeOf(value);
    if (!array && proto !== Object.prototype && proto !== null) {
      throw new TypeError('Request objects must have a plain or null prototype');
    }
    const keys = Reflect.ownKeys(value);
    if (keys.length > MAX_REQUEST_NODES) throw new RangeError('Request property bound exceeded');
    if (keys.some(key => typeof key !== 'string')) {
      throw new TypeError('Request symbol keys are unsupported');
    }
    if (array && (value.length > MAX_REQUEST_NODES
        || keys.length !== value.length + 1
        || keys.some(key => key !== 'length'
          && (!/^(0|[1-9][0-9]*)$/.test(key) || Number(key) >= value.length)))) {
      throw new TypeError('Request arrays must be dense and have no extra properties');
    }
    active.add(value);
    const output = array ? [] : Object.create(null);
    for (const key of keys) {
      if (array && key === 'length') continue;
      const descriptor = Object.getOwnPropertyDescriptor(value, key);
      if (!descriptor || !descriptor.enumerable || !('value' in descriptor)) {
        throw new TypeError('Request properties must be enumerable data properties');
      }
      charge(key.length);
      output[key] = copy(descriptor.value, depth + 1);
    }
    active.delete(value);
    return Object.freeze(output);
  }
  return copy(input, 0);
}

function readField(value, key) {
  try {
    const field = value[key];
    if (field === undefined) return {state: 'absent_or_undefined'};
    if (field === null) return {state: 'null'};
    return {state: 'present', value: field};
  } catch (_) {
    return {state: 'unreadable'};
  }
}

function errorDescription(error) {
  const seen = new Set();
  function textField(field) {
    if (field.state !== 'present') return {value: null, state: field.state};
    if (typeof field.value !== 'string') return {value: null, state: 'non_string'};
    return {
      value: field.value.slice(0, MAX_ERROR_CHARS),
      state: 'string',
      chars: field.value.length,
      truncated: field.value.length > MAX_ERROR_CHARS,
    };
  }
  function visit(value, depth) {
    const type = value === null ? 'null' : typeof value;
    if ((type !== 'object' && type !== 'function') || value === null) {
      const message = ['string', 'number', 'boolean'].includes(type)
        ? String(value) : null;
      return {
        thrown_type: type, name: null, name_state: 'non_error_value',
        message: message === null ? null : message.slice(0, MAX_ERROR_CHARS),
        message_state: message === null ? 'unavailable' : 'primitive',
        message_chars: message === null ? null : message.length,
        message_truncated: message !== null && message.length > MAX_ERROR_CHARS,
        cause_state: 'not_applicable', cause: null,
      };
    }
    if (seen.has(value)) return {thrown_type: type, cycle: true};
    seen.add(value);
    const name = textField(readField(value, 'name'));
    const message = textField(readField(value, 'message'));
    const result = {
      thrown_type: type,
      name: name.value, name_state: name.state,
      name_chars: name.chars ?? null, name_truncated: name.truncated ?? false,
      message: message.value, message_state: message.state,
      message_chars: message.chars ?? null, message_truncated: message.truncated ?? false,
      cause_state: 'absent_or_undefined', cause: null,
    };
    const cause = readField(value, 'cause');
    result.cause_state = cause.state;
    if (cause.state === 'present') {
      if (depth >= MAX_CAUSE_DEPTH) result.cause_state = 'depth_limit';
      else if (seen.has(cause.value)) result.cause_state = 'cycle';
      else {
        result.cause_state = 'captured';
        result.cause = visit(cause.value, depth + 1);
      }
    }
    return result;
  }
  return visit(error, 0);
}

class ConnectedOperationRecordingError extends Error {
  constructor(message, diagnostic, privateValues) {
    super(message);
    this.name = 'ConnectedOperationRecordingError';
    this.diagnostic = diagnostic;
    // These original values are private recovery handles, not JSON diagnostics.
    for (const [key, value] of Object.entries(privateValues)) {
      Object.defineProperty(this, key, {value, enumerable: false});
    }
  }

  toJSON() {
    return {name: this.name, message: this.message, ...this.diagnostic};
  }
}

function createConnectedOperationRecorder(options) {
  object(options, 'options');
  for (const key of Object.keys(options)) {
    if (!['operation_id', 'entry_prefix', 'retain', 'max_calls', 'serializable_errors', 'observe_timestamps'].includes(key)) {
      throw new TypeError('Unknown recorder option: ' + key);
    }
  }
  const operationId = label(options.operation_id, 'operation_id', 256);
  const prefix = label(options.entry_prefix, 'entry_prefix', 200);
  if (typeof options.retain !== 'function') throw new TypeError('retain must be a function');
  const maxCalls = options.max_calls ?? 128;
  if (!Number.isSafeInteger(maxCalls) || maxCalls < 1 || maxCalls > MAX_CALLS) {
    throw new RangeError('max_calls must be an integer in 1..' + MAX_CALLS);
  }
  if (options.serializable_errors !== undefined
      && typeof options.serializable_errors !== 'boolean') {
    throw new TypeError('serializable_errors must be boolean');
  }
  const serializableErrors = options.serializable_errors === true;
  if (options.observe_timestamps !== undefined
      && typeof options.observe_timestamps !== 'boolean') {
    throw new TypeError('observe_timestamps must be boolean');
  }
  const observeTimestamps = options.observe_timestamps === true;
  const retain = options.retain;
  const directoryKey = prefix + '_directory';
  const entries = [];
  let retentionTail = Promise.resolve();

  function observeTimestamp(entry, event) {
    if (!observeTimestamps) return;
    let at = null;
    let status = 'unavailable';
    try {
      at = new Date().toISOString();
      status = 'observed';
    } catch (_) {
      // Clock failure must not change invocation count or its outcome.
    }
    entry.timestamps[event + '_at'] = at;
    entry.timestamps[event + '_status'] = status;
  }

  function metadata(entry) {
    return {
      call_id: entry.call_id, kind: entry.kind, name: entry.name,
      request_role: entry.kind === 'binding'
        ? 'binding_arguments' : 'caller_local_input_descriptor',
      phase: entry.phase,
      invocation_started: entry.invocation_started,
      settlement: entry.settlement,
      ...(observeTimestamps ? {timestamps: {...entry.timestamps}} : {}),
      provider_outcome: entry.kind === 'binding' ? 'not_assessed' : 'not_applicable',
      keys: {...entry.keys},
      retention: {...entry.retention},
      custody_failure: entry.custody_failure ? {...entry.custody_failure} : null,
    };
  }

  function directory() {
    return {
      schema: 'commons.connected_operation_directory/v1',
      operation_id: operationId, entry_prefix: prefix, directory_key: directoryKey,
      assigned_count: entries.length, max_calls: maxCalls,
      index_order: 'synchronous_assignment_not_completion',
      entry_key_pattern: prefix + '_call_<id>_entry',
      request_key_pattern: prefix + '_call_<id>_request',
      result_key_pattern: prefix + '_call_<id>_result',
      error_key_pattern: prefix + '_call_<id>_error',
      retention_scope: 'injected_callback_acknowledgement; durability_not_established',
    };
  }

  function snapshot() {
    return {...directory(), entries: entries.map(metadata)};
  }

  function diagnostic(entry, phase, error, extra = {}) {
    return {
      schema: 'commons.connected_operation_error/v1',
      operation_id: operationId, entry_prefix: prefix, directory_key: directoryKey,
      call: entry ? metadata(entry) : null,
      phase, error: errorDescription(error), ...extra,
    };
  }

  async function put(entry, slot, key, value, privateOutcome = {}) {
    entry.retention[slot] = 'pending';
    const queued = retentionTail.then(() => retain(key, value));
    // A rejected callback affects its own call, not future queue execution.
    retentionTail = queued.then(() => undefined, () => undefined);
    try {
      await queued;
      entry.retention[slot] = 'acknowledged';
    } catch (error) {
      entry.retention[slot] = 'not_acknowledged';
      entry.custody_failure = {slot, key};
      const detail = diagnostic(entry, 'retention', error, {
        failed_retention_key: key,
        returned_value_available: privateOutcome.returned === true,
        original_error_available: privateOutcome.error_available === true,
        original_error_phase: privateOutcome.error_phase ?? null,
        original_error: privateOutcome.error_available === true
          ? errorDescription(privateOutcome.error) : null,
      });
      throw new ConnectedOperationRecordingError(
        'Retention was not acknowledged for ' + key + '; invocation is not repeated',
        detail,
        {cause: error, retention_error: error,
          ...(privateOutcome.returned === true ? {returned_value: privateOutcome.value} : {}),
          ...(privateOutcome.error_available === true ? {original_error: privateOutcome.error} : {})},
      );
    }
  }

  async function saveEntry(entry, privateOutcome) {
    const record = metadata(entry);
    // A record cannot acknowledge its own persistence. The returned snapshot
    // reports callback acknowledgement; the saved entry records other slots.
    delete record.retention.entry;
    if (record.phase === 'invocation_intent') record.invocation_started = null;
    await put(entry, 'entry', entry.keys.entry, record, privateOutcome);
  }

  function rethrow(error, entry, phase) {
    if (!serializableErrors) throw error;
    throw new ConnectedOperationRecordingError(
      'Recorded ' + phase + (entry ? ' in ' + entry.name : ''),
      diagnostic(entry, phase, error),
      {cause: error, original_error: error},
    );
  }

  async function finishThrown(entry, error, phase) {
    entry.phase = phase;
    entry.settlement = entry.invocation_started === true ? 'threw' : 'not_invoked';
    const outcome = {error_available: true, error, error_phase: phase};
    await put(entry, 'error', entry.keys.error, errorDescription(error), outcome);
    await saveEntry(entry, outcome);
    rethrow(error, entry, phase);
  }

  async function run(descriptor, invoke) {
    let entry;
    try {
      object(descriptor, 'descriptor');
      for (const key of Object.keys(descriptor)) {
        if (!['kind', 'name', 'request'].includes(key)) {
          throw new TypeError('Unknown operation descriptor field: ' + key);
        }
      }
      if (!['binding', 'local'].includes(descriptor.kind)) {
        throw new TypeError('kind must be binding or local');
      }
      const name = label(descriptor.name, 'name', 256);
      if (typeof invoke !== 'function') throw new TypeError('invoke must be a function');
      if (!Object.prototype.hasOwnProperty.call(descriptor, 'request')) {
        throw new TypeError('request must be supplied explicitly');
      }
      if (entries.length >= maxCalls) throw new RangeError('Recorder call bound reached');
      const callId = entries.length + 1;
      const stem = prefix + '_call_' + callId;
      entry = {
        call_id: callId, kind: descriptor.kind, name,
        phase: 'assigned', invocation_started: false, settlement: 'not_observed',
        ...(observeTimestamps ? {timestamps: {
          basis: 'caller_wall_clock_not_provider_native',
          format: 'ISO_8601_UTC',
          invocation_at: null, invocation_status: 'not_observed',
          settlement_at: null, settlement_status: 'not_observed',
        }} : {}),
        keys: {request: stem + '_request', result: stem + '_result',
          error: stem + '_error', entry: stem + '_entry'},
        retention: {directory: 'not_attempted', request: 'not_attempted',
          result: 'not_attempted', error: 'not_attempted', entry: 'not_attempted'},
        custody_failure: null,
      };
      entries.push(entry);
    } catch (error) {
      rethrow(error, null, 'recorder_validation');
    }

    // Snapshot before the first await, including a possibly asynchronous retain.
    let request;
    let snapshotError;
    let snapshotFailed = false;
    try {
      request = requestSnapshot(descriptor.request);
    } catch (error) {
      snapshotError = error;
      snapshotFailed = true;
    }
    await put(entry, 'directory', directoryKey, directory(), snapshotFailed
      ? {error_available: true, error: snapshotError, error_phase: 'request_snapshot'} : {});
    if (snapshotFailed) return finishThrown(entry, snapshotError, 'request_snapshot');
    await put(entry, 'request', entry.keys.request, Object.freeze({
      schema: 'commons.connected_operation_request/v1',
      operation_id: operationId, call_id: entry.call_id,
      kind: entry.kind, name: entry.name, request,
    }));
    entry.phase = 'invocation_intent';
    // The saved intent does not establish whether the callback/provider ran.
    await saveEntry(entry);
    entry.invocation_started = true;
    entry.phase = 'invoking';

    let value;
    try {
      observeTimestamp(entry, 'invocation');
      value = await invoke(request);
    } catch (error) {
      observeTimestamp(entry, 'settlement');
      return finishThrown(entry, error, 'invocation_threw');
    }
    observeTimestamp(entry, 'settlement');
    entry.phase = 'returned';
    entry.settlement = 'returned';
    const outcome = {returned: true, value};
    // The full result is retained before any caller receives or inspects it.
    // MCP isError and other provider fields are deliberately not interpreted.
    await put(entry, 'result', entry.keys.result, value, outcome);
    await saveEntry(entry, outcome);
    return value;
  }

  function wrapBindings(bindings) {
    object(bindings, 'bindings');
    const wrapped = {};
    for (const name of Object.keys(bindings)) {
      label(name, 'binding name', 256);
      const binding = bindings[name];
      if (typeof binding !== 'function') throw new TypeError('Binding must be a function: ' + name);
      Object.defineProperty(wrapped, name, {
        enumerable: true,
        value: args => run({kind: 'binding', name, request: args},
          snapshotArgs => binding.call(bindings, snapshotArgs)),
      });
    }
    return Object.freeze(wrapped);
  }

  return Object.freeze({run, wrapBindings, snapshot});
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {createConnectedOperationRecorder, ConnectedOperationRecordingError};
}
