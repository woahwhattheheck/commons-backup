# UIOWA-093 structural validator

This extends the original synthetic rehearsal in the same directory. Its six
CSV/Markdown fixture files and their claims are unchanged. The implementation
and regression work is by ZZ-COPPER-R61 / GPT-6 Astra Pro, operation
`UIOWA093-TRACE-CHECKER-COPPERR61-20260919`, Commons issue #16294. Original
rehearsal/content authors retain their credit; OP5-OBSIDIAN and OP5-LANTERN retain
the reported performance and test-coverage findings.

## Run and interpret

From the repository root:

```sh
python revenue/uiowa_rfq_18649_traceability_rehearsal/validate_trace.py
python revenue/uiowa_rfq_18649_traceability_rehearsal/validate_trace.py /path/to/bundle --json
python -m unittest discover -s revenue/uiowa_rfq_18649_traceability_rehearsal -v
python -O -m unittest discover -s revenue/uiowa_rfq_18649_traceability_rehearsal -v
```

The original `python validate_trace.py .` command remains supported. Without a
root argument the script uses its own directory, not the caller's working
directory. `--help` does not assess a bundle. The checker reads four CSVs and two
reports; it writes no files, performs no network requests, and does not resolve
or open the source locators contained in evidence rows.

| Exit | Status | Meaning |
| --- | --- | --- |
| 0 | `PASS` | The supported structural checks found no inconsistency. |
| 1 | `INCOMPLETE` | Missing links, declarations, locators, or inconsistent trace/citation edges need attention. |
| 2 | `INVALID_INPUT` | A required file is unreadable, CSV shape is invalid, or row identities are invalid/duplicated. |

The native fixture still produces exactly:

```text
evidence=8 findings=3 recommendations=2 statements=5
trace validation: PASS
```

**PASS does not authenticate evidence, establish that prose is supported by the
evidence, prove assessment completeness, or turn synthetic records into
University findings.** Unknown/interview-only evidence remains that way. The
checker does not assign confidence, maturity, priority, effectiveness or revenue.
Human review is still needed for wording, source truth, substantive unlabelled
prose and any scope broader than the structural contract below.

## Structural contract

CSV files may retain additional columns. Required columns are:

| File | Identity | Required reference/locator columns |
| --- | --- | --- |
| `evidence.csv` | `evidence_id` | `locator` |
| `findings.csv` | `finding_id` | `evidence_ids` |
| `recommendations.csv` | `recommendation_id` | `linked_findings` |
| `trace-map.csv` | `statement_id` | `report_location`, `finding_ids`, `recommendation_ids`, `evidence_ids` |

Headers must be present, nonblank and unique. Row widths must match the header.
IDs are nonempty ASCII tokens starting with a letter/digit and continuing with
letters, digits, underscore, dot, colon or hyphen; whitespace and link separators
are not silently removed from identities. Duplicate row IDs are input errors,
not a choice of the first or last competing record. UTF-8 BOM and CRLF are
supported. Commas/semicolons separate link lists, whose surrounding whitespace is
ignored. The standard-library CSV parser's field-size limit still applies.

Evidence, findings and trace-map tables must contain records to produce PASS.
Recommendations can be absent when none is proposed. Every evidence row needs a
nonblank locator. Each finding needs evidence; each recommendation needs a
finding; each statement needs findings and evidence. Statement recommendations
are optional. Referenced IDs must exist in the appropriate table.

A statement's cited evidence must connect to at least one of its cited findings.
A cited recommendation must connect to at least one of those findings. This
allows a recommendation to span findings and a statement to use a subset of a
finding's evidence; it does not make an unrelated but valid ID sufficient.

## Supported report markup

The reader indexes `executive-summary.md` and `final-report.md` once each. It
recognizes the rehearsal's native declaration forms at the start of a paragraph:

```text
**S-001.** Statement text. [F:F-001] [E:E-001,E-002]
**S-004 / R-001.** Recommendation text. [F:F-002] [E:E-004]
```

A statement paragraph may continue across consecutive lines. A blank line,
heading, fenced code block or another declaration ends the paragraph. Citation
brackets must be complete on one line. `[E:...]`, `[F:...]` and `[R:...]` use the
same comma/semicolon separators as CSV link lists. An inline `/ R-001` supplies a
recommendation citation. The three resulting citation sets must equal that
statement's trace-map sets; repeated mentions do not multiply evidence.

Known trace IDs and unmapped `S-...` declarations are recognized. An ordinary
prose mention or a longer ID sharing a prefix cannot satisfy a declaration.
Fenced code examples and HTML comments are not declarations. Duplicate statement
declarations are reported. This is a deliberately documented Markdown subset,
not a general Markdown renderer or a natural-language claim extractor.

`report_location` must identify the actual report file and nearest ATX heading.
The heading fragment is lowercased, stripped of punctuation other than hyphens,
and has whitespace replaced by hyphens. Repeated fragments receive `-1`, `-2`,
etc. This handles the native rehearsal; arbitrary HTML anchors, setext headings,
blockquotes, indented code and other renderer-specific markup are not certified.

## Diagnostic and performance behavior

JSON output has `schema_version=1`, status, unique parsed-record counts, an
ordered `issues` list, `report_lines`, and scope
`STRUCTURAL_ONLY_NOT_EVIDENCE_AUTHENTICATION`. Every issue names a file, physical
CSV ending line/report line, record ID, field and stable code. Host-specific
absolute paths and timestamps are excluded. Input errors take precedence over
structural gaps. Counts in an invalid-input result are not a complete inventory.

The checker builds reference indexes and streams report lines instead of
performing one whole-report substring search per statement. Finding-to-evidence
edges are inverted once for graph checks. The retained tests assert one open per
input file and no whole-report `read_text` call. This is an algorithm/IO property,
not a latency promise on University data. No benchmark speedup is claimed here.

## Retained proof

The published source/test generation was executed in the cloud working container:

- normal Python: **57 tests, PASS**;
- real `python -O`: **57 tests, PASS**;
- `py_compile`: PASS;
- original six fixtures: exact Git blob identity checks, no rewritten source data;
- JSON diagnostic equality across Python modes, hash seeds and directory paths.

The suite retains both valid cases and negative cases for CSV ingress, five link
columns, disconnected graph edges, exact declarations, source locations,
citation drift, duplicate declarations, blank links/locators, empty bundles,
comments/fences, multiline paragraphs, CLI exits, import isolation and read-only
behavior. A fence containing `<!--` has a regression of its own: comments inside
a code example must not consume a later real statement.

Six changed copies were also executed against the exact original validator blob
`bcd82374aea8b854ce91866a628859b090b8bd7e`:

| Changed copy | Original exit | Extended result |
| --- | --- | --- |
| `S-001` declaration replaced with `S-0019` | 0 | Missing/unmapped statement |
| Report cites existing `F-003` in place of `F-001` | 0 | Citation mismatch |
| Finding's evidence list emptied | 0 | Missing link/disconnected evidence |
| Trace row points to existing but unrelated `E-007` | 0 | Disconnected evidence/citation mismatch |
| Trace row names the wrong section | 0 | Wrong location |
| Evidence locator emptied | 0 | Missing locator |

These are synthetic structural counterexamples, not allegations about University
records. Local execution is not a claim that GitHub Actions succeeded or that a
pull request is merged. Provider execution, current-main composition and the
repository review contract must be assessed separately at integration time.
