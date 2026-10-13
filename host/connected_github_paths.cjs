"use strict";

/* Exact filename lookup through native, commit-pinned Git tree reads.
 * See CONNECTED_GITHUB_PATHS.md. No filesystem, network client, or write tools.
 */

const SHA = /^[0-9a-f]{40}$/i;
const FETCH = "mcp__codex_apps__github_fetch";
const TOKEN_READ = "mcp__codex_apps__github_token_connection_github_read";
const MODES = new Map([
  ["100644", "blob"], ["100755", "blob"], ["120000", "blob"],
  ["040000", "tree"], ["160000", "commit"],
]);

class LookupStop extends Error {
  constructor(code, message, nativeMessage = null) {
    super(message);
    this.name = "LookupStop";
    this.code = code;
    this.nativeMessage = nativeMessage;
  }
}

function integer(value, fallback, minimum, name) {
  const chosen = value === undefined ? fallback : value;
  if (!Number.isSafeInteger(chosen) || chosen < minimum) {
    throw new TypeError(name + " must be a safe integer >= " + minimum);
  }
  return chosen;
}

function component(value) {
  return typeof value === "string" && value.length > 0 &&
    value !== "." && value !== ".." && !/[\/\0]/.test(value);
}

function settings(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new TypeError("options must be an object");
  }
  const repository = input.repository_full_name;
  if (typeof repository !== "string" ||
      !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository) ||
      repository.split("/").some(x => x === "." || x === "..")) {
    throw new TypeError("repository_full_name must be owner/repository");
  }
  if (typeof input.ref !== "string" || !input.ref || /[\0\r\n]/.test(input.ref)) {
    throw new TypeError("ref must be a nonempty observed branch, tag, or commit");
  }
  let filenames;
  if (input.filenames !== undefined) {
    if (input.filename !== undefined) {
      throw new TypeError("provide filename or filenames, not both");
    }
    if (!Array.isArray(input.filenames) || input.filenames.length === 0) {
      throw new TypeError("filenames must be a nonempty array of exact basenames");
    }
    filenames = [...new Set(input.filenames)];
    if (!filenames.every(component)) {
      throw new TypeError("filenames must contain only exact basenames");
    }
  } else {
    if (!component(input.filename)) {
      throw new TypeError("filename must be one exact basename");
    }
    filenames = [input.filename];
  }
  if (!Array.isArray(input.prefixes) || input.prefixes.length === 0) {
    throw new TypeError('prefixes must be a nonempty array; use [""] for the root');
  }
  if (input.stop_after_first !== undefined && typeof input.stop_after_first !== "boolean") {
    throw new TypeError("stop_after_first must be a boolean");
  }
  const prefixes = [];
  for (const prefix of input.prefixes) {
    if (typeof prefix !== "string" ||
        (prefix !== "" && !prefix.split("/").every(component))) {
      throw new TypeError("prefixes must be canonical relative directory paths");
    }
    if (!prefixes.includes(prefix)) prefixes.push(prefix);
  }
  // Check URI encodability before any native call, including lone surrogates.
  for (const value of [input.ref, ...filenames, ...prefixes]) {
    encodeURIComponent(value);
  }
  return {
    repository_full_name: repository,
    ref: input.ref,
    filename: input.filename,
    filenames,
    prefixes,
    stop_after_first: input.stop_after_first === undefined ? true : input.stop_after_first,
    max_calls: integer(input.max_calls, 32, 1, "max_calls"),
    max_entries: integer(input.max_entries, 50000, 1, "max_entries"),
    max_depth: integer(input.max_depth, 8, 0, "max_depth"),
    timeout_ms: integer(input.timeout_ms, 30000, 1, "timeout_ms"),
  };
}

