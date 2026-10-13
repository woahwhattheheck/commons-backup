# Project retained native Drive search metadata

`host/connected_drive_search_headers.cjs` exports the pure function
`projectDriveSearchHeaders(response, options?)`. Pass a complete native Google
Drive search MCP envelope already retained privately with its exact request.
Only `response.structuredContent.results[]` is supported; JSON text blocks,
REST payloads, token wrappers and arbitrary nested fallbacks are excluded.
The helper makes no provider calls and does not mutate, sort or deduplicate the
retained rows. A recognized shape does not authenticate its provenance.

## Metadata discovery and retained selection

For a metadata-only document discovery, combine the caller's prepared native
search arguments with these selectors:

```js
const metadataSearchSelectors = {
  item_type: "document",
  best_effort_fetch: false,
  topn: 10
};
```

Retain the original native response and request privately before projection.
From the repository root in Node, select original row positions; this example
requires at least ten supplied rows:

```js
const {projectDriveSearchHeaders} =
  require("./host/connected_drive_search_headers.cjs");
const view = projectDriveSearchHeaders(retainedNativeDriveMetadataPage, {
  source_indices: [0, 4, 9],
  max_files: 3,
  max_metadata_chars: 512
});
```

These indices select retained rows rather than file IDs or provider offsets.
No file body, download or export is requested by the projector.

## Options and local limits

All numeric options require safe integers within these bounds:

| Option | Default | Accepted range and meaning |
| --- | ---: | --- |
| `start_index` | 0 | 0–largest safe integer; must not exceed the retained row count. Starts a contiguous window. |
| `source_indices` | Omitted | Distinct increasing nonnegative indices inside the retained array; length must fit `max_files`. Cannot accompany an explicitly supplied `start_index`. |
| `max_files` | 10 | 0–100 selected rows. |
| `max_metadata_chars` | 4,096 | 0–1,000,000 shared metadata code units, including every selected full file ID. |
| `max_header_chars` | 4,096 | 1–16,384 maximum supplied ID or optional string-field length. |
| `max_input_files` | 10,000 | 1–100,000 maximum supplied rows. |

Sparse selection preserves original indices and order; `[]` selects none and
has no automatic next index. Contiguous selection returns a local
`coverage.next_index` when retained rows remain. With `max_files: 0`, that index
can stay unchanged. Half-open `omitted_source_index_ranges` describe omitted
positions in the original array. None of these indices is a provider cursor.

All supplied rows are validated before selection, including omitted rows.
Input-count and per-header bounds do not impose a total serialized-input,
output-byte or token ceiling.

## Exact fields, source paths and budget omissions

The result uses schema `commons.connected_drive_search_headers/v1`,
`source.representation: "native_drive_search"` and
`source.source_path: ["structuredContent", "results"]`. Each selected row keeps
its original `source_index`, array-form `source_path` and complete opaque string
`id`. The ID must be nonempty; it is copied without trimming, decoding or numeric
conversion. `metadata_source_paths` locates each included native field, for
example `["structuredContent", "results", 4, "mime_type"]`.

| Native field | Accepted value when supplied |
| --- | --- |
| `id` | Required nonempty string within `max_header_chars`. |
| `mime_type`, `file_or_folder`, `title`, `created_at`, `updated_at`, `viewedByMeTime`, `url`, `display_title`, `display_url` | String or null. |
| `size` | String, null or nonnegative safe integer; its original type is preserved without parsing or coercion. |
| `shared`, `can_download`, `can_list_children` | Boolean or null. |

Missing optional fields stay absent and supplied nulls stay null. Included
strings, flags and sizes are literal retained metadata, without date parsing,
URL normalization, content-readability certification or permission inference.

The shared metadata budget first reserves the full lengths of every selected
file ID. If those identities alone cannot fit, the whole projection returns
`INPUT_LIMIT / SELECTED_ID_METADATA_BUDGET` with no projected files.

