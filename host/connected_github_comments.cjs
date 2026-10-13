"use strict";

// Pure views of retained native or successful token issue-comment arrays.
// No provider binding, query, filesystem, mutation, archive decoding or access decision.
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
const MAX_ROWS = 1000;

function optionsFor(options) {
  if (!object(options)) throw new TypeError("comment options must be an object");
  const allowed = new Set([
    "start_index", "source_indices", "max_comments", "include_bodies",
    "max_body_chars", "max_total_body_chars", "max_header_chars",
    "max_total_header_chars", "max_input_chars",
  ]);
  for (const key of Object.keys(options)) {
    if (!allowed.has(key)) throw new TypeError("unsupported comment option");
  }
  function bounded(name, fallback, maximum) {
    const value = own(options, name) ? options[name] : fallback;
    if (!Number.isSafeInteger(value) || value < 0 || value > maximum) {
      throw new RangeError(name + " is outside its supported integer range");
    }
    return value;
  }
  if (own(options, "include_bodies") && typeof options.include_bodies !== "boolean") {
    throw new TypeError("include_bodies must be boolean");
  }
  const includeBodies = options.include_bodies === true;
  const sparse = own(options, "source_indices");
  if (sparse && own(options, "start_index")) {
    throw new TypeError("source_indices and start_index are mutually exclusive");
  }
  if (includeBodies && !sparse) {
    throw new TypeError("body output requires explicit source_indices");
  }
  return {
    max_comments: bounded("max_comments", 20, 100),
    max_body_chars: bounded("max_body_chars", 800, 65536),
    max_total_body_chars: bounded("max_total_body_chars", 6400, 262144),
    max_header_chars: bounded("max_header_chars", 4096, 65536),
    max_total_header_chars: bounded("max_total_header_chars", 16384, 1048576),
    max_input_chars: bounded("max_input_chars", 1048576, 8388608),
    includeBodies, sparse,
    start: sparse ? null : bounded("start_index", 0, MAX_ROWS),
  };
}

function parseComments(response, maxInputChars) {
  if (!object(response)) throw new TypeError("response must be an MCP envelope object");
  if (response.isError === true) throw new TypeError("native response reports an error");
  if (own(response, "isError") && typeof response.isError !== "boolean") {
    throw new TypeError("response.isError has an invalid type");
  }
  if (!object(response.structuredContent)) {
    throw new TypeError("response needs supported structuredContent");
  }
  const payload = response.structuredContent;
  let rows, input, payloadPath, rowPath, representation;
  if (typeof payload.content === "string") {
    input = payload.content;
    if (input.length > maxInputChars) throw new RangeError("comment payload exceeds max_input_chars");
    try { rows = JSON.parse(input); }
    catch (_) { throw new TypeError("comment payload is not valid JSON"); }
    payloadPath = "structuredContent.content";
    rowPath = "JSON.parse(structuredContent.content)";
    representation = "JSON_array";
  } else if (own(payload, "data")) {
    if (payload.ok !== true || !Number.isSafeInteger(payload.status) ||
        payload.status < 200 || payload.status >= 300) {
      throw new TypeError("token response does not report successful HTTP status");
    }
    rows = payload.data;
    if (!Array.isArray(rows)) throw new TypeError("comment payload must be a JSON array");
    if (rows.length > MAX_ROWS) throw new RangeError("comment payload exceeds 1000 rows");
    try { input = JSON.stringify(rows); }
    catch (_) { throw new TypeError("comment payload cannot be serialized as JSON"); }
    if (input.length > maxInputChars) throw new RangeError("comment payload exceeds max_input_chars");
    payloadPath = "structuredContent.data";
    rowPath = payloadPath;
    representation = "array";
  } else {
    throw new TypeError("response needs supported comment payload");
  }
  if (!Array.isArray(rows)) throw new TypeError("comment payload must be a JSON array");
  if (rows.length > MAX_ROWS) throw new RangeError("comment payload exceeds 1000 rows");
  return {rows, inputChars: input.length, payloadPath, rowPath, representation};
}

