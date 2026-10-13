# Project retained native and token workflow-run headers

`host/connected_github_workflow_run_headers.cjs` exports the pure function
`projectGitHubWorkflowRunHeaders(response, options?)`. Pass an original supported
MCP response, retained privately with its exact request. Native input uses
`response.structuredContent.workflow_runs[]`. A successful token response uses
`response.structuredContent.data.workflow_runs[]`, with `structuredContent.ok`
exactly `true`, integer HTTP `status` from 200 through 299 and object `data`.
Plain REST objects and JSON text-block fallbacks remain outside this contract.
The helper makes no provider calls and does not change, sort or deduplicate the
response. If native `workflow_runs[]` is present, that existing shape has priority.

The native action advertises PR-triggered runs from the first page. Projection
does not verify that filtering, the requested head, page coverage or CI success.
Record the token GET path and selectors beside its original response; the token
shape does not prove which request produced it. Use the existing workflow finder
when its separate search contract is needed; this projector does not change that
helper, choose a transport or issue a follow-up request.

## Use a retained response

From the repository root in Node, select indices from the supplied run array.
This example requires at least two retained rows:

```js
const {projectGitHubWorkflowRunHeaders} =
  require("./host/connected_github_workflow_run_headers.cjs");
const view = projectGitHubWorkflowRunHeaders(retainedNativeWorkflowRunsResponse, {
  source_indices: [0, 1],
  max_runs: 2,
  max_metadata_chars: 400
});
```

The same function and options accept an original successful token response:

```js
const tokenView = projectGitHubWorkflowRunHeaders(retainedTokenWorkflowRunsResponse, {
  max_runs: 2,
  max_metadata_chars: 400
});
```

Keep the complete original response private beside the bounded view. No job,
step, log or other body content is fetched or expanded by this call.

## Options and selection

All numeric options require safe integers within these bounds:

| Option | Default | Accepted range and meaning |
| --- | ---: | --- |
| `start_index` | 0 | 0–largest safe integer; must not exceed the retained run count. Starts a contiguous window. |
| `source_indices` | Omitted | Distinct increasing nonnegative indices inside the retained array; length must fit `max_runs`. Cannot accompany an explicitly supplied `start_index`. |
| `max_runs` | 10 | 0–100 selected runs. |
| `max_metadata_chars` | 4,096 | 0–1,000,000 shared metadata code units, including every selected run ID's decimal length. |
| `max_header_chars` | 4,096 | 1–16,384 maximum supplied header-string and ID length. |
| `max_input_runs` | 10,000 | 1–100,000 maximum supplied run rows. |

Sparse selection preserves original indices and order; `[]` selects none and
has no automatic next index. Contiguous selection returns a local
`coverage.next_index` when retained rows remain. With `max_runs: 0`, that index
can stay unchanged. Half-open `omitted_source_index_ranges` identify omitted
positions in the original array. A next index is never a provider cursor or a
request to continue the native first page.

All supplied rows are validated before selection, including omitted rows.
The input-count and per-header bounds do not impose a total serialized-input,
output-byte or token ceiling.

## Source values, paths and metadata budget

The view keeps schema `commons.connected_github_workflow_run_headers/v1`.

| Supported shape | `source.representation` | `source.source_path` |
| --- | --- | --- |
| Native commit workflow runs | `native_commit_workflow_runs` | `["structuredContent", "workflow_runs"]` |
| Successful token repository workflow runs | `token_repository_workflow_runs` | `["structuredContent", "data", "workflow_runs"]` |

Each selected run retains its exact `source_index`, array-form `source_path` and
supplied `id`. Every metadata and withheld-field path starts from the selected
shape. For example, a token conclusion path is
`["structuredContent", "data", "workflow_runs", 1, "conclusion"]`. The complete
native projection remains unchanged.

| Run field | Accepted value when supplied |
| --- | --- |
| `id` | Required positive safe integer or a positive decimal digit string without leading zeroes; original numeric/string type is preserved. |
| `status`, `conclusion`, `name`, `jobs_url`, `logs_url`, `html_url`, `head_sha`, `head_branch`, `event`, `path`, `created_at`, `updated_at`, `run_started_at` | String or null, copied literally when the metadata budget allows. |
| `workflow_id` | Null, positive safe integer or positive decimal digit string without leading zeroes, within the header-length bound. |
| `run_number`, `run_attempt` | Null or nonnegative safe integer. |

