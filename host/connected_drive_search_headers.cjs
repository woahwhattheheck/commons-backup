"use strict";

const SCHEMA = "commons.connected_drive_search_headers/v1";
const DEFAULTS = Object.freeze({
  start_index: 0, max_files: 10, max_metadata_chars: 4096,
  max_header_chars: 4096, max_input_files: 10000
});
const STRINGS = ["mime_type", "file_or_folder", "title", "size", "created_at",
  "updated_at", "viewedByMeTime", "url", "display_title", "display_url"];
const FLAGS = ["shared", "can_download", "can_list_children"];
const WITHHELD = ["parent_ids", "owners", "permissions", "content", "text", "body",
  "snippet", "download_url", "export_links"];
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const object = value => value !== null && typeof value === "object" && !Array.isArray(value);

function optionsOf(value) {
  const input = value === undefined ? {} : value;
  if (!object(input)) throw new TypeError("options must be an object");
  const allowed = new Set([...Object.keys(DEFAULTS), "source_indices"]);
  for (const key of Object.keys(input)) {
    if (!allowed.has(key)) throw new TypeError("Unsupported option: " + key);
  }
  if (own(input, "source_indices") && own(input, "start_index")) {
    throw new TypeError("source_indices and an explicit start_index are mutually exclusive");
  }
  const limits = {...DEFAULTS}, bounds = {
    start_index: [0, Number.MAX_SAFE_INTEGER], max_files: [0, 100],
    max_metadata_chars: [0, 1000000], max_header_chars: [1, 16384],
    max_input_files: [1, 100000]
  };
  for (const key of Object.keys(DEFAULTS)) {
    if (!own(input, key)) continue;
    const [minimum, maximum] = bounds[key], number = input[key];
    if (!Number.isSafeInteger(number) || number < minimum || number > maximum) {
      throw new RangeError(key + " must be an integer from " + minimum + " to " + maximum);
    }
    limits[key] = number;
  }
  let selected = null;
  if (own(input, "source_indices")) {
    if (!Array.isArray(input.source_indices)) throw new TypeError("source_indices must be an array");
    selected = input.source_indices.slice();
    if (selected.length > limits.max_files) throw new RangeError("max_files must accommodate source_indices");
    for (let index = 0; index < selected.length; index++) {
      if (!Number.isSafeInteger(selected[index]) || selected[index] < 0 ||
          (index > 0 && selected[index] <= selected[index - 1])) {
        throw new RangeError("source_indices must be distinct increasing nonnegative integers");
      }
    }
  }
  return {limits, selected};
}

function omittedRanges(count, selected) {
  const ranges = [];
  let cursor = 0;
  for (const index of selected) {
    if (cursor < index) ranges.push([cursor, index]);
    cursor = index + 1;
  }
  if (cursor < count) ranges.push([cursor, count]);
  return ranges;
}

function withheld(row, key, path) {
  const present = own(row, key), value = present ? row[key] : undefined;
  return {present, source_path: [...path, key],
    value_type: !present ? "absent" : value === null ? "null" :
      Array.isArray(value) ? "array" : typeof value,
    ...(Array.isArray(value) ? {retained_count: value.length} : {}),
    ...(typeof value === "string" ? {retained_chars: value.length} : {}),
    withheld: true};
}