function responseJSON(result, transport) {
  if (result && result.isError) {
    const detail = Array.isArray(result.content) ? result.content.filter(x => x.type === "text").map(x => x.text).join("\n").slice(0, 1200) : null;
    throw new LookupStop("NATIVE_TOOL_ERROR", "The native GitHub fetch returned isError=true", detail);
  }
  if (transport === "token") {
    const envelope = result && result.structuredContent;
    if (envelope && typeof envelope === "object" && !Array.isArray(envelope) &&
        (envelope.ok === false ||
         (Number.isInteger(envelope.status) && envelope.status >= 400))) {
      const detail = typeof envelope.data?.message === "string"
        ? envelope.data.message.slice(0, 1200) : null;
      throw new LookupStop("NATIVE_TOOL_ERROR", "The token GitHub reader returned an HTTP error", detail);
    }
    if (!envelope || typeof envelope !== "object" || Array.isArray(envelope) ||
        envelope.ok !== true || !Number.isInteger(envelope.status) ||
        envelope.status < 200 || envelope.status >= 300 ||
        !envelope.data || typeof envelope.data !== "object") {
      throw new LookupStop("RESPONSE_SHAPE", "The token reader omitted its successful HTTP data envelope");
    }
    return envelope.data;
  }
  const body = result && result.structuredContent && result.structuredContent.content;
  if (typeof body !== "string") {
    throw new LookupStop("RESPONSE_SHAPE", "The native fetch omitted its JSON content string");
  }
  let parsed;
  try { parsed = JSON.parse(body); }
  catch (_) { throw new LookupStop("RESPONSE_JSON", "The native fetch did not return valid JSON"); }
  if (!parsed || typeof parsed !== "object") {
    throw new LookupStop("RESPONSE_SHAPE", "Expected a GitHub JSON object or array");
  }
  return parsed;
}

function joined(parent, name) {
  return parent ? parent + "/" + name : name;
}

