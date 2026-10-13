# Change trace timing and evidence review

The published 041 synthetic trace contained one extra empty CSV field in stage 8, shifting its evidence meaning, exception, gap and follow-up question into the wrong columns. The repair removes exactly one comma and changes no substantive wording. The acceptance stage remains **UNKNOWN**.

Open [change-trace.xlsx](change-trace.xlsx) for the completed editable review workbook. It covers all 13 stages, preserves evidence statements and reviewer questions, and shows a reversible timing scenario. The source example is fictional and is not a University finding.

## Run the strict reader

Python 3.10 or later, standard library only. From the repository root:

```sh
python3 revenue/uiowa_rfq_18649_change_trace/change_trace.py revenue/uiowa_rfq_18649_workbench/41-synthetic-change-trace.csv --synthetic --format markdown
python3 revenue/uiowa_rfq_18649_change_trace/change_trace.py revenue/uiowa_rfq_18649_workbench/41-synthetic-change-trace.csv --synthetic --advance-triage-hours 3 --format json
```

Use `--supplied-records` instead of `--synthetic` for an explicitly identified nonsynthetic input. The label is caller-supplied, not independently authenticated. The reader requires the exact 21-column header, equal row widths, unique change/group/stage identities, positive stage numbers, recognized source evidence states and offset-qualified timestamps. It rejects reversed within-stage chronology. It never silently discards surplus fields or shifts their meaning. Exit 0 means a report was produced; invalid input exits 2 with a diagnostic.

JSON retains all source fields, exact file bytes as Base64, SHA-256, Git blob ID, record numbers, original timestamp offsets, rational interval values and the scenario. Markdown is the readable timing and follow-up view. Neither format replaces source evidence or resolves an unknown claim. `worked-report.json` and `.md` are the actual CLI outputs for the three-hour scenario above.

## What the actual trace shows

| Measure | Original | Three-hour earlier triage |
|---|---:|---:|
| Triage queue interval | 209/60 h (3.483333) | 29/60 h (0.483333) |
| Following stage's queue interval | 298/15 h (19.866667) | 343/15 h (22.866667) |
| Sum of known queue intervals | 179/4 h (44.75) | 179/4 h (44.75) |
| Sum of known work-start/end spans | 331/12 h (27.583333) | 331/12 h (27.583333) |
| Earliest observed queue entry to latest observed work end | 217/3 h (72.333333) | 217/3 h (72.333333) |
| Stages missing queue/work intervals | 1 | 1 |

The scenario advances stage 2's start and end by three elapsed hours and advances stage 3's queue entry to that earlier handoff. It holds every subsequent work start/end fixed. Waiting moves between stages; the observed endpoint span does not improve. No evidence status, wording, owner or source reference changes. The declared two-decimal source duration fields remain original source values, not revised scenario measurements.

The tool checks that the advance cannot precede the observed triage queue entry and that stage 3 originally receives the triage handoff at triage completion. This scenario is limited to one supplied change/group with the expected stage 2/3 relationship. An advance of zero restores the source timing. It is an illustrative assumption, not an optimization or a claim about feasible operational changes.

## Interpretation boundaries

`active_hours` is the historical source column name. Its timestamps establish **elapsed work-start/end spans**, not person-hours, continuous activity, utilization or staffing cost. The implementation interval includes overnight time. Business calendars and parallel staffing are not modeled.

Known interval sums exclude missing intervals and disclose how many are missing. They do not prove completeness. Summing overlapping stages can exceed the elapsed journey time; the tool does not treat that sum as a critical path. Endpoint span means only the distance between the earliest supplied queue entry and latest supplied work end. Missing acceptance evidence stays unknown even though surrounding timestamps are available.

Source durations are rounded to two decimals. The reader reports a diagnostic if a stated value differs from its timestamp-derived interval by more than 0.005 hours, or if no timestamp pair supports it. All stated values remain in the report. The actual repaired example has no such discrepancies. The evidence states remain nine `SUPPORTED`, two `PARTIAL`, one `UNKNOWN` and one `CONFLICT`; these are retained source conclusions, not newly authenticated findings.

## Workbook workflow

**Timing** is the primary view. Edit the amber triage-advance input; zero restores observed timing, three shows the worked scenario. An advance beyond the observed queue produces `INVALID_ADVANCE`, without a plausible numeric scenario total. All hours use formulas; the source timestamps stay unchanged. Dates on **Source timing** are displayed in UTC; original offset-qualified strings remain in the CSV and JSON report. Tiny floating-point differences in spreadsheet dates are rounded for display; JSON retains exact rational hour values.

**Evidence** retains the source expectations, observed activities, roles, handoffs, reference IDs, evidence meanings, exceptions, gaps and follow-up questions. Enter interview notes in its amber reviewer-response column. Keep the original statements intact until a separately sourced revision is prepared. Frozen identifiers support horizontal navigation of the full evidence table. Timing changes do not modify evidence conclusions.

The workbook is a bounded view of this 13-stage example. To work with new source records, edit a separate CSV, run the strict reader and rebuild; workbook responses are not automatically written back to CSV or JSON. Preserve a separate saved workbook if collecting real reviewer responses before rebuilding.

`build_workbook.mjs` generates the artifact with `@oai/artifact-tool` in an environment where that package is installed:

```sh
node build_workbook.mjs worked-report.json output-directory
```

The analyzer has no spreadsheet dependency. The exported XLSX is directly editable in spreadsheet applications.

## Source repair and execution

Original source blob `08ff7e5b0409c868f090711530687aaba88c89a0` is 6,328 bytes. Repaired blob `9d0de446e5b0c73945b717abc0b76fb58951e45d` is 6,327 bytes. The original reader execution exits 2 at CSV record 9: 22 fields instead of 21. The repaired source has 13 stage records, each 21 fields; the evidence-semantics sentence, `none` exception, gap and question now occupy their intended columns.

Both actual CLI formats completed on the repaired source. The workbook was recalculated and all three sheets visually inspected. Reopening the saved file and changing the advance to zero restored the observed queues; four hours produced an invalid-input state; returning to three restored the scenario. Acceptance stayed UNKNOWN throughout. Native LibreOffice recalculation retained the headline results and no formula errors. Excel-specific behavior was not separately exercised.

The original method and example remain credited to [PR #16102](https://github.com/woahwhattheheck/commons/pull/16102). OP5-FLINT identified the export alignment problem; ZZ-ORIEL-462 preserved the repair/workbook scope in [#16315](https://github.com/woahwhattheheck/commons/issues/16315). This completion changes the one malformed source delimiter and adds this isolated companion. The existing workflow map, application, server and compiler remain unchanged.
