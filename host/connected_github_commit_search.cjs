"use strict";

const SCHEMA = "commons.connected_github_commit_search/v1";
const DEFAULTS = Object.freeze({
  start_index: 0, max_commits: 10, max_message_chars: 0,
  max_total_message_chars: 4096, max_metadata_chars: 4096,
  max_header_chars: 4096, max_input_commits: 10000
});
const SHA = /^[0-9a-f]{40}$/;
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
const HEADER_FIELDS = ["repository_full_name", "url", "html_url", "display_url", "created_at"];

function readOptions(value) {
  const input = value === undefined ? {} : value;
  if (!object(input)) throw new TypeError("options must be an object");
  const allowed = new Set([...Object.keys(DEFAULTS), "source_indices", "expected_repository_full_name"]);
  for (const key of Object.keys(input)) {
    if (!allowed.has(key)) throw new TypeError("Unsupported option: " + key);
  }
  if (own(input, "source_indices") && own(input, "start_index")) {
    throw new TypeError("source_indices and an explicit start_index are mutually exclusive");
  }
  const limits = {...DEFAULTS}, bounds = {
    start_index: [0, Number.MAX_SAFE_INTEGER], max_commits: [0, 100],
    max_message_chars: [0, 100000], max_total_message_chars: [0, 1000000],
    max_metadata_chars: [0, 1000000], max_header_chars: [40, 16384],
    max_input_commits: [1, 100000]
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
    if (selected.length > limits.max_commits) throw new RangeError("max_commits must accommodate source_indices");
    for (let index = 0; index < selected.length; index++) {
      if (!Number.isSafeInteger(selected[index]) || selected[index] < 0 ||
          (index > 0 && selected[index] <= selected[index - 1])) {
        throw new RangeError("source_indices must be distinct increasing nonnegative integers");
      }
    }
  }
  const repository = input.expected_repository_full_name;
  if (repository !== undefined &&
      (typeof repository !== "string" || !/^[^/\s?#]+\/[^/\s?#]+$/.test(repository))) {
    throw new TypeError("expected_repository_full_name must have owner/name form");
  }
  return {limits, selected, repository};
}

function prefixLength(value, maximum) {
  let length = Math.min(value.length, maximum);
  if (length > 0 && length < value.length &&
      value.charCodeAt(length - 1) >= 0xd800 && value.charCodeAt(length - 1) <= 0xdbff &&
      value.charCodeAt(length) >= 0xdc00 && value.charCodeAt(length) <= 0xdfff) length--;
  return length;
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

function withheldField(row, key, path) {
  const present = own(row, key), value = present ? row[key] : undefined;
  return {present, source_path: [...path, key],
    value_type: !present ? "absent" : value === null ? "null" :
      Array.isArray(value) ? "array" : typeof value,
    ...(Array.isArray(value) ? {retained_count: value.length} : {}),
    ...(typeof value === "string" ? {retained_chars: value.length} : {}),
    withheld: true};
}

/** Project an unchanged native search_commits envelope; no reads or mutations. */
function projectGitHubCommitSearchHeaders(response, options) {
  const {limits, selected: requested, repository} = readOptions(options);
  const sourcePath = ["structuredContent", "commits"];
  const base = {schema: SCHEMA, status: null, limits: {...limits},
    source: {representation: "native_commit_search", source_path: sourcePath,
      range_unit: "utf16_code_units", range_end: "exclusive"},
    coverage: {scope: "retained_response_only", snapshot: false,
      provider_result_completeness: "not_inferred", pagination: "not_inferred",
      diff_withheld: true, file_content_withheld: true,
      comments_withheld: true, email_fields_withheld: true},
    commits: [], issue: null};
  const refuse = (status, code, detail = {}) =>
    ({...base, status, issue: {code, ...detail}});
  if (!object(response)) return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_CALL_TOOL_RESULT");
  if (response.isError === true) return refuse("PROVIDER_ERROR", "PROVIDER_ERROR_ENVELOPE");
  const payload = response.structuredContent;
  if (!object(payload)) return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_NATIVE_COMMIT_SEARCH");
  if (payload.isError === true || payload.ok === false || own(payload, "error") ||
      (Number.isInteger(payload.status) && payload.status >= 400)) {
    return refuse("PROVIDER_ERROR", "PROVIDER_ERROR_PAYLOAD");
  }
  if (!Array.isArray(payload.commits) || own(payload, "commit")) {
    return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_NATIVE_COMMIT_SEARCH");
  }
  const rows = payload.commits;
  if (rows.length > limits.max_input_commits) {
    return refuse("INPUT_LIMIT", "COMMITS_LIMIT", {observed: rows.length, maximum: limits.max_input_commits});
  }
  for (let index = 0; index < rows.length; index++) {
    const row = rows[index], path = [...sourcePath, index];
    if (!object(row) || typeof row.sha !== "string" || !SHA.test(row.sha) ||
        typeof row.message !== "string") {
      return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_COMMIT_FIELDS", {source_path: path});
    }
    for (const key of HEADER_FIELDS) {
      if (!own(row, key)) continue;
      const value = row[key];
      if (value !== null && typeof value !== "string") {
        return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_HEADER_FIELD", {source_path: [...path, key]});
      }
      if (typeof value === "string" && value.length > limits.max_header_chars) {
        return refuse("INPUT_LIMIT", "HEADER_CHAR_LIMIT", {source_path: [...path, key],
          observed: value.length, maximum: limits.max_header_chars});
      }
    }
    if (repository !== undefined && row.repository_full_name !== repository) {
      return refuse("IDENTITY_MISMATCH", "REPOSITORY_MISMATCH", {
        source_path: [...path, "repository_full_name"], expected_repository_full_name: repository,
        observed_repository_full_name: own(row, "repository_full_name") ? row.repository_full_name : null});
    }
    for (const key of ["author", "committer"]) {
      if (!own(row, key) || row[key] === null) continue;
      const actor = row[key], actorPath = [...path, key];
      if (!object(actor)) {
        return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_ACTOR_FIELD", {source_path: actorPath});
      }
      if (own(actor, "login") && actor.login !== null && typeof actor.login !== "string") {
        return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_ACTOR_LOGIN", {source_path: [...actorPath, "login"]});
      }
      if (typeof actor.login === "string" && actor.login.length > limits.max_header_chars) {
        return refuse("INPUT_LIMIT", "HEADER_CHAR_LIMIT", {source_path: [...actorPath, "login"],
          observed: actor.login.length, maximum: limits.max_header_chars});
      }
      if (own(actor, "id") && actor.id !== null &&
          !(Number.isSafeInteger(actor.id) && actor.id >= 0) &&
          !(typeof actor.id === "string" && /^[0-9]+$/.test(actor.id) &&
            actor.id.length <= limits.max_header_chars)) {
        return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_ACTOR_ID", {source_path: [...actorPath, "id"]});
      }
    }
  }
  if (requested !== null && requested.some(index => index >= rows.length)) {
    throw new RangeError("source_indices contains an index outside retained commits");
  }
  if (requested === null && limits.start_index > rows.length) {
    throw new RangeError("start_index exceeds the retained commit count");
  }
  const indices = requested === null
    ? Array.from({length: Math.min(limits.max_commits, rows.length - limits.start_index)},
      (_, index) => limits.start_index + index)
    : requested;
  const mandatoryChars = indices.length * 40;
  if (mandatoryChars > limits.max_metadata_chars) {
    return refuse("INPUT_LIMIT", "SELECTED_SHA_METADATA_BUDGET", {
      observed: mandatoryChars, maximum: limits.max_metadata_chars});
  }
  let metadataChars = mandatoryChars, messageChars = 0;
  const omittedMetadata = [];
  function copyField(target, key, value, path, paths) {
    const chars = typeof value === "string" ? value.length : 0;
    if (metadataChars + chars > limits.max_metadata_chars) {
      omittedMetadata.push({source_path: path, chars, reason: "METADATA_CHAR_BUDGET"});
      return;
    }
    target[key] = value;
    paths[key] = path;
    metadataChars += chars;
  }
  const commits = indices.map(index => {
    const row = rows[index], path = [...sourcePath, index];
    const length = prefixLength(row.message,
      Math.min(limits.max_message_chars, limits.max_total_message_chars - messageChars));
    messageChars += length;
    const result = {source_index: index, source_path: path, sha: row.sha,
      metadata_source_paths: {sha: [...path, "sha"]},
      message: row.message.slice(0, length), message_source_path: [...path, "message"],
      message_chars: row.message.length, returned_message_chars: length,
      returned_message_range: [0, length], message_truncated: length < row.message.length,
      withheld_fields: Object.fromEntries(["diff", "files", "comments", "git_author_email"]
        .map(key => [key, withheldField(row, key, path)]))};
    for (const key of HEADER_FIELDS) {
      if (own(row, key)) copyField(result, key, row[key], [...path, key], result.metadata_source_paths);
    }
    for (const key of ["author", "committer"]) {
      if (!own(row, key)) continue;
      result.metadata_source_paths[key] = [...path, key];
      if (row[key] === null) {result[key] = null; continue;}
      const actor = {source_path: [...path, key], metadata_source_paths: {}, email_fields_withheld: true};
      for (const field of ["login", "id"]) {
        if (own(row[key], field)) copyField(actor, field, row[key][field],
          [...path, key, field], actor.metadata_source_paths);
      }
      result[key] = actor;
    }
    return result;
  });
  const next = requested === null ? limits.start_index + indices.length : null;
  return {...base, status: "PROJECTED", commits,
    coverage: {...base.coverage, retained_commits: rows.length, returned_commits: commits.length,
      selection_mode: requested === null ? "contiguous" : "source_indices",
      selected_source_indices: indices, omitted_commits: rows.length - commits.length,
      omitted_source_index_ranges: omittedRanges(rows.length, indices),
      next_index: requested === null && next < rows.length ? next : null,
      all_retained_commit_headers_included: commits.length === rows.length,
      returned_metadata_chars: metadataChars, returned_message_chars: messageChars,
      metadata_omitted_fields: omittedMetadata,
      all_selected_metadata_included: omittedMetadata.length === 0}};
}

module.exports = {projectGitHubCommitSearchHeaders, SCHEMA, DEFAULTS};
