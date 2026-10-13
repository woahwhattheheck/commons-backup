# Project retained web source responses

Use [connected_web_projection.cjs](connected_web_projection.cjs) to inspect web-tool source responses without printing every returned page in full. The synchronous public API retains each detected source reference, title, URL and word limit, and puts explicit bounds on the returned content. It makes no provider calls and does not mutate the supplied response.

The caller retains the complete original response. Every range points back into one original text content item; selected previews are never treated as complete pages or complete search results.

## Public API

The module has no dependencies and works as CommonJS or through the existing in-memory module loader.

~~~js
const { projectWebSources } = require("./host/connected_web_projection.cjs");

const overview = projectWebSources(retainedResponse, {
  max_sources: 8,
  max_content_chars: 400,
  max_total_content_chars: 3200
});
~~~

Pass the actual web-tool CallToolResult with its content array. The supported source header rendering has a title field, which may be empty, and an HTTP(S) URL on one line, followed by a returned search/view/fetch/news/academia reference and a numeric word-limit marker. The space before the parenthesized URL is still required. An empty title is returned as the literal empty string; the adapter does not derive a title from the URL, filename or page content. A renderer-shaped boundary uses a reference made of `turn`, decimal digits, a lowercase ASCII family name, and decimal digits. A family outside the supported list, or a supported-family header with an empty or unsupported URL, separates an unparsed block; it is not added as a supported source. The adapter reads that rendering; it does not synthesize source IDs from URLs or interpret arbitrary prose as an empty result set.

A successful response has status PROJECTED and a sources array. Each source includes:

| Field | Meaning |
| --- | --- |
| source_index | Position across all parsed source blocks, in original content-item order |
| content_index | Index of the original text item in the supplied content array |
| reference_id, title, url, word_limit | Fields read directly from the supported rendered header |
| rendered_source_range | Entire supported source block, from its title to the next detected rendered header boundary or text-item end |
| rendered_header_range | Title, URL, reference and word-limit prefix |
| rendered_content_range | Remaining source content, including returned crawl/publication metadata and page text |
| rendered_content | Bounded literal prefix of that content |
| returned_content_range | Exact range of the returned prefix |
| content_chars, returned_chars, truncated | Full content length, returned length and explicit truncation state |

All ranges are half-open UTF-16 code-unit offsets in response.content[content_index].text. They are **rendered response ranges**, not byte offsets in the original web page. CRLFs, entities, citations, line labels and separators are retained. The adapter does not decode HTML entities, remove link wrappers, normalize whitespace, or turn an open-result line label into a page byte offset. A prefix boundary backs up one code unit if necessary to avoid splitting a surrogate pair.

The rendered source block extends to the next detected header boundary, including a boundary whose reference family is unsupported or whose URL is empty or unsupported. Separator lines immediately before that header consequently remain at the end of the preceding content range; the unsupported header and its following body do not.

## Continue within the retained response

For a contiguous view, use start_index and max_sources. coverage.next_index points to the next retained source index when more parsed sources remain. It is not a provider cursor or a command to search again.

~~~js
const next = projectWebSources(retainedResponse, {
  start_index: overview.coverage.next_index,
  max_sources: 4,
  max_content_chars: 1200,
  max_total_content_chars: 4800
});
~~~

Call this form only when next_index is a non-null integer. A metadata-only request can use max_sources: 0; its unchanged next_index is not forward progress.

After an overview, select exact observed source indices without spending the output budget on intervening bodies:

~~~js
const selected = projectWebSources(retainedResponse, {
  source_indices: selectedIndices,
  max_sources: selectedIndices.length,
  max_content_chars: 12000,
  max_total_content_chars: 24000
});
~~~

The indices must be distinct, nonnegative, strictly increasing and within the parsed response. max_sources must accommodate the entire list. An explicit start_index cannot accompany source_indices. Sparse selection returns null start_index and next_index, plus the full selected_source_indices and omitted_source_index_ranges. Omitted ranges are half-open source-index intervals.

Selection is a caller decision based on the actual overview. There is no domain, keyword, recency, authority or relevance filter in the adapter.

