'use strict';

// Pure supplied-record view. Rendered text is never returned or treated as raw file bytes.
const SCHEMA = 'commons.connected_library_read_headers/v1';
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const STRINGS = [
  'library_file_id', 'file_id', 'requested_file_id', 'ref_id', 'version_id',
  'name', 'mime_type', 'file_provider', 'library_artifact_type', 'surface',
  'api_tool_source', 'mode', 'created_at', 'modified_at'
];
const NUMBERS = [
  'size_bytes', 'start_line', 'end_line', 'total_lines', 'num_pages',
  'requested_start_page', 'requested_end_page', 'next_start_line', 'next_start_page', 'read_index'
];
const BOOLEANS = ['has_more', 'include_text', 'include_images'];

function limit(options, key, fallback, ceiling) {
  const value = own(options, key) ? options[key] : fallback;
  if (!Number.isSafeInteger(value) || value < 0 || value > ceiling) {
    throw new RangeError(key + ' must be an integer between 0 and ' + ceiling);
  }
  return value;
}

function projectLibraryReadHeaders(supplied, options = {}) {
  if (!object(options)) throw new TypeError('options must be an object');
  const limits = {
    start_index: limit(options, 'start_index', 0, Number.MAX_SAFE_INTEGER),
    max_items: limit(options, 'max_items', 20, 100),
    max_metadata_units: limit(options, 'max_metadata_units', 4096, 16384),
    max_string_units: limit(options, 'max_string_units', 512, 4096),
    max_content_blocks: limit(options, 'max_content_blocks', 16, 1024)
  };
  const errorState = !object(supplied) || !own(supplied, 'isError') ? 'missing'
    : supplied.isError === null ? 'null' : typeof supplied.isError === 'boolean' ? 'observed' : 'invalid';
  const base = {
    schema: SCHEMA, status: 'UNSUPPORTED', supplied_error_state: errorState,
    limits, items: [], metadata_utf16_units: 0,
    scope: 'supplied_record_only; rendered_text_not_raw_bytes; no_provider_or_byte_equality_certification'
  };
  if (object(supplied) && supplied.isError === true) return {...base, reason: 'SUPPLIED_ERROR'};
  // The observed native read response exposes results here. No JSON-string parsing or arbitrary envelope guessing.
  if (!object(supplied) || !object(supplied.structuredContent) || !Array.isArray(supplied.structuredContent.results)) {
    return {...base, reason: 'EXPECTED_NATIVE_LIBRARY_READ_RESULTS'};
  }
  const results = supplied.structuredContent.results;
  const start = Math.min(limits.start_index, results.length);
  const end = Math.min(results.length, start + limits.max_items);
  let used = 0;
  const items = [];
  for (let index = start; index < end; index++) {
    const row = results[index];
    const item = {source_path: ['structuredContent', 'results', index], source_index: index,
      status: 'UNSUPPORTED', metadata: {}, field_states: {}};
    if (!own(results, index) || !object(row)) {
      item.reason = own(results, index) ? 'EXPECTED_RECORD' : 'MISSING_ARRAY_ENTRY';
      items.push(item);
      continue;
    }
    item.status = 'PROJECTED';
    function copy(key, valid) {
      if (!own(row, key)) { item.field_states[key] = 'missing'; return; }
      const value = row[key];
      if (value === null) { item.metadata[key] = null; item.field_states[key] = 'null'; return; }
      if (!valid(value)) { item.field_states[key] = 'invalid'; return; }
      if (typeof value === 'string') {
        if (value.length > limits.max_string_units || value.length > limits.max_metadata_units - used) {
          item.field_states[key] = 'budget_omitted';
          return;
        }
        used += value.length;
      }
      item.metadata[key] = value;
      item.field_states[key] = 'observed';
    }
    STRINGS.forEach(key => copy(key, value => typeof value === 'string'));
    NUMBERS.forEach(key => copy(key, value => Number.isSafeInteger(value) && value >= 0));
    BOOLEANS.forEach(key => copy(key, value => typeof value === 'boolean'));
    item.warnings = !own(row, 'warnings') ? {state: 'missing', count: null}
      : row.warnings === null ? {state: 'null', count: null}
      : Array.isArray(row.warnings) ? {state: 'observed_array', count: row.warnings.length}
      : {state: 'invalid', count: null};
    if (!own(row, 'content') || !Array.isArray(row.content)) {
      item.content_summary = {state: !own(row, 'content') ? 'missing' : row.content === null ? 'null' : 'invalid',
        declared_blocks: null, scanned_blocks: 0, scanned_text_utf16_units: null, scan_complete: false};
    } else {
      const blocks = row.content;
      const scanEnd = Math.min(blocks.length, limits.max_content_blocks);
      let textUnits = 0, nonString = 0, missing = 0;
      for (let block = 0; block < scanEnd; block++) {
        if (!own(blocks, block)) missing++;
        else if (typeof blocks[block] === 'string') textUnits += blocks[block].length;
        else nonString++;
      }
      item.content_summary = {state: 'observed_array', declared_blocks: blocks.length,
        scanned_blocks: scanEnd, scanned_text_utf16_units: textUnits,
        scanned_nonstring_blocks: nonString, scanned_missing_blocks: missing,
        scan_complete: scanEnd === blocks.length};
    }
    items.push(item);
  }
  return {...base, status: 'PROJECTED', source_shape: 'structuredContent.results',
    retained_results: results.length, window_start: start, window_end: end,
    projected_items: items.length, remaining_results: results.length - end,
    metadata_utf16_units: used, items};
}

module.exports = {projectLibraryReadHeaders};
