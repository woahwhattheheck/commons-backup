# Read retained source changes with bounded output

`createTextDiff(beforeText, afterText, options = {})` compares two complete retained strings and returns a reusable line alignment. Use it when scattered changes make a full source dump or one large changed span too expensive to read. It performs no provider calls, file reads or writes.

Load the complete trusted CommonJS helper once in the connected runtime:

```javascript
const box = {exports: {}};
new Function("module", "exports", helperSource)(box, box.exports);
const {createTextDiff} = box.exports;

const diff = createTextDiff(beforeText, afterText);
const first = diff.project();
```

Here `helperSource` is the complete fetched `host/connected_text_diff.cjs` source; `beforeText` and `afterText` are the retained source versions. Keep their original provider responses and immutable source identifiers alongside the comparison. The helper does not fetch missing content or establish which version is current.

## Exact comparison and preparation limits

Inputs must be complete strings. LF separates line tokens, but each token preserves its raw content and terminator: LF, CRLF, or an unterminated final line. Empty input has zero lines. Whitespace, line endings and Unicode are not normalized.

The constructor trims the exact common prefix and suffix, then computes a longest common subsequence of the remaining raw lines. The resulting alignment minimizes the total inserted and deleted line count. Raw line tokens are interned to numeric equality identifiers before the matrix calculation. Equal choices delete before inserting, so repeated-line alignments are deterministic. A changed line appears as deletion plus insertion; this is not a semantic or move-aware comparison.

| Constructor option | Default | Maximum |
| --- | ---: | ---: |
| `context_lines` | 3 | 20 |
| `max_input_chars` | 1,048,576 combined | 8,388,608 combined |
| `max_lines_per_input` | 10,000 | 50,000 |
| `max_matrix_cells` | 2,000,000 | 4,000,000 |

Character counts use JavaScript UTF-16 code units, not UTF-8 bytes. The matrix budget applies to the trimmed comparison. Its Uint32 storage uses four bytes per matrix cell; this is matrix storage, not a bound on total runtime memory or retained output.

Unknown or invalid options raise `TypeError`. Exceeding the input-character, per-input-line, or matrix budget raises `RangeError` before the dynamic-programming matrix is allocated. A rejected comparison does not return a partial alignment or silently switch algorithms.

The frozen result has schema `commons.connected_text_diff/v1`, source metadata, statistics and a `project` method. Statistics include:

- `comparison_complete: true`, `algorithm: "line_lcs"`, and `tie_break: "delete_before_insert"`;
- common prefix/suffix line counts and matrix cell/byte counts;
- matched, inserted and deleted line counts;
- `hunk_count` and `hunk_rows`.

The complete comparison and the amount of projected output are separate facts. The matrix reference is discarded before the result returns; reclamation follows the runtime’s garbage collection. Subsequent projections reuse the retained alignment and do not perform another comparison.

## Read the alignment in bounded pages

`diff.project(options = {})` selects hunk rows and limits returned text:

| Projection option | Default | Maximum |
| --- | ---: | ---: |
| `start_hunk` | 0 | Position in this alignment |
| `start_row` | 0 | Row within the selected starting hunk |
| `max_hunks` | 8 | 256 |
| `max_rows` | 160 | 2,000 |
| `max_line_chars` | 400 | 65,536 |
| `max_total_line_chars` | 12,000 | 262,144 |

Hunk and row positions are zero-based. The end position `start_hunk: diff.statistics.hunk_count, start_row: 0` is a valid sentinel. Follow the returned coverage cursor:

```javascript
const page = diff.project({max_rows: 80});
const next = page.coverage.next_position;
const following = next === null ? null : diff.project({
  start_hunk: next.hunk_index,
  start_row: next.row_index,
  max_rows: 80
});
```

Each returned hunk retains its full before/after one-based start and line count, even when only a selected row interval is included. When one side has count zero, its one-based start is the insertion or deletion cursor position, not a claim that a source line exists there. Each row reports:

| Field | Meaning |
| --- | --- |
| `kind` | `context`, `delete`, or `insert` |
| `before_line`, `after_line` | One-based source line numbers; `null` on the absent side |
| `before_range`, `after_range` | Absolute UTF-16 half-open source ranges; `null` on the absent side |
| `line_ending` | `LF`, `CRLF`, or `none` for the original raw line |
| `text` | Raw line prefix; includes its terminator when fully returned |
| `content_chars`, `returned_chars`, `truncated` | Original size, returned size, and explicit clipping state |

Text clipping never splits a surrogate pair. A clipped prefix can omit the line terminator while `line_ending` still describes the original line.

Coverage reports omitted rows before and after the selection, truncated rows, `all_hunks_included`, `all_hunk_rows_included`, and `next_position`. Inspect these fields before treating a page as complete. Unchanged lines outside the context windows are not hunk rows.

**The cursor advances by rows even when their text is clipped.** A `null` next position therefore does not by itself prove that every selected line was returned in full. To read a clipped row completely, project its same hunk/row position again with wider text budgets, within the documented maxima, or read its exact range from the retained source. Advancing the cursor will not recover the omitted suffix.

Projection budgets bound returned line text and row/hunk counts; they are not an exact cap on serialized JSON bytes. Metadata and field names also occupy space.

## Compact display and first use

Keep the full result for source navigation. For reading, a compact view can preserve coverage and hunk headers while omitting verbose row ranges:

```javascript
const page = diff.project({
  max_hunks: 16,
  max_rows: 256,
  max_line_chars: 1200,
  max_total_line_chars: 20000
});
const display = {
  source: diff.source,
  statistics: diff.statistics,
  coverage: page.coverage,
  hunks: page.hunks.map(({rows, ...header}) => ({
    ...header,
    rows: rows.map(row => ({
      kind: row.kind,
      before_line: row.before_line,
      after_line: row.after_line,
      text: row.text,
      truncated: row.truncated
    }))
  }))
};
text(display); // Connected-runtime output; retain the complete page separately.
```

This view preserves the raw returned text and its clipping flag. It does not change the retained alignment or the original projection.

The first actual public-API use loaded helper Git blob `28b710f4b0ade94ebe0a5cf6935ab37a156c5853` and compared two complete retained versions of `host/connected_slack_pages.cjs`:

| Input | Immutable Git blob | UTF-16 characters | Lines |
| --- | --- | ---: | ---: |
| Before | `a0cf5d684ca01b025404e0273536e453df645b7a` | 35,542 | 691 |
| After | `8477fca1dfd5cc722c9f17f461b19ac54030384f` | 38,892 | 754 |

One constructor call found 112 common prefix lines and 13 common suffix lines. The trimmed matrix contained 357,210 cells, occupying 1,428,840 matrix bytes. The complete alignment matched 681 lines, inserted 73 and deleted 10. It produced five hunks containing 126 rows.

The projection used the explicit limits shown above and returned all five hunks and all 126 rows, containing 7,433 raw line characters. No rows were omitted or clipped; coverage was complete and `next_position` was `null`. All five hunks were read completely. This is one observed source-reading operation, not a runtime-behavior check of the Slack reader or a performance benchmark.

## Scope and custody

This result is source-reading data, not an applicable patch. It neither mutates a repository nor verifies runtime behavior, authorization, repository freshness, source provenance or semantic equivalence. Exactness concerns the supplied strings. A complete comparison of incomplete provider excerpts remains a comparison of those excerpts.

Retain the original strings and provider locators when later work depends on the result. Keeping a function object or a session store key is not durable custody. Reuse the alignment while it is available; preserve uniquely expensive or unrecoverable inputs through the existing private or repository-backed work record.
