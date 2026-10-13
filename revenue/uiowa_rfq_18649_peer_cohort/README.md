# Public-source peer cohort — UIOWA-014

An eight-candidate research shortlist and a methodology-appendix rationale, prepared from official sources on **2026-09-19**.

- [14-peer-cohort.csv](14-peer-cohort.csv): editable, UTF-8, 8 rows and 17 columns.
- [14-selection-rationale.md](14-selection-rationale.md): source-linked selection reasoning, scope limits and the steps needed before quantitative benchmarking.
- [14-compiler-input.json](14-compiler-input.json): curated real input for the existing peer-evidence compiler.
- [14-compiler-walkthrough.md](14-compiler-walkthrough.md): mapping choices, actual results, source pin and replay command.
- [compiled/peer-evidence.md](compiled/peer-evidence.md): generated evidence register; the adjacent JSON and five CSV files preserve all source and metric context.

The first three university candidates have unknown staffing. Fairfax and Austin have explicitly scoped authorized-capacity evidence; Austin's is historical. Nebraska is a conditional system comparator. Wisconsin and Indiana remain outside the stated size band. No staffing average, performance ranking or University of Iowa finding is produced.

## Reading the CSV

`peer_id` is a stable reference, not a rank. `selection_role` records the proposed use; `scale_fit` keeps staffing qualification separate. `staff_value`, `staff_measure` and `staff_period` must travel together. Do not coerce `UNKNOWN` into zero or strip qualifiers such as approximately, more than, historical, or authorized.

`staff_source_url` identifies the official page or budget reviewed for staffing context; when staffing is UNKNOWN, that link does not imply the page contains a count. `practice_source_urls` uses ` | ` to retain multiple sources within one CSV cell. `practice_source_period` distinguishes historical reports from undated pages. `retrieved_on` is the reading date, not the observation date.

Fairfax's three figures retain their fund boundaries. They must not be loaded as three organizations or silently collapsed into an observed department headcount. Austin's 360.00 is a directly reported department authorization, not occupied staffing. Service breadth is a source-backed description of remit, not evidence that every service was effective throughout the period.

These are real public-source descriptions, not the fictional assessment fixtures elsewhere in the demo. Institution-authored reports remain self-reports. The proposed fit judgments belong to this research and are explicitly conditional.

Work record: [issue 16311](https://github.com/woahwhattheheck/commons/issues/16311). The existing peer-evidence compiler in [issue 16091](https://github.com/woahwhattheheck/commons/issues/16091) was exercised unchanged using the explicit curated mapping above. The original cohort CSV retains its own documented columns; no generic automatic conversion is claimed. Actual output: three comparisons with differing context and four authorization metrics needing context. Approximate headcounts remain text and unknown observation fields remain null.
