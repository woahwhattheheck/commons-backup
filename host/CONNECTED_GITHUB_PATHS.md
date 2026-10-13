# Find repository paths through connected GitHub trees

[connected_github_paths.cjs](connected_github_paths.cjs) finds one or more exact
filenames under selected directory prefixes through a connected GitHub tool. The
planned additive transport option keeps the native fetch tool as the default
and supports an explicitly selected token connection. It resolves one commit
and follows that commit's Git trees. It returns paths and blob metadata without
downloading file bodies or creating a checkout.

Use this when a repository search omits a file, when a branch is moving, or
when the likely directory is known but the full path is not. The motivating
native search for `repo_backup.py` in `woahwhattheheck/commons` returned an
empty result even though the file was readable at the backup lane's recorded
commit. An empty code-search result establishes no repository-wide absence.

The default stops at the first matching basename. Set `stop_after_first: false`
when all matches in the selected scopes are needed. Every result keeps
coverage separate from matching.

## Connected use

Read the full helper source before evaluating it. In a JavaScript tool
orchestrator with the connected GitHub tools available:

```javascript
const fetched = await tools.mcp__codex_apps__github_fetch_file({
  repository_full_name: "woahwhattheheck/commons",
  path: "host/connected_github_paths.cjs",
  ref: "main",
});
if (fetched.isError ||
    typeof fetched.structuredContent?.content !== "string") {
  throw new Error("The helper source was not returned");
}
const moduleBox = { exports: {} };
new Function("module", "exports", fetched.structuredContent.content)(
  moduleBox, moduleBox.exports
);

const result = await moduleBox.exports.findGitHubPaths(tools, {
  repository_full_name: "woahwhattheheck/commons",
  ref: "fd70db8032e97ef8ba59faa2d14413b4616b9dd4",
  filename: "repo_backup.py",
  prefixes: ["host", "backups"],
});
text({ helper_blob_sha: fetched.structuredContent.sha, ...result });
```

A normal CommonJS host can instead import the file with `require()` and pass
its connected tool object. The module itself uses no Node filesystem, shell,
network client, package dependency, credential, or repository writer.
The planned signature is
`findGitHubPaths(tools, input, { transport, onResponse })`. It calls the
selected existing binding only:

```javascript
// Default: transport: "native"
tools.mcp__codex_apps__github_fetch({ url })

// Explicit: transport: "token"
tools.mcp__codex_apps__github_token_connection_github_read({ path })
```

Tool discovery stays with the invoking session. If discovery is partial, keep
working and repeat it under the existing [connected-tool guidance](../AGENTS.md).
A missing selected binding throws before any provider call. The helper does
not switch connections or transports, look up credentials, or substitute a
different account or route.

### Planned token transport and response retention

Token mode uses relative REST paths to resolve one commit and read only the
pinned, nonrecursive trees reached from it. The endpoint shapes remain those
described under commit and tree identity below. Its ref query formatter leaves
slash and colon literal, uses `+` for spaces, and escapes delimiters and literal
`+` characters. Native URLs and their encoding stay unchanged.

```javascript
const result = await moduleBox.exports.findGitHubPaths(tools, {
  repository_full_name: "woahwhattheheck/commons",
  ref: "aa9c92e7f7535a4c9319ceffa74e78582cc54a20",
  filename: "connected_github_issue_search.cjs",
  prefixes: ["host"],
}, {
  transport: "token",
  onResponse: async ({ url, kind, path, binding, response }) => {
    store("pinned-path-read:" + kind + ":" + path,
      { url, kind, path, binding, response });
  },
});
```

Token results add `request: { transport, binding }`, with
`transport: "token"` and
`binding: "mcp__codex_apps__github_token_connection_github_read"`.
Each token read also records its relative `path` and `binding`. The optional
awaited `onResponse` callback receives `{ url, kind, response }` in either
transport, plus `path` and `binding` in token mode. It receives the exact
original returned response, including failed or malformed wrappers. A callback
error is retained as `callback_error` on the affected read; it neither replays
the provider call nor discards returned data.

The token decoder accepts only a successful `structuredContent` wrapper with
a 2xx `status`, `ok === true`, and `data` containing a REST object or array.
Failed or ill-shaped wrappers retain the existing `LookupStop` outcome
classifications. Path matching, identity checks, coverage and existing result
fields stay unchanged. No retries, connection switches, mutations, credential
lookup or checkout are added.

Use the returned `path` and `commit_sha` for the next full source read:

```javascript
const match = result.matches.find(item => item.kind === "file");
if (!match) throw new Error("No regular file was located in the completed lookup");

const source = await tools.mcp__codex_apps__github_fetch_file({
  repository_full_name: result.repository_full_name,
  path: match.path,
  ref: match.commit_sha,
});
// Keep the native response. Check its SHA and full content before consuming it.
```

The existing [source importer](CONNECTED_GITHUB_SOURCE.md) can materialize that
full native response with its blob check. The existing
[publisher](CONNECTED_GITHUB_PUBLISH.md) remains the write road.

## Discover filenames in a known directory

`findGitHubPaths` requires an exact filename. When only the directory is
known, retain its native Contents response before inspecting it. For a new
needed read, use the actual observed directory URL and ref:

```javascript
const request = {url: observedDirectoryUrl};
store("directory.request", request);
const response = await tools.mcp__codex_apps__github_fetch(request);
store("directory.native", response);
```

If the response is already retained, reuse it without another provider read.
The caller-selected filename filter below is the one used for the actual
SHA/hash/digest/blob-identity lookup; it is not a filter added by the helper.

```javascript
const full = load("directory.native");
if (full?.isError ||
    typeof full?.structuredContent?.content !== "string" ||
    full.structuredContent.content.length > 1048576) {
  throw new Error("Inspect the retained response: expected bounded native JSON");
}
const entries = JSON.parse(full.structuredContent.content);
if (!Array.isArray(entries) || entries.some(entry =>
    !entry || typeof entry !== "object" || Array.isArray(entry) ||
    ["name", "path", "type", "sha"].some(key => typeof entry[key] !== "string"))) {
  throw new Error("Expected directory metadata; the native response is retained");
}
const matches = entries.map((entry, source_index) => ({entry, source_index}))
  .filter(({entry}) => /sha|hash|digest|blob_identity/i.test(entry.name));
const selected = matches.slice(0, 20).map(({entry, source_index}) => ({
  source_index, name: entry.name, path: entry.path,
  type: entry.type, sha: entry.sha, size: entry.size,
}));
const view = {
  request: load("directory.request"),
  scope: "retained_directory_response_only", snapshot: false,
  source_verification: "not_performed",
  observed_entries: entries.length, matched_entries: matches.length,
  selected_entries: selected.length,
  omitted_entries: entries.length - selected.length,
  omitted_matches: matches.length - selected.length,
  entries: selected,
};
if (JSON.stringify(view).length > 12000) {
  throw new Error("Select fewer entries; the complete response is retained");
}
text(view);
```

Source indices refer to the original retained array. The input guard at
1,048,576 UTF-16 code units, 20-row limit and 12,000 serialized code-unit
display guard apply after the native response arrives; they do not bound
a provider call. Names, paths and SHAs are not silently shortened. Selection and omission
counts describe the returned array, not complete repository coverage or
absence. A different native envelope or Contents media type needs its own
observed contract; it must not be treated as an empty directory.

GitHub's [Contents documentation](https://docs.github.com/en/rest/repos/contents#get-repository-content)
limits a directory response to 1,000 files and points larger directories to
the Git Trees API. Once a filename is known, use the existing bounded tree
lookup and its explicit coverage rather than inferring absence from a
directory count or a filtered display.

Provider descriptors are not full-source or Git-mode proof; this selection
follows no symlink or submodule. Use the located commit and full source read
before consuming a file. A listing from a moving ref and a later pinned read
remain separate observations unless their generation identity is established.

The motivating directory response contained 950 entries. The explicit
filename expression selected seven metadata rows from those same retained
bytes for a subsequent hashing-tool lookup. It also matched names containing
`shallow` or `shared`: a filename match does not establish hashing behavior.
No additional directory request or path-finder execution was needed.

## Find several filenames in one walk

Use `filenames` when the next source step needs several known entry points.
The helper checks the whole name set while visiting each directory, sharing
commit resolution, tree responses and the existing budgets across the lookup.

```javascript
const entries = await moduleBox.exports.findGitHubPaths(tools, {
  repository_full_name: "woahwhattheheck/smb-showcase-inventory",
  ref: "e1a8ed74fc1f7d318be58932a102893458f726ab",
  filenames: ["README.md", "cli.mjs"],
  prefixes: [
    "apps/retainer_drawdown_desk",
    "apps/sales_commission_desk",
    "apps/license_seat_trueup_desk",
  ],
  stop_after_first: false,
  max_depth: 0,
});
text(entries);
```

Supply either `filename` or a nonempty `filenames` array. Each array entry
has the same exact-basename rules as the single option. Duplicate names are
removed while preserving their first occurrence. Name order does not change
traversal priority: directory and provider entry order still determine the
first match. With the default `stop_after_first: true`, the lookup returns
after the first match for **any** requested name, not one match per name.

