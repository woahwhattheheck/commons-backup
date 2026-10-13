"use strict";

const SCHEMA = "commons.connected_github_workflow_run_headers/v1";
const DEFAULTS = Object.freeze({
  start_index: 0, max_runs: 10, max_metadata_chars: 4096,
  max_header_chars: 4096, max_input_runs: 10000
});
const STRINGS = ["status", "conclusion", "name", "jobs_url", "logs_url", "html_url",
  "head_sha", "head_branch", "event", "path", "created_at", "updated_at", "run_started_at"];
const NUMBERS = ["run_number", "run_attempt"];
const WITHHELD = ["pull_requests", "head_commit", "repository", "head_repository",
  "actor", "triggering_actor", "jobs", "steps", "logs"];
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
const id = value => (Number.isSafeInteger(value) && value > 0) ||
  (typeof value === "string" && /^[1-9][0-9]*$/.test(value));

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
    start_index: [0, Number.MAX_SAFE_INTEGER], max_runs: [0, 100],
    max_metadata_chars: [0, 1000000], max_header_chars: [1, 16384],
    max_input_runs: [1, 100000]
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
    if (selected.length > limits.max_runs) throw new RangeError("max_runs must accommodate source_indices");
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

/** Project retained native or successful token workflow-run metadata; no calls. */
function projectGitHubWorkflowRunHeaders(response, options) {
  const {limits, selected: requested} = optionsOf(options);
  let sourcePath = ["structuredContent", "workflow_runs"];
  const base = {schema: SCHEMA, status: null, limits: {...limits},
    source: {representation: "native_commit_workflow_runs", source_path: sourcePath,
      range_unit: "utf16_code_units", range_end: "exclusive"},
    coverage: {scope: "retained_response_only", snapshot: false,
      provider_result_completeness: "not_inferred", pagination: "not_inferred",
      requested_head_verification: "not_inferred", provider_filter_application: "not_inferred",
      all_workflow_result: "not_inferred", ci_success: "not_inferred",
      job_step_log_content_withheld: true, actor_email_fields_withheld: true},
    runs: [], issue: null};
  const refuse = (status, code, detail = {}) =>
    ({...base, status, issue: {code, ...detail}});
  if (!object(response)) return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_CALL_TOOL_RESULT");
  if (response.isError === true) return refuse("PROVIDER_ERROR", "PROVIDER_ERROR_ENVELOPE");
  const payload = response.structuredContent;
  if (!object(payload)) return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_NATIVE_WORKFLOW_RUNS");
  if (payload.isError === true || payload.ok === false || own(payload, "error") ||
      (Number.isInteger(payload.status) && payload.status >= 400)) {
    return refuse("PROVIDER_ERROR", "PROVIDER_ERROR_PAYLOAD");
  }
  let runsPayload = payload;
  if (!Array.isArray(payload.workflow_runs)) {
    if (payload.ok !== true || !Number.isInteger(payload.status) ||
        payload.status < 200 || payload.status >= 300 || !object(payload.data)) {
      return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_NATIVE_WORKFLOW_RUNS");
    }
    runsPayload = payload.data;
    sourcePath = ["structuredContent", "data", "workflow_runs"];
    base.source = {...base.source, representation: "token_repository_workflow_runs",
      source_path: sourcePath};
    if (runsPayload.isError === true || runsPayload.ok === false || own(runsPayload, "error") ||
        (Number.isInteger(runsPayload.status) && runsPayload.status >= 400)) {
      return refuse("PROVIDER_ERROR", "PROVIDER_ERROR_PAYLOAD");
    }
    if (!Array.isArray(runsPayload.workflow_runs)) {
      return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_TOKEN_WORKFLOW_RUNS");
    }
  }
  const rows = runsPayload.workflow_runs;
  if (rows.length > limits.max_input_runs) {
    return refuse("INPUT_LIMIT", "RUNS_LIMIT", {observed: rows.length, maximum: limits.max_input_runs});
  }
  for (let index = 0; index < rows.length; index++) {
    const row = rows[index], path = [...sourcePath, index];
    if (!object(row) || !id(row.id)) {
      return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_RUN_ID", {source_path: [...path, "id"]});
    }
    if (String(row.id).length > limits.max_header_chars) {
      return refuse("INPUT_LIMIT", "HEADER_CHAR_LIMIT", {source_path: [...path, "id"],
        observed: String(row.id).length, maximum: limits.max_header_chars});
    }
    for (const key of STRINGS) {
      if (!own(row, key)) continue;
      if (row[key] !== null && typeof row[key] !== "string") {
        return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_HEADER_FIELD", {source_path: [...path, key]});
      }
      if (typeof row[key] === "string" && row[key].length > limits.max_header_chars) {
        return refuse("INPUT_LIMIT", "HEADER_CHAR_LIMIT", {source_path: [...path, key],
          observed: row[key].length, maximum: limits.max_header_chars});
      }
    }
    if (own(row, "workflow_id") && row.workflow_id !== null &&
        (!id(row.workflow_id) || String(row.workflow_id).length > limits.max_header_chars)) {
      return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_WORKFLOW_ID", {
        source_path: [...path, "workflow_id"]});
    }
    for (const key of NUMBERS) {
      if (own(row, key) && row[key] !== null &&
          !(Number.isSafeInteger(row[key]) && row[key] >= 0)) {
        return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_RUN_NUMBER", {source_path: [...path, key]});
      }
    }
  }
  if (requested !== null && requested.some(index => index >= rows.length)) {
    throw new RangeError("source_indices contains an index outside retained runs");
  }
  if (requested === null && limits.start_index > rows.length) {
    throw new RangeError("start_index exceeds the retained run count");
  }
  const indices = requested === null
    ? Array.from({length: Math.min(limits.max_runs, rows.length - limits.start_index)},
      (_, index) => limits.start_index + index)
    : requested;
  const identityChars = indices.reduce((total, index) => total + String(rows[index].id).length, 0);
  if (identityChars > limits.max_metadata_chars) {
    return refuse("INPUT_LIMIT", "SELECTED_ID_METADATA_BUDGET", {
      observed: identityChars, maximum: limits.max_metadata_chars});
  }
  let metadataChars = identityChars;
  const omittedMetadata = [];
  const runs = indices.map(index => {
    const row = rows[index], path = [...sourcePath, index];
    const result = {source_index: index, source_path: path, id: row.id,
      metadata_source_paths: {id: [...path, "id"]},
      withheld_fields: Object.fromEntries(WITHHELD.map(key => [key, withheld(row, key, path)]))};
    for (const key of [...STRINGS, "workflow_id", ...NUMBERS]) {
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
  return {...base, status: "PROJECTED", runs,
    coverage: {...base.coverage, retained_runs: rows.length, returned_runs: runs.length,
      selection_mode: requested === null ? "contiguous" : "source_indices",
      selected_source_indices: indices, omitted_runs: rows.length - runs.length,
      omitted_source_index_ranges: omittedRanges(rows.length, indices),
      next_index: requested === null && next < rows.length ? next : null,
      all_retained_run_headers_included: runs.length === rows.length,
      returned_metadata_chars: metadataChars, metadata_omitted_fields: omittedMetadata,
      all_selected_metadata_included: omittedMetadata.length === 0,
      retained_head_sha_fields: rows.filter(row => own(row, "head_sha")).length,
      total_count_present: own(runsPayload, "total_count")}};
}

module.exports = {projectGitHubWorkflowRunHeaders, SCHEMA, DEFAULTS};