async function findGitHubPaths(tools, input, runtime = {}) {
  const options = settings(input);
  if (!runtime || typeof runtime !== "object" || Array.isArray(runtime) ||
      Object.keys(runtime).some(key => key !== "transport" && key !== "onResponse")) {
    throw new TypeError("runtime options supports only transport and onResponse");
  }
  const transport = runtime.transport ?? "native";
  if (transport !== "native" && transport !== "token") {
    throw new TypeError("transport must be native or token");
  }
  if (runtime.onResponse !== undefined && typeof runtime.onResponse !== "function") {
    throw new TypeError("onResponse must be a function");
  }
  const binding = transport === "token" ? TOKEN_READ : FETCH;
  if (!tools || typeof tools[binding] !== "function") {
    throw new TypeError(transport === "native"
      ? "The native GitHub fetch tool is not exposed"
      : "The connected " + binding + " tool is not exposed");
  }
  const encodeQuery = value => transport === "token"
    ? encodeURIComponent(value).replace(/%2F/gi, "/").replace(/%3A/gi, ":")
      .replace(/%20/g, "+")
    : encodeURIComponent(value);
  const started = Date.now();
  const repository = options.repository_full_name;
  const api = "https://api.github.com/repos/" +
    repository.split("/").map(encodeURIComponent).join("/");
  const web = "https://github.com/" + repository;
  const requestedFilenames = new Set(options.filenames);
  const counts = {
    calls: 0, tree_reads: 0, tree_cache_hits: 0,
    entries_received: 0, entries_examined: 0, directories_scanned: 0,
  };
  const scopes = options.prefixes.map(prefix => ({
    prefix, state: "NOT_STARTED", complete: false, directories_scanned: 0,
    matches: 0, issues: [],
  }));
  const matches = new Map();
  const trees = new Map();
  const submodules = new Map();
  const reads = [];
  const directories = [];
  let commitSha = null;
  let rootTreeSha = null;
  let scope = null;
  let stage = "resolve_ref";
  let location = "";
  let activeTree = null;
  let activeDirectory = null;
  let nextEntry = 0;
  let queue = [];
  let stop = null;

  function check(kind) {
    if (Date.now() - started >= options.timeout_ms) {
      throw new LookupStop("DEADLINE", "Cooperative lookup deadline reached");
    }
    if (kind === "call" && counts.calls >= options.max_calls) {
      throw new LookupStop("CALL_BUDGET", "Native read budget reached");
    }
    if (kind === "entry" && counts.entries_examined >= options.max_entries) {
      throw new LookupStop("ENTRY_BUDGET", "Tree-entry inspection budget reached");
    }
  }

  async function fetchJSON(url, kind) {
    check("call");
    counts.calls++;
    if (kind === "tree") counts.tree_reads++;
    const read = { url, kind, state: "STARTED" };
    const path = url.slice("https://api.github.com".length);
    if (transport === "token") Object.assign(read, { path, binding });
    reads.push(read);
    let result;
    try {
      const response = await tools[binding](transport === "token" ? { path } : { url });
      if (runtime.onResponse) {
        try {
          await runtime.onResponse({ url, kind, response,
            ...(transport === "token" ? { path, binding } : {}) });
        } catch (error) {
          read.callback_error = { message: String(error && error.message || error).slice(0, 1200) };
        }
      }
      result = responseJSON(response, transport);
      read.state = "RETURNED";
    } catch (error) {
      read.state = "FAILED";
      throw error instanceof LookupStop ? error :
        new LookupStop("NATIVE_TOOL_THROW", String(error && error.message || error).slice(0, 300));
    }
    return result;
  }

  async function tree(sha) {
    check("time");
    activeTree = sha;
    if (trees.has(sha)) {
      counts.tree_cache_hits++;
      return trees.get(sha);
    }
    const result = await fetchJSON(api + "/git/trees/" + sha, "tree");
    if (result.sha !== sha || !Array.isArray(result.tree) ||
        typeof result.truncated !== "boolean") {
      throw new LookupStop("TREE_SHAPE", "Tree identity, entries, or truncation flag is invalid");
    }
    counts.entries_received += result.tree.length;
    trees.set(sha, result);
    return result;
  }

  function entry(raw) {
    check("entry");
    counts.entries_examined++;
    if (!raw || typeof raw !== "object" || !component(raw.path) ||
        (typeof raw.sha !== "string" || !SHA.test(raw.sha)) ||
        !MODES.has(raw.mode) || MODES.get(raw.mode) !== raw.type ||
        (raw.size !== undefined && (!Number.isSafeInteger(raw.size) || raw.size < 0))) {
      throw new LookupStop("TREE_ENTRY_SHAPE", "A non-recursive tree entry is invalid");
    }
    return raw;
  }

  function issue(code, path, treeSha, message) {
    scope.issues.push({ code, path, tree_sha: treeSha, message });
  }

  try {
    const fullSha = SHA.test(options.ref);
    const refURL = api + (fullSha ? "/git/commits/" + options.ref :
      "/commits?sha=" + encodeQuery(options.ref) + "&per_page=1");
    const refResult = await fetchJSON(refURL, "commit");
    if (!fullSha && (!Array.isArray(refResult) || refResult.length !== 1)) {
      throw new LookupStop("COMMIT_SHAPE", "The ref did not return exactly one starting commit");
    }
    const resolved = fullSha ? refResult : refResult[0];
    const resolvedCommit = resolved.sha;
    const resolvedTree = fullSha ? resolved.tree && resolved.tree.sha :
      resolved.commit && resolved.commit.tree && resolved.commit.tree.sha;
    if (typeof resolvedCommit !== "string" || !SHA.test(resolvedCommit) ||
        typeof resolvedTree !== "string" || !SHA.test(resolvedTree) ||
        (fullSha && resolvedCommit.toLowerCase() !== options.ref.toLowerCase())) {
      throw new LookupStop("COMMIT_SHAPE", "The ref did not resolve to an exact commit and tree");
    }
    commitSha = resolvedCommit.toLowerCase();
    rootTreeSha = resolvedTree.toLowerCase();

    for (scope of scopes) {
      scope.state = "RESOLVING";
      stage = "resolve_prefix";
      location = "";
      activeDirectory = null;
      queue = [];
      let sha = rootTreeSha;
      let absent = false;
      for (const segment of scope.prefix === "" ? [] : scope.prefix.split("/")) {
        const parent = await tree(sha);
        let found = null;
        for (let i = 0; i < parent.tree.length; i++) {
          const item = entry(parent.tree[i]);
          if (item.path === segment) { found = item; break; }
        }
        if (!found) {
          if (parent.truncated) {
            throw new LookupStop("TRUNCATED_PREFIX", "The missing prefix entry is in a truncated parent tree");
          }
          scope.state = "PREFIX_MISSING";
          scope.complete = true;
          scope.missing_path = joined(location, segment);
          absent = true;
          break;
        }
        location = joined(location, segment);
        if (found.type !== "tree") {
          throw new LookupStop(
            found.type === "commit" ? "SUBMODULE_PREFIX" : "PREFIX_NOT_DIRECTORY",
            "The selected prefix does not resolve to a directory in this repository");
        }
        sha = found.sha.toLowerCase();
      }
      if (absent) continue;

      scope.tree_sha = sha;
      scope.state = "SCANNING";
      stage = "scan_directory";
      queue = [{ path: scope.prefix, tree_sha: sha, depth: 0 }];
      while (queue.length) {
        activeDirectory = queue.shift();
        location = activeDirectory.path;
        nextEntry = 0;
        const current = await tree(activeDirectory.tree_sha);
        const scan = {
          prefix: scope.prefix, path: location, tree_sha: activeDirectory.tree_sha,
          depth: activeDirectory.depth, entries_returned: current.tree.length,
          entries_examined: 0, complete: false,
        };
        directories.push(scan);
        const names = new Set();
        for (; nextEntry < current.tree.length; nextEntry++) {
          const item = entry(current.tree[nextEntry]);
          scan.entries_examined++;
          if (names.has(item.path)) {
            throw new LookupStop("TREE_DUPLICATE_PATH", "A tree repeated a direct entry name");
          }
          names.add(item.path);
          const path = joined(location, item.path);
          if (item.type === "blob" && requestedFilenames.has(item.path)) {
            if (!matches.has(path)) {
              matches.set(path, {
                path, blob_sha: item.sha.toLowerCase(), mode: item.mode,
                kind: item.mode === "120000" ? "symlink" : "file",
                size: item.size === undefined ? null : item.size,
                tree_sha: activeDirectory.tree_sha,
                commit_sha: commitSha,
                display_url: web + "/blob/" + commitSha + "/" +
                  path.split("/").map(encodeURIComponent).join("/"),
              });
            }
            scope.matches++;
            if (options.stop_after_first) {
              nextEntry++;
              throw new LookupStop("FIRST_MATCH", "The first requested filename match was found");
            }
          } else if (item.type === "tree") {
            if (activeDirectory.depth < options.max_depth) {
              queue.push({ path, tree_sha: item.sha.toLowerCase(), depth: activeDirectory.depth + 1 });
            } else {
              issue("DEPTH_LIMIT", path, item.sha.toLowerCase(),
                "This subtree is deeper than the selected scope's max_depth");
            }
          } else if (item.type === "commit") {
            submodules.set(path, { path, commit_sha: item.sha.toLowerCase() });
          }
        }
        if (current.truncated) {
          issue("TREE_TRUNCATED", location, activeDirectory.tree_sha,
            "The provider omitted entries from this non-recursive tree");
        }
        scan.complete = !current.truncated;
        counts.directories_scanned++;
        scope.directories_scanned++;
        activeDirectory = null;
      }
      scope.complete = scope.issues.length === 0;
      scope.state = scope.complete ? "COMPLETE" : "PARTIAL";
    }
  } catch (error) {
    const stopped = error instanceof LookupStop ? error :
      new LookupStop("LOOKUP_ERROR", String(error && error.message || error).slice(0, 300));
    stop = {
      code: stopped.code, message: stopped.message, stage, path: location,
      prefix: scope ? scope.prefix : null, tree_sha: activeTree,
      native_message: stopped.nativeMessage,
    };
    if (scope) {
      scope.issues.push(stop);
      scope.state = stopped.code === "FIRST_MATCH" ? "MATCH_FOUND" : "INTERRUPTED";
      scope.complete = false;
    }
  }

  const complete = stop === null && scopes.every(item => item.complete);
  return {
    schema: "commons-connected-github-paths/v1",
    status: matches.size ? "FOUND" : complete ? "NOT_FOUND_IN_SCOPE" : "INCONCLUSIVE",
    repository_full_name: repository,
    requested_ref: options.ref,
    commit_sha: commitSha,
    root_tree_sha: rootTreeSha,
    ...(transport === "token" ? { request: { transport, binding } } : {}),
    ...(options.filename === undefined ?
      { filenames: options.filenames } : { filename: options.filename }),
    matches: [...matches.values()].sort((a, b) => a.path < b.path ? -1 : a.path > b.path ? 1 : 0),
    coverage: {
      complete, scopes, directories,
      pending_directories: stop ? [
        ...(activeDirectory ? [{ ...activeDirectory, next_entry: nextEntry }] : []),
        ...queue,
      ] : [],
      unstarted_prefixes: scopes.filter(item => item.state === "NOT_STARTED").map(item => item.prefix),
      submodules_not_followed: [...submodules.values()],
      domain: "Blobs tracked in the selected repository; symlink targets and submodule contents are not followed.",
    },
    limits: {
      stop_after_first: options.stop_after_first,
      max_calls: options.max_calls, max_entries: options.max_entries,
      max_depth: options.max_depth, timeout_ms: options.timeout_ms,
    },
    counts,
    elapsed_ms: Date.now() - started,
    reads,
    stop,
  };
}

module.exports = { findGitHubPaths };

