# Evidence request prioritization

An operator-run answer to: **Which additional evidence requests cover the most
important open questions within our current collection-effort budget?**

This completes the missing implementation from #16187 / UIOWA-113. It uses
editable priority and effort assumptions, keeps every request visible, and
explains each selected request's additional question coverage. It performs no
network calls, collection, scheduling, assessment scoring or provider writes.
Python 3.10+ and the standard library are sufficient.

## Use the published register

From the repository root:

```sh
python3 revenue/uiowa_rfq_18649_evidence_requests/planner.py from-register \
  revenue/uiowa_rfq_18649_workshare/methodology/23-synthetic-evidence-register.csv \
  > /tmp/evidence-requests.json

python3 revenue/uiowa_rfq_18649_evidence_requests/planner.py worksheet-csv \
  /tmp/evidence-requests.json questions > /tmp/questions.csv

python3 revenue/uiowa_rfq_18649_evidence_requests/planner.py worksheet-csv \
  /tmp/evidence-requests.json requests > /tmp/requests.csv
```

Edit question priorities in `questions.csv` and collection effort in
`requests.csv`. Blank effort is unknown. An explicit `0` means an operator
actually assumes no collection time; it is never substituted for a blank.
`question_ids` is a JSON array inside a CSV cell, preserving exact IDs even if
they contain commas. CSV quoting and multiline titles are supported.

```sh
python3 revenue/uiowa_rfq_18649_evidence_requests/planner.py plan \
  /tmp/evidence-requests.json --questions-csv /tmp/questions.csv \
  --requests-csv /tmp/requests.csv --budgets 60,120,240 --format markdown
```

Use `--format json` for the complete source-linked plan, or `--format csv` for
selected-request rows across scenarios. All commands emit to stdout; redirect
to a destination of your choice. Errors use stderr and exit 2 before any result
is printed. A valid scenario with no selected requests exits 0 and explains why.

## Input and source preservation

The JSON worksheet has schema `uiowa.evidence-requests.v1`, `questions`, and
`requests`. Each question requires `question_id`, `question` and nonnegative
integer `priority`. Each request requires `request_id`, `title`, nullable
nonnegative integer `effort_minutes`, and an array of exact `question_ids`.
New questions or requests can be added in JSON. CSV overlays update existing
IDs; they reject unknown or duplicate IDs. Omitted overlay rows retain their
existing values. All unknown JSON fields and original CSV overlay rows remain
in the resulting worksheet.

The register importer consumes existing follow-up text rather than inferring
a maturity rating from confidence labels. It preserves every original register
byte as Base64 with its SHA-256, source path, headers and row count. Per-question
records retain the entire source row, evidence/finding IDs and logical CSV
record locators. Logical record 1 is the header; multiline cells do not alter
that numbering. Source claims are not rewritten.

Each nonempty follow-up creates one question and one request. An explicitly
declared `conflict_group` also creates a shared question, referenced by the
requests in that group. Thus the two IAM requests in the published source can
both address the same contradiction, while its priority is counted once.
Initial priorities are explicitly equal weights of 1, and every initial effort
is null. These are editable preparation defaults, not measurements.

The library entry points are `from_register(raw_bytes, source_path)`,
`worksheet_csv(packet, kind)`, `apply_csv(packet, raw_bytes, kind)` and
`plan(packet, budgets)`. They do not mutate input worksheets. The plan includes
the complete effective worksheet and a canonical SHA-256 so each result can
be traced to its actual assumptions and source generation.

## Selection behavior and limits

For each budget independently, select the request with the highest sum of
currently uncovered question priorities per estimated minute, among requests
that fit the remaining budget. Explicit zero-effort useful requests come first.
Exact rational comparison avoids floating-point ties; remaining ties use larger
new priority, lower effort, then request ID. After each choice, coverage and
marginal priorities are recomputed. A question contributes at most once.

This is a deterministic greedy heuristic, **not a globally optimal portfolio
claim**. Increasing a budget can change selection order or membership; scenarios
are independent. There are no probabilities, Bayesian updates, inferred truth,
dependencies, shared setup costs, calendar availability or parallel staffing.
Use the separate costed-work-batch calculator for its richer economic model.

The selected rows retain step, effort, newly covered question IDs, new priority
and cumulative totals. Unselected rows retain their remaining possible coverage
and one of `EFFORT_UNESTIMATED`, `NO_ADDITIONAL_PRIORITY`, or
`REMAINING_BUDGET`. Unknown effort is never treated as free. Selecting a request
does not resolve any question: the report keeps `collection_performed`,
`evidence_resolved` and `assessment_authority` false.

## Reproduce the worked preparation scenario

`worksheet.json` comes from the actual published 3,826-byte synthetic 023
register (Git blob `d479d976aee321f8d20905a53d9ddab94eebc4f6`). Original
methodology ownership and source statements remain with that component.
`worked-questions.csv` and `worked-requests.csv` add **illustrative operator
assumptions**, not actual collection estimates or University priorities. One
request deliberately remains unestimated.

```sh
python3 revenue/uiowa_rfq_18649_evidence_requests/planner.py plan \
  revenue/uiowa_rfq_18649_evidence_requests/worksheet.json \
  --questions-csv revenue/uiowa_rfq_18649_evidence_requests/worked-questions.csv \
  --requests-csv revenue/uiowa_rfq_18649_evidence_requests/worked-requests.csv \
  --budgets 60,120,240 --format markdown
```

The retained `worked-plan.json`, `worked-plan.csv` and `worked-plan.md` were
produced by these CLI calls on the actual source-derived worksheet:

| Budget minutes | Minutes selected | Distinct questions | Editable priority covered |
| ---: | ---: | ---: | ---: |
| 60 | 50 | 3 | 11 |
| 120 | 90 | 4 | 14 |
| 240 | 210 | 6 | 21 |

Both IAM requests appear in the 120-minute plan, but the shared contradiction
is credited only to the first. `EV-SYN-ESS-AI-INV-006` remains unestimated in
every scenario. The original baseline worksheet, without the CSV assumptions,
selects nothing and reports all seven requests as `EFFORT_UNESTIMATED`.

These are fictional preparation records and transparent planning assumptions.
Do not present their output as observed University findings, resolved evidence,
actual collection effort, a maturity score or a procurement commitment.