## Bounds

| Option | Default | Accepted range |
| --- | ---: | --- |
| start_index | 0 | Nonnegative safe integer within the parsed source count |
| max_sources | 8 | 0–100 |
| max_content_chars | 800 | 0–100,000 per selected source |
| max_total_content_chars | 6,400 | 0–1,000,000 across selected sources |
| max_input_chars | 1,048,576 | 1–8,388,608 across all text items |
| max_header_chars | 4,096 | 128–16,384 per title/URL/reference/word-limit prefix |

A source's title, URL and reference remain complete. An oversized header produces an explicit input-limit result instead of a shortened URL that might be mistaken for a usable source link. Content budgets cover rendered_content; they are not a token estimate or a bound on the complete JSON output, which also contains headers and coverage metadata.

All text is parsed before output selection. Limiting the returned sources does not imply that unselected input was never received or consumed. At most 4,096 content items are accepted.

## Coverage and non-success outcomes

The output always identifies its scope as retained_response_only, snapshot false, and provider_completeness not_inferred. It reports parsed source count, selected and omitted indices, selected/returned content lengths, and truncated source count.

Non-text items are identified by their original index and type; their payload is not decoded or represented as page text. Text before a recognized first header, complete text items with no recognized header, and header blocks without a supported reference family or URL remain visible as unparsed_text_ranges. Repeated supported-source reference IDs are preserved as separate source entries and listed in duplicate_reference_ids; the adapter does not silently deduplicate them.

all_rendered_source_content_included means that all parsed HTTP(S) source blocks were returned without content truncation. It does not assert completeness of the underlying pages, retrieval results, provider pagination or non-text payloads. all_input_text_has_source_headers describes only the absence of unparsed text ranges in this rendering.

| Status | Meaning |
| --- | --- |
| PROJECTED | Supported source blocks were parsed; inspect all coverage fields |
| PROVIDER_ERROR | The supplied envelope has isError true |
| UNSUPPORTED_REPRESENTATION | The envelope/content-item shape cannot be consumed |
| INPUT_LIMIT | A content-item, text or header bound was exceeded |
| UNSUPPORTED_RENDERING | A detected word-limit field cannot be represented safely |
| UNRECOGNIZED_RENDERING | No supported source headers were found |

A no-header result is **not** evidence that a search found zero results. It may be another native rendering, a provider notice or text that requires direct inspection. Invalid caller options throw TypeError or RangeError rather than silently changing selection.

## Mixed source and unsupported-header blocks

A renderer-shaped boundary is recognized before its URL is classified. Its title,
parenthesized URL field, renderer-shaped reference and numeric word-limit marker
must have the same line structure described above. Boundary detection accepts
`turn` followed by decimal digits, a lowercase ASCII family name, and decimal
digits. Source entries additionally require one of the supported families
(search, view, fetch, news or academia) and an HTTP(S) URL with no whitespace.
An unfamiliar family remains unparsed even when its URL is HTTP(S); it does not
become content belonging to the preceding source.

A boundary with an empty URL, or another unsupported URL representation, closes
the preceding source. Its complete block remains in `unparsed_text_ranges`
until the next recognized boundary or text-item end. That entry includes the
original `content_index`, half-open `range`,
`reference_id`, `rendered_header_range` and reason
`SOURCE_HEADER_WITHOUT_SUPPORTED_URL`. Retrieve that exact slice
from the original text item when its contents matter.

A boundary with an unsupported reference family has the same range fields and
reason `SOURCE_HEADER_WITHOUT_SUPPORTED_REFERENCE`. This check precedes URL
classification; the literal `reference_id` is retained without interpreting the
family or asserting that the reference is invalid. Such a block can be read
directly from its original response range. Supported-family URL refusals keep
the existing `SOURCE_HEADER_WITHOUT_SUPPORTED_URL` reason.

This keeps a rendered error notice from becoming part of the preceding page's
content. The title is not an error classifier: a header named "Internal Error"
is handled through its URL representation, and an arbitrary error-looking title
does not by itself establish provider failure or source authority.

