"use strict";

const FETCH = "mcp__codex_apps__github_fetch";
const TOKEN_READ = "mcp__codex_apps__github_token_connection_github_read";
const SHA = /^[0-9a-f]{40}$/;

function object(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function integer(value, name, minimum, maximum) {
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    throw new TypeError(`${name} must be an integer from ${minimum} through ${maximum}`);
  }
  return value;
}

function keys(value, allowed, name) {
  if (!object(value)) throw new TypeError(`${name} must be an object`);
  for (const key of Object.keys(value)) {
    if (!allowed.includes(key)) throw new TypeError(`unknown ${name} key: ${key}`);
  }
}

function decode(response) {
  const candidates = [response && response.structuredContent, response];
  for (const candidate of candidates) {
    if (!object(candidate)) continue;
    if (Object.prototype.hasOwnProperty.call(candidate, "data")) {
      if (candidate.ok !== true || !Number.isSafeInteger(candidate.status) ||
          candidate.status < 200 || candidate.status >= 300) {
        throw new TypeError("token read did not report a successful HTTP response");
      }
      if (object(candidate.data) && Array.isArray(candidate.data.commits)) return candidate.data;
      throw new TypeError("token read did not return a GitHub comparison with commits");
    }
    if (Array.isArray(candidate.commits)) return candidate;
    if (typeof candidate.content === "string") {
      try {
        const parsed = JSON.parse(candidate.content);
        if (object(parsed) && Array.isArray(parsed.commits)) return parsed;
      } catch (_) { /* Try the other native response envelopes. */ }
    }
  }
  for (const block of response && Array.isArray(response.content) ? response.content : []) {
    if (!object(block) || block.type !== "text" || typeof block.text !== "string") continue;
    try {
      const parsed = JSON.parse(block.text);
      if (object(parsed) && Array.isArray(parsed.commits)) return parsed;
    } catch (_) { /* A native text block need not be JSON. */ }
  }
  throw new TypeError("native fetch did not return a GitHub comparison with commits");
}

function errorText(error) {
  return String(error && error.message ? error.message : error).slice(0, 1200);
}

function commitRow(row) {
  if (!object(row) || typeof row.sha !== "string" || !SHA.test(row.sha) ||
      !object(row.commit) || typeof row.commit.message !== "string" ||
      !Array.isArray(row.parents) ||
      row.parents.some(parent => !object(parent) || !SHA.test(parent.sha))) {
    throw new TypeError("comparison contains an invalid commit identity or message");
  }
  return {
    sha: row.sha,
    html_url: typeof row.html_url === "string" ? row.html_url : null,
    parent_shas: row.parents.map(parent => parent.sha),
    author_date: object(row.commit.author) && typeof row.commit.author.date === "string"
      ? row.commit.author.date : null,
    committer_date: object(row.commit.committer) && typeof row.commit.committer.date === "string"
      ? row.commit.committer.date : null,
    message: row.commit.message
  };
}

function fileRow(row) {
  if (!object(row) || typeof row.filename !== "string" || !row.filename ||
      typeof row.status !== "string" || !row.status ||
      (row.sha !== undefined && row.sha !== null && !SHA.test(row.sha))) {
    throw new TypeError("comparison contains an invalid file identity");
  }
  return {
    filename: row.filename,
    previous_filename: typeof row.previous_filename === "string" ? row.previous_filename : null,
    status: row.status,
    sha: typeof row.sha === "string" ? row.sha : null,
    additions: Number.isSafeInteger(row.additions) ? row.additions : null,
    deletions: Number.isSafeInteger(row.deletions) ? row.deletions : null,
    changes: Number.isSafeInteger(row.changes) ? row.changes : null,
    patch_returned: typeof row.patch === "string"
  };
}

