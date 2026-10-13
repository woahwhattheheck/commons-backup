# Project retained native commit-search headers

`host/connected_github_commit_search.cjs` exports the pure function
`projectGitHubCommitSearchHeaders(response, options?)`. Pass the original native
`github_search_commits` MCP response already retained privately, alongside its
exact request. The helper makes no provider call and does not mutate, sort or
deduplicate the retained commits.

Only `response.structuredContent.commits[]` is supported. Each row must contain
a lowercase 40-character Git `sha` and a string `message`. Single-commit
envelopes, REST search payloads, token wrappers and JSON text-block fallbacks are
outside this API. A structured payload with both `commits` and an own `commit`
property is refused.

## Use an already retained search response

Load the helper from the repository root in Node. Choose indices from the actual
retained array; this example requires at least three supplied rows:

```js
const {projectGitHubCommitSearchHeaders} =
  require("./host/connected_github_commit_search.cjs");
const view = projectGitHubCommitSearchHeaders(retainedNativeCommitSearchResponse, {
  source_indices: [0, 2],
  max_commits: 2,
  max_message_chars: 0,
  max_total_message_chars: 0,
  max_metadata_chars: 512
});
```

Keep the complete raw response private. The view contains bounded selected
metadata and explicit omissions; it cannot recover rows missing from that native
response. The existing single-commit helper retains its separate input contract.

## Options and local limits

All numeric options require safe integers within these bounds:

| Option | Default | Accepted range and meaning |
| --- | ---: | --- |
| `start_index` | 0 | 0–largest safe integer; must not exceed the retained row count. Starts a contiguous window. |
| `source_indices` | Omitted | Distinct increasing nonnegative indices inside the retained array; length must fit `max_commits`. Mutually exclusive with an explicitly supplied `start_index`. |
| `max_commits` | 10 | 0–100 selected rows. |
| `max_message_chars` | 0 | 0–100,000 returned message code units per selected row. |
| `max_total_message_chars` | 4,096 | 0–1,000,000 returned message code units shared across selected rows. |
| `max_metadata_chars` | 4,096 | 0–1,000,000 shared metadata string code units, including every selected full SHA. |
| `max_header_chars` | 4,096 | 40–16,384 maximum length of each supplied optional header string or actor login; also bounds digit-string actor IDs. |
| `max_input_commits` | 10,000 | 1–100,000 maximum supplied rows. |
| `expected_repository_full_name` | Omitted | Optional `owner/name` string asserted against the exact `repository_full_name` of every supplied row. |

An omitted or explicit `undefined` expected repository disables that assertion.
When supplied as a string, comparison is exact and case-sensitive; missing,
null or different row values produce an identity refusal. It checks retained
metadata, not authentication, ownership, query application or current access.

Sparse selection preserves original indices and order, with no automatic next
index. `[]` selects no rows. Contiguous selection uses `start_index` and
`max_commits`, returning a local `coverage.next_index` when rows remain. With a
zero item budget that index may stay unchanged. The half-open
`omitted_source_index_ranges` refer to the original retained array; no selector
fetches another provider page.

Every supplied row is validated before selection, including omitted rows.
`max_header_chars` and `max_input_commits` constrain accepted input; they do not
bound total serialized input, message allocation or output bytes.

## Exact metadata and visible omissions

The result uses `source.representation: "native_commit_search"` and
`source.source_path: ["structuredContent", "commits"]`. Each selected row keeps
its original `source_index`, array-form `source_path` and complete SHA. Its
`metadata_source_paths` locates each included metadata field in the original
response, for example
`["structuredContent", "commits", 2, "author", "login"]`.

Optional `repository_full_name`, `url`, `html_url`, `display_url` and `created_at`
must be strings or null when present. Null stays null; absent fields stay absent.
Strings are copied exactly when they fit the shared metadata budget, with no
normalization, clipping or date/URL certification.

Optional `author` and `committer` remain null when supplied as null. Otherwise
they must be objects; only their supplied `login` and `id` fields are eligible
for copying. Login is a string or null. ID is null, a nonnegative safe integer,
or a bounded digits-only string. Those original types are preserved. Returned
actor objects include their source location and `email_fields_withheld: true`;
other actor properties are not copied.

