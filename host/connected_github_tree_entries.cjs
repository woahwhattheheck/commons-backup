"use strict";

const SCHEMA = "commons.connected_github_tree_entries/v1";
const DEFAULTS = Object.freeze({start_index: 0, max_entries: 10,
  max_path_chars: 4096, max_url_chars: 4096, max_total_metadata_chars: 4096,
  max_input_chars: 2000000, max_input_entries: 10000});
const SHA = /^[0-9a-f]{40}$/;
const TYPES = new Set(["blob", "tree", "commit"]);
const MODES = new Set(["040000", "100644", "100755", "120000", "160000"]);
const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);

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
  const limits = {...DEFAULTS}, bounds = {
    start_index: [0, Number.MAX_SAFE_INTEGER], max_entries: [0, 100],
    max_path_chars: [1, 16384], max_url_chars: [1, 16384],
    max_total_metadata_chars: [40, 1000000], max_input_chars: [0, 10000000],
    max_input_entries: [1, 100000]
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
    if (selected.length > limits.max_entries) throw new RangeError("max_entries must accommodate source_indices");
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

/** Project one retained native JSON-text or successful token tree; no IO. */
function projectGitHubTreeEntries(response, options) {
  const {limits, selected: requested} = readOptions(options);
  const base = {schema: SCHEMA, status: null, limits: {...limits},
    source: {representation: "unrecognized", decoded_entries_path: ["tree"],
      range_unit: "utf16_code_units", range_end: "exclusive"},
    coverage: {scope: "retained_response_only", snapshot: "not_verified",
      git_object_sha_verified: false, commit_resolution: "not_performed",
      repository_binding: "not_verified", recursion: "not_inferred",
      repository_completeness: "not_inferred", other_fields_withheld: true},
    entries: [], issue: null};
  const refuse = (status, code, detail = {}) => ({...base, status, issue: {code, ...detail}});
  if (!object(response)) return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_CALL_TOOL_RESULT");
  if (response.isError === true) return refuse("PROVIDER_ERROR", "PROVIDER_ERROR_ENVELOPE");
  if (own(response, "isError") && typeof response.isError !== "boolean") {
    return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_ERROR_FLAG");
  }
  const native = response.structuredContent;
  if (!object(native)) return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_TREE_ENVELOPE");
  const hasText = typeof native.content === "string";
  const hasHTTP = ["status", "ok", "data"].every(key => own(native, key));
  if (hasText && !hasHTTP) {
    base.source = {...base.source, representation: "native_fetch_json_text",
      envelope_payload_path: ["structuredContent", "content"], decoding: "JSON.parse"};
  } else if (hasHTTP && !hasText) {
    base.source = {...base.source, representation: "token_http_tree",
      envelope_payload_path: ["structuredContent", "data"], decoding: "none"};
  }
  if (native.isError === true || native.ok === false || own(native, "error") ||
      (Number.isInteger(native.status) && native.status >= 400)) {
    return refuse("PROVIDER_ERROR", "PROVIDER_ERROR_PAYLOAD");
  }
  if (hasText && hasHTTP) return refuse("UNSUPPORTED_REPRESENTATION", "AMBIGUOUS_REPRESENTATION");
  let payload;
  if (hasText) {
    if (native.content.length > limits.max_input_chars) {
      return refuse("INPUT_LIMIT", "JSON_CHAR_LIMIT", {observed: native.content.length, maximum: limits.max_input_chars});
    }
    try { payload = JSON.parse(native.content); }
    catch (_) { return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_TREE_JSON"); }
  } else if (hasHTTP && native.ok === true && Number.isInteger(native.status) &&
      native.status >= 200 && native.status < 300 && object(native.data)) {
    payload = native.data;
  } else return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_TREE_ENVELOPE");
  if (object(payload) && (payload.isError === true || payload.ok === false || own(payload, "error") ||
      (Number.isInteger(payload.status) && payload.status >= 400))) {
    return refuse("PROVIDER_ERROR", "PROVIDER_ERROR_DECODED_PAYLOAD");
  }
  if (!object(payload) || typeof payload.sha !== "string" || !SHA.test(payload.sha) ||
      !Array.isArray(payload.tree) || typeof payload.truncated !== "boolean") {
    return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_GIT_TREE_FIELDS");
  }
  const rows = payload.tree;
  if (rows.length > limits.max_input_entries) {
    return refuse("INPUT_LIMIT", "ENTRIES_LIMIT", {observed: rows.length, maximum: limits.max_input_entries});
  }
  const counts = {blob: 0, tree: 0, commit: 0};
  const urls = [[payload, ["url"]]];
  for (let index = 0; index < rows.length; index++) {
    const row = rows[index], path = ["tree", index];
    if (!object(row) || typeof row.path !== "string" || row.path.length === 0 ||
        typeof row.mode !== "string" || !MODES.has(row.mode) || !TYPES.has(row.type) ||
        typeof row.sha !== "string" || !SHA.test(row.sha)) {
      return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_ENTRY_FIELDS", {decoded_source_path: path});
    }
    if (row.path.length > limits.max_path_chars) {
      return refuse("INPUT_LIMIT", "PATH_CHAR_LIMIT", {decoded_source_path: [...path, "path"],
        observed: row.path.length, maximum: limits.max_path_chars});
    }
    if (own(row, "size") && !(Number.isSafeInteger(row.size) && row.size >= 0)) {
      return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_ENTRY_SIZE", {decoded_source_path: [...path, "size"]});
    }
    counts[row.type]++;
    urls.push([row, [...path, "url"]]);
  }
  for (const [row, path] of urls) {
    if (!own(row, "url")) continue;
    if (row.url !== null && typeof row.url !== "string") {
      return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_URL", {decoded_source_path: path});
    }
    if (typeof row.url === "string" && row.url.length > limits.max_url_chars) {
      return refuse("INPUT_LIMIT", "URL_CHAR_LIMIT", {decoded_source_path: path,
        observed: row.url.length, maximum: limits.max_url_chars});
    }
  }
  if (requested !== null && requested.some(index => index >= rows.length)) {
    throw new RangeError("source_indices contains an index outside retained entries");
  }
  if (requested === null && limits.start_index > rows.length) {
    throw new RangeError("start_index exceeds the retained entry count");
  }
  const indices = requested === null
    ? Array.from({length: Math.min(limits.max_entries, rows.length - limits.start_index)},
      (_, index) => limits.start_index + index)
    : requested;
  const mandatory = 40 + indices.reduce((total, index) => {
    const row = rows[index];
    return total + row.path.length + row.mode.length + row.type.length + row.sha.length;
  }, 0);
  if (mandatory > limits.max_total_metadata_chars) {
    return refuse("INPUT_LIMIT", "SELECTED_METADATA_BUDGET", {
      observed: mandatory, maximum: limits.max_total_metadata_chars});
  }
  let metadataChars = mandatory;
  const omittedFields = [];
  function copyUrl(target, row, path) {
    if (!own(row, "url")) return;
    const chars = typeof row.url === "string" ? row.url.length : 0;
    if (metadataChars + chars > limits.max_total_metadata_chars) {
      omittedFields.push({decoded_source_path: path, chars, reason: "METADATA_CHAR_BUDGET"});
    } else { target.url = row.url; metadataChars += chars; }
  }
  const result = {...base, status: "PROJECTED", sha: payload.sha,
    sha_decoded_source_path: ["sha"], truncated: payload.truncated,
    truncated_decoded_source_path: ["truncated"]};
  copyUrl(result, payload, ["url"]);
  result.entries = indices.map(index => {
    const row = rows[index], path = ["tree", index];
    const entry = {source_index: index, decoded_source_path: path,
      path: row.path, mode: row.mode, type: row.type, sha: row.sha};
    if (own(row, "size")) entry.size = row.size;
    copyUrl(entry, row, [...path, "url"]);
    return entry;
  });
  const next = requested === null ? limits.start_index + indices.length : null;
  result.coverage = {...base.coverage, retained_entries: rows.length,
    retained_type_counts: counts, returned_entries: result.entries.length,
    selection_mode: requested === null ? "contiguous" : "source_indices",
    selected_source_indices: indices, omitted_entries: rows.length - result.entries.length,
    omitted_source_index_ranges: omittedRanges(rows.length, indices),
    next_index: requested === null && next < rows.length ? next : null,
    all_retained_entries_included: result.entries.length === rows.length,
    returned_metadata_chars: metadataChars, omitted_optional_fields: omittedFields,
    all_selected_metadata_included: omittedFields.length === 0};
  return result;
}

module.exports = {projectGitHubTreeEntries, SCHEMA, DEFAULTS};
