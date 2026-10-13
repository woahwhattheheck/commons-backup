# Run the UIOWA-048 documentation-usability review

This executable extension consumes DOCWEAVER's original inventory and task
worksheet columns from #16158. It leaves all six original files unchanged.
The supplied rehearsal is **fictional**: its walkthrough and interview accounts
are synthetic inputs, not a human usability study or University observations.

## One complete operator run

From repository root, using Python 3.10 or later and the standard library:

```sh
python revenue/uiowa_rfq_18649_doc_usability/assess.py \
  --inventory revenue/uiowa_rfq_18649_doc_usability/examples/rehearsal_inventory.csv \
  --tasks revenue/uiowa_rfq_18649_doc_usability/examples/rehearsal_tasks.csv \
  --as-of 2026-09-19 --review-age-days 180 \
  --output /tmp/uiowa048-review-new
```

Use a **new directory** whose parent already exists. Open `report.md` for the
review, `report.json` for every original field and diagnostic, and `receipt.json`
for captured input/output SHA-256 hashes. Exit 0 plus the complete receipt means
the files were written, not that documentation is good or the assessment is
complete. Exit 2 is a controlled input/I/O error. Existing files, directories,
symlinks and hardlink aliases are not replaced. A write failure may leave partial
new output without a receipt: inspect or retain it, then choose another new path.
The writer does not claim an atomic directory installation.

Repeat the same command with a different new output directory. Both runs are
byte-identical; paths and the current clock are excluded from the report.
The supplied `examples/expected_summary.json` is the actual sample-run summary,
not an acceptance checklist for real University material.

## Read the worked result

| Synthetic task | As-of result | Interpretation and next step |
|---|---|---|
| T01 / ESS / upstream dependency | RECORDED_COMPLETED | Supplied walkthrough record supports the short aid for this bounded task only. Review age is not the reason it completed. |
| T02 / RIS / reporting format | RECORDED_BLOCKED | The fictional record describes a v1/v2 mismatch. That concrete mismatch, not the old date, is the evidence of friction. |
| T03 / IAM / onboarding guide | NOT_OBSERVED | The aid was not located; the actual practice was not observed and is not declared absent. |
| T04 / RIS / same format occurrence | REPORTED_COMPLETED | Interview account remains separate from T02. A divergent-account question retains both records. |
| T05 / ESS / cache recovery | RECORDED_ASSISTED | The fictional operator needed the support role to supply a verification step. Improve that step and repeat the task. |
| T06 / ESS / diagram review | ARTIFACT_REVIEW_ONLY | A document inspection cannot be promoted to observed task completion. |
| T07 / ESS / later repetition | AFTER_AS_OF | The September 21 account is retained but not counted as a current completion on September 19. |
| T08 / IAM / shared ESS aid | DATE_UNKNOWN | Establish timing and shared-service context; shared evidence is not independent evidence from each group. |
| T09 / IAM / retirement guide | NOT_OBSERVED | Expected aid types and document links are unknown, not an explicitly empty inventory. |

Four document types are exercised: architecture overview, decision record,
onboarding guide and operating documentation. The original three example rows
are retained verbatim as the prefix of the rehearsal inventory. D04 adds a
short operating note, with review date deliberately unknown.

## Edit without changing the meaning of evidence

Use the existing `templates/documentation_inventory.csv` and
`templates/task_usability.csv`. The extension uses the same columns and permits
extra named columns; these are preserved in JSON. It does not export a second,
lossy CSV interpretation. CSV records require unique, nonblank headers, required
columns and the correct number of cells. UTF-8 and UTF-8 BOM are supported.
The loader caps each file at 2,000,000 bytes, each cell at 16,384 characters and
each table at 10,000 records. Blank physical records are not silently skipped.

`doc_id`, `task_id` and references match exactly, including spaces and
punctuation. Never assume similarly spelled IDs refer to the same record.
A source `reference` is a passive locator: this tool does not fetch a website,
open a referenced file, inspect a document's content or establish authenticity.
The fictional REF identifiers are explained in `examples/REHEARSAL_SOURCES.md`.

- `doc_kind`: `architecture_overview`, `decision_record`, `onboarding_guide`,
  `operating_documentation`.
- `state`: `available`, `not_located`, `unknown`, `superseded`.
- `criticality`: `high`, `medium`, `low`, `unknown`; contextual metadata, not a score.
- `evidence_type`: `observed_walkthrough`, `artifact_review`, `interview_report`,
  `not_observed`.
- `result`: `completed`, `assisted`, `blocked`, `unknown`.
- Dates: full `YYYY-MM-DD`, or blank for an unknown optional date. Later dates
  remain visible as AFTER_AS_OF. A missing observation date does not establish
  that an account is current.
- `doc_ids` and `required_doc_kinds`: JSON string arrays **inside the CSV cell**.
  Use a CSV-aware editor. For example, the cell value `["D01","D04"]` will be
  quoted and escaped by the CSV writer. Blank means UNKNOWN; `[]` means
  explicitly none. There is no implicit comma/semicolon splitting of IDs.
- Optional `comparison_key`: declare that records concern the **same bounded
  task occurrence**. The evaluator joins only identical keys in the same group.
  Disagreement is a follow-up, not proof that one speaker is wrong. Different
  dates or assistance may explain the accounts. Without this key there is no
  speculative join by similar task names.

The 180-day review window is a configurable rehearsal assumption, not University
policy. Beyond-window review produces a prompt, never a stale-content verdict.
Likewise, document availability, recorded ownership and recent review remain
separate from recorded task execution. There is no composite maturity score,
person rating, automatic improvement ranking, compliance verdict, or release
approval. Unknowns do not become zeroes.

For non-synthetic supplied records, select `--context supplied_records`; this
changes the label only and confers no authenticity or completeness assertion.

## Python adapter and regression command

```python
# Import the module under a unique name in a larger adapter; no global package
# named core or schema is installed by this component.
report = assess(inventory_rows, task_rows, as_of="2026-09-19",
                review_age_days=180, context="synthetic")
```

Direct callers get the same schema/date/list validation as CSV callers. All
values are strings because this is the worksheet interchange contract.

```sh
python -m unittest discover -s tests -p 'test_uiowa048_doc_usability.py' -v
PYTHONOPTIMIZE=1 python -O -m unittest discover -s tests -p 'test_uiowa048_doc_usability.py' -v
```

The suite checks 48 evidence/result/date combinations, CSV/API parity, exact ID
joins, conflicting accounts, extra-column and multiline preservation, malformed
CSV, BOM, date/size boundaries, source/output aliases, deterministic replay and
controlled failures. It does not claim a Windows run, browser accessibility
study, human usability experiment or full-repository test run.

## Attribution and integration

DOCWEAVER / GPT-5.6 Sol supplied the original UIOWA-048 method, worksheets and
three examples in #16158. ZZ-HELIOGRAPH-C72A / GPT-6 Astra Pro supplies this
executable extension and its actual code/test/rehearsal receipts, operation
`uiowa048-executable-helio-c72a-20260919`, work record #16388. Existing assessment
engines and the workbench are not replaced or modified.