## Options

| Option | Meaning | Default |
|---|---|---|
| `repository_full_name` | One GitHub repository in owner/name form | Required |
| `ref` | An observed branch, tag, or full commit SHA | Required |
| `filename` | One exact, case-sensitive basename | Required unless `filenames` is supplied |
| `filenames` | Nonempty array of exact, case-sensitive basenames | Alternative to `filename` |
| `prefixes` | Ordered relative directory paths to search | Required |
| `stop_after_first` | Return as soon as the first matching blob entry is found | `true` |
| `max_calls` | Maximum calls through the selected binding, including commit resolution | `32` |
| `max_entries` | Maximum tree entries inspected across prefix resolution and searching | `50000` |
| `max_depth` | Descendant directory depth relative to each selected prefix | `8` |
| `timeout_ms` | Cooperative elapsed-time limit | `30000` |
| `options.transport` | Planned third-argument selection: `"native"` or `"token"` | `"native"` |
| `options.onResponse` | Optional awaited callback with `{url, kind, response}`; token mode also includes `path` and `binding` | None |

Use `prefixes: [""]` to select the repository root. Other prefixes use canonical
relative paths, without a leading/trailing slash, empty component, `.`, or
`..`. A prefix names a directory, so selecting a file produces
`PREFIX_NOT_DIRECTORY`. Filename matching is literal; there is no glob,
substring, case folding, content search, or Unicode normalization.

Exact duplicate prefixes are removed while preserving order. Overlapping
prefixes remain separate because each has its own relative depth. Likely
directories should come first: the helper completes or stops the current
prefix before starting the next.

At depth zero the selected directory itself is inspected. If it contains
child directories, those children are recorded as `DEPTH_LIMIT` gaps.
Choosing a depth limit does not turn an unsearched subtree into an absence
claim. Prefix resolution can inspect ancestors outside the selected subtree
to obtain its exact tree identity; it never searches sibling file bodies.

Call, entry, and time limits are positive safe integers. Depth can be zero.
Limits are caller-selected work budgets, not access controls.

## Commit and tree identity

A full 40-character commit SHA uses the small Git commit endpoint:

```text
GET /repos/{owner}/{repo}/git/commits/{sha}
```

