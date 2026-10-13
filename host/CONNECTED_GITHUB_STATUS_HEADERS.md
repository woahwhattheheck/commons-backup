# Retained commit-status headers

`host/connected_github_status_headers.cjs` projects a supplied successful native combined-status response or GitHub Token Connection status envelope. It is a pure reader: no fetch, polling, workflow execution, transport, filesystem, clock or CI verdict. Keep the original request and complete raw response separately.

```javascript
const {projectGitHubStatusHeaders} = require('./host/connected_github_status_headers.cjs');
const view = projectGitHubStatusHeaders(retainedResponse, {
  max_statuses: 20,
  max_field_chars: 256,
  max_total_metadata_chars: 4000,
});
```

Supported native data lives in `structuredContent.statuses`. Optional aggregate fields live beside it. A token envelope must report `ok: true`, an integer HTTP status from 200 through 299, and object `data`; the supported array then lives in `structuredContent.data.statuses`. Error envelopes, sparse/nonobject rows and unsupported shapes are refused. Expected binding names are documentary and do not authenticate the response's origin.

The reader exposes aggregate `state`, `sha` and `total_count` independently. A missing aggregate field stays `missing`, rather than borrowing a row count or another field. A literal zero remains a literal reported count. A returned SHA must be 40 lowercase hexadecimal characters; its format does not verify the original request's commit or repository. Aggregate state remains uninterpreted provider text. No aggregate value is synthesized from the supplied array.

Selected rows expose `id`, `state`, `context`, `description`, `created_at` and `updated_at`, with their exact zero-based source index and literal field paths. URLs, creator identity, repository objects and other fields are not selected. Text fields return complete values or `limit_exceeded`, including descriptions. Nulls, missing fields and invalid types stay distinct. IDs and aggregate counts must be nonnegative safe integers; invalid values do not become zero. Timestamps remain literal text, without date conversion or a snapshot claim.

| Option | Default | Range |
| --- | --- | --- |
| `indices` | First supplied rows within `max_statuses` | Dense unique indices within the actual array and below 10,000 |
| `max_statuses` | 20 | 0–500 |
| `max_field_chars` | 256 | 0–4,096 UTF-16 code units per complete text value |
| `max_total_metadata_chars` | 4,000 | 0–64,000 UTF-16 code units across aggregate and row text |
| `max_response_chars` | 1,048,576 | 256–8,388,608 serialized JSON code units |

At most 10,000 supplied rows are accepted, and the full array is validated before selection. Explicit indices must fit `max_statuses`. Invalid options throw before projection; unsupported/error payloads and out-of-range source indices return `REFUSED` with no projected aggregate or rows. Nonempty arrays with an empty selection are `HEADERS_ONLY`. Empty arrays are `EMPTY_SUPPLIED_STATUS_ARRAY`, even if a separate literal aggregate state is present. That status does not mean CI passed, failed or ran.

Coverage counts only the supplied array and selected text. It does not compare a reported total against supplied rows, establish pagination or collection completeness, inspect other check families, or certify workflow results. Empty native arrays must not be interpreted as a successful build. Missing aggregate state is unknown; a returned aggregate state is retained evidence rather than a synthesized verdict.

Initial activation consumed two retained actual responses: a compact native response containing only an empty `statuses` array, and a successful token status response reporting `pending`, `total_count: 0` and commit SHA `9b3a65892f3964406fc71ea205de2cd5b4b010b2`. The native aggregate state/SHA/count remained missing. The token aggregate fields retained exact values and paths, using 47 metadata code units. Both arrays remained empty and neither produced a CI verdict. The native request context came from the prior worker's accepted read receipt; it is not authenticated by the compact response itself. Complete supplied inputs/options remained unchanged under JSON serialization. No provider read was repeated for this local activation. Positive status-row execution is not established by this receipt.
