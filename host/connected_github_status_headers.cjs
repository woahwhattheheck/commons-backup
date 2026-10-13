'use strict';

// Pure projection of retained commit-status responses, with no CI verdict.
const SCHEMA = 'commons.connected_github_status_headers/v1';
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const ROW_TEXT = ['state', 'context', 'description', 'created_at', 'updated_at'];

function fail(code, message) {
  const error = new TypeError(message);
  error.code = code;
  throw error;
}
function integer(value, fallback, maximum, name, minimum = 0) {
  const actual = value === undefined ? fallback : value;
  if (!Number.isSafeInteger(actual) || actual < minimum || actual > maximum) {
    fail('INVALID_INPUT', name + ' exceeds its integer budget');
  }
  return actual;
}

function projectGitHubStatusHeaders(response, options = {}) {
  if (!record(options)) fail('INVALID_INPUT', 'options must be an object');
  const allowed = new Set(['indices', 'max_statuses', 'max_field_chars', 'max_total_metadata_chars', 'max_response_chars']);
  for (const key of Object.keys(options)) {
    if (!allowed.has(key)) fail('INVALID_INPUT', 'Unknown option: ' + key);
  }
  const limits = {
    max_input_statuses: 10000,
    max_statuses: integer(options.max_statuses, 20, 500, 'max_statuses'),
    max_field_chars: integer(options.max_field_chars, 256, 4096, 'max_field_chars'),
    max_total_metadata_chars: integer(options.max_total_metadata_chars, 4000, 64000, 'max_total_metadata_chars'),
    max_response_chars: integer(options.max_response_chars, 1048576, 8388608, 'max_response_chars', 256),
  };
  let selected = null;
  if (own(options, 'indices')) {
    if (!Array.isArray(options.indices) || options.indices.length > limits.max_statuses) {
      fail('INVALID_INPUT', 'indices must fit max_statuses');
    }
    selected = [];
    const seen = new Set();
    for (let i = 0; i < options.indices.length; i += 1) {
      const index = options.indices[i];
      if (!own(options.indices, i) || !Number.isSafeInteger(index) || index < 0
          || index >= limits.max_input_statuses || seen.has(index)) {
        fail('INVALID_INPUT', 'indices must be dense unique bounded integers');
      }
      selected.push(index);
      seen.add(index);
    }
  }
  const result = {
    schema: SCHEMA, status: 'REFUSED', limits,
    source: {
      scope: 'supplied_commit_status_payload_only',
      source_shape: null, source_path: null,
      expected_bindings: ['mcp__codex_apps__github_get_commit_combined_status', 'mcp__codex_apps__github_token_connection_github_read'],
      binding_origin: 'not_authenticated',
      commit_request_binding: 'not_verified',
      aggregate_state_basis: 'literal_field_if_present',
      status_collection_completeness: 'not_established',
      other_check_families: 'not_selected_or_assessed',
      repository_identity: 'not_inferred',
      observation_time: 'not_inferred',
      ci_verdict: 'not_inferred',
      provider_calls: 0,
    },
    aggregate: {}, statuses: [], coverage: null, issue: null,
  };
  try {
    if (!record(response) || response.isError === true || !record(response.structuredContent)) {
      fail('EXPECTED_STATUS_RESPONSE', 'Expected a successful structured native or token response');
    }
    const wrapper = response.structuredContent;
    if (own(wrapper, 'error') || own(wrapper, 'error_code')) fail('PROVIDER_ERROR', 'Response reports a provider error');
    let data = wrapper, path = 'structuredContent', shape = 'native_structured';
    if (own(wrapper, 'data') || own(wrapper, 'ok')) {
      if (wrapper.ok !== true || !Number.isInteger(wrapper.status) || wrapper.status < 200
          || wrapper.status >= 300 || !record(wrapper.data)) {
        fail('EXPECTED_TOKEN_STATUS_RESPONSE', 'Token response lacks a confirmed successful data envelope');
      }
      data = wrapper.data;
      path += '.data';
      shape = 'token_data';
    }
    if (own(data, 'error') || own(data, 'error_code') || !Array.isArray(data.statuses)) {
      fail('EXPECTED_STATUS_ARRAY', 'Expected a statuses array at the selected response path');
    }
    const serialized = JSON.stringify(response);
    if (typeof serialized !== 'string' || serialized.length > limits.max_response_chars) {
      fail('RESPONSE_LIMIT', 'Retained response exceeds its input character budget');
    }
    if (data.statuses.length > limits.max_input_statuses) fail('SOURCE_LIMIT', 'Too many supplied status rows');
    for (let i = 0; i < data.statuses.length; i += 1) {
      if (!own(data.statuses, i) || !record(data.statuses[i])) {
        fail('EXPECTED_STATUS_ARRAY', 'Status rows must be dense objects');
      }
    }
    const indices = selected === null
      ? Array.from({length: Math.min(data.statuses.length, limits.max_statuses)}, (_, i) => i)
      : selected;
    if (indices.some(index => index >= data.statuses.length)) fail('SOURCE_INDEX_RANGE', 'Selected status row is absent');
    let remaining = limits.max_total_metadata_chars;
    let selectedChars = 0, returnedChars = 0, omittedTextFields = 0;
    const textField = (value, key, sourcePath, sha = false) => {
      const field = {source_path: sourcePath};
      if (!own(value, key)) { field.status = 'missing'; return field; }
      if (value[key] === null) { field.status = 'null'; return field; }
      if (typeof value[key] !== 'string') { field.status = 'invalid_type'; return field; }
      const text = value[key];
      if (sha && !/^[0-9a-f]{40}$/.test(text)) { field.status = 'invalid_sha'; return field; }
      selectedChars += text.length;
      field.original_chars = text.length;
      if (text.length > limits.max_field_chars || text.length > remaining) {
        field.status = 'limit_exceeded'; field.returned_chars = 0;
        omittedTextFields += 1;
        return field;
      }
      field.status = 'included'; field.value = text; field.returned_chars = text.length;
      remaining -= text.length; returnedChars += text.length;
      return field;
    };
    const integerField = (value, key, sourcePath) => {
      const field = {source_path: sourcePath};
      if (!own(value, key)) field.status = 'missing';
      else if (value[key] === null) field.status = 'null';
      else if (!Number.isSafeInteger(value[key]) || value[key] < 0) field.status = 'invalid_integer';
      else { field.status = 'included'; field.value = value[key]; }
      return field;
    };
    result.source.source_shape = shape;
    result.source.source_path = path;
    result.aggregate = {
      state: textField(data, 'state', path + '.state'),
      sha: textField(data, 'sha', path + '.sha', true),
      total_count: integerField(data, 'total_count', path + '.total_count'),
    };
    for (const index of indices) {
      const rowPath = path + '.statuses[' + index + ']';
      const value = data.statuses[index];
      const row = {source_index: index, source_path: rowPath,
        fields: {id: integerField(value, 'id', rowPath + '.id')}};
      for (const key of ROW_TEXT) row.fields[key] = textField(value, key, rowPath + '.' + key);
      result.statuses.push(row);
    }
    result.coverage = {
      supplied_statuses: data.statuses.length,
      selected_indices: indices.slice(), returned_statuses: indices.length,
      omitted_statuses: data.statuses.length - indices.length,
      all_supplied_statuses_included: indices.length === data.statuses.length,
      selected_metadata_chars: selectedChars, returned_metadata_chars: returnedChars,
      omitted_metadata_chars: selectedChars - returnedChars, omitted_text_fields: omittedTextFields,
      reported_total_vs_supplied_rows: 'not_assessed',
      urls_creator_repository_and_other_fields: 'not_selected',
    };
    result.status = data.statuses.length === 0 ? 'EMPTY_SUPPLIED_STATUS_ARRAY'
      : indices.length === 0 ? 'HEADERS_ONLY' : 'PROJECTED';
    return result;
  } catch (error) {
    result.aggregate = {}; result.statuses = []; result.coverage = null;
    result.issue = {code: error.code || 'UNSUPPORTED_RESPONSE', detail: error.message};
    return result;
  }
}

module.exports = {projectGitHubStatusHeaders};
