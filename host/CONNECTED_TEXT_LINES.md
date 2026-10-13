# Read selected lines from a complete, identified text source

`connected_text_lines.cjs` exposes `createTextLines(leaf, options = {})`, a
pure reader for one complete UTF-8 source. The constructor checks the supplied
content against its expected Git blob SHA once, then retains line boundaries for
repeated bounded projections. It performs no provider calls, envelope extraction,
decoding, Markdown or HTML interpretation, source execution, or output writes.

## Bind the complete source

Supply `{content, encoding: 'utf-8', expected_blob_sha}`.
The expected SHA must be a complete lowercase 40-character Git blob identity.
Optional `locators` may contain `repository_full_name`, `path`, `ref`, and `url`;
each supplied locator must be a nonempty string of at most 4,096 UTF-16 code
units. Locators are copied as caller-supplied context, not independently verified
repository membership, ancestry, freshness or permission.

A complete-body hash mismatch throws an error with code
`TEXT_SOURCE_BLOB_MISMATCH`, expected/observed blob identities and observed byte
count. No projector is returned. A clipped provider response is not a complete
source merely because it carries the full-file SHA. Invalid fields/options and
unpaired UTF-16 surrogates are rejected; no line-ending or Unicode normalization
is performed.

The constructor depends on the existing `./connected_git_blob_identity.cjs`.
In CommonJS, use `require('./host/connected_text_lines.cjs')`. In connected V8,
load the complete trusted modules explicitly:

```javascript
const identityBox = {exports: {}};
new Function('module', 'exports', identitySource)(
  identityBox, identityBox.exports);

const box = {exports: {}};
new Function('module', 'exports', 'require', projectorSource)(
  box, box.exports, name => {
    if (name !== './connected_git_blob_identity.cjs') {
      throw new Error('Unsupported dependency: ' + name);
    }
    return identityBox.exports;
  });
const {createTextLines} = box.exports;
```

Here `identitySource` is the complete accepted
`host/connected_git_blob_identity.cjs` (blob
`132074b6393afd73a921939ad39789f3a6b38ce5`), and `projectorSource` is this
module's complete source. Fetching and extracting those source bodies remain
explicit caller operations. The dependency computes Git's UTF-8 SHA-1 blob
identity; this projector does not contain another digest implementation.

Keep the original full provider response and request privately. Extract only
the complete retained text into `leaf.content`; set its explicit UTF-8 encoding
and the separately observed expected blob identity. Passing an entire native
tool envelope or a base64 body does not cause automatic extraction or decoding.

## Select and display source lines

A contiguous projection starts at a one-based line number:

```javascript
const view = createTextLines({
  content: completeText,
  encoding: 'utf-8',
  expected_blob_sha: observedBlobSha,
  locators: {repository_full_name, path, ref},
});
const page = view.project({
  start_line: 1,
  max_lines: 160,
  max_line_chars: 400,
  max_total_line_chars: 12000,
});
text({source: page.source, coverage: page.coverage, lines: page.lines});
```

The frozen constructor result has schema `commons.connected_text_lines/v1`,
`source`, copied preparation `limits` and `project`. Source metadata
separates computed byte identity (`identity_matches: true`,
`identity_basis: computed_git_blob_sha1_utf8`) from
`locator_binding: caller_supplied_not_verified`. It reports UTF-8 bytes,
UTF-16 characters and source line count. Projections reuse this verified source;
they do not hash again or mutate caller inputs.

For nonadjacent regions, pass `line_ranges` instead of `start_line`. Ranges
are **one-based and half-open**: `[[1, 3], [4, N + 1]]` selects lines 1-2 and
4-N, explicitly omitting line 3. This is useful when an already-observed inline
data URL occupies one giant line. The omission is reported, not silently
discarded or interpreted.

```javascript
const page = view.project({
  line_ranges: [[1, 3], [4, view.source.lines + 1]],
  max_lines: 200,
  max_line_chars: 1200,
  max_total_line_chars: 20000,
});
```

