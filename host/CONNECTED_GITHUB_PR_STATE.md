# Read canonical pull-request state once

`connected_github_pr_state.cjs` reads a single pull request through the existing
native `github_fetch` action and preserves GitHub's nullable fields. Callers may
explicitly select the existing GitHub Token Connection read action instead. It
also projects an already retained response from either connection without
another provider call.

During integration of Commons PR #31205 on October 4, 2026, the compact
`get_pr_info` action reported `mergeable: false`. The canonical REST response
reported `mergeable: null` and `mergeable_state: "unknown"` for the same head.
The normal expected-head merge then succeeded. Treating the compact value as a
conflict would have created unnecessary source work or repeated checks.

GitHub documents three values for `mergeable`: `true`, `false`, and `null`.
`null` means its background calculation is pending. This helper does not
convert that observation to `false` or choose an integration action.

## Use in connected code mode

Fetch the helper once and retain its source for the current operation:

~~~javascript
const fetched = await tools.mcp__codex_apps__github_fetch_file({
  repository_full_name: "woahwhattheheck/commons",
  path: "host/connected_github_pr_state.cjs"
});
if (fetched.isError) throw new Error("PR reader source was not retrieved");
const box = { exports: {} };
new Function("module", "exports", fetched.structuredContent.content)(box, box.exports);

const result = await box.exports.readGitHubPullRequest(tools, {
  repository_full_name: "woahwhattheheck/commons",
  pr_number: 31205
});
store("current-pr", result);
text({ status: result.status, calls: result.calls, pr: result.pr });
~~~

Use the repository and PR number of the actual task. Pin the helper's source
`ref` when retaining a particular version matters. The helper makes one native
GET to `/repos/{owner}/{repo}/pulls/{number}`. It performs no polling, sleeping,
automatic retry, secondary search, credential lookup, or mutation. Reuse the
loaded module instead of fetching it for every PR. The initial module-source
fetch is separate from `result.calls`.

Retain the result privately: `response` contains the complete native envelope,
including bodies and other metadata that the compact view omits. A provider
error response also remains available there. Printing only `status`, `calls`,
and `pr` avoids repeating the full provider response in the working context.

### Select the existing private-token read route

When the current operation uses the GitHub Token Connection, select it explicitly:

~~~javascript
const result = await box.exports.readGitHubPullRequest(tools, {
  repository_full_name: "woahwhattheheck/commons",
  pr_number: 32226
}, { transport: "token" });
store("current-token-pr", result);
text({ status: result.status, calls: result.calls, pr: result.pr });
~~~

The selected binding is
`mcp__codex_apps__github_token_connection_github_read`, called once with the
relative REST `path`. The result's `request` retains that path, transport and
binding alongside the canonical API URL. Default or `transport: "native"`
preserves the existing native request and result shape. Unknown options or
transport values throw before a provider call, as does a missing selected
binding.

Route selection belongs to the caller's current authorization and provider
state. The helper never switches connections after an error, retries a denied
operation, looks up credentials, or infers account permission. A successful
token response's `{status, ok, data}` wrapper is decoded only when `ok` is true
and the recorded HTTP status is 2xx. Its canonical PR fields retain the same
nullable descriptors. A returned `ok: false`, error envelope or HTTP error
status becomes `NATIVE_ERROR`; the complete response remains available privately.

## Interpret fields without losing information

Nullable fields have `{present, value}` descriptors:

| `mergeable` descriptor | Meaning |
| --- | --- |
| `{present: true, value: true}` | GitHub reported mergeable at this observation. |
| `{present: true, value: false}` | GitHub reported not mergeable at this observation. |
| `{present: true, value: null}` | GitHub has not provided a computed mergeability value. |
| `{present: false, value: null}` | The supplied payload omitted the field. |

Read `mergeable_state` separately and preserve its literal string. A missing
value is distinct from a present `null`. The same descriptors preserve
`draft`, `merged`, `merge_commit_sha`, `merged_at`, and `updated_at`.

`state`, `title`, `number`, the canonical URL, and both branch refs, SHAs and
repository names are included. A deleted head repository remains `null`.
Reviewers, status checks, labels and other provider fields stay in the original
`response`; this is a compact view, not their absence from GitHub. Body text is
omitted by default and can be selected explicitly as described below.

### Read exact body text for claim and description changes

For a claim or description update, request the body from this same canonical
PR response instead of using the indexed body returned by `github_search_prs`:

~~~javascript
const current = await box.exports.readGitHubPullRequest(tools, {
  repository_full_name: "amithmandassociates-oss/hash-report-tool",
  pr_number: 56
}, { include_body: true });
if (current.status !== "READ" || !current.pr.body.present) {
  throw new Error("The current PR body was not retrieved");
}
const originalBody = current.pr.body.value;
store("current-description", { head: current.pr.head, body: originalBody });
~~~