function field(row, key, valid, stringLimit) {
  if (!own(row, key)) return {state: "missing"};
  const value = row[key];
  if (value === null) return {state: "null", value: null};
  if (!valid(value)) return {state: "invalid"};
  if (typeof value === "string" && value.length > stringLimit) {
    return {state: "omitted_oversize", chars: value.length};
  }
  return {state: "value", value};
}

function commentHeader(row, index, maxHeaderChars, rowPath) {
  const result = {
    source_index: index,
    source_path: rowPath + "[" + index + "]",
    row_state: object(row) ? "object" : "invalid",
    metadata: {}, metadata_states: {}, omitted_metadata_chars: {},
  };
  if (!object(row)) {
    return {...result, user_state: "unassessed", body_state: "unassessed", body_chars: null};
  }
  const validators = {
    id: value => (Number.isSafeInteger(value) && value > 0) ||
      (typeof value === "string" && /^[1-9][0-9]*$/.test(value)),
    url: value => typeof value === "string",
    html_url: value => typeof value === "string",
    issue_url: value => typeof value === "string",
    created_at: value => typeof value === "string",
    updated_at: value => typeof value === "string",
  };
  function record(name, observed) {
    result.metadata_states[name] = observed.state;
    if (own(observed, "value")) result.metadata[name] = observed.value;
    if (observed.state === "omitted_oversize") {
      result.omitted_metadata_chars[name] = observed.chars;
    }
  }
  for (const [key, valid] of Object.entries(validators)) {
    record(key, field(row, key, valid, maxHeaderChars));
  }
  result.user_state = !own(row, "user") ? "missing"
    : row.user === null ? "null" : object(row.user) ? "object" : "invalid";
  if (result.user_state === "object") {
    record("author_login", field(row.user, "login", value => typeof value === "string", maxHeaderChars));
  } else {
    result.metadata_states.author_login = "unassessed";
  }
  result.body_state = !own(row, "body") ? "missing"
    : row.body === null ? "null" : typeof row.body === "string" ? "text" : "invalid";
  result.body_chars = result.body_state === "text" ? row.body.length : null;
  return result;
}

/**
 * Project one retained supported comment array. Headers are the default.
 * Selection is local to this payload; it is not native pagination or authority.
 */