Use only observed line bounds and set `max_lines` high enough for the total
selected lines. At most 128 dense, sorted, nonoverlapping ranges are accepted;
adjacent ranges are allowed. Endpoints must be safe integers with
`1 <= start < end <= source.lines + 1`. Holes, duplicates, overlapping or
descending ranges, and out-of-bounds endpoints are rejected. `[]` selects
nothing. `line_ranges` and `start_line` cannot be combined.

The default contiguous `start_line` is 1. `source.lines + 1` is a valid
empty end sentinel. LF separates lines. Each LF or CRLF terminator remains part
of its original raw line; an unterminated final line is retained. Empty text has
zero lines, a final LF creates no phantom extra line, and a lone CR remains
content. These line-token and surrogate-boundary rules follow the existing
text-diff reader without changing that module or invoking its LCS algorithm.

## Exact spans and coverage

Each projection has schema `commons.connected_text_lines_projection/v1`,
status `PROJECTED`, source metadata, output limits, selection, `lines`
and coverage. Each row reports:

| Field | Meaning |
| --- | --- |
| `line_number` | One-based original source line |
| `source_range` | Complete raw line's absolute zero-based UTF-16 half-open range |
| `returned_range` | Returned prefix's range in that same original text |
| `line_ending` | Original `LF`, `CRLF`, or `none` |
| `text` | Exact raw prefix, with its terminator only when included |
| `content_chars`, `returned_chars`, `truncated` | Full size, returned size and explicit clipping |

Text clipping never splits a surrogate pair. A clipped line may omit its
terminator while `line_ending` still describes the original full line.
Character counts and offsets use JavaScript UTF-16 code units, not byte offsets.

Coverage reports omitted line ranges and their complete source-character
ranges, plus separate truncated suffix ranges for selected lines. It distinguishes
selected, returned, omitted and truncated content characters:

```text
source.chars = omitted_content_chars + selected_content_chars
selected_content_chars = returned_content_chars + truncated_content_chars
```

`all_source_lines_selected`, `all_selected_content_included`, and
`all_source_content_included` describe different coverage boundaries.
The scope is the retained verified text only; `snapshot: false` remains explicit.

A contiguous page's `coverage.next_start_line` advances past returned rows,
even when their text was clipped. To recover a clipped suffix, reselect that same
line with a larger text budget, or inspect its exact range in the retained source.
Simply following the next-line cursor does not recover it. A null cursor does
not prove complete source text was returned. Sparse selection uses
`navigation: caller_selected_ranges` and has no automatic continuation.

## Budgets and refusals

| Option | Default | Maximum |
| --- | ---: | ---: |
| Constructor `max_input_chars` | 1,048,576 | 8,388,608 |
| Constructor `max_lines` | 10,000 | 50,000 |
| Projection `max_lines` | 160 | 2,000 |
| Projection `max_line_chars` | 400 | 65,536 |
| Projection `max_total_line_chars` | 12,000 | 262,144 |

Options must be finite safe integers within these bounds. Both projection text
budgets may be zero for metadata-only rows; the other limits are positive.
Unknown options and invalid shapes raise `TypeError`. Exceeding input/line
budgets, invalid range endpoints, and an explicit selection exceeding its line
budget raise `RangeError`. No silently partial explicit range is returned.

Returned budgets bound row counts and text characters, not total serialized
JSON bytes or total runtime memory. Source locators, ranges and other metadata
also occupy space. The constructor retains the supplied string and a bounded
line index; it does not make an encoded copy of the source for hashing.

## Motivating input and custody

The concrete motivating input is an already-retained official
`drivendataorg/lost-in-transcription-runtime` README, observed Git blob
`26849c241bdd99ff834e6833742e8c593e022490`, whose third line contains a large
inline badge/data URL. The surrounding prose can be selected without expanding
that line, while preserving its omitted source range. This does not interpret
the badge, execute HTML, establish the repository's current state, or authorize
a provider mutation.

Retain the original source response, locator and actual projection outcome when
later work depends on them. A session store or function object is not durable
custody. Use the existing private or repository-backed work record for uniquely
expensive or unrecoverable inputs; do not publish private source bodies merely
to demonstrate the projector.
