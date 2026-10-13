'use strict';

// Pure projection of a retained native list_labels response. No provider calls.
const SCHEMA = 'commons.connected_gmail_label_headers/v1';
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const TEXT_FIELDS = ['id', 'name', 'type', 'messageListVisibility', 'labelListVisibility'];
const COUNT_FIELDS = ['messagesTotal', 'messagesUnread', 'threadsTotal', 'threadsUnread'];

function fail(code, message) {
  const error = new TypeError(message);
  error.code = code;
  throw error;
}

function integer(value, fallback, minimum, maximum, name) {
  const actual = value === undefined ? fallback : value;
  if (!Number.isSafeInteger(actual) || actual < minimum || actual > maximum) {
    fail('INVALID_INPUT', name + ' exceeds its integer budget');
  }
  return actual;
}

function projectGmailLabelHeaders(response, options = {}) {
  if (!record(options)) fail('INVALID_INPUT', 'options must be an object');
  const allowed = new Set(['indices', 'max_labels', 'max_field_chars', 'max_total_metadata_chars', 'max_response_chars']);
  for (const key of Object.keys(options)) {
    if (!allowed.has(key)) fail('INVALID_INPUT', 'Unknown option: ' + key);
  }
  const limits = {
    max_input_labels: 10000,
    max_labels: integer(options.max_labels, 20, 0, 500, 'max_labels'),
    max_field_chars: integer(options.max_field_chars, 256, 0, 4096, 'max_field_chars'),
    max_total_metadata_chars: integer(options.max_total_metadata_chars, 4000, 0, 64000, 'max_total_metadata_chars'),
    max_response_chars: integer(options.max_response_chars, 1048576, 256, 8388608, 'max_response_chars'),
  };
  let declaredIndices = null;
  if (own(options, 'indices')) {
    if (!Array.isArray(options.indices) || options.indices.length > limits.max_labels) {
      fail('INVALID_INPUT', 'indices must be an array within max_labels');
    }
    declaredIndices = [];
    const seen = new Set();
    for (let i = 0; i < options.indices.length; i += 1) {
      const index = options.indices[i];
      if (!own(options.indices, i) || !Number.isSafeInteger(index) || index < 0
          || index >= limits.max_input_labels || seen.has(index)) {
        fail('INVALID_INPUT', 'indices must be dense, unique bounded nonnegative integers');
      }
      seen.add(index);
      declaredIndices.push(index);
    }
  }
  const result = {
    schema: SCHEMA, status: 'REFUSED', limits,
    source: {
      scope: 'supplied_native_label_array_only',
      expected_binding: 'mcp__codex_apps__gmail_list_labels',
      response_path: 'structuredContent.labels',
      count_basis: 'literal_reported_label_fields',
      request_filter_application: 'not_verified',
      catalog_completeness: 'not_established',
      account_identity: 'not_inferred',
      observation_time: 'not_inferred',
      label_counts_summed: false,
      provider_calls: 0,
      message_content_selected: false,
    },
    labels: [], coverage: null, issue: null,
  };
  try {
    if (!record(response) || response.isError === true) {
      fail('NATIVE_ERROR', 'Expected a successful retained native response');
    }
    const data = response.structuredContent;
    if (!record(data) || own(data, 'error') || own(data, 'error_code') || !Array.isArray(data.labels)) {
      fail('EXPECTED_NATIVE_LABEL_LIST', 'Expected structuredContent.labels');
    }
    const serialized = JSON.stringify(response);
    if (typeof serialized !== 'string' || serialized.length > limits.max_response_chars) {
      fail('RESPONSE_LIMIT', 'Retained response exceeds the input character budget');
    }
    const labels = data.labels;
    if (labels.length > limits.max_input_labels) fail('SOURCE_LIMIT', 'Too many supplied label rows');
    for (let i = 0; i < labels.length; i += 1) {
      if (!own(labels, i) || !record(labels[i])) fail('EXPECTED_NATIVE_LABEL_LIST', 'Label rows must be dense objects');
    }
    const indices = declaredIndices === null
      ? Array.from({length: Math.min(labels.length, limits.max_labels)}, (_, i) => i)
      : declaredIndices;
    if (indices.some(index => index >= labels.length)) fail('SOURCE_INDEX_RANGE', 'Selected index is absent from the supplied array');
    let remaining = limits.max_total_metadata_chars;
    let selectedChars = 0, returnedChars = 0, omittedTextFields = 0;
    let includedCounts = 0, unavailableCounts = 0;
    for (const index of indices) {
      const value = labels[index];
      const path = 'structuredContent.labels[' + index + ']';
      const row = {source_index: index, source_path: path, fields: {}};
      for (const name of TEXT_FIELDS) {
        const field = {source_path: path + '.' + name};
        row.fields[name] = field;
        if (!own(value, name)) { field.status = 'missing'; continue; }
        if (value[name] === null) { field.status = 'null'; continue; }
        if (typeof value[name] !== 'string') { field.status = 'invalid_type'; continue; }
        const text = value[name];
        selectedChars += text.length;
        field.original_chars = text.length;
        // Return complete IDs and names, never identity-like prefixes.
        if (text.length > limits.max_field_chars || text.length > remaining) {
          field.status = 'limit_exceeded';
          field.returned_chars = 0;
          omittedTextFields += 1;
          continue;
        }
        field.status = 'included';
        field.value = text;
        field.returned_chars = text.length;
        remaining -= text.length;
        returnedChars += text.length;
      }
      for (const name of COUNT_FIELDS) {
        const field = {source_path: path + '.' + name};
        row.fields[name] = field;
        if (!own(value, name)) field.status = 'missing';
        else if (value[name] === null) field.status = 'null';
        else if (!Number.isSafeInteger(value[name]) || value[name] < 0) field.status = 'invalid_count';
        else { field.status = 'included'; field.value = value[name]; }
        if (field.status === 'included') includedCounts += 1;
        else unavailableCounts += 1;
      }
      result.labels.push(row);
    }
    result.coverage = {
      supplied_labels: labels.length,
      selected_indices: indices.slice(),
      returned_labels: indices.length,
      omitted_labels: labels.length - indices.length,
      all_supplied_labels_included: indices.length === labels.length,
      selected_metadata_chars: selectedChars,
      returned_metadata_chars: returnedChars,
      omitted_metadata_chars: selectedChars - returnedChars,
      omitted_text_fields: omittedTextFields,
      included_count_fields: includedCounts,
      unavailable_count_fields: unavailableCounts,
      other_response_fields: 'not_selected',
    };
    result.status = labels.length === 0 ? 'EMPTY_SUPPLIED_ARRAY'
      : indices.length === 0 ? 'EMPTY_SELECTION' : 'PROJECTED';
    return result;
  } catch (error) {
    result.labels = [];
    result.coverage = null;
    result.issue = {code: error.code || 'UNSUPPORTED_RESPONSE', detail: error.message};
    return result;
  }
}

module.exports = {projectGmailLabelHeaders};