The metadata budget first reserves 40 code units for every selected full SHA.
If those identities alone cannot fit, the entire projection returns
`INPUT_LIMIT / SELECTED_SHA_METADATA_BUDGET`. Remaining string fields consume
one global budget in selected-row order: header fields, then author and committer
login/ID fields. Nulls and numeric IDs consume zero string code units. A string
that cannot fit is omitted in full; later fields can still fit. Every such
omission appears in `coverage.metadata_omitted_fields` with its exact source
path, character count and `reason: "METADATA_CHAR_BUDGET"`. An omitted field is
not reported as absent from the retained source.

Each selected row also has `withheld_fields` descriptors for `diff`, `files`,
`comments` and `git_author_email`. These record `present`, exact `source_path`,
`value_type` and `withheld: true`, plus `retained_count` for arrays or
`retained_chars` for strings. The original values are not returned, traversed
into file content, parsed as diffs or substituted for missing metadata.

## Commit-message prefixes and coverage

Messages default to zero returned characters. Explicit message budgets return
literal prefixes in selected-row order. `message_source_path`, `message_chars`,
`returned_message_chars`, half-open `returned_message_range` and
`message_truncated` describe each retained string and its returned prefix. A
boundary moves back one code unit when needed to preserve a surrogate pair.
There is no whitespace, line-ending, Markdown or entity normalization.

All character counts and ranges use JavaScript UTF-16 code units. The metadata
budget excludes message text, field names, JSON syntax, numeric IDs and fixed
projection annotations. It is independent of per-message and total-message
budgets and is not a serialized byte or token ceiling.

Coverage reports retained, returned and omitted row counts, selection mode and
indices, omitted ranges, local next index, returned metadata/message characters
and optional-field omissions. `all_retained_commit_headers_included` means all
retained rows were selected; optional metadata may still be omitted.
`all_selected_metadata_included` separately reports whether any budgeted
metadata field was omitted. Message truncation remains per row.

Scope is always `retained_response_only`, `snapshot: false`, with provider
completeness and pagination `not_inferred`. A complete local selection or an
empty array cannot establish native END, an advertised total, full repository
history or the application of the original search query.

## Refusals and caller errors

Returned refusals have no projected commits and an explicit `status` and
`issue.code`:

| Status | Codes and source conditions |
| --- | --- |
| `UNSUPPORTED_REPRESENTATION` | `EXPECTED_CALL_TOOL_RESULT` for non-object input; `EXPECTED_NATIVE_COMMIT_SEARCH` for an unsupported structured shape; `INVALID_COMMIT_FIELDS`, `INVALID_HEADER_FIELD`, `INVALID_ACTOR_FIELD`, `INVALID_ACTOR_LOGIN` or `INVALID_ACTOR_ID` for malformed rows. |
| `PROVIDER_ERROR` | `PROVIDER_ERROR_ENVELOPE` for root `isError: true`; `PROVIDER_ERROR_PAYLOAD` for structured `isError: true`, `ok: false`, any own `error` property, or integer `status >= 400`. |
| `INPUT_LIMIT` | `COMMITS_LIMIT`, `HEADER_CHAR_LIMIT` or `SELECTED_SHA_METADATA_BUDGET`; issue metadata identifies the observed and allowed bound where applicable. |
| `IDENTITY_MISMATCH` | `REPOSITORY_MISMATCH` for the optional exact repository assertion. |

Invalid options throw locally. `TypeError` covers non-object options, unknown
option names, incompatible selectors, a non-array `source_indices`, or malformed
expected repository. `RangeError` covers invalid numeric bounds, too many
selected indices for `max_commits`, invalid/duplicate/descending indices,
out-of-range source indices, or a contiguous start beyond the retained row
count. No invalid index is sorted, deduplicated, capped or silently dropped.

The helper neither retries a read nor turns an unsupported or failed response
into an empty successful search. Keep the original response beside any refusal
for the caller's next deliberate action.
