# Retained GitHub REST comment views

[connected_github_comments.cjs](connected_github_comments.cjs) exports the pure
`projectGitHubRestComments(response, options)` function. It projects a retained
native `github_fetch` response whose `structuredContent.content` is a JSON
comment array, or a successful GitHub Token Connection response whose
`structuredContent.data` is the comment array. It makes no tool calls and owns no fetch, pagination, mutation,
filesystem, credentials, archive decoding or access decision.

The motivating intake selected recent complete issue comments and exposed a
10,857-character historical encoded-source archive to context. That archive
remains held and is not decoded, recovered or republished here. Safe retained
metadata establishes eleven comment rows with string bodies; those bodies
were not transferred to the author of this helper. Existing issue projections
require issue numbers, titles and states, or the shortcut's
`structuredContent.issues` shape. This module does not fabricate those fields
or change either existing issue API.

## Start with bodies withheld

Bank the exact native arguments and raw response before parsing or projecting.
Keep their operation-specific custody locators on the private receipt. Pass
the retained response to the helper; do not print the native envelope first.

```javascript
const headers = comments.projectGitHubRestComments(retainedResponse, {
  max_comments: 100,
  max_header_chars: 4096,
  max_total_header_chars: 32768,
});
store(headerReceiptKey, headers);
text(headers);
```

This example uses the actual caller's already-loaded module, retained response
and receipt key. It does not make a new request. The default body mode is
`withheld`; no body property is emitted. Header views preserve each source
index and the exact array path (`JSON.parse(structuredContent.content)[index]`
for native JSON text or `structuredContent.data[index]` for token data), observed comment
ID, API/browser/issue URLs, `user.login`, creation/update strings, and body
state/character count. Unlisted native fields, including reactions, application
metadata and user profile fields, are omitted.

These are observed fields, not authenticated identities or validated URLs,
dates, authorship, ownership or permissions. Exact request/repository/issue
binding remains with the caller's original native journal and is not inferred
from the array. Null or absent fields do not establish author absence. Array
length, short arrays and empty arrays never establish native END or complete
issue history. The helper does not sort, deduplicate or merge pages.

## Explicit bounded body selection

First apply the existing privacy, source and route holds to the selected
headers. An output option does not grant source or disclosure permission.
For an actual unheld comment needed by the current task, use explicit indices
from this same retained payload and opt in to body output:

```javascript
const selected = comments.projectGitHubRestComments(retainedResponse, {
  source_indices: selectedUnheldSourceIndices,
  include_bodies: true,
  max_comments: 20,
  max_body_chars: 800,
  max_total_body_chars: 2400,
});
store(selectionReceiptKey, selected);
text(selected);
```

`include_bodies: true` requires explicit `source_indices`; it cannot enable
bodies for an implicit contiguous selection. Indices must be increasing,
distinct, within the supplied array and within `max_comments`. They identify
source positions, not comment IDs or server pagination. An earlier comment
edit or another native page is a different retained input; do not silently
apply old indices to it.

Body output is a literal bounded prefix. There is no Base64/archive decoding,
decompression, Markdown execution, source reconstruction or content
classification. For each string body the result records its original
`body_chars`, returned count, exclusive `body_range: [0, end]` and
`body_truncated`. A truncation boundary does not split a UTF-16 surrogate pair.
Missing, null or invalid bodies emit no body text and retain their own states.

## Supported envelope and value states

The function accepts an MCP envelope object with one of these representations:

| Envelope | Required payload | Source path |
| --- | --- | --- |
| Native `github_fetch` | `structuredContent.content` is JSON text containing an array. | `JSON.parse(structuredContent.content)[index]` |
| GitHub Token Connection | `structuredContent.ok === true`, integer HTTP `status` in 200–299, and `structuredContent.data` is an array. | `structuredContent.data[index]` |

Both arrays are bounded to 1,000 rows. Native JSON text retains precedence if
both representations are supplied. The function refuses native `isError: true`,
invalid error-flag types, token responses without successful status, unsupported
envelopes, malformed JSON and non-array payloads. Failure messages are fixed and
body-free; parsing and serialization error details are not forwarded. The
original response remains the caller's evidence. There is no alternate parser
for top-level text, REST search objects or connector shortcut comments.

