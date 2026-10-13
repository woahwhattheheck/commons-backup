# Connected GitHub issue search and retained projections

[connected_github_issue_search.cjs](connected_github_issue_search.cjs) provides bounded issue and pull-request search through the existing native GitHub fetch action. It forwards the caller's exact GitHub query to `/search/issues` and retains the returned item fields. Its pure `projectGitHubIssueItems` companion provides bounded views of those retained bodies without another provider call.

The same module also provides `projectGitHubConnectorIssueHeaders` for an already retained shortcut search or native single-issue envelope. It preserves the inner issue metadata, including issue numbers and nullable fields, while producing bounded headers with body text withheld. See [shortcut search headers](#project-shortcut-search-headers-from-a-retained-envelope) for its separate input and coverage contract.

This packages the existing route workaround for queue intake. During the October 3 Broker work, `github_search_issues` returned ordinary issue #1406 for a query containing `is:pr`. Direct metadata confirmed that item was an open issue. The identical query through the approved native REST route returned zero open Broker PRs. The route had already been shared in fleet coordination; this module supplies reusable pagination and coverage reporting.

The module uses the caller's connected tool object. It owns no credentials, network client, filesystem, or mutation action. Native fetch remains the default; callers may explicitly select the existing GitHub Token Connection read action.

## Use from code mode

~~~javascript
const fetched = await tools.mcp__codex_apps__github_fetch_file({
  repository_full_name: "woahwhattheheck/commons",
  path: "host/connected_github_issue_search.cjs",
  ref: "main"
});
if (fetched.isError) throw new Error("Issue reader source was not retrieved");

const box = { exports: {} };
new Function("module", "exports", fetched.structuredContent.content)(
  box, box.exports
);
const result = await box.exports.searchGitHubIssues(tools, {
  query: "repo:woahwhattheheck/smb-showcase-inventory is:pr is:open broker",
  sort: "updated",
  order: "desc",
  per_page: 50,
  max_pages: 2,
  timeout_ms: 30000
});
store("broker-pr-query", result);
text({
  status: result.status,
  stats: result.stats,
  coverage: result.coverage,
  items: result.items.map(item => ({
    number: item.number,
    title: item.title,
    state: item.state,
    kind: item.pull_request ? "pull_request" : "issue",
    url: item.html_url
  }))
});
~~~

Pin the helper source ref when an operation needs a retained version. Supply repository, author, kind, state, date and other selectors in `query` as needed. The helper neither adds repository qualifiers nor rewrites the query. The current connector's approved resource access still applies.

Keep an explicit `is:issue` or `is:pr` selector for single-kind queues. GitHub documents that some GitHub App user-token searches require a kind qualifier. Use separate queries when both kinds are needed under those connections.

### Select the existing private-token read connection

~~~javascript
const result = await box.exports.searchGitHubIssues(tools, {
  query: "repo:woahwhattheheck/commons is:issue is:open connector -label:board",
  per_page: 20,
  max_pages: 1
}, {
  transport: "token",
  onResponse: ({ page, path, binding, response }) => {
    store("token-issue-query-" + page, { path, binding, response });
  }
});
text({ status: result.status, stats: result.stats, coverage: result.coverage });
~~~

The selected binding is `mcp__codex_apps__github_token_connection_github_read`.
Each page makes one call with a relative `/search/issues` path. Token results
add `request.transport` and `request.binding`; each coverage page retains its
actual `path`, and the response callback additionally receives `path` and
`binding`. Existing URL, query, pagination, deduplication and coverage fields
remain available. Default or `transport: "native"` keeps the native request
and result shape. Route selection is explicit: the helper never switches
connections after an error or performs credential lookup.

For this selected route, query encoding leaves colon and slash literal, uses
`+` for spaces, and keeps reserved parameter delimiters and literal `+` escaped.
Those spellings preserve the parameter value. The token connector rejected a
fully encoded scoped query with `INVALID_ARGUMENT` / “Use a relative GitHub
REST path”; the query-safe spelling reached GitHub successfully and returned
the intended repository's open non-board issues. This is an observed formatter
workaround, not a change to that connector's validation or provider access.
Native URL encoding is unchanged. Unknown query shapes can still receive a
provider error; no scope, permission or query-application claim is inferred.

Only a token wrapper with `ok: true`, a 2xx integer `status` and canonical
search `data` is decoded. An explicit error, `ok: false` or HTTP error status
stops as `NATIVE_ERROR`; the original callback response remains available.
Arbitrary objects under `data` are not search payloads without the successful
HTTP envelope.

### Choose whether imported board records belong in the query

A technical keyword can also match issue-body transport metadata. In the Commons
intake, imported board records included carrier text such as `discord-connector`
and appeared in a search for `connector`. A keyword match alone therefore does
not identify a new tooling request.

When the caller intentionally wants open issues other than those labeled `board`,
put that choice in the native query:

~~~javascript
const result = await box.exports.searchGitHubIssues(tools, {
  query: "repo:woahwhattheheck/commons is:issue is:open connector -label:board",
  sort: "updated",
  order: "desc",
  per_page: 30,
  max_pages: 1
});
~~~

Keep board records in scope when their imported work is the intended source.
The `board` label is a convention observed in this repository, not a universal
issue kind or an ownership decision. Inspect the selected record and its current
source before deciding what work remains. The adapter forwards either query
exactly; it never adds this exclusion or classifies records on the caller's behalf.

In the actual October 4, 2026 intake, the same open-issue query without the label
exclusion advertised 6,284 matches; the explicitly scoped query returned 12 items.
Those are dated search observations, not a full inventory of work or a statement
that the excluded records lack useful tasks. The original native responses and
query strings were retained; no adapter change or repeat query was needed.

## Inputs and retained responses

| Input | Meaning |
| --- | --- |
| `query` | Required nonempty GitHub search string, forwarded without normalization. |
| `sort` | Optional supported GitHub sort: comments, reactions and its named variants, interactions, created, or updated. Omitted uses provider best-match order. |
| `order` | `asc` or `desc`; default `desc`. GitHub ignores it when sort is omitted. |
| `per_page` | 1–100; default 100. Reduce it when individual issue bodies make native responses too large. |
| `start_page` | Default 1. Starting later remains explicitly partial. |
| `max_pages` | Maximum native request attempts; default 4. |
| `timeout_ms` | Cooperative budget checked before each request; default 30,000 ms. Zero returns before a request. |
| `updated_at_lte` | Optional caller-declared inclusive update-time ceiling; observes retained metadata without changing the query or filtering rows. See the bound observation below. |
| `options.onResponse` | Optional awaited callback receiving `{page, url, response}` for each original native result, including native errors. |
| `options.transport` | `native` (default) or `token`; selects one existing connected read binding without automatic fallback. |

~~~javascript
const result = await box.exports.searchGitHubIssues(tools, {
  query: "repo:woahwhattheheck/commons is:issue is:open tooling",
  sort: "updated",
  per_page: 20,
  max_pages: 2
}, {
  onResponse: async ({ page, url, response }) => {
    store("tooling-query-page-" + page, { url, response });
  }
});
~~~

`items` contains the first observed native item for each unique GitHub item ID. Its fields, including body, state, repository URL, and any `pull_request` object, are retained unchanged. Returned issue metadata is therefore available for the next useful read without another discovery search. The callback can retain the original MCP envelope and duplicate occurrences privately.

The helper counts ordinary issues and PRs from the returned `pull_request` marker. It does not infer mergeability, ownership, approval, current source state, or task completion from a search match. Read a selected record directly when those facts matter.

For a selected pull request, use the [canonical PR-state reader](CONNECTED_GITHUB_PR_STATE.md). It preserves GitHub's `true`/`false`/`null` mergeability in one native GET and can project a retained response without another request. A compact tool's `false` may represent an upstream `null`; do not infer a source conflict from that summary alone.

Unknown helper fields, invalid budgets, unsupported sort/order, invalid callbacks, or a missing native fetch binding throw before a provider call. GitHub receives the search expression itself and reports query validation or access errors.

## Coverage and stop reasons

| Result status | Interpretation |
| --- | --- |
| `FOUND` | At least one actual search item was retained. Remaining coverage may be partial or a later call may have failed. |
| `NOT_FOUND_IN_QUERY` | A complete observed search traversal returned no items. This is a result for this query, not proof of absence from a repository. |
| `INCONCLUSIVE` | No item was retained and the observed traversal is incomplete. |

`coverage.complete` requires traversal from page 1, a page end or advertised total, exactly that many unique IDs, and no provider incompleteness, changing counts, repeated IDs, or search-limit boundary. It describes the observed query response only. `search_index` is always true and `snapshot` is always false: indexed search and live offset pages cannot establish an immutable repository inventory. Equal-size substitutions and indexing lag need not change the advertised count.

GitHub exposes up to 1,000 results per search. The helper reports `SEARCH_RESULT_LIMIT` when the advertised result reaches that boundary and refuses to request an offset at or beyond it. Even an advertised total of exactly 1,000 remains conservatively incomplete. Narrow the query to inspect additional results; a larger local page budget does not remove the provider ceiling.

Each page records its actual URL, total count, `incomplete_results` flag, received count and newly retained count. The result also includes observed totals, repeated item IDs, request counts, issue/PR counts, and the next page. A provider `incomplete_results:true` sets `PROVIDER_INCOMPLETE_RESULTS` even if a short page is returned.

Other stop codes are `PAGE_BUDGET`, `DEADLINE`, `PAGINATION_END`, `ADVERTISED_TOTAL_REACHED`, `TOOL_ERROR`, `NATIVE_ERROR`, and `INVALID_RESPONSE`. Items obtained before an error remain usable. Compact diagnostics are limited to 1,200 characters; the callback retains the complete native response when supplied.

An in-flight provider call or callback can finish after the cooperative deadline. Callback failures are recorded and do not cause a provider replay. The helper has no retry loop, background process, or scheduled continuation.

## Continue a useful partial query

Retain the original query, sort, order and page size, then supply `coverage.next_page` in a later deliberate invocation:

~~~javascript
const nextPage = result.coverage.next_page;
if (nextPage !== null) {
  const continuation = await box.exports.searchGitHubIssues(tools, {
    query: result.query,
    sort: result.sort,
    order: result.order,
    per_page: result.coverage.per_page,
    start_page: nextPage,
    max_pages: 2
  });
  store("tooling-query-continuation", continuation);
}
~~~

A page number is an offset into a live search, not a snapshot cursor. A later invocation reports `STARTED_AFTER_FIRST_PAGE` and cannot certify earlier pages. Preserve prior observations when combining results. On an invalid item or failed request, `next_page` remains the attempted page; a caller may need to reread that page and reconcile repeated IDs.

Coverage is information for intake. It does not create a work reservation or a publication requirement.

## Actual native use, October 3, 2026

The final source ran directly in code mode with the real connected GitHub fetch action. Four useful reader operations made six native requests:

| Operation | Native outcome |
| --- | --- |
| Current open Broker PR query | One page, zero items, `NOT_FOUND_IN_QUERY`, complete observed query. |
| Closed Broker titles, one item per page, two-page budget | Two actual PRs: #2122 and #2119. Six results advertised; `PAGE_BUDGET` and next page 3. |
| Continue the same history from page 3 for two pages | Actual PRs #2115 and #2104. `STARTED_AFTER_FIRST_PAGE`, `PAGE_BUDGET` and next page 5; two advertised items remain unread. |
| Open Goodwood issue query | One ordinary issue, #1406, with its open state and original metadata. Complete observed query. |

Each returned item matched the corresponding original native object exactly; callback errors were empty. The first two bounded history windows intentionally did not exhaust the query. The Broker keyword also matches the customs-broker title, as the explicit query requests.

Observed operation durations were 430 ms, 907 ms, 856 ms, and 503 ms respectively. These are individual native lookup observations, not a general throughput claim. There was no VM process, install, generated input, fixture, provider mutation, or replay of a prior product proof.

This exercise covered real issue/PR distinction, native metadata retention, an empty result, page-budget stopping and continuation. Provider timeout, rate-limit, malformed-response and 1,000-result boundary handling are implemented conservatively; no induced provider failure or synthetic response was used.

Provider contract: [GitHub REST — search issues and pull requests](https://docs.github.com/en/rest/search/search#search-issues-and-pull-requests), read October 3, 2026. The page ceiling, search limit, incompleteness flag and token-specific kind requirement inform this adapter; the connector qualifier mismatch and supported route above are actual session observations.

Related connected capabilities: [path lookup](CONNECTED_GITHUB_PATHS.md), [workflow runs](CONNECTED_GITHUB_WORKFLOW_RUNS.md), [source materialization](CONNECTED_GITHUB_SOURCE.md), and [publication](CONNECTED_GITHUB_PUBLISH.md).


## Read selected bodies without repeating the search

The same module also exports the synchronous function
`projectGitHubIssueItems(items, options)`. Pass the retained native item
array, either `result.items` from `searchGitHubIssues` or
`retainedNativePayload.items` from a captured REST search page. It does not
call a tool, fetch a page, sort or deduplicate items, mutate the input, or claim
that the supplied records came from GitHub. Keep the complete original response
and its request context with the caller.

Use a bounded overview before selecting full bodies:

~~~javascript
const view = box.exports.projectGitHubIssueItems(result.items, {
  max_items: 12,
  max_body_chars: 240,
  max_total_body_chars: 2880
});
text({
  query: result.query,
  search_coverage: result.coverage,
  view
});
~~~

The overview retains item IDs, numbers, issue/PR kind, titles, state, API and
HTML URLs. When supplied, it also retains repository URL, creation/update/close
times and comment count. Other native fields, including author, labels,
assignees, reactions and the full `pull_request` object, remain in the
original items. This is a projection of selected fields, not a complete copy.

Select the next useful records by their original zero-based array indices:

~~~javascript
const selected = box.exports.projectGitHubIssueItems(result.items, {
  source_indices: [1, 4, 16],
  max_items: 3,
  max_body_chars: 10000,
  max_total_body_chars: 20000
});
text(selected);
~~~

These indices are caller choices from the first observed array, not GitHub issue
numbers or a recommendation to inspect those positions in every query. A sparse
selection preserves their increasing original order. To read a contiguous later
window, supply `start_index` instead and use the returned
`selection.next_index`. Neither form requests another provider page.

### Projection inputs and bounds

| Option | Default | Accepted values |
| --- | --- | --- |
| `start_index` | 0 | Safe integer from 0 through the supplied array length; cannot be supplied with `source_indices`. |
| `source_indices` | Omitted | Increasing, distinct, in-range zero-based indices; length cannot exceed `max_items`. |
| `max_items` | 12 | Safe integer from 0 through 100. |
| `max_body_chars` | 500 | Safe integer from 0 through 100,000; applies separately to each selected text body. |
| `max_total_body_chars` | 6,000 | Safe integer from 0 through 1,000,000; consumed in selected-item order. |
| `max_metadata_chars` | 4,096 | Safe integer from 0 through 65,536; applies to the selected metadata fields of every supplied item before projection. |

The input must be an array with at most 1,000 entries. This is a local projection
bound; it neither changes the search reader nor establishes query completeness.
Every input item is checked using the existing native ID/number/URL/PR-marker
contract. Title and state must be strings; optional metadata fields must have
their documented string/null or nonnegative-integer shape. Metadata character
count is the sum of these primitive values' string lengths, with null counting
as zero. It excludes JSON syntax and field names. Metadata is never silently
truncated.

All input rows are checked, including omitted rows. Non-array input, excessive
input length, unknown options, incompatible selectors, malformed records, or
invalid budgets throw `TypeError` or `RangeError` before any
projection is returned. The function has no provider side effects. A zero
metadata budget therefore only accommodates an empty input array. A zero
item budget returns no items; for a nonempty remaining contiguous window its
next index is unchanged, so repeating that same call will not advance.

### Literal bodies and visible omissions

For a text body, `body` is a literal prefix of the supplied string.
There is no Unicode, whitespace, line-ending, Markdown, HTML-entity or link
normalization. Limits and ranges use JavaScript UTF-16 code units, not UTF-8
bytes or rendered characters. A truncation boundary moves back by one code unit
if needed to keep a valid surrogate pair together.

Each selected item includes:

- `source_index`: its original position in the supplied array;
- `body_state`: `text`, `null` or
  `missing`, preserving those different input states;
- `body_chars`: the full supplied text length, or null when no text
  body was supplied;
- `returned_body_chars`: the returned prefix length;
- `body_range`: the half-open prefix interval
  `[0, returned_body_chars]`, or null for a null/missing body;
- `truncated`: whether supplied body text was omitted, or null
  for a null/missing body.

An empty string remains a text body with length zero and range
`[0, 0]`. A null or missing body does not establish that the issue has
no description or work remaining. Exhausting a text budget does not drop a
selected item's metadata; its remaining body is explicitly truncated.

Coverage records supplied, selected and omitted item counts; half-open omitted
index ranges; text/null/missing body counts; full supplied and selected text
lengths; returned text length; and the number of truncated text bodies. The
`all_*` flags concern selection and text strings in this supplied array
only. They do not include unprojected native fields, uncaptured pages or absent
body text.

The projector does not evaluate search coverage. Retain and display the original
query and `result.coverage` separately; a fully projected captured page
may still belong to an incomplete search. Sparse selection has no automatic
next index. For empty input, the selection flags are vacuously true, without
making any provider-level absence claim.

Indices refer to the exact array passed to this call. The search reader already
retains the first observation of each unique item ID; projecting that result
does not restore duplicate occurrences from native pages. Use the original
`onResponse` captures when individual occurrences matter. The projector
itself preserves all supplied entries, including repeated IDs, in their original
positions.

### Actual retained-page use, October 4, 2026

The first real input was a captured REST search page for
`repo:woahwhattheheck/commons is:issue is:open -label:board`, sorted by
oldest update, with 20 items per page. It advertised 80 matches and supplied
20 issue objects with 82,594 UTF-16 body code units. That first page alone did not
exhaust the query. An unbounded body print exceeded the output window.

The new public API then ran directly in connected V8 on that retained array:

| Read | Actual returned body scope |
| --- | --- |
| Contiguous overview | First 12 items, 240 code units each, 2,880 total; all 12 bodies explicitly truncated and original indices 12–19 omitted. |
| Sparse full-body selection | Indices 1, 4 and 16, corresponding to issues #14805, #14864 and #15661; all 13,490 selected body code units returned, 17 other items omitted. |

The complete input array remained unchanged. Both reads made zero provider
calls; there was no second search or old product-proof replay. The observation
covers these actual issue-body selections and their omission accounting.
PR-marker, null/missing body, surrogate-boundary and error handling are
implemented as described, without an induced provider failure, generated
fixture or synthetic check run.


## Observe an explicit update-time ceiling without interpreting the query

Successful traversal does not establish that every requested qualifier was
applied to the returned metadata. The collector always reports
`query_application: "not_verified"`. Its existing `status`,
`coverage.complete`, stop reasons, pagination and retained rows keep their
previous meanings. They do not become an eligibility decision or a verified
query result.

For a query whose intended source window has an inclusive update-time ceiling,
declare that ceiling separately:

~~~javascript
const result = await box.exports.searchGitHubIssues(tools, {
  query: exactPreparedQuery,
  updated_at_lte: "2026-10-04T23:23:40Z",
  per_page: 20,
  max_pages: 1
});
text({
  query: result.query,
  query_application: result.query_application,
  coverage: result.coverage,
  updated_at_bound: result.updated_at_bound
});
~~~

The helper does not parse, add, replace or validate the meaning of an
`updated:` query token. In particular, it does not interpret quoted text,
OR expressions, ranges, exclusion clauses or GitHub date-only syntax.
The bound is explicitly `caller_declared`; recording it does not prove that
it appears in, or is logically implied by, the opaque query. Keep the actual
query and original native request/response with the observation.

Omitting `updated_at_lte` omits `result.updated_at_bound`. Supplying it adds
one metadata scan when the collector finishes, including when only partial
items were retained before a provider error or page limit. It adds no provider
call, retry or filtering, and a mismatch does not change `FOUND`,
`NOT_FOUND_IN_QUERY`, `INCONCLUSIVE` or pagination coverage.

### Inspect retained items directly

The same module exports a pure companion for an already-captured native item
array:

~~~javascript
const audit = box.exports.inspectGitHubIssueUpdatedAtBound(
  retainedNativePayload.items,
  "2026-10-04T23:23:40Z",
  {max_records: 20}
);
text(audit);
~~~

No query is replayed. The input array and its items are not changed, sorted or
deduplicated. Pass `result.items` to inspect the collector's first retained
observation of each unique ID. That does not inspect duplicate occurrences
discarded by the collector; use each original `onResponse` capture when those
occurrences are the intended source. The companion's scope is only the supplied
items, and `query_application` remains `not_verified`.

The bound and evaluable metadata use the strict UTC form
`YYYY-MM-DDTHH:mm:ssZ` or `YYYY-MM-DDTHH:mm:ss.sssZ`.
The date must round-trip to the same calendar instant; invalid dates, leap-second
strings, offsets, date-only values and other fractional precision are not
silently coerced. Equal timestamps are within the inclusive ceiling. An invalid
caller bound throws before a collector request. A missing `updated_at` field
is counted as missing; present null, non-string, unsupported or invalid date
values are counted as invalid and unevaluated. Their full original fields
remain in the input.

| Observation status | Meaning |
| --- | --- |
| `mismatch` | At least one evaluable supplied timestamp is later than the caller's ceiling. Other timestamps may remain unevaluated. |
| `no_mismatch_observed` | The nonempty supplied array has evaluable timestamps throughout, and none exceeds the ceiling. This does not verify any query qualifier. |
| `unevaluated` | No mismatch was found, but the array is empty or at least one supplied timestamp could not be evaluated. |

The report counts supplied items, evaluable dates, dates within the bound,
mismatches, missing fields and invalid dates. Metadata-only `records` retain
original zero-based source indices, native IDs and issue numbers, issue/PR kind,
and an observation of `mismatch`, `missing` or `invalid`. Only a valid
mismatching timestamp is copied; an unevaluated value is represented as null.
No issue title, body, author, URL or arbitrary invalid value is copied.

Records preserve input order. `max_records` defaults to 20 and accepts integers
from 0 through 100; all supplied items are still counted when record output is
limited. `diagnostic_records` and `omitted_diagnostic_records` expose the
difference. The collector uses the default 20-record bound. The companion accepts
at most 1,000 items and validates every row with the existing native identity
contract, including rows with omitted diagnostics. Unknown options and malformed
identity envelopes throw. `all_supplied_timestamps_evaluated` is vacuously true
for an empty array, whose status remains `unevaluated`; it does not certify a
provider-level absence.

### Observed motivation and execution boundary

An actual successful native query on October 5, 2026 included
`is:pr is:open author:woahwhattheheck archived:false updated:<=2026-10-04T23:23:40Z`.
Its retained 20-item page included RemitFlow/RemitFlow-Backend #143 with
`updated_at: 2026-10-05T00:33:02Z`. The returned metadata is outside the requested
ceiling. This observation does not determine why the search and row metadata
differed; live updates and search-index behavior remain distinct from transport
success. Do not silently drop the contradictory row or infer a new request,
permission or work gate.

[Source publication #31520](https://github.com/woahwhattheheck/commons/pull/31520)
merged at `c90586a0723d2bb08762ede8a38490bded2c8043` with module blob
`db1723a94fc513fab131ffc73bca79ce4b6d0d98`. At that publication the new
bound-observation branches had been inspected as source only.

After publication, the first actual consumer called
`inspectGitHubIssueUpdatedAtBound` exactly once on the complete retained native
20-item page, using ceiling `2026-10-04T23:23:40Z` and `max_records: 20`.
It returned `status: "mismatch"`: 20 supplied and evaluated items, 19 within the
bound, one mismatch, no missing dates and no invalid dates. The sole diagnostic
retained source index 12, native ID 5575324851, pull-request number 143 and
`updated_at: 2026-10-05T00:33:02Z`, corresponding to
[RemitFlow/RemitFlow-Backend #143](https://github.com/RemitFlow/RemitFlow-Backend/pull/143).
There was one diagnostic record and zero omitted records;
`all_supplied_timestamps_evaluated` was true. Both
`query_application: "not_verified"` and `query_syntax_parsed: false` remained
explicit.

The complete input JSON was unchanged and the audit made zero provider calls.
This was a new metadata audit of retained observations, not a repeated search
or a replay of a previous computation. No issue bodies were copied into this
guide. The collector-integrated audit, empty input, missing/invalid date,
diagnostic-limit and invalid-input branches remain source-inspected only.
No generated inputs, fixtures, tests or native process were used. The existing
collector and body projector's accepted uses remain unchanged.


## Project shortcut search headers from a retained envelope

The connected `github_search_issues` action has a different response shape from
the REST route above. Its actual retained envelope supplied
`structuredContent.issues`, with `issue_number` and a single `url` field.
State, comment counts and timestamps were present as null. It did not supply
REST item IDs, `number`, `html_url`, a `pull_request` marker, advertised totals,
an incompleteness flag, or native pagination evidence.

The native `github_fetch_issue` envelope is also supported when its
`structuredContent.issue` contains one issue object with the same field
contract. It represents one retained row. A wrapper with both own `issue` and
`issues` properties is rejected as ambiguous rather than choosing a shape.
The single-issue path does not introduce a nested-payload fallback or accept an
error payload as an issue.

Use the separate pure export
`projectGitHubConnectorIssueHeaders(response, options)` for either shape:

~~~javascript
const headers = box.exports.projectGitHubConnectorIssueHeaders(
  retainedShortcutResponse,
  {
    max_items: 20,
    max_metadata_chars: 4096,
    max_total_metadata_chars: 8000
  }
);
store("retained-shortcut-headers", headers);
text({
  source: headers.source,
  selection: headers.selection,
  coverage: headers.coverage,
  items: headers.items
});
~~~

`retainedShortcutResponse` is the complete MCP envelope already captured from
the shortcut action. Keep its exact request and native response separately.
The projector performs no tool call, chooses no transport route and does not
replay a search. A failed source read remains subject to the caller's hold;
projection refusal is not a reason to acquire the same source another way.

For an already retained single-issue response, use the same API and budgets:

~~~javascript
const singleHeaders = box.exports.projectGitHubConnectorIssueHeaders(
  retainedSingleIssueResponse,
  {source_indices: [0], max_items: 1, max_metadata_chars: 4096,
    max_total_metadata_chars: 8000}
);
store("retained-single-issue-headers", singleHeaders);
text({source: singleHeaders.source, items: singleHeaders.items});
~~~

Only the new single shape adds `source.source_shape: "single"`; its
`source.payload_path` is `"structuredContent.issue"`. Existing search-result
JSON shape remains unchanged. Display aliases, titles or URLs on the outer
wrapper are not copied into the header or certified as inner issue metadata.

The existing REST collector, REST item projector and timestamp-bound observer
keep their input contracts. Do not manufacture REST IDs or copy `issue_number`
into `number` to make a shortcut row satisfy those contracts. In particular, a
query containing `is:open` is not a source for a missing or null state.

### Literal header fields and uncertainty

Every returned header preserves the following supplied fields:

| Field | Accepted shape and projection |
| --- | --- |
| `issue_number` | Required positive safe integer; retained under its native name. |
| `title`, `url` | Required strings, copied in full within the metadata bounds. |
| `state`, `state_reason` | When present, string or null; no semantic state or kind inference. |
| `created_at`, `updated_at`, `closed_at` | When present, string or null; strings are not parsed or certified as dates. |
| `comments` | When present, nonnegative safe integer or null. Null does not become zero. |

The six optional metadata fields also have `metadata_states` entries:

- `missing` means the original row has no own property with that name. The
  corresponding native field remains absent from the header.
- `null` means the property is present and null. The header retains null.
- `value` means the present value has the accepted scalar type. It does not
  certify a date, state, comment freshness, query match or eligibility.

An invalid type causes an explicit `TypeError`; the function does not drop the
row or return a partially validated collection. All supplied rows are checked,
including rows outside the requested output window. Other original fields,
including author, assignees, labels, milestone, display aliases and arbitrary
nested objects, stay in the retained response.

Each header includes its original `source_index` and
`source_path: "structuredContent.issues[i]"` for search rows. A single-issue
header has `source_index: 0` and `source_path: "structuredContent.issue"`.
Both shapes use the exact inner native fields and the same nullable metadata,
body-withheld annotations and budgets. Search order and duplicate occurrences
are preserved. The function does not infer issue-versus-PR kind from a query or
URL, add a global item ID, sort rows, or deduplicate them.

Body text is never included. `body_state` distinguishes a supplied string, null
and missing property; `body_chars` gives the string's UTF-16 length or null.
An empty string remains a text body of length zero. `body_withheld` is true,
`returned_body_chars` is zero, and no `body` field is added to a header.
This is field selection, not a privacy classification of title or URL text;
the caller's topic and publication limits still apply.

### Local selection and metadata budgets

| Option | Default | Accepted values |
| --- | --- | --- |
| `start_index` | 0 | Safe integer from 0 through the supplied array length; exclusive with `source_indices`. |
| `source_indices` | Omitted | Increasing, distinct, in-range original indices; length at most `max_items`. |
| `max_items` | 20 | Safe integer from 0 through 100. |
| `max_metadata_chars` | 4,096 | Safe integer from 0 through 65,536, checked for every supplied row. |
| `max_total_metadata_chars` | 8,000 | Safe integer from 0 through 1,000,000, applied to selected output in order. |

The search envelope must contain at most 1,000 rows in
`structuredContent.issues`; the single envelope must contain one object in
`structuredContent.issue`. That is a local input bound, not a shortcut-provider
result ceiling. For a single issue, `source_indices` can only be `[]` or `[0]`,
and its length still cannot exceed `max_items`; contiguous `start_index` can be
0 or 1. `max_items` retains its normal 0–100 range for both shapes. Starting at
1 or selecting `[]` omits the retained single row without altering its source.
`isError: true` is refused before projection. A non-boolean `isError` value,
malformed envelope, malformed or error single payload, invalid row, unknown
option or incompatible selector is also refused. An omitted `isError` is
allowed by the MCP envelope contract.
Ordinary status text such as “Action completed.” is not parsed or treated as
issue metadata. The function has no nested-payload fallback.

Metadata character counts sum the selected native scalar values' string lengths,
with null contributing zero. They use UTF-16 code units and exclude field
names, JSON syntax, body text and the fixed projection annotations. They are
not serialized-output byte or token measurements. Body sizes are obtained from
string lengths; the function does not serialize the envelope or parse bodies.

A per-row metadata overflow throws `RangeError` before output. Metadata and URLs
are never silently truncated. If a requested row would exceed the total output
metadata budget, projection stops before that row and does not skip ahead.
`metadata_budget_blocked_index` identifies it;
`omitted_requested_source_indices` preserves the unreturned requested suffix.

For contiguous selection, `next_index` is the next local collection index. If the
budget cannot fit even the first requested header, that index stays unchanged;
repeating the same projection cannot advance. Increase a local budget or make
a deliberate different selection. For sparse selection, `next_index` is null
and the explicit omitted requested indices guide any later local choice.
Neither value is a native pagination cursor.

Coverage reports supplied, requested, returned and omitted item counts, omitted
half-open source-index ranges, body-state counts, supplied body lengths, returned
metadata characters and metadata-budget exhaustion. The `all_*` flags concern
this supplied collection and requested headers only. Empty search input can satisfy a local
selection flag without establishing that the provider has no results.

`source.query_application` and `source.kind_application` remain `not_verified`.
`source.pagination_evidence` is `not_available_in_supported_envelope`.
A full local projection, one retained issue, twenty rows, a short array or an empty array establishes
no advertised total, native END, current source state or global absence. The
shape label records the supplied structure; it does not authenticate where an
envelope originated. Read a selected canonical record when current metadata is
needed and its source route is available.

### Actual retained shortcut use, October 5, 2026

The first consumer used one already captured successful shortcut response for
`repo:woahwhattheheck/commons is:issue is:open`, with `sort: "updated"`,
`order: "desc"` and `topn: 20`. Its twenty bodies contained 54,972 UTF-16 code
units. Every supplied state, state reason, comment count and creation/update/close
timestamp was null. The response supplied no provider pagination or total.

The new export ran once on that exact envelope with its default options:

| Observation | Actual result |
| --- | --- |
| Supplied / requested / returned headers | 20 / 20 / 20 |
| Original source indices | 0 through 19, unchanged order |
| Returned metadata scalar characters | 2,055 |
| Supplied text body characters | 54,972 |
| Returned body characters | 0; no header had a `body` key |
| Null metadata | 20 null values retained in each of the six optional fields |
| Local omissions / metadata-budget exhaustion | 0 / false |
| Native calls made by projection | 0 |

The complete input JSON was unchanged. All native issue numbers were retained
under `issue_number`; no state, kind, date-bound compliance or provider-end
claim was inferred. The caller kept mirrored Slack records and held topics out
of further body expansion; the header view did not recover failed Slack reads.
This was a new use of the projector on retained source, with no repeated search.

Only the successful default contiguous path and actual null metadata were
executed. Sparse selection, budget boundaries, zero-item cases, missing fields,
other scalar metadata, null/missing bodies and refusal paths remain inspected
as source only. No synthetic response, fixture, test, native process or accepted
REST operation was replayed. The older REST function bodies are byte-for-byte
preserved; the module adds this function and its export.