Optional strings then consume the remaining global budget in selected-row
order. Within each row, field order is `mime_type`, `file_or_folder`, `title`,
`size`, `created_at`, `updated_at`, `viewedByMeTime`, `url`, `display_title`,
`display_url`, followed by `shared`, `can_download` and `can_list_children`.
Nulls, booleans and numeric sizes consume zero string characters. A string that
cannot fit is omitted in full; later fields can still fit. No field is clipped.
Every budget omission appears in `coverage.metadata_omitted_fields` with its
exact source path, character count and `reason: "METADATA_CHAR_BUDGET"`.
Omission from this view does not mean absence from the original response.

Counts and ranges use JavaScript UTF-16 code units. Metadata counts exclude field
names, JSON syntax, fixed annotations and withheld values; they are not exact
serialized byte or token measurements.

## Withheld values and opaque pagination

Each selected row has `withheld_fields` descriptors for `parent_ids`, `owners`,
`permissions`, `content`, `text`, `body`, `snippet`, `download_url` and
`export_links`. These record `present`, exact `source_path`, `value_type` and
`withheld: true`, plus `retained_count` for arrays or `retained_chars` for strings.
The original values are not copied, traversed into permissions or owners, or
used to fetch content. URLs admitted as ordinary header metadata cause no
follow-up read.

`coverage.next_page_token_present` records only whether the native payload has
an own `next_page_token` property. When present,
`pagination_token_source_path: ["structuredContent", "next_page_token"]`
identifies that original field. `pagination_token_withheld` is true; the token
value is never returned or validated by this projector. Presence alone does not
establish a usable continuation, and absence does not establish native END.

If continuation is independently needed, read the original opaque token from
the privately retained native response and forward that token unchanged through
the native API. This also applies when a supplied page has an empty `results[]`.
Do not substitute the local `next_index`, reconstruct a token, or infer that an
empty page ends the provider search.

## Coverage and strict errors

Coverage reports retained, returned and omitted file counts, local selection
indices/ranges, returned metadata characters and omitted fields.
`all_retained_file_headers_included` means every supplied row was selected;
optional metadata may still be omitted. `all_selected_metadata_included`
separately reports whether any budgeted field was omitted.

Scope remains `retained_response_only`, `snapshot: false`. Provider completeness,
pagination, query application and content readability remain `not_inferred`.
A complete local projection or an empty array establishes no advertised total,
native END, complete Drive inventory or current access to document bodies.

Returned refusals contain no projected files and expose `status` and `issue.code`:

| Status | Codes and conditions |
| --- | --- |
| `UNSUPPORTED_REPRESENTATION` | `EXPECTED_CALL_TOOL_RESULT` for non-object input; `EXPECTED_NATIVE_DRIVE_RESULTS` for an unsupported structured shape; `INVALID_FILE_ID`, `INVALID_HEADER_FIELD` or `INVALID_FLAG_FIELD` for invalid rows. |
| `PROVIDER_ERROR` | `PROVIDER_ERROR_ENVELOPE` for root `isError: true`; `PROVIDER_ERROR_PAYLOAD` for structured `isError: true`, `ok: false`, any own `error` property, or integer `status >= 400`. |
| `INPUT_LIMIT` | `FILES_LIMIT`, `HEADER_CHAR_LIMIT` or `SELECTED_ID_METADATA_BUDGET`, with observed and allowed bounds. |

Invalid options throw locally. `TypeError` covers non-object options, unknown
option names, incompatible selectors and non-array `source_indices`.
`RangeError` covers invalid numeric bounds, too many selected indices for
`max_files`, invalid/duplicate/descending indices, an index outside the retained
rows, or a contiguous start beyond their count. No index is silently sorted,
deduplicated, capped or dropped.

Keep the original request and raw response beside any refusal. The projector
does not retry, switch transport or turn failed/unsupported data into an empty
successful provider result.
