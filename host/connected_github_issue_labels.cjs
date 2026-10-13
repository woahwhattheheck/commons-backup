"use strict";

const SCHEMA = "commons.connected_github_issue_labels/v1";
const DEFAULTS = Object.freeze({start_index: 0, max_labels: 20,
  max_field_chars: 4096, max_total_metadata_chars: 4096, max_input_labels: 1000});
const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const OPTIONAL = ["id", "color", "default", "archived_at"];

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
    start_index: [0, Number.MAX_SAFE_INTEGER], max_labels: [0, 100],
    max_field_chars: [1, 16384], max_total_metadata_chars: [0, 1000000],
    max_input_labels: [1, 100000]
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
    if (selected.length > limits.max_labels) throw new RangeError("max_labels must accommodate source_indices");
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

function state(row, key) {
  return !own(row, key) ? "missing" : row[key] === null ? "null" : "value";
}

/** Project the labels field of one supplied issue record; no IO or text bodies. */
function projectGitHubIssueLabelHeaders(record, options) {
  const {limits, selected: requested} = readOptions(options);
  const base = {schema: SCHEMA, status: null, limits: {...limits},
    source: {representation: "supplied_record", labels_path: ["labels"],
      path_origin: "supplied_record", range_unit: "utf16_code_units", range_end: "exclusive"},
    coverage: {scope: "retained_record_labels_only", record_identity: "not_verified",
      provider_success: "not_verified", snapshot: "not_verified", labels_state: "unrecognized",
      retained_labels: null, returned_labels: 0, selection_evaluated: false,
      description_text_chars_returned: 0, other_fields_withheld: true},
    labels: [], issue: null};
  const refuse = (status, code, detail = {}) => ({...base, status, issue: {code, ...detail}});
  if (!object(record)) return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_ISSUE_RECORD");
  if (record.isError === true || record.ok === false || own(record, "error") ||
      (Number.isInteger(record.status) && record.status >= 400)) {
    return refuse("PROVIDER_ERROR", "EXPLICIT_ERROR_RECORD");
  }
  const labelsState = state(record, "labels");
  base.coverage.labels_state = labelsState === "value" && Array.isArray(record.labels) ? "array" : labelsState;
  if (labelsState === "missing" || labelsState === "null") {
    return {...base, status: "UNAVAILABLE", issue: {code: "LABELS_NOT_AVAILABLE"}};
  }
  if (!Array.isArray(record.labels)) return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_LABEL_ARRAY");
  const rows = record.labels;
  if (rows.length > limits.max_input_labels) {
    return refuse("INPUT_LIMIT", "LABEL_COUNT_LIMIT", {observed: rows.length, maximum: limits.max_input_labels});
  }
  for (let index = 0; index < rows.length; index++) {
    const row = rows[index], path = ["labels", index];
    if (!object(row) || !own(row, "name") || typeof row.name !== "string" || row.name.length === 0) {
      return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_LABEL_NAME", {source_path: path});
    }
    for (const key of OPTIONAL) {
      if (!own(row, key) || row[key] === null) continue;
      const value = row[key];
      const valid = key === "id"
        ? (Number.isSafeInteger(value) && value > 0) || (typeof value === "string" && /^[1-9][0-9]*$/.test(value))
        : key === "color" ? typeof value === "string" && /^[0-9a-fA-F]{6}$/.test(value)
        : key === "default" ? typeof value === "boolean" : typeof value === "string";
      if (!valid) return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_LABEL_FIELD", {source_path: [...path, key]});
    }
    if (own(row, "description") && row.description !== null && typeof row.description !== "string") {
      return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_DESCRIPTION_FIELD", {source_path: [...path, "description"]});
    }
    for (const key of ["name", ...OPTIONAL]) {
      if (own(row, key) && typeof row[key] === "string" && row[key].length > limits.max_field_chars) {
        return refuse("INPUT_LIMIT", "FIELD_CHAR_LIMIT", {source_path: [...path, key],
          observed: row[key].length, maximum: limits.max_field_chars});
      }
    }
  }
  if (requested !== null && requested.some(index => index >= rows.length)) {
    throw new RangeError("source_indices contains an index outside retained labels");
  }
  if (requested === null && limits.start_index > rows.length) {
    throw new RangeError("start_index exceeds the retained label count");
  }
  const indices = requested === null
    ? Array.from({length: Math.min(limits.max_labels, rows.length - limits.start_index)},
      (_, index) => limits.start_index + index)
    : requested;
  const mandatory = indices.reduce((total, index) => total + rows[index].name.length, 0);
  if (mandatory > limits.max_total_metadata_chars) {
    return refuse("INPUT_LIMIT", "SELECTED_NAME_BUDGET", {
      observed: mandatory, maximum: limits.max_total_metadata_chars});
  }
  let metadataChars = mandatory;
  const omittedFields = [];
  const labels = indices.map(index => {
    const row = rows[index], path = ["labels", index];
    const label = {source_index: index, source_path: path, name: row.name,
      metadata_states: {}, description: {state: state(row, "description"),
        source_path: [...path, "description"],
        chars: own(row, "description") && typeof row.description === "string" ? row.description.length : null}};
    for (const key of OPTIONAL) {
      label.metadata_states[key] = state(row, key);
      if (!own(row, key)) continue;
      const chars = typeof row[key] === "string" ? row[key].length : 0;
      if (metadataChars + chars > limits.max_total_metadata_chars) {
        omittedFields.push({source_path: [...path, key], chars, reason: "METADATA_CHAR_BUDGET"});
      } else { label[key] = row[key]; metadataChars += chars; }
    }
    return label;
  });
  const next = requested === null ? limits.start_index + indices.length : null;
  return {...base, status: "PROJECTED", labels,
    coverage: {...base.coverage, retained_labels: rows.length, returned_labels: labels.length,
      selection_evaluated: true, selection_mode: requested === null ? "contiguous" : "source_indices",
      selected_source_indices: indices, omitted_labels: rows.length - labels.length,
      omitted_source_index_ranges: omittedRanges(rows.length, indices),
      next_index: requested === null && next < rows.length ? next : null,
      all_retained_labels_included: labels.length === rows.length,
      returned_metadata_chars: metadataChars, omitted_optional_fields: omittedFields,
      all_selected_metadata_included: omittedFields.length === 0}};
}

module.exports = {projectGitHubIssueLabelHeaders, SCHEMA, DEFAULTS};
