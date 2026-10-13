# Retained GitHub issue labels

`host/connected_github_issue_labels.cjs` exports
`projectGitHubIssueLabelHeaders(record, options)`, a synchronous, IO-free view of
one supplied record's `labels` field. It does not fetch issues, modify labels,
filter issues, or read issue bodies. Existing issue readers stay unchanged.

Pass the inner issue record after checking its provider response. For a retained
native `fetch` JSON-text response:

```js
const {projectGitHubIssueLabelHeaders} = require("./connected_github_issue_labels.cjs");
if (response.isError === true) throw new Error("Issue read failed");
const record = JSON.parse(response.structuredContent.content);
const view = projectGitHubIssueLabelHeaders(record, {
  max_labels: 2, max_total_metadata_chars: 128
});
```

The function does not certify that the record belongs to an issue, repository,
query, or current snapshot. Paths such as `["labels", 0]` begin at the supplied
record, rather than at the original MCP envelope. The caller retains that
envelope and its outer path separately.

`labels` missing or null produces `UNAVAILABLE`, `retained_labels: null`, no
returned labels, and `selection_evaluated: false`. An unavailable value never
becomes a known empty list. A valid observed empty array produces `PROJECTED`
with a retained count of zero; this describes that field in that record only.

For arrays, every retained row must have a nonempty string `name`. Optional `id`
admits a positive safe integer, a positive decimal string, or null. Optional
`color` admits a six-digit hex string or null; `default` admits a boolean or
null; `archived_at` admits a string or null without interpreting its date.
Missing optional fields remain absent, with explicit `metadata_states`.
Names and copied metadata remain whole and preserve their observed values.
Description text is withheld: only its missing/null/value state, relative path,
and UTF-16 length for a string are returned. URLs, node IDs, actors, issue
identity, bodies, and all other fields are withheld. No label eligibility,
ownership, permission, or workflow decision is inferred.

| Option | Default | Bound or meaning |
| --- | --- | --- |
| `start_index` | 0 | Nonnegative safe integer, at most the retained count |
| `max_labels` | 20 | Integer 0–100 |
| `source_indices` | absent | Distinct increasing indices; mutually exclusive with explicit `start_index` |
| `max_field_chars` | 4096 | Integer 1–16384, checked on name and supported string metadata |
| `max_total_metadata_chars` | 4096 | Integer 0–1000000, counts copied name/id/color/archived-at string values |
| `max_input_labels` | 1000 | Integer 1–100000, bounds the retained array |

All retained rows are validated before selection. Required selected names are
reserved together; insufficient budget returns `INPUT_LIMIT` with no labels.
Optional string fields that do not fit are omitted whole and listed with their
paths and lengths. Numbers, booleans, and null values cost zero string units.
Description text does not use the copied metadata budget because it is never
returned. `metadata_states` still describes a field when its value is omitted.

Coverage reports selected source indices, half-open omitted ranges, local
counts, metadata omissions, and a contiguous `next_index` when available.
Sparse selections have no next index. These fields describe only the retained
array and local selection. The input is not mutated.

Malformed record/label fields produce `UNSUPPORTED_REPRESENTATION`; explicit
error records produce `PROVIDER_ERROR`; input limits produce `INPUT_LIMIT`.
Invalid options and out-of-range indices for a valid array throw. Missing/null
labels do not evaluate index selection. Every refused view returns no labels;
provider success and record identity remain unverified in every outcome.