/** Project one unchanged native Google Drive search envelope; no provider calls. */
function projectDriveSearchHeaders(response, options) {
  const {limits, selected: requested} = optionsOf(options);
  const sourcePath = ["structuredContent", "results"];
  const base = {schema: SCHEMA, status: null, limits: {...limits},
    source: {representation: "native_drive_search", source_path: sourcePath,
      range_unit: "utf16_code_units", range_end: "exclusive"},
    coverage: {scope: "retained_response_only", snapshot: false,
      provider_result_completeness: "not_inferred", pagination: "not_inferred",
      query_application: "not_inferred", content_readability: "not_inferred",
      parent_ids_withheld: true, owner_permission_content_fields_withheld: true},
    files: [], issue: null};
  const refuse = (status, code, detail = {}) =>
    ({...base, status, issue: {code, ...detail}});
  if (!object(response)) return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_CALL_TOOL_RESULT");
  if (response.isError === true) return refuse("PROVIDER_ERROR", "PROVIDER_ERROR_ENVELOPE");
  const payload = response.structuredContent;
  if (!object(payload)) return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_NATIVE_DRIVE_RESULTS");
  if (payload.isError === true || payload.ok === false || own(payload, "error") ||
      (Number.isInteger(payload.status) && payload.status >= 400)) {
    return refuse("PROVIDER_ERROR", "PROVIDER_ERROR_PAYLOAD");
  }
  if (!Array.isArray(payload.results)) {
    return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_NATIVE_DRIVE_RESULTS");
  }
  const rows = payload.results;
  if (rows.length > limits.max_input_files) {
    return refuse("INPUT_LIMIT", "FILES_LIMIT", {observed: rows.length, maximum: limits.max_input_files});
  }
  for (let index = 0; index < rows.length; index++) {
    const row = rows[index], path = [...sourcePath, index];
    if (!object(row) || typeof row.id !== "string" || !row.id.length) {
      return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_FILE_ID", {source_path: [...path, "id"]});
    }
    if (row.id.length > limits.max_header_chars) {
      return refuse("INPUT_LIMIT", "HEADER_CHAR_LIMIT", {source_path: [...path, "id"],
        observed: row.id.length, maximum: limits.max_header_chars});
    }
    for (const key of STRINGS) {
      if (!own(row, key)) continue;
      if (key === "size" && Number.isSafeInteger(row[key]) && row[key] >= 0) continue;
      if (row[key] !== null && typeof row[key] !== "string") {
        return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_HEADER_FIELD", {source_path: [...path, key]});
      }
      if (typeof row[key] === "string" && row[key].length > limits.max_header_chars) {
        return refuse("INPUT_LIMIT", "HEADER_CHAR_LIMIT", {source_path: [...path, key],
          observed: row[key].length, maximum: limits.max_header_chars});
      }
    }
    for (const key of FLAGS) {
      if (own(row, key) && row[key] !== null && typeof row[key] !== "boolean") {
        return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_FLAG_FIELD", {source_path: [...path, key]});
      }
    }
  }
  if (requested !== null && requested.some(index => index >= rows.length)) {
    throw new RangeError("source_indices contains an index outside retained files");
  }
  if (requested === null && limits.start_index > rows.length) {
    throw new RangeError("start_index exceeds the retained file count");
  }
  const indices = requested === null
    ? Array.from({length: Math.min(limits.max_files, rows.length - limits.start_index)},
      (_, index) => limits.start_index + index)
    : requested;
  const identityChars = indices.reduce((total, index) => total + rows[index].id.length, 0);
  if (identityChars > limits.max_metadata_chars) {
    return refuse("INPUT_LIMIT", "SELECTED_ID_METADATA_BUDGET", {
      observed: identityChars, maximum: limits.max_metadata_chars});
  }
  let metadataChars = identityChars;
  const omittedMetadata = [];
  const files = indices.map(index => {
    const row = rows[index], path = [...sourcePath, index];
    const result = {source_index: index, source_path: path, id: row.id,
      metadata_source_paths: {id: [...path, "id"]},
      withheld_fields: Object.fromEntries(WITHHELD.map(key => [key, withheld(row, key, path)]))};
    for (const key of [...STRINGS, ...FLAGS]) {
      if (!own(row, key)) continue;
      const chars = typeof row[key] === "string" ? row[key].length : 0;
      if (metadataChars + chars > limits.max_metadata_chars) {
        omittedMetadata.push({source_path: [...path, key], chars, reason: "METADATA_CHAR_BUDGET"});
        continue;
      }
      result[key] = row[key];
      result.metadata_source_paths[key] = [...path, key];
      metadataChars += chars;
    }
    return result;
  });
  const next = requested === null ? limits.start_index + indices.length : null;
  return {...base, status: "PROJECTED", files,
    coverage: {...base.coverage, retained_files: rows.length, returned_files: files.length,
      selection_mode: requested === null ? "contiguous" : "source_indices",
      selected_source_indices: indices, omitted_files: rows.length - files.length,
      omitted_source_index_ranges: omittedRanges(rows.length, indices),
      next_index: requested === null && next < rows.length ? next : null,
      all_retained_file_headers_included: files.length === rows.length,
      returned_metadata_chars: metadataChars, metadata_omitted_fields: omittedMetadata,
      all_selected_metadata_included: omittedMetadata.length === 0,
      next_page_token_present: own(payload, "next_page_token"),
      pagination_token_withheld: true,
      ...(own(payload, "next_page_token")
        ? {pagination_token_source_path: ["structuredContent", "next_page_token"]} : {})}};
}

module.exports = {projectDriveSearchHeaders, SCHEMA, DEFAULTS};