/** Read native, immutable commit-pair pages. The caller owns private raw-response retention. */
async function readGitHubCompare(tools, input, options = {}) {
  keys(input, ["repository_full_name", "base", "head", "per_page", "max_pages", "timeout_ms"], "input");
  keys(options, ["onResponse", "transport"], "options");
  const transport = options.transport === undefined ? "native" : options.transport;
  if (transport !== "native" && transport !== "token") {
    throw new TypeError("transport must be native or token");
  }
  const tool = transport === "token" ? TOKEN_READ : FETCH;
  if (options.onResponse !== undefined && typeof options.onResponse !== "function") {
    throw new TypeError("onResponse must be a function");
  }
  if (typeof input.repository_full_name !== "string" ||
      !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(input.repository_full_name)) {
    throw new TypeError("repository_full_name must be owner/name");
  }
  if (!SHA.test(input.base) || !SHA.test(input.head)) {
    throw new TypeError("base and head must be exact lowercase 40-character commit SHAs");
  }
  if (!tools || typeof tools[tool] !== "function") throw new TypeError(`connected tool ${tool} is required`);
  const perPage = integer(input.per_page === undefined ? 100 : input.per_page, "per_page", 1, 100);
  const maxPages = integer(input.max_pages === undefined ? 10 : input.max_pages, "max_pages", 1, 100);
  const timeout = integer(input.timeout_ms === undefined ? 30000 : input.timeout_ms, "timeout_ms", 0, 1200000);
  const started = Date.now();
  const seen = new Set();
  const totals = new Set();
  const gaps = [];
  const pair = `${input.base}...${input.head}`;
  const api = `https://api.github.com/repos/${input.repository_full_name.split("/").map(encodeURIComponent).join("/")}/compare/${pair}`;
  const result = {
    schema: "commons.connected_github_compare.v1",
    status: "INCONCLUSIVE",
    source: { tool, repository_full_name: input.repository_full_name, base: input.base, head: input.head, compare_url: api },
    comparison: null,
    commits: [],
    files: [],
    coverage: {
      commits: { complete: false, immutable_pair: true, per_page: perPage, max_pages: maxPages,
        pages: [], total_counts: [], end_observed: false, unique_commits: 0,
        repeated_shas: [], next_page: 1, gaps },
      files: { source_page: 1, api_maximum: 300, returned: false, returned_count: 0,
        ceiling_reached: false, below_api_ceiling: false, complete: null,
        limitation: "GitHub returns files only on page 1, at most 300; no total-file count is supplied." },
      classification: "No generated/non-generated classification is inferred."
    },
    head_correspondence: { head_seen: false, last_commit_sha: null, last_commit_matches_head: false },
    stats: { calls: 0, pages: 0, received_commits: 0, retained_responses: 0 },
    started_at: new Date(started).toISOString(),
    finished_at: null,
    elapsed_ms: null,
    stop_reason: null,
    error: null
  };
  function gap(code) { if (!gaps.includes(code)) gaps.push(code); }
  function finish(reason, error) {
    result.coverage.commits.total_counts = [...totals];
    result.coverage.commits.unique_commits = seen.size;
    const last = result.commits.length ? result.commits[result.commits.length - 1].sha : null;
    result.head_correspondence = { head_seen: seen.has(input.head), last_commit_sha: last,
      last_commit_matches_head: last === input.head };
    result.status = result.coverage.commits.complete ? "COMPLETE" : "INCONCLUSIVE";
    result.stop_reason = reason;
    result.error = error === undefined ? null : errorText(error);
    result.finished_at = new Date().toISOString();
    result.elapsed_ms = Date.now() - started;
    return result;
  }
  for (let page = 1; page <= maxPages; page += 1) {
    if (Date.now() - started >= timeout) return finish("DEADLINE_BEFORE_CALL");
    const url = `${api}?per_page=${perPage}&page=${page}`;
    let response;
    result.stats.calls += 1;
    try {
      const args = transport === "token"
        ? { path: url.slice("https://api.github.com".length) } : { url };
      response = await tools[tool](args);
    }
    catch (error) { return finish("TOOL_ERROR", error); }
    if (options.onResponse) {
      try {
        await options.onResponse(response, { page, url, repository_full_name: input.repository_full_name,
          base: input.base, head: input.head, observed_at: new Date().toISOString() });
        result.stats.retained_responses += 1;
      } catch (error) { gap("RETAIN_HOOK_FAILED"); return finish("RETAIN_HOOK_ERROR", error); }
    }
    if (response && response.isError) return finish("NATIVE_ERROR", "native fetch returned isError");
    let payload;
    let rows;
    try {
      payload = decode(response);
      integer(payload.total_commits, "total_commits", 0, Number.MAX_SAFE_INTEGER);
      integer(payload.ahead_by, "ahead_by", 0, Number.MAX_SAFE_INTEGER);
      integer(payload.behind_by, "behind_by", 0, Number.MAX_SAFE_INTEGER);
      if (!["ahead", "behind", "diverged", "identical"].includes(payload.status) ||
          !object(payload.base_commit) || payload.base_commit.sha !== input.base ||
          !object(payload.merge_base_commit) || !SHA.test(payload.merge_base_commit.sha) ||
          payload.commits.length > perPage) throw new TypeError("comparison metadata or page length is invalid");
      const metadata = { status: payload.status, ahead_by: payload.ahead_by, behind_by: payload.behind_by,
        total_commits: payload.total_commits, base_commit_sha: payload.base_commit.sha,
        merge_base_commit_sha: payload.merge_base_commit.sha };
      if (result.comparison && JSON.stringify(result.comparison) !== JSON.stringify(metadata)) {
        gap("COMPARISON_METADATA_CHANGED");
      }
      if (!result.comparison) result.comparison = metadata;
      rows = payload.commits.map(commitRow);
      if (page === 1 && payload.files !== undefined) {
        if (!Array.isArray(payload.files) || payload.files.length > 300) throw new TypeError("invalid first-page files");
        result.files = payload.files.map(fileRow);
        Object.assign(result.coverage.files, { returned: true, returned_count: result.files.length,
          ceiling_reached: result.files.length === 300, below_api_ceiling: result.files.length < 300 });
      }
    } catch (error) { return finish("INVALID_RESPONSE", error); }
    totals.add(payload.total_commits);
    if (totals.size > 1) gap("ADVERTISED_TOTAL_CHANGED");
    result.stats.pages += 1;
    result.stats.received_commits += rows.length;
    result.coverage.commits.pages.push({ page, url, received_count: rows.length,
      total_commits: payload.total_commits, observed_at: new Date().toISOString(),
      first_sha: rows.length ? rows[0].sha : null, last_sha: rows.length ? rows[rows.length - 1].sha : null });
    for (const row of rows) {
      if (seen.has(row.sha)) {
        gap("REPEATED_COMMIT_SHA");
        if (!result.coverage.commits.repeated_shas.includes(row.sha)) result.coverage.commits.repeated_shas.push(row.sha);
      } else { seen.add(row.sha); result.commits.push(row); }
    }
    result.coverage.commits.next_page = page + 1;
    if (seen.size > payload.total_commits) gap("COUNT_EXCEEDS_ADVERTISED_TOTAL");
    const shortPage = rows.length < perPage;
    const reachedTotal = seen.size >= payload.total_commits;
    if (shortPage || reachedTotal) {
      result.coverage.commits.end_observed = shortPage;
      result.coverage.commits.next_page = null;
      if (seen.size !== payload.total_commits) gap("COUNT_DIFFERS_FROM_ADVERTISED_TOTAL");
      if (payload.total_commits > 0 && result.commits[result.commits.length - 1].sha !== input.head) {
        gap("TERMINAL_COMMIT_DOES_NOT_MATCH_HEAD");
      }
      result.coverage.commits.complete = gaps.length === 0 && seen.size === payload.total_commits;
      return finish(shortPage ? "PAGINATION_END" : "ADVERTISED_TOTAL_REACHED");
    }
  }
  return finish("PAGE_BUDGET");
}

