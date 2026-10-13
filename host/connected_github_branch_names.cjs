"use strict";

const SCHEMA = "commons.connected_github_branch_names/v1";
const DEFAULTS = Object.freeze({start_index: 0, max_branches: 10,
  max_name_chars: 4096, max_total_name_chars: 4096, max_input_branches: 10000});
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
    start_index: [0, Number.MAX_SAFE_INTEGER], max_branches: [0, 100],
    max_name_chars: [1, 16384], max_total_name_chars: [0, 1000000],
    max_input_branches: [1, 100000]
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
    if (selected.length > limits.max_branches) throw new RangeError("max_branches must accommodate source_indices");
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

/** Project an unchanged native search_branches page without reads or mutations. */
function projectGitHubBranchNames(response, options) {
  const {limits, selected: requested} = readOptions(options);
  const sourcePath = ["structuredContent", "branches"];
  const base = {schema: SCHEMA, status: null, limits: {...limits},
    source: {representation: "native_branch_search", source_path: sourcePath,
      range_unit: "utf16_code_units", range_end: "exclusive"},
    coverage: {scope: "retained_response_only", snapshot: false,
      provider_result_completeness: "not_inferred", provider_pagination: "not_inferred",
      repository_binding: "not_inferred", ref_resolution: "not_performed",
      branch_state: "not_inferred", other_fields_withheld: true},
    branches: [], issue: null};
  const refuse = (status, code, detail = {}) => ({...base, status, issue: {code, ...detail}});
  if (!object(response)) return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_CALL_TOOL_RESULT");
  if (response.isError === true) return refuse("PROVIDER_ERROR", "PROVIDER_ERROR_ENVELOPE");
  const payload = response.structuredContent;
  if (!object(payload)) return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_NATIVE_BRANCH_SEARCH");
  if (payload.isError === true || payload.ok === false || own(payload, "error") ||
      (Number.isInteger(payload.status) && payload.status >= 400)) {
    return refuse("PROVIDER_ERROR", "PROVIDER_ERROR_PAYLOAD");
  }
  if (!Array.isArray(payload.branches)) return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_NATIVE_BRANCH_SEARCH");
  const rows = payload.branches;
  if (rows.length > limits.max_input_branches) {
    return refuse("INPUT_LIMIT", "BRANCHES_LIMIT", {observed: rows.length, maximum: limits.max_input_branches});
  }
  for (let index = 0; index < rows.length; index++) {
    const row = rows[index], path = [...sourcePath, index, "branch"];
    if (!object(row) || typeof row.branch !== "string" || row.branch.length === 0) {
      return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_BRANCH_NAME", {source_path: path});
    }
    if (row.branch.length > limits.max_name_chars) {
      return refuse("INPUT_LIMIT", "NAME_CHAR_LIMIT", {source_path: path,
        observed: row.branch.length, maximum: limits.max_name_chars});
    }
  }
  const cursorPresent = own(payload, "cursor"), cursor = payload.cursor;
  if (cursorPresent && cursor !== null && typeof cursor !== "string") {
    return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_CURSOR", {source_path: ["structuredContent", "cursor"]});
  }
  if (requested !== null && requested.some(index => index >= rows.length)) {
    throw new RangeError("source_indices contains an index outside retained branches");
  }
  if (requested === null && limits.start_index > rows.length) {
    throw new RangeError("start_index exceeds the retained branch count");
  }
  const indices = requested === null
    ? Array.from({length: Math.min(limits.max_branches, rows.length - limits.start_index)},
      (_, index) => limits.start_index + index)
    : requested;
  const nameChars = indices.reduce((total, index) => total + rows[index].branch.length, 0);
  if (nameChars > limits.max_total_name_chars) {
    return refuse("INPUT_LIMIT", "SELECTED_NAME_CHAR_BUDGET", {
      observed: nameChars, maximum: limits.max_total_name_chars});
  }
  const branches = indices.map(index => ({source_index: index, source_path: [...sourcePath, index],
    branch: rows[index].branch, branch_source_path: [...sourcePath, index, "branch"],
    branch_chars: rows[index].branch.length}));
  const next = requested === null ? limits.start_index + indices.length : null;
  return {...base, status: "PROJECTED", branches,
    provider_cursor: {present: cursorPresent, source_path: ["structuredContent", "cursor"],
      value_type: !cursorPresent ? "absent" : cursor === null ? "null" : "string",
      ...(typeof cursor === "string" ? {retained_chars: cursor.length} : {}), value_withheld: true},
    coverage: {...base.coverage, retained_branches: rows.length, returned_branches: branches.length,
      selection_mode: requested === null ? "contiguous" : "source_indices",
      selected_source_indices: indices, omitted_branches: rows.length - branches.length,
      omitted_source_index_ranges: omittedRanges(rows.length, indices),
      next_index: requested === null && next < rows.length ? next : null,
      all_retained_names_included: branches.length === rows.length, returned_name_chars: nameChars}};
}

module.exports = {projectGitHubBranchNames, SCHEMA, DEFAULTS};
