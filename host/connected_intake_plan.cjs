'use strict';

/*
 * Pure, caller-controlled intake planning. No tools, clocks, timers, transport,
 * persistent state, provider classification, retries, or request rewriting.
 * Caller-reported holds remain separate from a caller-chosen temporary pause.
 */

const LIMITS = Object.freeze({
  pending: 128,
  held: 512,
  depth: 16,
  nodesPerRequest: 4096,
  requestCharacters: 65536,
  totalRequestCharacters: 1048576,
  operationCharacters: 256,
  idCharacters: 128,
  pauseLabelCharacters: 256
});

function objectFields(value, allowed, where) {
  if (value === null || typeof value !== 'object' ||
      (Object.getPrototypeOf(value) !== Object.prototype &&
       Object.getPrototypeOf(value) !== null)) {
    throw new TypeError(where + ' must be a plain object');
  }
  if (Object.getOwnPropertySymbols(value).length) {
    throw new TypeError(where + ' must not have symbol keys');
  }
  const fields = Object.getOwnPropertyDescriptors(value);
  for (const key of Object.keys(fields)) {
    if (!allowed.includes(key)) throw new TypeError(where + ': unknown field ' + key);
    if (!Object.prototype.hasOwnProperty.call(fields[key], 'value') ||
        !fields[key].enumerable) {
      throw new TypeError(where + ' must contain enumerable data properties only');
    }
  }
  return fields;
}

function field(fields, name) {
  return Object.prototype.hasOwnProperty.call(fields, name) ? fields[name].value : undefined;
}

function boundedString(value, limit, where) {
  if (typeof value !== 'string' || value.length === 0 || value.length > limit) {
    throw new TypeError(where + ' must be a nonempty bounded string');
  }
  return value;
}

function nonnegativeInteger(value, where) {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new TypeError(where + ' must be a nonnegative safe integer');
  }
  return value;
}

function denseArray(value, limit, where) {
  if (!Array.isArray(value) || value.length > limit ||
      Object.getOwnPropertySymbols(value).length) {
    throw new TypeError(where + ' must be a bounded dense array');
  }
  const descriptors = Object.getOwnPropertyDescriptors(value);
  if (Object.keys(descriptors).length !== value.length + 1) {
    throw new TypeError(where + ' must not contain extra properties or holes');
  }
  const out = [];
  for (let i = 0; i < value.length; i++) {
    const item = descriptors[String(i)];
    if (!item || !Object.prototype.hasOwnProperty.call(item, 'value') || !item.enumerable) {
      throw new TypeError(where + ' must contain enumerable data elements only');
    }
    out.push(item.value);
  }
  return out;
}

// This is equality of plain JSON values, not URL/query normalization. Object
// member order is ignored; arrays, strings, omitted members, and null are not.
function canonicalJSON(value, where) {
  let nodes = 0;
  let characters = 0;
  const chunks = [];
  const ancestors = new Set();
  function append(chunk) {
    characters += chunk.length;
    if (characters > LIMITS.requestCharacters) {
      throw new RangeError(where + ' exceeds the character budget');
    }
    chunks.push(chunk);
  }
  function encode(current, depth) {
    nodes++;
    if (nodes > LIMITS.nodesPerRequest || depth > LIMITS.depth) {
      throw new RangeError(where + ' exceeds the structural budget');
    }
    if (current === null) append('null');
    else if (typeof current === 'string') {
      if (current.length > LIMITS.requestCharacters) {
        throw new RangeError(where + ' exceeds the character budget');
      }
      append(JSON.stringify(current));
    } else if (typeof current === 'boolean') append(current ? 'true' : 'false');
    else if (typeof current === 'number') {
      if (!Number.isFinite(current)) throw new TypeError(where + ' requires finite JSON numbers');
      // JSON transport represents both 0 and -0 as 0.
      append(JSON.stringify(current));
    } else {
      if (typeof current !== 'object') throw new TypeError(where + ' requires plain JSON values');
      if (ancestors.has(current)) throw new TypeError(where + ' must not contain a cycle');
      ancestors.add(current);
      if (Array.isArray(current)) {
        const entries = denseArray(current, LIMITS.nodesPerRequest, where);
        append('[');
        entries.forEach((item, i) => {
          if (i) append(',');
          encode(item, depth + 1);
        });
        append(']');
      } else {
        if (Object.getPrototypeOf(current) !== Object.prototype &&
            Object.getPrototypeOf(current) !== null) {
          throw new TypeError(where + ' requires plain JSON objects');
        }
        if (Object.getOwnPropertySymbols(current).length) {
          throw new TypeError(where + ' must not have symbol keys');
        }
        const descriptors = Object.getOwnPropertyDescriptors(current);
        const keys = Object.keys(descriptors).sort();
        if (keys.length > LIMITS.nodesPerRequest) {
          throw new RangeError(where + ' exceeds the member budget');
        }
        append('{');
        keys.forEach((key, i) => {
          const descriptor = descriptors[key];
          if (!Object.prototype.hasOwnProperty.call(descriptor, 'value') || !descriptor.enumerable) {
            throw new TypeError(where + ' requires enumerable data properties');
          }
          if (key.length > LIMITS.requestCharacters) {
            throw new RangeError(where + ' exceeds the key budget');
          }
          if (i) append(',');
          append(JSON.stringify(key));
          append(':');
          encode(descriptor.value, depth + 1);
        });
        append('}');
      }
      ancestors.delete(current);
    }
  }
  encode(value, 0);
  return chunks.join('');
}
/**
 * Plan one bounded batch from caller-supplied pending requests and exact holds.
 * Input: {pending, held, observed_at_ms, local_pause?, max_selected?}.
 * Request: {operation, args, id?}; args must be a plain JSON object.
 * A selected index is advisory. The caller owns dispatch and fresh state.
 */