A named or abbreviated ref resolves once through the
[commit-list endpoint](https://docs.github.com/en/rest/commits/commits#list-commits),
requesting only the starting commit's metadata:

```text
GET /repos/{owner}/{repo}/commits?sha={ref}&per_page=1
```

This endpoint avoids retrieving the changed-file patches of the single-commit
endpoint. The one returned commit SHA and root tree SHA must both be exact
object IDs. All
subsequent reads use tree SHAs reached from that root:

```text
GET /repos/{owner}/{repo}/git/trees/{tree_sha}
```

The `recursive` parameter is omitted entirely. GitHub treats even
`recursive=0` or `recursive=false` as a recursive request. Its
[tree API documentation](https://docs.github.com/en/rest/git/trees#get-a-tree)
describes the truncation flag and recommends fetching subtrees individually
when a recursive result is too large.

Named-ref movement after the first response does not mix revisions into the
lookup. Each match records the pinned commit, containing tree, blob SHA, mode,
size when supplied, and a URL pinned to that commit. The helper validates the
tree's returned SHA, entry shape, supported Git modes, and explicit boolean
truncation flag.

The same tree SHA is fetched at most once in an invocation. A cached tree can
still appear at more than one repository path. Both paths are traversed and
preserved; caching does not collapse different locations into one result.
Inspections of cached entries still count against `max_entries`.

## Match status and coverage

The result schema is `commons-connected-github-paths/v1`. A single-name
request retains the existing `filename` result field and shape. An array
request instead returns `filenames` with its deduplicated names.

| `status` | Meaning |
|---|---|
| `FOUND` | At least one matching tracked blob entry was located. Check its kind and coverage. |
| `NOT_FOUND_IN_SCOPE` | No matching blob was found, and every selected repository scope was completed or proved missing from a complete ancestor tree. |
| `INCONCLUSIVE` | No match was found and some requested coverage remains incomplete. |

A `FOUND` result can have `coverage.complete: false`. The default first-match
lookup intentionally does. This says the located path exists at the recorded
commit; it does not say that it is the only matching path.

For a `filenames` request, `FOUND` means at least one requested name has a
match; it does not mean every requested name was found. `NOT_FOUND_IN_SCOPE`
means none of the requested names matched in complete selected coverage.
Compare the requested names with returned paths when each name matters.
A requested name with no match remains unresolved while coverage is partial.

`coverage` includes:

- Per-prefix states, resolved tree IDs, missing-prefix paths, match counts, and
  issues.
- Every started directory scan, its relative depth, returned entry count,
  inspected entry count, and whether the direct listing was complete.
- Pending directory identities and the next entry index after a hard stop.
- Prefixes not yet started.
- Submodule entries encountered but not followed.

`stop` is null after uninterrupted traversal. Otherwise it records the
code, stage, current path/tree, prefix, and message. `FIRST_MATCH` is a
successful early return. `CALL_BUDGET`, `ENTRY_BUDGET`, and `DEADLINE`
identify work limits. Native failures and malformed responses carry distinct
codes; a native `isError=true` also retains up to 1,200 characters of its
text diagnostic in `native_message`. Keep provider diagnostics in the
invoking session.

Depth and provider truncation gaps are recorded in the affected scope even
when traversal can continue through other visible entries. A truncated
ancestor is sufficient to reach a prefix whose entry was returned; it is
insufficient to prove that an omitted prefix is missing.

The pending metadata describes remaining work. It is not an opaque resumption
token. To continue, select the remaining relevant prefixes using the same
`commit_sha`, or choose a larger budget for the original scope. A new call
has a new invocation-local tree cache. A pending current directory may already
have yielded matches; combine results by repository, commit, and path.

### Links and submodules

The search domain is **blob entries tracked by the selected repository**.

Regular and executable files return `kind: "file"`. A symlink entry is a blob
with mode `120000` and returns `kind: "symlink"`; its SHA identifies the
link's stored bytes. Its target is not followed or represented as a source
file. A submodule entry is recorded separately with its commit SHA, and its
external contents are outside the search domain. Selecting a prefix that
crosses a submodule stops with `SUBMODULE_PREFIX`.

Thus complete coverage never asserts that symlink destinations, external
submodule repositories, branches, history, untracked files, or working copies
were searched.

## Resource accounting and failures

`counts.calls` includes every read started through the selected binding, successful or failed.
`tree_reads` counts those calls that requested trees.
`tree_cache_hits` counts reuse of an already returned tree.
`entries_received` counts entries in successful tree payloads;
`entries_examined` counts the bounded inspections actually performed,
including ancestor resolution and cached entries.

The entry budget does not cap response bytes or the array returned by one
in-flight provider read. The time limit is checked before another read
or entry inspection; it cannot cancel a tool call already in progress.
The selected connector retains its own response-size and execution limits.

Invalid arguments and an unavailable selected binding throw before
network work. Runtime lookup failures return the structured partial result.
A host that requires a complete search should fail its command explicitly:

```javascript
text(result);
if (!result.coverage.complete) {
  throw new Error("Repository search incomplete: " +
    (result.stop?.code || "see per-scope coverage issues"));
}
```

A host that only needs one path should instead require a matching regular file
and keep the incomplete-coverage qualifier. Do not throw solely because the
normal first-match return has a `stop` record.

The helper performs no retries, recursive-tree fallback, source downloads,
local scan, clone, write, or account change after a failed read.

## Completed native use

The path traversal was executed through actual connected tool calls on
the backup lane's pinned commit:

```text
commit: fd70db8032e97ef8ba59faa2d14413b4616b9dd4
root tree: 566a6c6a3d5a8efb2fb4f88817aa4948be558026
```

| Actual lookup | Result | Native reads | Inspected entries | Coverage |
|---|---|---:|---:|---|
| `repo_backup.py` in `host`, then `backups`, first match | `host/repo_backup.py` | 3 | 1,230 | Stopped at first match; later entries and `backups` explicitly pending |
| `README.md` in `backups`, exhaustive selected scope | `backups/README.md` | 3 | 285 | Complete |

The located source blob was
`5c8a0cab3360ea2c154d3b45b4f91bd7d1df6739` (24,527 bytes); the guide blob
was `f0016309735f19b47696301702a6a1725d79c355` (4,494 bytes). Both matched
the previously recorded backup publication.

The first lookup took approximately 1.45 seconds and the second 1.12 seconds
in those native invocations. These are observations of those calls, not
latency guarantees. No file bodies, checkout, installs, test suite, fixture,
or workflow were needed for either lookup.

The named-ref resolution path was then executed on the final helper source.
The observed `main` resolved to `081f413dfe4b00319d37d496c6992a4e80850995`
(root tree `68df711c0233588df9de142d76fa92b44145df0d`) and located the same
`host/repo_backup.py` blob in three reads and 1,230 entry inspections,
stopping at its first match in approximately 1.08 seconds. Its first response
was the one-commit metadata list; subsequent reads used only the resolved tree
IDs.