function safePrefix(text, maximum) {
  let end = Math.min(text.length, maximum);
  if (end > 0 && end < text.length && /[\uD800-\uDBFF]/.test(text[end - 1]) &&
      /[\uDC00-\uDFFF]/.test(text[end])) end -= 1;
  return { text: text.slice(0, end), source_range: [0, end], source_length: text.length, truncated: end < text.length };
}

/** Bounded projection of collected commit messages; source indices and exact UTF-16 ranges survive. */
function projectGitHubCommits(commits, options = {}) {
  if (!Array.isArray(commits)) throw new TypeError("commits must be an array");
  keys(options, ["source_indices", "max_items", "max_message_chars", "max_total_message_chars"], "projection options");
  const maxItems = integer(options.max_items === undefined ? 12 : options.max_items, "max_items", 0, 1000);
  const maxMessage = integer(options.max_message_chars === undefined ? 1000 : options.max_message_chars, "max_message_chars", 0, 100000);
  const maxTotal = integer(options.max_total_message_chars === undefined ? 12000 : options.max_total_message_chars, "max_total_message_chars", 0, 1000000);
  for (const row of commits) {
    if (!object(row) || !SHA.test(row.sha) || typeof row.message !== "string") throw new TypeError("invalid collected commit");
  }
  const indices = options.source_indices === undefined ? commits.map((_, index) => index) : options.source_indices;
  if (!Array.isArray(indices) || indices.some((index, position) =>
    !Number.isSafeInteger(index) || index < 0 || index >= commits.length || (position > 0 && index <= indices[position - 1]))) {
    throw new TypeError("source_indices must be increasing distinct indices in the supplied array");
  }
  let used = 0;
  const items = indices.slice(0, maxItems).map(sourceIndex => {
    const row = commits[sourceIndex];
    const message = safePrefix(row.message, Math.min(maxMessage, maxTotal - used));
    used += message.text.length;
    return { source_index: sourceIndex, sha: row.sha, html_url: row.html_url,
      parent_shas: row.parent_shas, author_date: row.author_date, committer_date: row.committer_date,
      message };
  });
  const selected = new Set(items.map(item => item.source_index));
  return { schema: "commons.connected_github_commit_projection.v1", items,
    coverage: { source_count: commits.length, selected_count: items.length,
      omitted_source_indices: commits.map((_, index) => index).filter(index => !selected.has(index)),
      returned_message_chars: used, truncated_messages: items.filter(item => item.message.truncated).length,
      scope: "supplied commits only; query coverage belongs to readGitHubCompare.coverage.commits" } };
}

module.exports = { readGitHubCompare, projectGitHubCommits };