function planConnectedIntakeBatch(input) {
  const fields = objectFields(input,
    ['pending', 'held', 'observed_at_ms', 'local_pause', 'max_selected'], 'input');
  const observedAt = nonnegativeInteger(field(fields, 'observed_at_ms'), 'observed_at_ms');
  const maximum = Object.prototype.hasOwnProperty.call(fields, 'max_selected')
    ? field(fields, 'max_selected') : 1;
  if (!Number.isSafeInteger(maximum) || maximum < 1 || maximum > LIMITS.pending) {
    throw new TypeError('max_selected must be an integer from 1 through ' + LIMITS.pending);
  }
  const pending = denseArray(field(fields, 'pending'), LIMITS.pending, 'pending');
  const held = denseArray(field(fields, 'held'), LIMITS.held, 'held');
  let pause = null;
  if (Object.prototype.hasOwnProperty.call(fields, 'local_pause') &&
      field(fields, 'local_pause') !== null) {
    const pauseFields = objectFields(field(fields, 'local_pause'), ['until_ms', 'label'], 'local_pause');
    const until = nonnegativeInteger(field(pauseFields, 'until_ms'), 'local_pause.until_ms');
    const label = Object.prototype.hasOwnProperty.call(pauseFields, 'label')
      ? boundedString(field(pauseFields, 'label'), LIMITS.pauseLabelCharacters, 'local_pause.label') : null;
    pause = {
      until_ms: until,
      label,
      state: until > observedAt ? 'active' : 'elapsed',
      until_minus_observed_ms: until - observedAt,
      provenance: 'caller_chosen',
      provider_reset: 'not_inferred'
    };
  }
  let charged = 0;
  function request(entry, where) {
    const entryFields = objectFields(entry, ['operation', 'args', 'id'], where);
    const operation = boundedString(field(entryFields, 'operation'),
      LIMITS.operationCharacters, where + '.operation');
    const args = field(entryFields, 'args');
    if (args === null || typeof args !== 'object' || Array.isArray(args) ||
        (Object.getPrototypeOf(args) !== Object.prototype && Object.getPrototypeOf(args) !== null)) {
      throw new TypeError(where + '.args must be a plain JSON object');
    }
    const id = Object.prototype.hasOwnProperty.call(entryFields, 'id')
      ? boundedString(field(entryFields, 'id'), LIMITS.idCharacters, where + '.id') : null;
    const key = '[' + JSON.stringify(operation) + ',' + canonicalJSON(args, where + '.args') + ']';
    if (key.length > LIMITS.requestCharacters) {
      throw new RangeError(where + ' exceeds the request character budget');
    }
    charged += key.length;
    if (charged > LIMITS.totalRequestCharacters) {
      throw new RangeError('input exceeds the total request character budget');
    }
    return {operation, id, key};
  }
  // Read and validate every descriptor before producing a selection.
  const heldRequests = held.map((entry, i) => request(entry, 'held[' + i + ']'));
  const pendingRequests = pending.map((entry, i) => request(entry, 'pending[' + i + ']'));
  const holdsByKey = new Map();
  heldRequests.forEach((entry, i) => {
    const existing = holdsByKey.get(entry.key);
    if (existing) existing.count++;
    else holdsByKey.set(entry.key, {index: i, count: 1});
  });
  const firstPending = new Map();
  const selected = [];
  const counts = {
    selected: 0,
    excluded_exact_hold: 0,
    duplicate_pending: 0,
    deferred_local_pause: 0,
    deferred_batch_limit: 0
  };
  const records = pendingRequests.map((entry, index) => {
    const matchingHold = holdsByKey.get(entry.key);
    const duplicateOf = firstPending.has(entry.key) ? firstPending.get(entry.key) : null;
    if (duplicateOf === null) firstPending.set(entry.key, index);
    let disposition;
    if (matchingHold) disposition = 'excluded_exact_hold';
    else if (duplicateOf !== null) disposition = 'duplicate_pending';
    else if (pause && pause.state === 'active') disposition = 'deferred_local_pause';
    else if (selected.length >= maximum) disposition = 'deferred_batch_limit';
    else {
      disposition = 'selected';
      selected.push(index);
    }
    counts[disposition]++;
    return {
      source_index: index,
      id: entry.id,
      operation: entry.operation,
      disposition,
      duplicate_of_source_index: duplicateOf,
      first_matching_hold_source_index: matchingHold ? matchingHold.index : null,
      matching_hold_records: matchingHold ? matchingHold.count : 0
    };
  });
  return {
    schema: 'commons.connected_intake_plan/v1',
    observed_at_ms: observedAt,
    local_pause: pause,
    max_selected: maximum,
    pending_records: pendingRequests.length,
    held_records: heldRequests.length,
    unique_held_requests: holdsByKey.size,
    held_provenance: 'caller_reported_not_authenticated',
    equality: 'operation_and_structural_plain_json_args',
    selected_indices: selected,
    counts,
    records,
    input_request_characters: charged,
    request_arguments_included: false,
    state_persisted: false,
    requests_dispatched: 0,
    provider_reset_inferred: false
  };
}

module.exports = {planConnectedIntakeBatch};
