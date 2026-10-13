"use strict";

const SCHEMA = "commons.connected_github_commit_headers/v1";
const DEFAULTS = Object.freeze({
  start_index: 0, max_files: 8, max_message_chars: 0,
  max_header_chars: 4096, max_input_files: 10000
});
const SHA = /^[0-9a-f]{40}$/;
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const object = value => value !== null && typeof value === "object" && !Array.isArray(value);

function readOptions(value) {
  const input = value === undefined ? {} : value;
  if (!object(input)) throw new TypeError("options must be an object");
  const allowed = new Set([...Object.keys(DEFAULTS), "source_indices", "expected_commit_sha"]);
  for (const key of Object.keys(input)) {
    if (!allowed.has(key)) throw new TypeError("Unsupported option: " + key);
  }
  if (own(input, "source_indices") && own(input, "start_index")) {
    throw new TypeError("source_indices and an explicit start_index are mutually exclusive");
  }
  const limits = {...DEFAULTS}, bounds = {
    start_index: [0, Number.MAX_SAFE_INTEGER], max_files: [0, 100],
    max_message_chars: [0, 100000], max_header_chars: [128, 16384],
    max_input_files: [1, 100000]
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
    if (selected.length > limits.max_files) throw new RangeError("max_files must accommodate source_indices");
    for (let index = 0; index < selected.length; index++) {
      if (!Number.isSafeInteger(selected[index]) || selected[index] < 0 ||
          (index > 0 && selected[index] <= selected[index - 1])) {
        throw new RangeError("source_indices must be distinct increasing nonnegative integers");
      }
    }
  }
  const expected = input.expected_commit_sha;
  if (expected !== undefined && (typeof expected !== "string" || !SHA.test(expected))) {
    throw new TypeError("expected_commit_sha must be a complete lowercase commit SHA");
  }
  return {limits, selected, expected};
}

