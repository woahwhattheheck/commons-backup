# Inspect retained JSON web-search results

[connected_web_json_results.cjs](connected_web_json_results.cjs) projects the
JSON search-result representation returned by the observed TinyFish Search
tool. It uses the complete retained CallToolResult and makes no provider,
network or filesystem call. The existing
[rendered web projector](CONNECTED_WEB_PROJECTION.md) remains available for
citation-header source blocks.

```javascript
const {projectWebJsonResults} =
  require('./host/connected_web_json_results.cjs');
const overview = projectWebJsonResults(retainedResponse, {
  source_indices: [0, 4, 9],
  max_results: 3,
  max_snippet_chars: 160,
  max_total_snippet_chars: 360
});
```

The dependency-free CommonJS module can also be loaded from its complete
identified source through the existing in-memory module loader. The caller
retains the original response. Input and options are not mutated.

## Representation and identity

The selected `response.content[content_index].text` must be one complete JSON
object containing a `results` array. Every row must contain literal string
`title` and `url` fields. Optional `site_name` and `date` fields are strings
or null; `position` is a nonnegative safe integer or null; `snippet` is a
string or null. Missing optional fields remain missing. Date and URL text
is not normalized, validated as authority or interpreted as page content.
An empty title or URL remains the literal reported empty string.

The optional document `query` must be a string. The overview reports its
decoded path and character count, rather than repeating the query.
Optional `total_results` and `page` must be nonnegative safe integers.
They are returned as reported counts, without asserting that other pages
were retrieved or that the provider's search corpus is complete.

Every projected row includes its original `source_index`,
`text_source_path` and decoded `parsed_source_path` such as
`["results", 4]`. `metadata_source_paths` identifies the exact decoded
location of each returned metadata field. Snippet paths likewise identify
the original decoded field. These are paths into the parsed original JSON
text document, not byte offsets into a remote page or character offsets into
the escaped JSON text.

The projector supplies no citation reference, word limit, ranking
interpretation, canonical URL, fetched page body or signed provider identity.
The supported structure identifies a representation; it does not prove which
provider produced arbitrary caller-supplied data.

## Bounds and selection

| Option | Default | Allowed range or meaning |
| --- | --- | --- |
| `content_index` | 0 | 0–4095; choose the original text item explicitly. |
| `start_index` | 0 | Contiguous starting row; cannot accompany `source_indices`. |
| `source_indices` | absent | Distinct increasing nonnegative row indices; `max_results` must accommodate them. |
| `max_results` | 8 | 0–100 retained rows. |
| `max_snippet_chars` | 800 | 0–100,000 decoded UTF-16 code units per selected snippet. |
| `max_total_snippet_chars` | 6,400 | 0–1,000,000 decoded UTF-16 code units across selected snippets. |
| `max_input_chars` | 1,048,576 | 1–8,388,608 code units in the selected original JSON text. |
| `max_header_chars` | 4,096 | 128–16,384 code units per title, URL, site name or date field. |

The content array is limited to 4,096 items. All rows' supported field shapes
and header limits are checked before selection. Other original content items
are recorded in `ignored_content_item_indices`, rather than silently
represented as parsed search results. Unknown JSON fields remain in the
retained input and are not copied into the overview.

String snippets are literal prefixes in original row order. The total budget
is consumed sequentially. A prefix backs up one code unit if necessary to
avoid splitting a surrogate pair. `returned_snippet_range` is the half-open
range `[0, returned_chars]` in the decoded original snippet. A null snippet
remains null with no string range; an absent snippet remains absent and has
`snippet_present: false`. Zero snippet budgets preserve headers and exact
paths while withholding snippet text.

## Coverage and failure states

A supported document returns `status: "PROJECTED"`, including an observed
empty `results: []`. Coverage always says `retained_document_only`,
`snapshot: false` and `provider_completeness: "not_inferred"`. It records
retained, returned and omitted row counts, original selected indices,
half-open omitted index ranges, the next contiguous index when available,
selected and returned snippet sizes and the number of truncated snippets.
`all_retained_snippets_included` only describes this retained document.

A provider error envelope returns `PROVIDER_ERROR`. An oversized selected
text, oversized header or too many content items returns `INPUT_LIMIT`.
A missing text item, invalid JSON or unsupported document/field shape returns
`UNSUPPORTED_REPRESENTATION`, with an issue code and the relevant source
path when available. These states never mean an empty search. Invalid options
and out-of-range selections throw before returning a projection. The
projector neither fetches another page nor retries an operation.

## Actual activation

The implementation consumed the already-retained actual Search response from
the automatic free route: one JSON text document with ten result rows. It
selected original rows 0, 4 and 9 with bounded snippets and exact metadata and
snippet paths. The complete original envelope and supplied options remained
unchanged. No additional Search, wallet or account call was made.
