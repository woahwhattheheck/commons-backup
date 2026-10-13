"use strict";

// Decoded paths refer to one original JSON text document, not page byte offsets.
const SCHEMA = "commons.connected_web_json_results/v1";
const DEFAULTS = Object.freeze({
  content_index: 0, start_index: 0, max_results: 8,
  max_snippet_chars: 800, max_total_snippet_chars: 6400,
  max_input_chars: 1048576, max_header_chars: 4096
});
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const object = value => value !== null && typeof value === "object" && !Array.isArray(value);

function readOptions(value) {
  const input = value === undefined ? {} : value;
  if (!object(input)) throw new TypeError("options must be an object");
  const allowed = new Set([...Object.keys(DEFAULTS), "source_indices"]);
  for (const key of Object.keys(input)) {
    if (!allowed.has(key)) throw new TypeError("Unsupported option: " + key);
  }
  if (own(input, "source_indices") && own(input, "start_index")) {
    throw new TypeError("source_indices and an explicit start_index are mutually exclusive");
  }
  const limits = {...DEFAULTS};
  const bounds = {
    content_index: [0, 4095], start_index: [0, Number.MAX_SAFE_INTEGER],
    max_results: [0, 100], max_snippet_chars: [0, 100000],
    max_total_snippet_chars: [0, 1000000], max_input_chars: [1, 8388608],
    max_header_chars: [128, 16384]
  };
  for (const key of Object.keys(DEFAULTS)) {
    if (!own(input, key)) continue;
    const [min, max] = bounds[key], number = input[key];
    if (!Number.isSafeInteger(number) || number < min || number > max) {
      throw new RangeError(key + " must be an integer from " + min + " to " + max);
    }
    limits[key] = number;
  }
  let selected = null;
  if (own(input, "source_indices")) {
    if (!Array.isArray(input.source_indices)) throw new TypeError("source_indices must be an array");
    selected = input.source_indices.slice();
    if (selected.length > limits.max_results) {
      throw new RangeError("max_results must accommodate all source_indices");
    }
    for (let index = 0; index < selected.length; index++) {
      if (!Number.isSafeInteger(selected[index]) || selected[index] < 0 ||
          (index > 0 && selected[index] <= selected[index - 1])) {
        throw new RangeError("source_indices must be distinct increasing nonnegative integers");
      }
    }
  }
  return {limits, selected};
}

function omittedRanges(count, indices) {
  const ranges = [];
  let cursor = 0;
  for (const index of indices) {
    if (cursor < index) ranges.push([cursor, index]);
    cursor = index + 1;
  }
  if (cursor < count) ranges.push([cursor, count]);
  return ranges;
}

function prefixLength(value, maximum) {
  let length = Math.min(value.length, maximum);
  if (length > 0 && length < value.length &&
      value.charCodeAt(length - 1) >= 0xd800 && value.charCodeAt(length - 1) <= 0xdbff &&
      value.charCodeAt(length) >= 0xdc00 && value.charCodeAt(length) <= 0xdfff) length--;
  return length;
}

/**
 * Project a retained JSON search-result document without provider calls.
 * URL and metadata are literal reported fields; citation identities,
 * authority, other pages and provider completeness are never inferred.
 */