Token status describes the supplied envelope; this pure function performs no
authentication and does not certify the original request, account, permissions,
pagination or array completeness. It adds no tool binding or provider request.

A non-object row remains a header with `row_state: "invalid"`; its body and
user fields are `unassessed`. Object-row metadata preserves these states:

| State | Meaning |
| --- | --- |
| `missing` | The field was absent. |
| `null` | The field was explicitly null; metadata retains null. |
| `value` | Its type fits this projection; the original value is retained. |
| `invalid` | Its non-null type/ID form is unsupported; the value is omitted. |
| `omitted_oversize` | A string exceeded the per-header field bound; its value is omitted and original character count retained. |
| `unassessed` | The containing row/user did not permit that field to be examined. |

An ID is a positive safe integer or a positive decimal string, preserved in
its original representation. URL and date fields need string types only;
their syntax and meaning are not certified. `user_state` distinguishes
missing, null, object and invalid users. For an object user,
`metadata_states.author_login` independently describes the login field.
Only that login is projected, never the rest of the user object.

`body_state` distinguishes text, null, missing, invalid and unassessed.
`body_chars` is a number only for text, including zero for an empty string;
it is null otherwise. Invalid metadata or bodies do not become empty valid
values. Row and body-state counts cover all supplied rows, including those
whose headers are not selected.

## Bounds and omission accounting

All character counts and ranges are **UTF-16 code units**, matching JavaScript
string indexing. They are not UTF-8 byte counts, displayed glyph counts or
wire sizes. For native input, the input limit measures only the JSON payload string before
parsing. For token input, it measures `JSON.stringify(structuredContent.data)`
so equivalent array data has a comparable serialized-content bound. Neither
measurement includes other envelope fields or certifies original wire size.

| Option | Default | Maximum |
| --- | ---: | ---: |
| `max_comments` | 20 | 100 |
| `max_body_chars` | 800 | 65,536 |
| `max_total_body_chars` | 6,400 | 262,144 |
| `max_header_chars` | 4,096 | 65,536 |
| `max_total_header_chars` | 16,384 | 1,048,576 |
| `max_input_chars` | 1,048,576 | 8,388,608 |

Each numeric option is a nonnegative safe integer within its bound. Unknown
options are refused without echoing their names or values. `start_index`
defaults to zero for contiguous header selection and cannot be combined with
`source_indices`. It must not exceed the supplied array length.

Header budgets charge `JSON.stringify(header).length` before adding the
`header_chars` field, body-mode fields and any body output. This includes
source paths, field-state bookkeeping and metadata JSON escaping. It excludes
the fixed result envelope, selection/coverage summaries and body output, so
it is not a promise that the entire serialized result fits the header budget.
Body prefixes have their separate per-body and total budgets.

A header that exceeds either its own or the remaining total header budget is
omitted with its source index, charged count and a fixed reason. Later
requested headers may still fit; the result records the exact returned indices
and omitted requested entries. `omitted_source_index_ranges` are exclusive
ranges over all supplied rows not returned. No metadata value is silently
shortened into an apparent full identifier.

Coverage reports supplied/requested/returned counts, invalid rows, body-state
counts, original/selected/returned text counts, withheld and truncated string
bodies, and charged header characters. `all_supplied_headers_included` means
only this array's headers. `all_selected_text_bodies_included` can be true only
in explicit body mode and describes the returned selection's string bodies,
not invalid/missing data or omitted headers. No coverage field certifies an
upstream query, issue chronology, snapshot, native end, authentication,
ownership or source permission. No next native request is computed.

## Source and first-use status

This is an additive, source-inspected module and guide. The existing
`connected_github_issue_search.cjs` APIs and all collectors/publishers are
unchanged. No fixture, test suite, executor, browser, native request, archive
decode or historical computation is invoked by the projector.

The original native projector was published before its custodian's first use.
The token-envelope extension was executed against retained real native and token
reads of Commons issue #20318. Both responses supplied the same one comment ID;
header-only views retained its metadata, withheld its body, and recorded the
correct representation-specific source path. Native output matched the original
projector byte for byte. Empty token input from PR #32227 also projected zero
rows. No body output, historical archive decoding, malformed-input simulation,
fixture or test suite was used. Error and budget paths remain unexecuted until
a genuine operation exercises them; there is no acceptance or permission gate.