`include_body: true` adds `body: {present, value}` to the projection. The value
is the exact string, a present `null`, or an absent field distinguished by
`present: false`. It comes from the same GET as the branch head and update time;
there is no extra hydration request, search, retry or mutation. The compact
default remains unchanged. The retained-response projector supports the same
option: `projectGitHubPullRequest(response, {include_body: true})`.

The body contains provider-visible text, so retain it privately and print only
what the current work needs. A captured body does not prevent later concurrent
edits; the caller still rereads and composes current text before writing.

During the Hash Report PR #56 payment follow-through, native
`github_search_prs` omitted an existing `/claim #2`, while the exact REST PR
body already contained it. Indexed search supplied the lead; the canonical
body preserved the existing claim rather than duplicating it.

These are observed fields, not a claim that the work is ready, authorized,
accepted, or paid. In particular, `merge_commit_sha` can identify a temporary
test merge before integration. Check `merged` and `merged_at` before describing
it as a completed merge. A provider-level `false` is not by itself a diagnosis
of the exact conflicting source paths.

## Read retained responses locally

~~~javascript
const view = box.exports.projectGitHubPullRequest(retainedNativeResponse);
text(view);
~~~

The projector accepts a canonical REST PR object or the native MCP envelopes
that contain it in `structuredContent`, JSON-text `content`, or text content
blocks. It does not mutate the original object or assign a new observation
time. Keep the original request and capture time beside retained data.

It also accepts the successful HTTP envelope retained by the private-token
reader, including the envelope in `structuredContent` or a JSON text block.
Arbitrary objects nested under `data` are not traversed without that successful
HTTP wrapper. Failed wrappers do not become canonical PR state.

Native envelopes can repeat identical PR JSON at several wrapper paths. The
projector parses each canonical PR text once per invocation. Other wrapper JSON
keeps its original traversal; the cache does not survive a projection or hide a
later provider response.

The flattened compact `get_pr_info` response is intentionally not treated as
canonical REST data: once `null` has been converted to `false`, the original
value cannot be reconstructed from that summary. Use a retained canonical
response, or replace the compact lookup with this one-read path.

## Errors and request accounting

The live reader returns `READ`, `TOOL_ERROR`, `NATIVE_ERROR`, or
`INVALID_RESPONSE`. On a failed read, `pr` stays null; failure does not become
"closed", "not mergeable", or "not found". `error.message` explains the local
classification. The original provider envelope remains in `response` when a
response was returned; thrown tool errors retain their message instead.

`calls: 1` counts the attempted selected request, not a successful read. The
started/finished timestamps and elapsed milliseconds cover that invocation.
There is no timeout/retry wrapper or hidden continuation. Honor actual provider
cooldowns before a later deliberate request; this helper does not change quotas
or select another account or endpoint after rejection.

Invalid local inputs throw before a native call. Canonical payloads with
malformed typed fields or a different repository/PR identity return
`INVALID_RESPONSE` from the live reader; the original response remains
available for reconciliation. The standalone projector throws for malformed
payloads. It accepts absent nullable fields and makes their absence explicit.

## Actual use, October 4, 2026

The new module ran in the cloud VM with Node on the retained original PR
#31205 REST response. It exited zero and preserved the real open/unmerged state,
head `8c3da6665b7c218d174621dd40feff39c84d5139`, `mergeable: null`, and
`mergeable_state: "unknown"`. This projection made zero provider calls.

The live reader then ran with the actual connected native binding. Its single
GET returned `READ` in 441 ms and preserved the subsequently closed/merged
state, merge SHA `9027182da611ed83daf56eaef9988b3d145dd599`, merge time
`2026-10-04T11:48:30Z`, and the still-null mergeability field. The source's
earlier compact-then-REST lookup used two PR calls; this path obtains the
canonical fields in one. The source-module load is separate.

Those are individual observed calls and request counts, not a general latency
benchmark. No test suite, generated fixture, induced error, background task,
or repeated publication-validator run was used. The missing-field and error
branches are implemented as described but were not forced during this use.

On a later retained native response for Sourcey PR #1426, nested wrappers
contained the same 17,950-byte canonical JSON twice. Executing the original and
updated projectors in the connected V8 runtime reduced successful full-payload
parses from two (35,900 bytes) to one (17,950 bytes). The compact projection was
identical, the original envelope was unchanged, and both replays made zero
provider calls. The non-JSON status-text attempt remained. This measures parsing
work on that real response, not end-to-end latency or a change in API quotas.

Provider contract: [GitHub REST — get a pull request](https://docs.github.com/en/rest/pulls/pulls#get-a-pull-request).
Related helpers: [issue/PR search](CONNECTED_GITHUB_ISSUE_SEARCH.md),
[changed-file comparison](CONNECTED_GITHUB_COMPARE.md), and
[publication](CONNECTED_GITHUB_PUBLISH.md).

