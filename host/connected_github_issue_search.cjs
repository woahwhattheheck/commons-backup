"use strict";

// Use the approved native REST route without translating GitHub query syntax.
// The caller supplies the connected tool surface; this module owns no network
// client, credentials, filesystem, scheduler, or mutation operation.
const FETCH = "mcp__codex_apps__github_fetch";
const TOKEN_READ = "mcp__codex_apps__github_token_connection_github_read";
const SEARCH_LIMIT = 1000;
const SORTS = new Set([
  "comments", "reactions", "reactions-+1", "reactions--1", "reactions-smile",
  "reactions-thinking_face", "reactions-heart", "reactions-tada",
  "interactions", "created", "updated",
]);

function object(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function positiveInteger(value, name) {
  if (!Number.isSafeInteger(value) || value < 1) {
    throw new TypeError(name + " must be a positive safe integer");
  }
  return value;
}

function configFor(input) {
  if (!object(input)) throw new TypeError("input must be an object");
  const keys = new Set([
    "query", "sort", "order", "per_page", "start_page", "max_pages", "timeout_ms",
    "updated_at_lte",
  ]);
  for (const key of Object.keys(input)) {
    if (!keys.has(key)) throw new TypeError("unknown input field: " + key);
  }
  if (typeof input.query !== "string" || !input.query.trim()) {
    throw new TypeError("query must be a nonempty GitHub search string");
  }
  const sort = input.sort ?? null;
  if (sort !== null && !SORTS.has(sort)) throw new TypeError("unsupported sort");
  const order = input.order ?? "desc";
  if (order !== "asc" && order !== "desc") {
    throw new TypeError("order must be asc or desc");
  }
  const perPage = positiveInteger(input.per_page ?? 100, "per_page");
  if (perPage > 100) throw new TypeError("per_page exceeds GitHub's maximum of 100");
  const startPage = positiveInteger(input.start_page ?? 1, "start_page");
  const maxPages = positiveInteger(input.max_pages ?? 4, "max_pages");
  const timeout = input.timeout_ms ?? 30000;
  if (typeof timeout !== "number" || !Number.isFinite(timeout) || timeout < 0) {
    throw new TypeError("timeout_ms must be a finite nonnegative number");
  }
  const hasBound = Object.prototype.hasOwnProperty.call(input, "updated_at_lte");
  if (hasBound && canonicalUtcInstant(input.updated_at_lte) === null) {
    throw new TypeError("updated_at_lte must be a valid UTC timestamp with seconds or three fractional digits");
  }
  return {
    query: input.query, sort, order, perPage, startPage, maxPages, timeout,
    updatedAtLte: hasBound ? input.updated_at_lte : null,
  };
}

function searchPayload(value) {
  if (!object(value)) return null;
  if (value.isError === true || value.ok === false ||
      Object.prototype.hasOwnProperty.call(value, "error") ||
      (Number.isInteger(value.status) && value.status >= 400)) {
    const error = new Error("native GitHub response reports an error");
    error.code = "NATIVE_ERROR";
    throw error;
  }
  if (Array.isArray(value.items)) return value;
  if (value.ok === true && Number.isInteger(value.status) &&
      value.status >= 200 && value.status < 300 && object(value.data) &&
      Array.isArray(value.data.items)) return value.data;
  return null;
}

function decode(response) {
  const candidates = [response && response.structuredContent, response];
  for (const candidate of candidates) {
    if (!object(candidate)) continue;
    const payload = searchPayload(candidate);
    if (payload) return payload;
    if (typeof candidate.content === "string") {
      const parsed = JSON.parse(candidate.content);
      const payload = searchPayload(parsed);
      if (payload) return payload;
    }
  }
  for (const item of response && Array.isArray(response.content) ? response.content : []) {
    if (item.type !== "text" || typeof item.text !== "string") continue;
    try {
      const parsed = JSON.parse(item.text);
      const payload = searchPayload(parsed);
      if (payload) return payload;
    } catch (error) {
      if (error.code === "NATIVE_ERROR") throw error;
      // Ordinary provider status text is not a search payload.
    }
  }
  throw new TypeError("native response has no issue-search payload");
}

function diagnostic(value) {
  if (value instanceof Error) return value.message.slice(0, 1200);
  if (value && Array.isArray(value.content)) {
    return value.content.filter(item => item.type === "text")
      .map(item => item.text).join("\n").slice(0, 1200);
  }
  return String(value).slice(0, 1200);
}

function itemIdentity(row) {
  if (!object(row)) throw new TypeError("search item must be an object");
  let id;
  if (typeof row.id === "number") id = String(positiveInteger(row.id, "item.id"));
  else if (typeof row.id === "string" && /^[1-9][0-9]*$/.test(row.id)) id = row.id;
  else throw new TypeError("item.id must be a positive integer or decimal ID string");
  positiveInteger(row.number, "item.number");
  if (typeof row.url !== "string" || typeof row.html_url !== "string") {
    throw new TypeError("search item URLs are missing");
  }
  if (row.pull_request != null && !object(row.pull_request)) {
    throw new TypeError("item.pull_request must be an object when present");
  }
  return id;
}

/**
 * Read native issue/PR search pages with the caller's exact GitHub query.
 *
 * Items retain their original native fields, including pull_request metadata.
 * onResponse can retain each original MCP response privately. Completeness is
 * limited to this observed search traversal, never a repository inventory.
 */
async function searchGitHubIssues(tools, input, options = {}) {
  const config = configFor(input);
  if (!object(options) || Object.keys(options).some(key =>
    key !== "onResponse" && key !== "transport")) {
    throw new TypeError("options supports only onResponse and transport");
  }
  if (options.onResponse !== undefined && typeof options.onResponse !== "function") {
    throw new TypeError("onResponse must be a function");
  }
  const transport = options.transport ?? "native";
  if (transport !== "native" && transport !== "token") {
    throw new TypeError("transport must be native or token");
  }
  const binding = transport === "token" ? TOKEN_READ : FETCH;
  if (!tools || typeof tools[binding] !== "function") {
    throw new TypeError("the connected " + binding + " action is not available");
  }
  // These characters are query-safe; reserved parameter delimiters stay escaped.
  // Avoid the token connector's observed rejection of an encoded query slash.
  const encodeQuery = value => transport === "token"
    ? encodeURIComponent(value).replace(/%2F/gi, "/").replace(/%3A/gi, ":")
      .replace(/%20/g, "+")
    : encodeURIComponent(value);
  const started = Date.now();
  const seen = new Set();
  const repeated = new Set();
  const totals = new Set();
  const result = {
    schema: "commons.connected_github_issue_search/v1",
    status: "INCONCLUSIVE",
    query: config.query,
    query_application: "not_verified",
    sort: config.sort,
    order: config.order,
    items: [],
    coverage: {
      complete: false,
      search_index: true,
      snapshot: false,
      pagination: "live_offset_pages",
      start_page: config.startPage,
      per_page: config.perPage,
      api_search_limit: SEARCH_LIMIT,
      end_observed: false,
      provider_incomplete: false,
      pages: [],
      total_counts: [],
      repeated_item_ids: [],
      next_page: config.startPage,
      gaps: config.startPage === 1 ? [] : ["STARTED_AFTER_FIRST_PAGE"],
    },
    stats: {
      calls: 0, pages_read: 0, items_received: 0,
      unique_items: 0, issues: 0, pull_requests: 0,
    },
    callback_errors: [],
    started_at: new Date(started).toISOString(),
  };
  if (transport === "token") result.request = { transport, binding };
  const gap = code => {
    if (!result.coverage.gaps.includes(code)) result.coverage.gaps.push(code);
  };
  function finish(code, detail = {}) {
    result.coverage.total_counts = [...totals];
    result.coverage.repeated_item_ids = [...repeated];
    result.stats.unique_items = seen.size;
    result.stop = { code, ...detail };
    result.finished_at = new Date().toISOString();
    result.elapsed_ms = Date.now() - started;
    if (config.updatedAtLte !== null) {
      result.updated_at_bound = inspectGitHubIssueUpdatedAtBound(result.items, config.updatedAtLte);
    }
    result.status = result.items.length > 0 ? "FOUND"
      : result.coverage.complete ? "NOT_FOUND_IN_QUERY" : "INCONCLUSIVE";
    return result;
  }
  let page = config.startPage;
  while (result.stats.calls < config.maxPages) {
    if (Date.now() - started >= config.timeout) return finish("DEADLINE");
    const offset = (page - 1) * config.perPage;
    if (!Number.isSafeInteger(offset) || offset >= SEARCH_LIMIT) {
      gap("SEARCH_RESULT_LIMIT");
      return finish("SEARCH_RESULT_LIMIT");
    }
    const query = {
      q: config.query,
      ...(config.sort === null ? {} : { sort: config.sort }),
      order: config.order,
      per_page: String(config.perPage),
      page: String(page),
    };
    const path = "/search/issues?" + Object.entries(query)
      .map(([key, value]) => encodeQuery(key) + "=" + encodeQuery(value))
      .join("&");
    const url = "https://api.github.com" + path;
    result.coverage.next_page = page;
    result.stats.calls += 1;
    let response;
    try {
      response = await tools[binding](transport === "token" ? { path } : { url });
    } catch (error) {
      return finish("TOOL_ERROR", { url, native_message: diagnostic(error) });
    }
    if (options.onResponse) {
      try {
        await options.onResponse({ page, url, response,
          ...(transport === "token" ? { path, binding } : {}) });
      } catch (error) {
        result.callback_errors.push({ page, message: diagnostic(error) });
      }
    }
    if (response && response.isError) {
      return finish("NATIVE_ERROR", { url, native_message: diagnostic(response) });
    }
    let payload;
    try {
      payload = decode(response);
      if (!Array.isArray(payload.items) ||
          !Number.isSafeInteger(payload.total_count) || payload.total_count < 0 ||
          typeof payload.incomplete_results !== "boolean" ||
          payload.items.length > config.perPage) {
        throw new TypeError("invalid items, total_count, incomplete_results, or page length");
      }
    } catch (error) {
      return finish(error.code === "NATIVE_ERROR" ? "NATIVE_ERROR" : "INVALID_RESPONSE",
        { url, native_message: diagnostic(error) });
    }
    const rows = payload.items;
    totals.add(payload.total_count);
    if (totals.size > 1) gap("TOTAL_COUNT_CHANGED");
    if (payload.total_count >= SEARCH_LIMIT) gap("SEARCH_RESULT_LIMIT");
    if (payload.incomplete_results) {
      result.coverage.provider_incomplete = true;
      gap("PROVIDER_INCOMPLETE_RESULTS");
    }
    const observation = {
      page, url, total_count: payload.total_count,
      incomplete_results: payload.incomplete_results,
      received: rows.length, retained: 0,
    };
    if (transport === "token") observation.path = path;
    result.coverage.pages.push(observation);
    result.stats.pages_read += 1;
    result.stats.items_received += rows.length;
    for (let index = 0; index < rows.length; index += 1) {
      const row = rows[index];
      let id;
      try {
        id = itemIdentity(row);
      } catch (error) {
        return finish("INVALID_RESPONSE", { url, row_index: index, native_message: diagnostic(error) });
      }
      if (seen.has(id)) {
        repeated.add(id);
        gap("REPEATED_ITEM_ID");
        continue;
      }
      seen.add(id);
      result.items.push(row);
      observation.retained += 1;
      if (row.pull_request == null) result.stats.issues += 1;
      else result.stats.pull_requests += 1;
    }
    result.coverage.next_page = page + 1;
    const shortPage = rows.length < config.perPage;
    const observedTotal = config.startPage === 1 && seen.size >= payload.total_count;
    if (shortPage || observedTotal) {
      result.coverage.end_observed = true;
      result.coverage.next_page = null;
      if (config.startPage === 1 && seen.size !== payload.total_count) {
        gap("ADVERTISED_TOTAL_MISMATCH");
      }
      result.coverage.complete = config.startPage === 1 &&
        result.coverage.gaps.length === 0 && seen.size === payload.total_count;
      return finish(shortPage ? "PAGINATION_END" : "ADVERTISED_TOTAL_REACHED");
    }
    if (offset + rows.length >= SEARCH_LIMIT) {
      gap("SEARCH_RESULT_LIMIT");
      return finish("SEARCH_RESULT_LIMIT");
    }
    page += 1;
  }
  return finish("PAGE_BUDGET");
}

function canonicalUtcInstant(value) {
  if (typeof value !== "string" ||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(value)) return null;
  const milliseconds = Date.parse(value);
  if (!Number.isFinite(milliseconds)) return null;
  const canonical = value.length === 20 ? value.slice(0, -1) + ".000Z" : value;
  return new Date(milliseconds).toISOString() === canonical ? milliseconds : null;
}

/**
 * Observe one caller-declared updated_at upper bound on retained native items.
 * This does not parse the query, filter rows, or establish query fidelity.
 */
function inspectGitHubIssueUpdatedAtBound(items, updatedAtLte, options = {}) {
  if (!Array.isArray(items) || items.length > SEARCH_LIMIT) {
    throw new TypeError("items must be an array containing at most 1000 entries");
  }
  const bound = canonicalUtcInstant(updatedAtLte);
  if (bound === null) {
    throw new TypeError("updated_at_lte must be a valid UTC timestamp with seconds or three fractional digits");
  }
  if (!object(options) || Object.keys(options).some(key => key !== "max_records")) {
    throw new TypeError("bound options supports only max_records");
  }
  const maxRecords = options.max_records === undefined ? 20 : options.max_records;
  if (!Number.isSafeInteger(maxRecords) || maxRecords < 0 || maxRecords > 100) {
    throw new RangeError("max_records must be an integer from 0 through 100");
  }
  const stats = {
    supplied_items: items.length, evaluated_items: 0, within_bound: 0,
    mismatches: 0, missing_updated_at: 0, invalid_updated_at: 0,
  };
  const records = [];
  let diagnosticCount = 0;
  for (let sourceIndex = 0; sourceIndex < items.length; sourceIndex += 1) {
    const row = items[sourceIndex];
    itemIdentity(row);
    const present = Object.prototype.hasOwnProperty.call(row, "updated_at");
    const observed = present ? canonicalUtcInstant(row.updated_at) : null;
    let observation = null;
    if (!present) {
      stats.missing_updated_at += 1;
      observation = "missing";
    } else if (observed === null) {
      stats.invalid_updated_at += 1;
      observation = "invalid";
    } else {
      stats.evaluated_items += 1;
      if (observed > bound) {
        stats.mismatches += 1;
        observation = "mismatch";
      } else stats.within_bound += 1;
    }
    if (observation !== null) {
      diagnosticCount += 1;
      if (records.length < maxRecords) {
        records.push({
          source_index: sourceIndex, id: row.id, number: row.number,
          kind: row.pull_request == null ? "issue" : "pull_request",
          observation, updated_at: observed === null ? null : row.updated_at,
        });
      }
    }
  }
  return {
    schema: "commons.connected_github_issue_updated_at_bound/v1",
    status: stats.mismatches > 0 ? "mismatch"
      : items.length > 0 && stats.evaluated_items === items.length
        ? "no_mismatch_observed" : "unevaluated",
    query_application: "not_verified",
    scope: "supplied_items_only",
    query_syntax_parsed: false,
    bound: { field: "updated_at", operator: "<=", value: updatedAtLte, basis: "caller_declared" },
    limits: { max_input_items: SEARCH_LIMIT, max_records: maxRecords },
    stats, records,
    diagnostic_records: diagnosticCount,
    omitted_diagnostic_records: diagnosticCount - records.length,
    all_supplied_timestamps_evaluated: stats.evaluated_items === items.length,
  };
}


/**
 * Project selected bodies from already retained native issue/PR item objects.
 * This function performs no tool calls and says nothing about query coverage.
 */
function projectGitHubIssueItems(items, options = {}) {
  if (!Array.isArray(items) || items.length > SEARCH_LIMIT) {
    throw new TypeError("items must be an array containing at most 1000 entries");
  }
  if (!object(options)) throw new TypeError("projection options must be an object");
  const allowed = new Set([
    "start_index", "source_indices", "max_items", "max_body_chars",
    "max_total_body_chars", "max_metadata_chars",
  ]);
  for (const key of Object.keys(options)) {
    if (!allowed.has(key)) throw new TypeError("unknown projection option: " + key);
  }
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  function bounded(name, fallback, maximum) {
    const value = own(options, name) ? options[name] : fallback;
    if (!Number.isSafeInteger(value) || value < 0 || value > maximum) {
      throw new RangeError(name + " must be an integer from 0 through " + maximum);
    }
    return value;
  }
  const maxItems = bounded("max_items", 12, 100);
  const maxBody = bounded("max_body_chars", 500, 100000);
  const totalBody = bounded("max_total_body_chars", 6000, 1000000);
  const maxMetadata = bounded("max_metadata_chars", 4096, 65536);
  const sparse = own(options, "source_indices");
  let start = null;
  let indices;
  if (sparse) {
    if (own(options, "start_index")) {
      throw new TypeError("source_indices and start_index are mutually exclusive");
    }
    if (!Array.isArray(options.source_indices) || options.source_indices.length > maxItems) {
      throw new TypeError("source_indices must be an array within max_items");
    }
    indices = options.source_indices.slice();
    let previous = -1;
    for (const index of indices) {
      if (!Number.isSafeInteger(index) || index <= previous || index >= items.length) {
        throw new RangeError("source_indices must be increasing distinct in-range indices");
      }
      previous = index;
    }
  } else {
    start = bounded("start_index", 0, items.length);
    indices = Array.from({length: Math.min(maxItems, items.length - start)}, (_, i) => start + i);
  }

  const sourceBodies = {text: 0, null: 0, missing: 0};
  let sourceBodyChars = 0;
  const rows = Array.from(items, (row, sourceIndex) => {
    itemIdentity(row);
    if (typeof row.title !== "string" || typeof row.state !== "string") {
      throw new TypeError("item " + sourceIndex + " needs string title and state");
    }
    const metadata = {
      id: row.id, number: row.number,
      kind: row.pull_request == null ? "issue" : "pull_request",
      title: row.title, state: row.state,
      url: row.url, html_url: row.html_url,
    };
    for (const key of ["repository_url", "created_at", "updated_at", "closed_at"]) {
      if (!own(row, key)) continue;
      if (row[key] !== null && typeof row[key] !== "string") {
        throw new TypeError("item " + sourceIndex + "." + key + " must be a string or null");
      }
      metadata[key] = row[key];
    }
    if (own(row, "comments")) {
      if (!Number.isSafeInteger(row.comments) || row.comments < 0) {
        throw new TypeError("item " + sourceIndex + ".comments must be a nonnegative integer");
      }
      metadata.comments = row.comments;
    }
    const metadataChars = Object.values(metadata)
      .reduce((count, value) => count + (value === null ? 0 : String(value).length), 0);
    if (metadataChars > maxMetadata) {
      throw new RangeError("item " + sourceIndex + " exceeds max_metadata_chars");
    }
    const state = !own(row, "body") ? "missing" : row.body === null ? "null" : "text";
    if (state === "text" && typeof row.body !== "string") {
      throw new TypeError("item " + sourceIndex + ".body must be a string, null, or absent");
    }
    sourceBodies[state] += 1;
    if (state === "text") sourceBodyChars += row.body.length;
    return {metadata, metadataChars, state, body: state === "text" ? row.body : null};
  });

  let remaining = totalBody;
  let selectedChars = 0;
  let returnedChars = 0;
  let truncated = 0;
  const selectedBodies = {text: 0, null: 0, missing: 0};
  const projected = indices.map(sourceIndex => {
    const row = rows[sourceIndex];
    selectedBodies[row.state] += 1;
    if (row.state !== "text") {
      return {
        source_index: sourceIndex, ...row.metadata, metadata_chars: row.metadataChars,
        body_state: row.state, body: null, body_chars: null,
        returned_body_chars: 0, body_range: null, truncated: null,
      };
    }
    const body = row.body;
    selectedChars += body.length;
    let end = Math.min(body.length, maxBody, remaining);
    // Preserve a complete supplementary character at a truncation boundary.
    if (end > 0 && end < body.length &&
        body.charCodeAt(end - 1) >= 0xd800 && body.charCodeAt(end - 1) <= 0xdbff &&
        body.charCodeAt(end) >= 0xdc00 && body.charCodeAt(end) <= 0xdfff) end -= 1;
    remaining -= end;
    returnedChars += end;
    const shortened = end < body.length;
    if (shortened) truncated += 1;
    return {
      source_index: sourceIndex, ...row.metadata, metadata_chars: row.metadataChars,
      body_state: row.state, body: body.slice(0, end), body_chars: body.length,
      returned_body_chars: end, body_range: [0, end], truncated: shortened,
    };
  });
  const omittedRanges = [];
  let cursor = 0;
  for (const index of indices) {
    if (cursor < index) omittedRanges.push([cursor, index]);
    cursor = index + 1;
  }
  if (cursor < items.length) omittedRanges.push([cursor, items.length]);
  return {
    schema: "commons.connected_github_issue_projection/v1",
    source: {
      scope: "supplied_items_only",
      identity_basis: "caller_supplied_native_fields",
      range_unit: "UTF-16 code units", range_end: "exclusive",
      query_coverage: "not_evaluated", omitted_fields: "all_other_native_fields",
    },
    limits: {
      max_items: maxItems, max_body_chars: maxBody,
      max_total_body_chars: totalBody, max_metadata_chars: maxMetadata,
      max_input_items: SEARCH_LIMIT,
    },
    selection: {
      mode: sparse ? "source_indices" : "contiguous",
      source_indices: indices, start_index: start,
      next_index: sparse || start + indices.length >= items.length ? null : start + indices.length,
    },
    coverage: {
      supplied_items: items.length, returned_items: projected.length,
      omitted_items: items.length - projected.length,
      omitted_source_index_ranges: omittedRanges,
      source_body_states: sourceBodies, selected_body_states: selectedBodies,
      supplied_text_body_chars: sourceBodyChars,
      selected_text_body_chars: selectedChars, returned_body_chars: returnedChars,
      truncated_text_bodies: truncated,
      all_supplied_items_selected: indices.length === items.length,
      all_selected_text_bodies_included: truncated === 0,
      all_supplied_text_bodies_included: indices.length === items.length && truncated === 0,
    },
    items: projected,
  };
}


/**
 * Project headers from a retained native issue search or single-issue envelope.
 * The connector's nullable fields and absent paging evidence stay distinct
 * from the REST reader's native item and traversal contract.
 */
function projectGitHubConnectorIssueHeaders(response, options = {}) {
  if (!object(response)) throw new TypeError("response must be an MCP envelope object");
  if (response.isError === true) {
    throw new TypeError("native connector search returned isError: true");
  }
  if (response.isError !== undefined && typeof response.isError !== "boolean") {
    throw new TypeError("response.isError must be boolean when present");
  }
  if (!object(response.structuredContent)) {
    throw new TypeError("response needs structuredContent.issues or structuredContent.issue");
  }
  const structured = response.structuredContent;
  const single = Object.prototype.hasOwnProperty.call(structured, "issue");
  const batch = Object.prototype.hasOwnProperty.call(structured, "issues");
  if (single && batch) {
    throw new TypeError("structuredContent.issue and structuredContent.issues are ambiguous together");
  }
  if (single) {
    if (!object(structured.issue) || structured.isError === true || structured.ok === false ||
        structured.error != null || structured.error_code != null ||
        (Number.isInteger(structured.status) && structured.status >= 400)) {
      throw new TypeError("structuredContent.issue needs a successful native issue object");
    }
  } else if (!Array.isArray(structured.issues)) {
    throw new TypeError("response needs structuredContent.issues or structuredContent.issue");
  }
  const items = single ? [structured.issue] : structured.issues;
  if (items.length > SEARCH_LIMIT) {
    throw new RangeError("structuredContent.issues exceeds 1000 entries");
  }
  if (!object(options)) throw new TypeError("header options must be an object");
  const allowed = new Set([
    "start_index", "source_indices", "max_items",
    "max_metadata_chars", "max_total_metadata_chars",
  ]);
  for (const key of Object.keys(options)) {
    if (!allowed.has(key)) throw new TypeError("unknown header option: " + key);
  }
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  function bounded(name, fallback, maximum) {
    const value = own(options, name) ? options[name] : fallback;
    if (!Number.isSafeInteger(value) || value < 0 || value > maximum) {
      throw new RangeError(name + " must be an integer from 0 through " + maximum);
    }
    return value;
  }
  const maxItems = bounded("max_items", 20, 100);
  const maxMetadata = bounded("max_metadata_chars", 4096, 65536);
  const totalMetadata = bounded("max_total_metadata_chars", 8000, 1000000);
  const sparse = own(options, "source_indices");
  let start = null;
  let requested;
  if (sparse) {
    if (own(options, "start_index")) {
      throw new TypeError("source_indices and start_index are mutually exclusive");
    }
    if (!Array.isArray(options.source_indices) ||
        options.source_indices.length > maxItems) {
      throw new TypeError("source_indices must be an array within max_items");
    }
    requested = options.source_indices.slice();
    let previous = -1;
    for (const index of requested) {
      if (!Number.isSafeInteger(index) || index <= previous || index >= items.length) {
        throw new RangeError("source_indices must be increasing distinct in-range indices");
      }
      previous = index;
    }
  } else {
    start = bounded("start_index", 0, items.length);
    requested = Array.from(
      {length: Math.min(maxItems, items.length - start)}, (_, i) => start + i
    );
  }

  const nullableFields = [
    "state", "state_reason", "comments", "created_at", "updated_at", "closed_at",
  ];
  const sourceBodies = {text: 0, null: 0, missing: 0};
  let suppliedBodyChars = 0;
  const rows = Array.from(items, (row, sourceIndex) => {
    if (!object(row)) throw new TypeError("connector item " + sourceIndex + " must be an object");
    positiveInteger(row.issue_number, "connector item " + sourceIndex + ".issue_number");
    if (typeof row.title !== "string" || typeof row.url !== "string") {
      throw new TypeError("connector item " + sourceIndex + " needs string title and url");
    }
    const metadata = {
      issue_number: row.issue_number, title: row.title, url: row.url,
    };
    const metadataStates = {};
    for (const key of nullableFields) {
      if (!own(row, key)) {
        metadataStates[key] = "missing";
        continue;
      }
      const value = row[key];
      if (value === null) {
        metadata[key] = null;
        metadataStates[key] = "null";
        continue;
      }
      const valid = key === "comments"
        ? Number.isSafeInteger(value) && value >= 0
        : typeof value === "string";
      if (!valid) {
        throw new TypeError("connector item " + sourceIndex + "." + key +
          " has an invalid non-null type");
      }
      metadata[key] = value;
      metadataStates[key] = "value";
    }
    const metadataChars = Object.values(metadata)
      .reduce((count, value) => count + (value === null ? 0 : String(value).length), 0);
    if (metadataChars > maxMetadata) {
      throw new RangeError("connector item " + sourceIndex + " exceeds max_metadata_chars");
    }
    const bodyState = !own(row, "body") ? "missing" : row.body === null ? "null" : "text";
    if (bodyState === "text" && typeof row.body !== "string") {
      throw new TypeError("connector item " + sourceIndex + ".body must be string, null, or absent");
    }
    const bodyChars = bodyState === "text" ? row.body.length : null;
    sourceBodies[bodyState] += 1;
    if (bodyChars !== null) suppliedBodyChars += bodyChars;
    return {metadata, metadataStates, metadataChars, bodyState, bodyChars};
  });

  let returnedMetadataChars = 0;
  let blockedIndex = null;
  const selected = [];
  const projected = [];
  for (const sourceIndex of requested) {
    const row = rows[sourceIndex];
    if (returnedMetadataChars + row.metadataChars > totalMetadata) {
      blockedIndex = sourceIndex;
      break;
    }
    selected.push(sourceIndex);
    returnedMetadataChars += row.metadataChars;
    projected.push({
      source_index: sourceIndex,
      source_path: single ? "structuredContent.issue"
        : "structuredContent.issues[" + sourceIndex + "]",
      ...row.metadata,
      metadata_states: row.metadataStates,
      metadata_chars: row.metadataChars,
      body_state: row.bodyState, body_chars: row.bodyChars,
      body_withheld: true, returned_body_chars: 0,
    });
  }
  const omittedRanges = [];
  let cursor = 0;
  for (const index of selected) {
    if (cursor < index) omittedRanges.push([cursor, index]);
    cursor = index + 1;
  }
  if (cursor < items.length) omittedRanges.push([cursor, items.length]);
  return {
    schema: "commons.connected_github_connector_issue_headers/v1",
    source: {
      scope: "supplied_envelope_only",
      payload_path: single ? "structuredContent.issue" : "structuredContent.issues",
      ...(single ? {source_shape: "single"} : {}),
      identity_basis: "caller_supplied_connector_fields",
      query_application: "not_verified", kind_application: "not_verified",
      pagination_evidence: "not_available_in_supported_envelope",
      omitted_fields: "body_text_and_all_other_native_fields",
      metadata_unit: "UTF-16 code units",
    },
    limits: {
      max_items: maxItems, max_metadata_chars: maxMetadata,
      max_total_metadata_chars: totalMetadata, max_input_items: SEARCH_LIMIT,
    },
    selection: {
      mode: sparse ? "source_indices" : "contiguous",
      requested_source_indices: requested, source_indices: selected, start_index: start,
      next_index: sparse || start + selected.length >= items.length
        ? null : start + selected.length,
      metadata_budget_blocked_index: blockedIndex,
      omitted_requested_source_indices: requested.slice(selected.length),
    },
    coverage: {
      supplied_items: items.length, requested_items: requested.length,
      returned_items: projected.length, omitted_items: items.length - projected.length,
      omitted_source_index_ranges: omittedRanges,
      source_body_states: sourceBodies, supplied_text_body_chars: suppliedBodyChars,
      returned_body_chars: 0, returned_metadata_chars: returnedMetadataChars,
      metadata_budget_exhausted: blockedIndex !== null,
      all_requested_headers_included: selected.length === requested.length,
      all_supplied_items_selected: selected.length === items.length,
    },
    items: projected,
  };
}

module.exports = { searchGitHubIssues, projectGitHubIssueItems, inspectGitHubIssueUpdatedAtBound, projectGitHubConnectorIssueHeaders };

