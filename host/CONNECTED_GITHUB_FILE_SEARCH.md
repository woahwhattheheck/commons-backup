# Find literal text in retained GitHub files

`connected_github_file_search.cjs` exports `findRetainedGitHubText(files, options)`
and `RetainedGitHubFileSearchError`. It scans explicitly supplied retained native
UTF-8 file responses, returns exact source positions and bounded optional
excerpts, and makes no provider call.

The actual source intake queried indexed code search for `BANK_AVAILABLE`.
Native search returned an empty `results` list; the REST code-search envelope
returned zero items with `incomplete_results: false`. A fresh full-file request
for `host/payment_capability.py` nevertheless retained that literal once.
Those empty indexed results did not establish source absence. This separate
local finder lets the consumer search known source it already retained,
without changing the provider connector or manufacturing repository-wide coverage.

## Use the retained full-file pair

Load the complete identified source through the current CommonJS/source loader.
Keep the original request and complete native result beside the view:

```javascript
const files = [{
  request: actualFullFileArgs,
  response: actualRetainedFetchFileResult
}];
const options = {
  literal: actualLiteral,
  max_matches: 20,
  max_metadata_chars: 2048,
  excerpt_chars: 0,
  max_total_excerpt_chars: 0
};
const view = fileSearchModule.findRetainedGitHubText(files, options);
store(actualPrivateViewKey, view);
text({
  suppliedFiles: view.coverage.provided_files,
  retainedTextMatches: view.total_matches,
  positions: view.matches.map(row => row.match)
});
```

The function does not fetch a missing file, retry an indexed query, follow links
or infer an alternative repository. Direct native tools and the existing
publisher/source readers remain unchanged. Caller-held source and query
boundaries continue to apply; the module does not authorize reading or
printing a body. Excerpts require explicit per-match and total budgets.

## Input and exact positions

Each dense array entry is `{request, response}`. The request retains literal
`repository_full_name`, `path`, and optional string/null `ref`. Non-null
`start_line`/`end_line` or a requested non-UTF-8 encoding is rejected.
The native response must have a non-error `structuredContent` with string
`content`, `encoding: "utf-8"` and a literal 40-character `sha`.
Unprocessed token REST/base64 responses are outside this native shape; use
their existing explicit decoding route first.

The complete array, source shape and cumulative source-text bound are validated
before scanning. Literal matching is case-sensitive and overlapping. There
is no regex syntax, tokenization, Unicode normalization, case folding or
newline conversion. A multiline literal works as supplied.

Matches retain original file index and content source path:
`["files", index, "response", "structuredContent", "content"]`.
Offsets are zero-based UTF-16 code units, with an exclusive end.
Lines/columns are one-based UTF-16 positions, treating LF as the line separator;
the end column is exclusive. CR remains literal source text. A match ending
with LF ends at column 1 of the next line.

Repository/path/ref fields come from their actual retained request paths;
SHA/display URL fields come from actual response paths. Ref absence, null,
unsupported optional metadata types and whole-field budget omissions remain
distinct. Field strings are preserved literally or omitted as a whole.

The native SHA is an observed header. This helper does not independently compute
Git blob identity or certify that a provider retained every underlying byte.
Even a full-file request's match count describes only its actual returned text.
The original pair remains the source for any further provider or identity
reconciliation.

## Bounds and coverage

| Option | Default | Bound |
| --- | --- | --- |
| `literal` | required | String of 1–4096 UTF-16 code units. |
| `max_files` | 64 | Integer 1–1024. |
| `max_source_chars` | 16777216 | Integer 1–67108864 across all retained content. |
| `max_matches` | 100 | Integer 0–10000 returned matches. |
| `max_metadata_chars` | 8192 | Integer 0–1048576 returned metadata string units. |
| `excerpt_chars` | 0 | Integer 0–8192 source units per returned match. |
| `max_total_excerpt_chars` | 0 | Integer 0–1048576 across all returned excerpts. |

All text budgets count UTF-16 code units. They are not wire bytes, elapsed-time
limits or peak-memory claims. Metadata source paths and fixed schema text are
outside the returned metadata-string counter.

The function scans every supplied retained text even when the match-output
bound is reached. `total_matches` is exact for those texts; `returned_matches`
and `omitted_matches` report the bounded leading view. An empty array or no
matches is only that supplied-input result, never repository-wide absence.

Excerpts begin at the literal match's source offset and retain an exact prefix
within both budgets. A short excerpt may not include the complete literal;
`contains_full_match` records this. Default excerpts are empty, and no literal
query text is echoed into the returned view. Metadata/query inputs may still
be private. Keep originals and projections private when their source requires it.

Errors throw `RetainedGitHubFileSearchError` with code, message and source index
when available; `toJSON()` keeps those diagnostics through ordinary JSON
serialization. No partial search result or implicit provider action follows.

## Actual consumer

The unchanged real payment-capability native request/response is the input.
The finder consumes that retained pair once with literal `BANK_AVAILABLE`,
zero excerpt budgets and bounded metadata. It returns the exact observed
source SHA, one match at UTF-16 offsets [31050,31064), line 681, column 9,
172 returned metadata units, no source excerpt and no provider call. Original
request/response/options stay unchanged.
The indexed search responses remain retained separately as an inconclusive
source-absence road; no monetary or current-settlement conclusion is made.
