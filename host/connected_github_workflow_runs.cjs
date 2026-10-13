"use strict";

// Read the repository run collection when workflow-specific routes are absent.
// The caller supplies its existing native tool surface; this module owns no
// credentials, network client, filesystem, scheduler, or mutation operation.
const FETCH = "mcp__codex_apps__github_fetch";
const TOKEN_READ = "mcp__codex_apps__github_token_connection_github_read";
const SEARCH_FILTERS = new Set([
  "actor", "branch", "check_suite_id", "created", "event", "head_sha", "status",
]);
const RUN_FIELDS = [
  "id", "workflow_id", "name", "path", "run_number", "run_attempt", "event",
  "status", "conclusion", "head_branch", "head_sha", "created_at", "updated_at",
  "run_started_at", "html_url", "jobs_url", "logs_url", "artifacts_url",
];

function object(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function nonempty(value, name) {
  if (typeof value !== "string" || !value.trim()) {
    throw new TypeError(name + " must be a nonempty string");
  }
  return value;
}

function positiveInteger(value, name) {
  if (!Number.isSafeInteger(value) || value < 1) {
    throw new TypeError(name + " must be a positive safe integer");
  }
  return value;
}

function decimalId(value, name) {
  if (typeof value === "number") return String(positiveInteger(value, name));
  if (typeof value === "string" && /^[1-9][0-9]*$/.test(value)) return value;
  throw new TypeError(name + " must be a positive integer or decimal ID string");
}

function inputOptions(input) {
  if (!object(input)) throw new TypeError("input must be an object");
  const keys = new Set([
    "repository_full_name", "workflow_path", "workflow_id", "all_workflows", "filters",
    "per_page", "start_page", "max_pages", "timeout_ms", "stop_after_first",
  ]);
  for (const key of Object.keys(input)) {
    if (!keys.has(key)) throw new TypeError("unknown input field: " + key);
  }
  const repository = nonempty(input.repository_full_name, "repository_full_name");
  const parts = repository.split("/");
  if (parts.length !== 2 || parts.some(part => !part.trim())) {
    throw new TypeError("repository_full_name must be owner/repository");
  }
  const path = input.workflow_path === undefined
    ? null : nonempty(input.workflow_path, "workflow_path");
  const id = input.workflow_id === undefined
    ? null : decimalId(input.workflow_id, "workflow_id");
  const all = input.all_workflows === undefined ? false : input.all_workflows;
  if (typeof all !== "boolean") throw new TypeError("all_workflows must be boolean");
  if (all && (path !== null || id !== null)) {
    throw new TypeError("all_workflows cannot be combined with workflow_path or workflow_id");
  }
  if (!all && path === null && id === null) {
    throw new TypeError("supply workflow_path, workflow_id, or all_workflows");
  }
  const filters = input.filters === undefined ? {} : input.filters;
  if (!object(filters)) throw new TypeError("filters must be an object");
  const query = {};
  for (const [key, value] of Object.entries(filters)) {
    if (!SEARCH_FILTERS.has(key)) throw new TypeError("unknown run filter: " + key);
    query[key] = key === "check_suite_id"
      ? decimalId(value, "filters.check_suite_id")
      : nonempty(value, "filters." + key);
  }
  if (all && !/^[0-9a-f]{40}$/.test(query.head_sha ?? "")) {
    throw new TypeError("all_workflows requires filters.head_sha as a full lowercase commit SHA");
  }
  const perPage = positiveInteger(input.per_page ?? 100, "per_page");
  if (perPage > 100) throw new TypeError("per_page exceeds GitHub's maximum of 100");
  const startPage = positiveInteger(input.start_page ?? 1, "start_page");
  const maxPages = positiveInteger(input.max_pages ?? 10, "max_pages");
  const timeout = input.timeout_ms ?? 30000;
  if (typeof timeout !== "number" || !Number.isFinite(timeout) || timeout < 0) {
    throw new TypeError("timeout_ms must be a finite nonnegative number");
  }
  const first = input.stop_after_first ?? true;
  if (typeof first !== "boolean") throw new TypeError("stop_after_first must be boolean");
  return { repository, parts, path, id, all, query, perPage, startPage, maxPages, timeout, first };
}

function workflowPayload(value) {
  if (!object(value)) return null;
  if (value.isError === true || value.ok === false ||
      Object.prototype.hasOwnProperty.call(value, "error") ||
      (Number.isInteger(value.status) && value.status >= 400)) {
    const error = new Error("native GitHub response reports an error");
    error.code = "NATIVE_ERROR";
    throw error;
  }
  if (Array.isArray(value.workflow_runs)) return value;
  if (value.ok === true && Number.isInteger(value.status) &&
      value.status >= 200 && value.status < 300 && object(value.data) &&
      Array.isArray(value.data.workflow_runs)) return value.data;
  return null;
}

function decode(response) {
  const candidates = [response && response.structuredContent, response];
  for (const candidate of candidates) {
    if (!object(candidate)) continue;
    const payload = workflowPayload(candidate);
    if (payload) return payload;
    if (typeof candidate.content === "string") {
      const parsed = JSON.parse(candidate.content);
      const payload = workflowPayload(parsed);
      if (payload) return payload;
    }
  }
  for (const item of response && Array.isArray(response.content) ? response.content : []) {
    if (item.type !== "text" || typeof item.text !== "string") continue;
    try {
      const parsed = JSON.parse(item.text);
      const payload = workflowPayload(parsed);
      if (payload) return payload;
    } catch (error) {
      if (error.code === "NATIVE_ERROR") throw error;
      // An ordinary provider status message is not the JSON payload.
    }
  }
  throw new TypeError("native response has no repository workflow-run payload");
}

function message(value) {
  if (value instanceof Error) return value.message.slice(0, 1200);
  if (value && Array.isArray(value.content)) {
    return value.content.filter(item => item.type === "text")
      .map(item => item.text).join("\n").slice(0, 1200);
  }
  return String(value).slice(0, 1200);
}

/**
 * Find workflow runs using the native repository /actions/runs endpoint.
 *
 * Positive matches remain usable after a later read/budget failure. Absence is
 * reported only after a complete, consistent observed traversal from page 1.
 * Completeness describes the observed collection, never an immutable snapshot.
 * options.onResponse may retain each unchanged native response outside this
 * compact result. Callback failures are recorded and never replay a tool call.
 */
async function findGitHubWorkflowRuns(tools, input, options = {}) {
  const config = inputOptions(input);
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
  const encodeQuery = value => transport === "token"
    ? encodeURIComponent(value).replace(/%2F/gi, "/").replace(/%3A/gi, ":")
      .replace(/%20/g, "+")
    : encodeURIComponent(value);
  const started = Date.now();
  const filtered = Object.keys(config.query).length > 0;
  const searchLimit = filtered ? 1000 : null;
  const seen = new Set();
  const repeated = new Set();
  const totals = new Set();
  const result = {
    schema: "commons.connected_github_workflow_runs/v1",
    status: "INCONCLUSIVE",
    repository_full_name: config.repository,
    workflow: { path: config.path, id: config.id, ...(config.all ? { all: true } : {}) },
    filters: config.query,
    matches: [],
    coverage: {
      complete: false,
      snapshot: false,
      pagination: "live_offset_pages",
      start_page: config.startPage,
      per_page: config.perPage,
      api_search_limit: searchLimit,
      end_observed: false,
      pages: [],
      total_counts: [],
      repeated_run_ids: [],
      next: { page: config.startPage, row_index: 0 },
      gaps: config.startPage === 1 ? [] : ["STARTED_AFTER_FIRST_PAGE"],
    },
    stats: { calls: 0, pages_read: 0, runs_received: 0, runs_examined: 0, unique_runs: 0 },
    callback_errors: [],
    started_at: new Date(started).toISOString(),
  };
  if (transport === "token") result.request = { transport, binding };
  const gap = code => {
    if (!result.coverage.gaps.includes(code)) result.coverage.gaps.push(code);
  };
  function finish(code, detail = {}) {
    result.coverage.total_counts = [...totals];
    result.coverage.repeated_run_ids = [...repeated];
    result.stats.unique_runs = seen.size;
    result.stop = { code, ...detail };
    result.finished_at = new Date().toISOString();
    result.elapsed_ms = Date.now() - started;
    result.status = result.matches.length > 0 ? "FOUND"
      : result.coverage.complete ? "NOT_FOUND_IN_SCOPE" : "INCONCLUSIVE";
    return result;
  }
  const base = "/repos/" +
    config.parts.map(encodeURIComponent).join("/") + "/actions/runs";
  let page = config.startPage;
  while (result.stats.calls < config.maxPages) {
    if (Date.now() - started >= config.timeout) return finish("DEADLINE");
    if (!Number.isSafeInteger(page)) return finish("PAGE_NUMBER_LIMIT");
    const offset = (page - 1) * config.perPage;
    if (searchLimit !== null && offset >= searchLimit) {
      gap("FILTERED_SEARCH_LIMIT");
      return finish("FILTERED_SEARCH_LIMIT");
    }
    const query = {
      ...config.query,
      // This empties nested pull_requests arrays. It does NOT exclude PR runs.
      exclude_pull_requests: "true",
      per_page: String(config.perPage),
      page: String(page),
    };
    const path = base + "?" + Object.entries(query)
      .map(([key, value]) => encodeQuery(key) + "=" + encodeQuery(value)).join("&");
    const url = "https://api.github.com" + path;
    result.coverage.next = { page, row_index: 0 };
    result.stats.calls += 1;
    let response;
    try {
      response = await tools[binding](transport === "token" ? { path } : { url });
    } catch (error) {
      return finish("TOOL_ERROR", { url, native_message: message(error) });
    }
    if (options.onResponse) {
      try {
        await options.onResponse({ page, url, response,
          ...(transport === "token" ? { path, binding } : {}) });
      } catch (error) {
        result.callback_errors.push({ page, message: message(error) });
      }
    }
    if (response && response.isError) {
      return finish("NATIVE_ERROR", { url, native_message: message(response) });
    }
    let payload;
    try {
      payload = decode(response);
      if (!Array.isArray(payload.workflow_runs) ||
          !Number.isSafeInteger(payload.total_count) || payload.total_count < 0 ||
          payload.workflow_runs.length > config.perPage) {
        throw new TypeError("invalid workflow_runs, total_count, or page length");
      }
    } catch (error) {
      return finish(error.code === "NATIVE_ERROR" ? "NATIVE_ERROR" : "INVALID_RESPONSE",
        { url, native_message: message(error) });
    }
    const rows = payload.workflow_runs;
    totals.add(payload.total_count);
    if (totals.size > 1) gap("TOTAL_COUNT_CHANGED");
    const observation = {
      page, url, total_count: payload.total_count,
      received: rows.length, examined: 0, first_run_id: null, last_run_id: null,
    };
    if (transport === "token") observation.path = path;
    result.coverage.pages.push(observation);
    result.stats.pages_read += 1;
    result.stats.runs_received += rows.length;
    for (let index = 0; index < rows.length; index += 1) {
      result.coverage.next = { page, row_index: index };
      if (Date.now() - started >= config.timeout) return finish("DEADLINE");
      const row = rows[index];
      let id;
      let workflowId;
      try {
        if (!object(row)) throw new TypeError("workflow run must be an object");
        id = decimalId(row.id, "run.id");
        workflowId = decimalId(row.workflow_id, "run.workflow_id");
        if (config.path !== null && typeof row.path !== "string") {
          throw new TypeError("run.path is missing for workflow-path selection");
        }
        if (config.all && row.head_sha !== config.query.head_sha) {
          throw new TypeError("run.head_sha differs from the requested all-workflows head");
        }
      } catch (error) {
        return finish("INVALID_RESPONSE", { url, row_index: index, native_message: message(error) });
      }
      observation.first_run_id ??= id;
      observation.last_run_id = id;
      observation.examined += 1;
      result.stats.runs_examined += 1;
      result.coverage.next = { page, row_index: index + 1 };
      if (seen.has(id)) {
        repeated.add(id);
        gap("REPEATED_RUN_ID");
        continue;
      }
      seen.add(id);
      const matchesPath = config.path === null || row.path === config.path ||
        row.path.startsWith(config.path + "@");
      if (!matchesPath || (config.id !== null && workflowId !== config.id)) continue;
      const selected = {};
      for (const key of RUN_FIELDS) selected[key] = row[key] ?? null;
      result.matches.push(selected);
      if (config.first) return finish("FIRST_MATCH");
    }
    result.coverage.next = { page: page + 1, row_index: 0 };
    const atLimit = searchLimit !== null &&
      (offset + rows.length >= searchLimit || payload.total_count >= searchLimit);
    const shortPage = rows.length < config.perPage;
    const observedTotal = config.startPage === 1 && seen.size >= payload.total_count;
    if (shortPage || observedTotal) {
      result.coverage.end_observed = true;
      result.coverage.next = null;
      if (atLimit) gap("FILTERED_SEARCH_LIMIT");
      if (config.startPage === 1 && seen.size !== payload.total_count) {
        gap("ADVERTISED_TOTAL_MISMATCH");
      }
      result.coverage.complete = config.startPage === 1 &&
        result.coverage.gaps.length === 0 && seen.size === payload.total_count;
      return finish(shortPage ? "PAGINATION_END" : "ADVERTISED_TOTAL_REACHED");
    }
    if (searchLimit !== null && offset + rows.length >= searchLimit) {
      gap("FILTERED_SEARCH_LIMIT");
      return finish("FILTERED_SEARCH_LIMIT");
    }
    page += 1;
  }
  return finish("PAGE_BUDGET");
}

module.exports = { findGitHubWorkflowRuns };