A mixed response can remain PROJECTED with useful sources and an explicit
unparsed block. Its `all_input_text_has_source_headers` is false.
A response containing only unsupported-URL or unsupported-reference blocks
remains UNRECOGNIZED_RENDERING with its unparsed ranges retained. Top-level
`isError: true` still returns PROVIDER_ERROR as before. Header-size,
word-limit, input-size and selection bounds continue to apply.

The adapter cannot identify every possible notice format or authenticate a
header-shaped quotation inside page text. This change handles the documented
boundary structure; it does not turn every unrecognized rendering into a known
error or establish that no other text needs inspection.

## Evidence boundary

A requested domain filter does not establish that returned URLs satisfy it. The overview makes the observed URLs available to the caller, without filtering away mismatches.

A reference is labeled rendered_header identity. The parser cannot authenticate a web page, distinguish an exact header-shaped quotation from a renderer-issued header, validate a redirect, or establish source authority. Retain the original tool envelope and available citation references when attributing a claim. No provider fetch, screenshot, PDF-byte read, page completeness or factual verification is implied by projection.

The adapter preserves the returned word_limit metadata; it does not enforce quotation or source-use limits. Those limits still apply when writing from a source.

This helper is separate from [connected_slack_pages.cjs](connected_slack_pages.cjs), GitHub issue search, and retained HTTP-capture summaries. It adds no retrieval, credential, publication, execution or capacity policy.

## Actual intake use

The initial consumer was the October 4 R.O.A.D. Barbados source intake. The retained search response contained 35,134 UTF-16 code units and eight unrelated source headers despite the caller's requested domain. One actual API call returned all eight original references/URLs with 1,120 content code units and all eight truncation flags.

The next official-page open used the existing URL from the baseline README. Its fresh retained response contained 19,638 code units and one supported source. The consumer first read a 600-code-unit preview, then selected that observed source index for its complete 19,459-code-unit content. Both calls used the same retained response; no search/open operation was replayed.

These were calls to the exported API on actual tool responses. No synthetic input, fixture, new test, native process, screenshot or copied source-body artifact was used. The full responses and selections remain in the caller's session; this guide stores only the operating example and measured scope.


### Mixed-response correction, October 4, 2026

A later Alameda procurement intake combined an existing official-board link
click with a search for a project number and addendum. The retained native
response had one text item containing 23,961 UTF-16 code units and nine supported
source headers. A trailing empty-URL error block was previously absorbed into
the last search source's body, while the view reported no unparsed text.

The consumer ran the corrected public API once on that full retained response,
using the exact prepared Git blob
`31ab954857c86ae3985a78c7254d68c015ef61ef`. The same nine supported sources
were retained. The last source's range changed from [21,853, 23,961) to
[21,853, 23,766). The remaining 195 code units became an explicit unparsed range
[23,766, 23,961), with its own rendered reference and header range
[23,766, 23,813). The coverage flag for all input text having source headers
changed from true to false.

The earlier range and coverage values came from the already retained original
projection; the old API was not rerun. The corrected invocation used no new
search, click, portal request, native process, synthetic response or fixture.
The original mixed tool response remains with the consumer. No source body is
copied into this guide, and no procurement finding is inferred from the search
results or failed click.


### Empty-title PDF response, October 4, 2026

The xTech procurement reader supplied an actual retained official-PDF response
whose first rendered title field was empty. The response contained 24,731
UTF-16 code units. The previous parser returned UNRECOGNIZED_RENDERING with
no supported sources and the whole text item marked unparsed.

The consumer changed only the title-field quantifier in the existing header
pattern and invoked the public API once using candidate Git blob
`01f7a02d1cfddde21b0644ac82f9753a6ae4001d`. The input response and original
limits remained unchanged: start_index 0, max_sources 2, max_content_chars
15,000 and max_total_content_chars 15,000.

The result was PROJECTED with one source, the original reference, official URL
and word limit, and a literal empty-string title. Its rendered source range was
[0, 24,731), header range [0, 125), and content range [125, 24,731).
The returned content range [125, 15,125) exactly matched the corresponding
15,000-code-unit slice of the retained original. The 24,606-code-unit content
was explicitly truncated; no source was omitted and no text remained unparsed.
The original raw response was unchanged.