Missing optional fields stay absent and supplied nulls stay null. The helper
does not normalize URLs, parse dates, validate a head SHA's meaning or coerce ID
types. `status` and `conclusion` are literal observations: `completed` with
`action_required` is retained without becoming a success verdict.

Before optional metadata is copied, the budget reserves `String(id).length`
code units for each selected full run ID, including numeric IDs. If the complete
selected identities cannot fit, the entire projection returns
`INPUT_LIMIT / SELECTED_ID_METADATA_BUDGET` with no projected runs.

Optional string metadata then shares one global budget in selected-run order,
using the string-field order shown above, followed by `workflow_id`,
`run_number` and `run_attempt`. Optional integers and nulls charge zero string
characters. A field that cannot fit is omitted in full; later fields may still
fit. Strings are never clipped. Each omission has its exact source path,
character count and `reason: "METADATA_CHAR_BUDGET"` in
`coverage.metadata_omitted_fields`. Budget omission does not mean the original
field was missing.

Counts and ranges use JavaScript UTF-16 code units. The metadata budget excludes
field names, JSON syntax, fixed annotations and withheld values. It describes
selected scalar content rather than exact serialized output size.

## Withheld fields and coverage

Each selected run carries `withheld_fields` descriptors for `pull_requests`,
`head_commit`, `repository`, `head_repository`, `actor`, `triggering_actor`,
`jobs`, `steps` and `logs`. A descriptor records `present`, original
`source_path`, `value_type` and `withheld: true`, plus `retained_count` for arrays
or `retained_chars` for strings. The original values and actor email fields are
not copied. Included jobs/logs URLs remain metadata; they cause no follow-up read.

Coverage counts retained, selected, returned and omitted runs, local selection
indices/ranges, returned metadata characters and omitted fields.
`all_retained_run_headers_included` means every supplied row was selected;
optional fields may still be omitted. `all_selected_metadata_included`
separately reports budget omissions. `retained_head_sha_fields` counts supplied
own `head_sha` fields, including null; `total_count_present` only records whether
the selected run payload has that own field, without copying or validating its
value. For token input this is `structuredContent.data`, not the outer wrapper.

Scope remains `retained_response_only`, `snapshot: false`. Provider completeness,
pagination, requested-head verification, filter application, an all-workflow
result and CI success all remain `not_inferred`. An empty array or complete
local projection establishes no native END, full run inventory or successful CI
gate. The shape label does not authenticate the envelope's origin.

## Refusals and caller errors

Returned refusals contain no projected runs and expose `status` and `issue.code`:

| Status | Codes and conditions |
| --- | --- |
| `UNSUPPORTED_REPRESENTATION` | `EXPECTED_CALL_TOOL_RESULT` for non-object input; `EXPECTED_NATIVE_WORKFLOW_RUNS` for an unsupported structured shape or `EXPECTED_TOKEN_WORKFLOW_RUNS` for recognized successful token `data` without a run array; `INVALID_RUN_ID`, `INVALID_HEADER_FIELD`, `INVALID_WORKFLOW_ID` or `INVALID_RUN_NUMBER` for invalid run fields. An overlong supplied `workflow_id` also uses `INVALID_WORKFLOW_ID`. |
| `PROVIDER_ERROR` | `PROVIDER_ERROR_ENVELOPE` for root `isError: true`; `PROVIDER_ERROR_PAYLOAD` for structured `isError: true`, `ok: false`, any own `error` property, or integer `status >= 400`; the same error flags are checked inside recognized token `data`. |
| `INPUT_LIMIT` | `RUNS_LIMIT`, `HEADER_CHAR_LIMIT` or `SELECTED_ID_METADATA_BUDGET`, with the observed and allowed bounds. |

Invalid options throw locally. `TypeError` covers non-object options, unknown
options, incompatible selectors and non-array `source_indices`. `RangeError`
covers invalid numeric bounds, too many requested indices for `max_runs`,
invalid/duplicate/descending indices, an index outside the retained runs, or a
contiguous start beyond their count. No index is silently sorted, deduplicated,
capped or dropped.

Keep the original request and raw response beside a refusal. The projector
does not retry, change transport or represent a failed/unsupported response as
an empty successful provider result. Recognized token `data` with a missing or
non-array `workflow_runs` is refused; it does not become a zero-run result.