function prefixLength(text, maximum) {
  let length = Math.min(text.length, maximum);
  if (length > 0 && length < text.length &&
      text.charCodeAt(length - 1) >= 0xd800 && text.charCodeAt(length - 1) <= 0xdbff &&
      text.charCodeAt(length) >= 0xdc00 && text.charCodeAt(length) <= 0xdfff) length--;
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

/** Inspect one retained native or token commit envelope; no calls or mutations. */
function projectGitHubCommitHeaders(response, options) {
  const {limits, selected: requested, expected} = readOptions(options);
  let commitPath = ["structuredContent", "commit"];
  const base = {
    schema: SCHEMA, status: null, limits: {...limits},
    source: {representation: "native_commit", source_path: commitPath,
      range_unit: "utf16_code_units", range_end: "exclusive"},
    coverage: {scope: "retained_response_only", snapshot: false,
      provider_file_completeness: "not_inferred", diff_withheld: true,
      file_patches_withheld: true, comments_withheld: true, email_fields_withheld: true},
    commit: null, files: [], issue: null
  };
  const refuse = (status, code, detail = {}) =>
    ({...base, status, issue: {code, ...detail}});
  if (!object(response)) return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_CALL_TOOL_RESULT");
  if (response.isError === true) return refuse("PROVIDER_ERROR", "PROVIDER_ERROR_ENVELOPE");
  const payload = response.structuredContent;
  if (!object(payload)) {
    return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_NATIVE_COMMIT");
  }
  let commit, token = false;
  if (object(payload.commit)) {
    commit = payload.commit;
  } else if (own(payload, "data") && own(payload, "status") && own(payload, "ok")) {
    token = true;
    commitPath = ["structuredContent", "data"];
    base.source = {...base.source, representation: "token_commit", source_path: commitPath};
    if (!Number.isSafeInteger(payload.status) || payload.status < 100 || payload.status > 599 ||
        typeof payload.ok !== "boolean") {
      return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_TOKEN_STATUS");
    }
    if (!payload.ok || payload.status < 200 || payload.status >= 300) {
      return refuse("PROVIDER_ERROR", "TOKEN_PROVIDER_ERROR", {provider_status: payload.status});
    }
    if (!object(payload.data) || !object(payload.data.commit)) {
      return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_TOKEN_COMMIT");
    }
    commit = payload.data;
  } else {
    return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_NATIVE_COMMIT");
  }
  const message = token ? commit.commit.message : commit.message;
  const messagePath = token ? [...commitPath, "commit", "message"] : [...commitPath, "message"];
  if (typeof commit.sha !== "string" || !SHA.test(commit.sha) ||
      typeof message !== "string" || !Array.isArray(commit.files)) {
    return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_COMMIT_FIELDS");
  }
  if (expected !== undefined && commit.sha !== expected) {
    return refuse("IDENTITY_MISMATCH", "COMMIT_SHA_MISMATCH", {
      expected_commit_sha: expected, observed_commit_sha: commit.sha});
  }
  const headerFields = token ? ["url", "html_url"] :
    ["repository_full_name", "url", "html_url", "display_url", "created_at"];
  for (const key of headerFields) {
    if (!own(commit, key)) continue;
    const value = commit[key], path = [...commitPath, key];
    if (value !== null && typeof value !== "string") {
      return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_HEADER_FIELD", {source_path: path});
    }
    if (typeof value === "string" && value.length > limits.max_header_chars) {
      return refuse("INPUT_LIMIT", "HEADER_CHAR_LIMIT", {
        source_path: path, observed: value.length, maximum: limits.max_header_chars});
    }
  }
  const actors = {};
  for (const key of ["author", "committer"]) {
    if (!own(commit, key)) continue;
    const value = commit[key], path = [...commitPath, key];
    if (value === null) { actors[key] = null; continue; }
    if (!object(value)) return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_ACTOR_FIELD", {source_path: path});
    const actor = {source_path: path, metadata_source_paths: {}};
    if (own(value, "login")) {
      if (value.login !== null && typeof value.login !== "string") {
        return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_ACTOR_LOGIN", {source_path: [...path, "login"]});
      }
      if (typeof value.login === "string" && value.login.length > limits.max_header_chars) {
        return refuse("INPUT_LIMIT", "HEADER_CHAR_LIMIT", {source_path: [...path, "login"],
          observed: value.login.length, maximum: limits.max_header_chars});
      }
      actor.login = value.login;
      actor.metadata_source_paths.login = [...path, "login"];
    }
    if (own(value, "id")) {
      if (value.id !== null &&
          !(Number.isSafeInteger(value.id) && value.id >= 0) &&
          !(typeof value.id === "string" && /^[0-9]+$/.test(value.id) &&
            value.id.length <= limits.max_header_chars)) {
        return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_ACTOR_ID", {source_path: [...path, "id"]});
      }
      actor.id = value.id;
      actor.metadata_source_paths.id = [...path, "id"];
    }
    actors[key] = actor;
  }
  const rows = commit.files;
  if (rows.length > limits.max_input_files) {
    return refuse("INPUT_LIMIT", "FILES_LIMIT", {observed: rows.length, maximum: limits.max_input_files});
  }
  for (let index = 0; index < rows.length; index++) {
    const row = rows[index], path = [...commitPath, "files", index];
    if (!object(row) || typeof row.filename !== "string") {
      return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_FILE_HEADER", {source_path: path});
    }
    if (row.filename.length > limits.max_header_chars) {
      return refuse("INPUT_LIMIT", "HEADER_CHAR_LIMIT", {source_path: [...path, "filename"],
        observed: row.filename.length, maximum: limits.max_header_chars});
    }
    if (own(row, "patch") && row.patch !== null && typeof row.patch !== "string") {
      return refuse("UNSUPPORTED_REPRESENTATION", "INVALID_FILE_PATCH_FIELD", {source_path: [...path, "patch"]});
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
  const messageLength = prefixLength(message, limits.max_message_chars);
  const header = {sha: commit.sha, metadata_source_paths: {sha: [...commitPath, "sha"]},
    message: message.slice(0, messageLength), message_source_path: messagePath,
    message_chars: message.length, returned_message_chars: messageLength,
    returned_message_range: [0, messageLength], message_truncated: messageLength < message.length};
  for (const key of headerFields) {
    if (!own(commit, key)) continue;
    header[key] = commit[key];
    header.metadata_source_paths[key] = [...commitPath, key];
  }
  for (const [key, value] of Object.entries(actors)) header[key] = value;
  const files = indices.map(index => {
    const row = rows[index], path = [...commitPath, "files", index];
    const result = {source_index: index, source_path: path, filename: row.filename,
      filename_source_path: [...path, "filename"], patch_present: own(row, "patch"),
      patch_withheld: true};
    if (own(row, "patch")) {
      result.patch_source_path = [...path, "patch"];
      result.patch_chars = typeof row.patch === "string" ? row.patch.length : null;
    }
    return result;
  });
  const next = requested === null ? limits.start_index + indices.length : null;
  return {...base, status: "PROJECTED", commit: header, files,
    coverage: {...base.coverage, retained_files: rows.length, returned_files: files.length,
      selection_mode: requested === null ? "contiguous" : "source_indices",
      selected_source_indices: indices, omitted_files: rows.length - files.length,
      omitted_source_index_ranges: omittedRanges(rows.length, indices),
      next_index: requested === null && next < rows.length ? next : null,
      all_retained_file_headers_included: files.length === rows.length,
      diff_present: own(commit, "diff"),
      diff_chars: typeof commit.diff === "string" ? commit.diff.length : null,
      comments_present: own(commit, "comments")}};
}

module.exports = {projectGitHubCommitHeaders, SCHEMA, DEFAULTS};
