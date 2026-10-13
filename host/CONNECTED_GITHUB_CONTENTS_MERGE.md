# Continue a confirmed Contents publication through merge and readback

`host/connected_github_contents_merge.cjs` exports
`createGitHubContentsMergeContinuation(publisherExports)`. Supply the already
loaded `connected_github_publish.cjs` exports; the constructor binds its
`resolveReadback`, `inspectToolError` and `GitHubPublishError` helpers. It returns
an async `continue(tools, change, savedContentsProgress, options?)` function.

Use this continuation after every required UTF-8 Contents create/update write
and the existing pull request have successful acknowledgements. It reads and
reconciles those identities, optionally merges that PR once, and checks the
prepared files at the immutable merge commit. It creates no source objects,
files, branches or PRs. The original Contents checkpoint remains unchanged.

## Required checkpoint and prepared change

Pass the same exact prepared change used for the Contents publication. Keep the
file array in its original order, with the exact UTF-8 `content`, `path`, observed
`expected_blob_sha` (or explicit `null` for a new file), and required
`expected_new_blob_sha` for every file. Pins are lowercase 40-character Git SHAs.
Encoding must be omitted or `"utf-8"`. Deletions, binary/base64 files and
caller-selected modes are unsupported.

The checkpoint must have `operation: "contents_publication"`,
`branch_created: true` and `pending_write: null`. Its repository, base branch
and publication branch must match the change; `base_commit_sha` and `commit_sha`
must be observed identities. The complete `files[]` must match the prepared
paths and old/new pins, including each boolean `write_required`. A no-op file
must already have its new pin as its old blob identity.

At least one file must require a write. Every required write must have one
`serial_writes[]` acknowledgement in changed-file order: matching path,
`create_file` for a null preimage or `update_file` otherwise, observed
`commit_sha`, and `parent_sha`. The chain starts at `base_commit_sha` and ends
exactly at saved `commit_sha`; any retained response/commit blob pins must match
the prepared new pin. This helper cannot continue a partial file publication or
an unacknowledged pending write.

Keep the confirmed existing PR in saved `pull_request`, with its native
`number` and `head_sha`. Alternatively supply the exact successful native
create-PR MCP acknowledgement as `options.confirmed_pull_request`; its
`structuredContent` must carry those fields. An error or arbitrary nested
payload is refused. If both are supplied, their number and head must match.
The confirmed PR head must equal the acknowledged Contents `commit_sha`.

## API

| Argument or option | Contract |
| --- | --- |
| `publisherExports` | Loaded core exports containing `resolveReadback`, `inspectToolError` and `GitHubPublishError`. |
| `tools` | Caller-supplied discovered functions with the exact native contracts below. |
| `change.repository_full_name` | Exact prepared `owner/repository`. |
| `change.base_branch`, `change.branch_name` | Matching short branch names; base defaults to `main` and must differ from the publication branch. |
| `change.merge`, `change.merge_method` | Explicit `merge: true`; method is `merge` (default), `squash` or `rebase`. |
| `change.files` | Complete ordered prepared file set, 1–300 files, with required old/new pins and exact UTF-8 content. |
| `savedContentsProgress` | Complete acknowledged checkpoint described above. |
| `options.bindings` | Optional action-to-tool-name overrides for `fetch`, `fetch_file`, `fetch_blob` and `merge_pull_request` only. Defaults are `mcp__codex_apps__github_` plus the action. |
| `options.confirmed_pull_request` | Original successful native create-PR MCP acknowledgement when needed. |
| `options.onResponse` | Optional awaited callback receiving `{action, binding, args, response}` for each returned raw native response, including failures. |
| `options.onProgress` | Optional awaited callback receiving a JSON copy of continuation progress. |
| `options.readback_concurrency` | Safe integer 1–16; default 4, bounding independent per-file readbacks. |

Unknown options or binding actions are rejected. `fetch` and `fetch_file` must
be available before reading the PR. `merge_pull_request` is required only when
the canonical PR is open and reaches the merge step; `fetch_blob` is optional.
Overrides must preserve these native argument and return contracts:

| Action | Native arguments and required returned data |
| --- | --- |
| `fetch` | `{url}` for the exact GitHub REST resource; successful `structuredContent` is a REST object or contains its JSON string as `content`. |
| `fetch_file` | `{repository_full_name, path, ref, encoding: "utf-8"}`; successful native file payload supplies observed `sha` and available literal content for the core resolver. |
| `fetch_blob` | `{repository_full_name, blob_sha}`; optional immutable blob read supplies decoded UTF-8 `content` for the core resolver. |
| `merge_pull_request` | `{repository_full_name, pr_number, expected_head_sha, merge_method}`; success must return `merged: true` and the actual merge `sha` in `structuredContent`. |

The helper uses `inspectToolError` for native failure evidence and requires a
successful structured payload. It has no automatic retry, transport switch,
credential lookup or nested-payload fallback. Retain the original raw responses
through the callback; ordinary HTTP or connector success alone cannot stand in
for the required payload identities.

## Load beside the already loaded core module

In code mode, retain the new helper's source envelope before loading it. The
following uses `publisherExports` from the already loaded core module and an
existing prepared change, checkpoint and successful PR acknowledgement:

```js
if (retainedContentsMergeSource.isError ||
    retainedContentsMergeSource.structuredContent?.encoding !== "utf-8") {
  throw new Error("Readable continuation source is required");
}
const continuationBox = {exports: {}};
new Function("module", "exports",
  retainedContentsMergeSource.structuredContent.content
)(continuationBox, continuationBox.exports);
const continueContentsMerge = continuationBox.exports
  .createGitHubContentsMergeContinuation(publisherExports);
const rawCalls = [];
const progress = await continueContentsMerge(tools, preparedChange,
  savedContentsProgress, {
    confirmed_pull_request: retainedSuccessfulCreatePRAcknowledgement,
    onResponse: async observed => {
      rawCalls.push(observed);
      store("contents-merge-native-calls", rawCalls);
    },
    onProgress: async checkpoint => {
      store("contents-merge-progress", checkpoint);
    }
  });
store("contents-merge-result", progress);
```

Omit `confirmed_pull_request` when the saved checkpoint already contains the
confirmed PR. Keep the original source checkpoint and prepared content beside
the new continuation progress and native-call records.

## Reconciliation, merge and immutable readback

The helper first reads the canonical existing PR and checks its number, exact
head SHA, publication branch, head repository and base branch. A confirmed
merged, closed PR skips the merge call and proceeds to immutable readback using
its actual `merge_commit_sha`. On this path,
`serial_lineage_verification` remains `"retained_metadata_only"` and
`aggregate_paths_verification` remains `"not_performed"`; skipped checks are
not reported as observed. Mode and whole-tree verification remain
`"not_performed"`.

For an open PR, it observes every acknowledged Contents commit as a sole-parent,
sole-path added/modified change with the expected blob. It compares the original
base and acknowledged head to check the aggregate paths and commit count, then
checks the current publication branch head and current base-file preimages at
the observed base commit. A new file's null preimage requires an explicit native
404 error; a provider failure never becomes an empty successful file. Changed
preimages or a moved head stop before merging.

Only after those checks does it call the expected-head merge once. Progress
records `pending_write` before dispatch; an exception, error or unconfirmed
merge leaves that uncertainty retained for reconciliation. A confirmed merge
clears `pending_write` and records its actual SHA. Do not replay an uncertain
effect from an error checkpoint.

Every prepared file, including retained no-op files, is read at the immutable
merge SHA. The existing core `resolveReadback` compares the observed blob and
literal UTF-8 content with the prepared source. If file content is omitted and
an explicit `fetch_blob` binding exists, the resolver can read that observed
immutable blob; it does not manufacture empty content. Settled readbacks stay
in prepared-file order. `status: "merged"` with `stage: "complete"` requires
every readback to report `matches: true`. An incomplete readback retains the
confirmed merge and calls for readback reconciliation alone.

## Preserve responses and callback failures

`onResponse` runs after the original response is retained and before payload
validation. Its errors are kept in `callback_errors` without erasing that
response or causing another provider call. `onProgress` errors are separately
kept in `progress_callback_errors`; progress callbacks receive copies.

Failures throw the core `GitHubPublishError`. Retain its `progress`, `cause` and
original raw failed `response`, plus any `tool_error` and per-file readback
evidence in progress. A thrown provider call has no returned response to emit.
Returned native errors and invalid structured payloads also remain in
`progress.failed_responses`, with their exact action, binding, arguments and
raw response. This retains a failed optional blob read even when the core
resolver reports it as an incomplete readback rather than throwing it onward.
The original Contents checkpoint is never rewritten to conceal a failure or
claim that retained metadata was freshly verified.