function projectWebJsonResults(response, options) {
  const {limits, selected: requested} = readOptions(options);
  const textPath = ["content", limits.content_index, "text"];
  const base = {
    schema: SCHEMA, status: null, limits: {...limits},
    source: {representation: "json_text", text_source_path: textPath,
      parsed_results_path: ["results"], range_unit: "decoded_utf16_code_units",
      range_end: "exclusive"},
    coverage: {scope: "retained_document_only", snapshot: false,
      provider_completeness: "not_inferred"},
    results: [], issue: null
  };
  const refuse = (status, code, detail = {}) =>
    ({...base, status, issue: {code, ...detail}});
  if (!object(response)) return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_CALL_TOOL_RESULT");
  if (response.isError === true) return refuse("PROVIDER_ERROR", "PROVIDER_ERROR_ENVELOPE");
  if (!Array.isArray(response.content)) return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_CONTENT_ITEMS");
  if (response.content.length > 4096) {
    return refuse("INPUT_LIMIT", "CONTENT_ITEMS_LIMIT", {observed: response.content.length, maximum: 4096});
  }
  const item = response.content[limits.content_index];
  if (!object(item) || item.type !== "text" || typeof item.text !== "string") {
    return refuse("UNSUPPORTED_REPRESENTATION", "SELECTED_ITEM_IS_NOT_TEXT", {source_path: textPath});
  }
  base.source.input_chars = item.text.length;
  base.coverage.ignored_content_item_indices = response.content
    .map((_, index) => index).filter(index => index !== limits.content_index);
  if (item.text.length > limits.max_input_chars) {
    return refuse("INPUT_LIMIT", "TEXT_CHAR_LIMIT", {
      observed: item.text.length, maximum: limits.max_input_chars, source_path: textPath});
  }
  let payload;
  try { payload = JSON.parse(item.text); }
  catch (_) { return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_JSON", {source_path: textPath}); }
  if (!object(payload) || !Array.isArray(payload.results)) {
    return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_RESULTS_ARRAY");
  }
  if (own(payload, "query")) {
    if (typeof payload.query !== "string") return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_QUERY_FIELD");
    // A caller can inspect the retained query at this path without repeating it
    // in every bounded overview.
    base.source.query = {parsed_source_path: ["query"], chars: payload.query.length};
  }
  for (const key of ["total_results", "page"]) {
    if (!own(payload, key)) continue;
    if (!Number.isSafeInteger(payload[key]) || payload[key] < 0) {
      return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_REPORTED_COUNT", {parsed_source_path: [key]});
    }
    base.coverage[key === "total_results" ? "reported_total_results" : "reported_page"] = payload[key];
  }
  const rows = payload.results;
  for (let index = 0; index < rows.length; index++) {
    const row = rows[index], path = ["results", index];
    if (!object(row) || typeof row.title !== "string" || typeof row.url !== "string") {
      return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_RESULT_HEADER", {parsed_source_path: path});
    }
    for (const key of ["title", "url", "site_name", "date"]) {
      if (!own(row, key)) continue;
      if (row[key] !== null && typeof row[key] !== "string") {
        return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_HEADER_FIELD", {parsed_source_path: [...path, key]});
      }
      if (typeof row[key] === "string" && row[key].length > limits.max_header_chars) {
        return refuse("INPUT_LIMIT", "HEADER_CHAR_LIMIT", {
          observed: row[key].length, maximum: limits.max_header_chars, parsed_source_path: [...path, key]});
      }
    }
    if (own(row, "position") && row.position !== null &&
        (!Number.isSafeInteger(row.position) || row.position < 0)) {
      return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_POSITION_FIELD", {parsed_source_path: [...path, "position"]});
    }
    if (own(row, "snippet") && row.snippet !== null && typeof row.snippet !== "string") {
      return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_SNIPPET_FIELD", {parsed_source_path: [...path, "snippet"]});
    }
  }
  if (requested !== null && requested.some(index => index >= rows.length)) {
    throw new RangeError("source_indices contains an index outside the retained results");
  }
  if (requested === null && limits.start_index > rows.length) {
    throw new RangeError("start_index exceeds the retained result count");
  }
  const indices = requested === null
    ? Array.from({length: Math.min(limits.max_results, rows.length - limits.start_index)},
      (_, index) => limits.start_index + index)
    : requested;
  let remaining = limits.max_total_snippet_chars, returnedChars = 0, selectedChars = 0, truncated = 0;
  const results = indices.map(index => {
    const row = rows[index], path = ["results", index];
    const result = {source_index: index, text_source_path: textPath.slice(),
      parsed_source_path: path, title: row.title, url: row.url,
      metadata_source_paths: {title: [...path, "title"], url: [...path, "url"]}};
    for (const key of ["site_name", "date", "position"]) {
      if (!own(row, key)) continue;
      result[key] = row[key];
      result.metadata_source_paths[key] = [...path, key];
    }
    if (!own(row, "snippet")) {
      result.snippet_present = false;
      return result;
    }
    const length = typeof row.snippet === "string"
      ? prefixLength(row.snippet, Math.min(limits.max_snippet_chars, remaining)) : 0;
    const fullLength = typeof row.snippet === "string" ? row.snippet.length : 0;
    result.snippet_present = true;
    result.snippet = row.snippet === null ? null : row.snippet.slice(0, length);
    result.snippet_source_path = [...path, "snippet"];
    result.returned_snippet_range = row.snippet === null ? null : [0, length];
    result.snippet_chars = fullLength;
    result.returned_chars = length;
    result.truncated = length < fullLength;
    selectedChars += fullLength;
    returnedChars += length;
    remaining -= length;
    if (result.truncated) truncated++;
    return result;
  });
  const next = requested === null ? limits.start_index + indices.length : null;
  return {...base, status: "PROJECTED", results,
    coverage: {...base.coverage, retained_results: rows.length,
      selection_mode: requested === null ? "contiguous" : "source_indices",
      selected_source_indices: indices, returned_results: results.length,
      omitted_results: rows.length - results.length,
      omitted_source_index_ranges: omittedRanges(rows.length, indices),
      next_index: requested === null && next < rows.length ? next : null,
      selected_snippet_chars: selectedChars, returned_snippet_chars: returnedChars,
      truncated_results: truncated,
      all_retained_snippets_included: results.length === rows.length && truncated === 0}};
}

module.exports = {projectWebJsonResults, SCHEMA, DEFAULTS};