Only the corrected API ran on that retained response. The earlier refusal was
already retained; no old API, web retrieval, native process, fixture or suite
was rerun. This guide retains only the measured projection boundary, not the
PDF text or a procurement conclusion.


### Academia reference boundaries, October 4, 2026

A later Inkomoko search response contained native academia references alongside
search references in one retained 38,827-code-unit text item. The previous
pattern recognized only search/view/fetch/news references. It parsed 18 sources
and attributed academia headers and their following text to preceding sources,
while reporting no unparsed text.

The consumer invoked the corrected API once with candidate Git blob
`f69609cb865273542d2a90c24b2dd290f261c3ed`. The existing limits were unchanged:
start_index 10, max_sources 10, max_content_chars 1,000 and
max_total_content_chars 5,000. The result parsed 22 sources, returned indices
10–19, and reported next_index 20 with omitted ranges [0, 10) and [20, 22).
The four additional parsed blocks were the actual academia references; the
last two stayed omitted by this selection rather than being folded into an
earlier source.

Two corrected boundaries illustrate the attribution change. The source with
reference turn583search15 now ends at 35,998 rather than 36,427; its content
range is [35,827, 35,998). The following turn583academia16 block occupies
[35,998, 36,427), with header [35,998, 36,172) and content [36,172, 36,427).
The turn583search18 block now ends at 37,509 rather than 38,827; its content
range is [36,932, 37,509). The following turn583academia19 block occupies
[37,509, 37,958), with header [37,509, 37,632) and content [37,632, 37,958).
The selected search references were preserved, and the unaffected selected
search ranges were unchanged.

All ten returned contents matched their exact original text slices. The result
returned 4,912 content code units with three explicit truncation flags, no
unparsed ranges, and no duplicate references. Titles, URLs and word limits came
from the actual headers, and the original response was unchanged. Only this
corrected API invocation ran; the prior projection was already retained. No
web retrieval, native process, fixture, suite or raw source-body publication
was used. Recognizing a reference kind does not classify its relevance or
establish authority for the procurement task.


### Unsupported reference-family boundary, October 4, 2026

The next retained Raleigh search response contained three reddit reference
headers after an official PDF source. The existing supported-family pattern
absorbed those headers and their bodies into the PDF source, whose range ended
at the end of the 32,697-code-unit response. No procurement conclusion was drawn
from that mixed range.

The consumer invoked candidate Git blob
`bc68a05aa46c12000814c158dccb57caefb69fda` once on the unchanged retained
response. The existing source selection [10, 14, 15, 16, 17], max_sources 5,
max_content_chars 1,800 and max_total_content_chars 9,000 were preserved.
There were still 18 supported sources, and all five selected references remained.
Every returned content string matched its exact original response slice.

The official turn595search17 source now occupies [30,242, 30,809), with content
[30,420, 30,809), rather than ending at 32,697. Three unsupported-reference
blocks are retained separately:

| Reference | Unparsed range | Rendered header range |
| --- | --- | --- |
| turn595reddit18 | [30,809, 31,461) | [30,809, 30,988) |
| turn595reddit19 | [31,461, 31,864) | [31,461, 31,672) |
| turn595reddit20 | [31,864, 32,697) | [31,864, 32,105) |

Each has reason SOURCE_HEADER_WITHOUT_SUPPORTED_REFERENCE. The response stays
PROJECTED, while all_input_text_has_source_headers changes from true to false.
The selected output returns 1,414 content code units without truncation and
explicitly omits 13 supported sources in ranges [0, 10) and [11, 14).
Unsupported-family blocks are not assigned supported-source indices.

The original response and earlier projection remain unchanged. A caller setup
attempt selected the tool-result content array as helper source and failed
before invoking the API; using the retained structured source corrected that
setup without a provider reread. The single actual API invocation used no web
retrieval, old API replay, native process, fixture or suite. No response body is
published here, and no relevance or authority is inferred from the unparsed
reference families.