function projectGitHubRestComments(response, options = {}) {
  const config = optionsFor(options);
  const {rows, inputChars, payloadPath, rowPath, representation} =
    parseComments(response, config.max_input_chars);
  let requested;
  if (config.sparse) {
    if (!Array.isArray(options.source_indices) ||
        options.source_indices.length > config.max_comments) {
      throw new TypeError("source_indices must be an array within max_comments");
    }
    requested = options.source_indices.slice();
    let previous = -1;
    for (const index of requested) {
      if (!Number.isSafeInteger(index) || index <= previous || index >= rows.length) {
        throw new RangeError("source_indices must be increasing distinct in-range indices");
      }
      previous = index;
    }
  } else {
    if (config.start > rows.length) throw new RangeError("start_index exceeds supplied rows");
    requested = Array.from(
      {length: Math.min(config.max_comments, rows.length - config.start)},
      (_, index) => config.start + index
    );
  }

  const bodyStates = {text: 0, null: 0, missing: 0, invalid: 0, unassessed: 0};
  let suppliedBodyChars = 0;
  let invalidRows = 0;
  const headers = rows.map((row, index) => {
    const header = commentHeader(row, index, config.max_header_chars, rowPath);
    bodyStates[header.body_state] += 1;
    if (header.body_chars !== null) suppliedBodyChars += header.body_chars;
    if (header.row_state === "invalid") invalidRows += 1;
    return header;
  });

  const comments = [];
  const selected = [];
  const omittedRequested = [];
  let headerChars = 0;
  let returnedBodyChars = 0;
  let selectedBodyChars = 0;
  let truncatedBodies = 0;
  let withheldBodies = 0;
  for (const sourceIndex of requested) {
    const header = headers[sourceIndex];
    // Charge the serialized header fields, excluding this count and body output.
    const charged = JSON.stringify(header).length;
    if (charged > config.max_header_chars ||
        headerChars + charged > config.max_total_header_chars) {
      omittedRequested.push({
        source_index: sourceIndex,
        reason: charged > config.max_header_chars ? "HEADER_LIMIT" : "TOTAL_HEADER_LIMIT",
        header_chars: charged,
      });
      continue;
    }
    headerChars += charged;
    selected.push(sourceIndex);
    const projected = {
      ...header, header_chars: charged,
      body_withheld: !config.includeBodies, returned_body_chars: 0,
      body_range: null, body_truncated: null,
    };
    if (header.body_state === "text") {
      selectedBodyChars += header.body_chars;
      if (!config.includeBodies) {
        withheldBodies += 1;
      } else {
        const body = rows[sourceIndex].body;
        let end = Math.min(body.length, config.max_body_chars,
          config.max_total_body_chars - returnedBodyChars);
        if (end > 0 && end < body.length &&
            body.charCodeAt(end - 1) >= 0xd800 && body.charCodeAt(end - 1) <= 0xdbff &&
            body.charCodeAt(end) >= 0xdc00 && body.charCodeAt(end) <= 0xdfff) end -= 1;
        projected.body = body.slice(0, end);
        projected.returned_body_chars = end;
        projected.body_range = [0, end];
        projected.body_truncated = end < body.length;
        returnedBodyChars += end;
        if (projected.body_truncated) truncatedBodies += 1;
      }
    }
    comments.push(projected);
  }
  const omittedRanges = [];
  let position = 0;
  for (const index of selected) {
    if (position < index) omittedRanges.push([position, index]);
    position = index + 1;
  }
  if (position < rows.length) omittedRanges.push([position, rows.length]);

  return {
    schema: "commons.connected_github_rest_comments/v1",
    source: {
      scope: "one_supplied_envelope_only",
      payload_path: payloadPath,
      representation,
      identity_basis: "caller_supplied_native_fields",
      request_binding: "not_verified", route: "not_inferred",
      authentication: "not_performed", pagination: "not_evaluated",
      end_observed: null, snapshot: false, source_permission: "not_assessed",
      units: "UTF-16 code units", range_end: "exclusive",
      omitted_fields: "all_unlisted_native_fields",
    },
    limits: {
      max_comments: config.max_comments,
      max_body_chars: config.max_body_chars,
      max_total_body_chars: config.max_total_body_chars,
      max_header_chars: config.max_header_chars,
      max_total_header_chars: config.max_total_header_chars,
      max_input_chars: config.max_input_chars, max_input_rows: MAX_ROWS,
    },
    selection: {
      mode: config.sparse ? "explicit_source_indices" : "contiguous_headers",
      start_index: config.start, requested_source_indices: requested,
      returned_source_indices: selected, omitted_requested: omittedRequested,
      body_mode: config.includeBodies ? "explicit_bounded_selection" : "withheld",
    },
    coverage: {
      input_chars: inputChars, supplied_comments: rows.length,
      invalid_rows: invalidRows, requested_comments: requested.length,
      returned_comments: comments.length, omitted_comments: rows.length - comments.length,
      omitted_source_index_ranges: omittedRanges,
      supplied_body_states: bodyStates, supplied_text_body_chars: suppliedBodyChars,
      selected_text_body_chars: selectedBodyChars,
      returned_body_chars: returnedBodyChars, withheld_text_bodies: withheldBodies,
      truncated_text_bodies: truncatedBodies, returned_header_chars: headerChars,
      all_requested_headers_included: selected.length === requested.length,
      all_supplied_headers_included: selected.length === rows.length,
      all_selected_text_bodies_included: config.includeBodies && truncatedBodies === 0,
    },
    comments,
  };
}

module.exports = {projectGitHubRestComments};
