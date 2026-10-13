# Development data-lifecycle evidence kit — UIOWA-059

**Offline assessment preparation. The supplied example is entirely fictional.**
This kit assesses records about data used in development and support. It does not
read the data itself, contact systems, delete copies, or determine legal compliance.
The ESS, RIS and IAM labels organize an exercise, not University findings.

## Run the complete example

Python 3.10 or later; standard library only. From the repository root:

```sh
python revenue/uiowa_rfq_18649_data_lifecycle/cli.py \
  revenue/uiowa_rfq_18649_data_lifecycle/example.json /tmp/lifecycle-059-report
```

The output directory must not exist, and its parent must exist. The CLI creates
`report.json`, `assessment.md`, and `follow-ups.csv`; it refuses to overwrite an
existing directory. Invalid packets exit 2 before creating output. An I/O failure
after directory creation may leave partial output; rerun to a new directory.

Use `template.json` to prepare a new metadata inventory. Set `assessment_id`, the
explicit UTC `as_of`, and `evidence_mode` deliberately. Retain `SYNTHETIC` for any
invented or mixed training collection. `SUPPLIED_METADATA_UNVERIFIED` means only
that a facilitator supplied the records; it does not authenticate their origin.
Never paste actual record values, personal identifiers, access tokens, secrets,
or raw diagnostic logs into this packet. Category labels and controlled record
locators are sufficient. A closed schema prevents extra payload fields, but the
kit is not a sensitive-data detector: the facilitator must inspect free text.

## Portable review page

Create a new standalone HTML file from the same strict packet, using only Python's
standard library. From the repository root:

```sh
python revenue/uiowa_rfq_18649_data_lifecycle/review_html.py \
  revenue/uiowa_rfq_18649_data_lifecycle/example.json \
  --output /tmp/lifecycle-059-review.html
```

Open that file directly in a browser; no server, network, assets or dependencies
are required. The parent directory must exist, and an existing output is never
overwritten. Invalid packets are rejected before output creation. An I/O failure
while writing may leave a partial file; use a new output path when retrying.

The page verifies the complete native assessment before rendering. It retains
all copies, applicable checks, observation/documentation timestamps and IDs,
findings, historical evidence and native digests. Search and group/disposition
filters select whole copy sections. Following a copy or evidence link restores
visibility if filters concealed its target. Downloads always contain the full
native `report.json` and `follow-ups.csv`, including the existing CSV formula
escaping. They are byte-identical to the original CLI outputs for the same packet.

All substantive content and downloads remain available with JavaScript disabled.
With JavaScript enabled, **Print full review** temporarily restores every copy and
opens all record sections, then restores the screen state after printing. Browser
Print also includes the complete review. The page uses no external resources and
escapes supplied strings; its fixed interaction script is hash-bound by a content
security policy. Source references remain literal text, not executable links.

This is an authored portable-view continuation, not a replacement assessment or
an authenticity/compliance/deletion claim. `render_html(packet, report)` refuses a
report that fails the existing `verify_report`. The HTML digest identifies the
presentation bytes; the native report digest still covers only the native report.
The original engine, CLI and three output formats retain their behavior.

## Files and outputs

- `lifecycle.py`: reusable validation, assessment, rendering and semantic verification.
- `cli.py`: local-file CLI; no network or provider client.
- `review_html.py`: verified standalone review page and create-exclusive HTML CLI.
- `schema.json`: structural JSON Schema; the Python validator additionally checks
  IDs, lineage, chronology, and other cross-record conditions.
- `template.json`: valid unknown-state catalog starter with no evidence.
- `example.json`: four-copy, fifteen-record synthetic assessment exercise.
- `interview_worksheet.md`: facilitator worksheet, lifecycle map, expected exercise
  observations, and proportionate improvement options.

The report preserves each original item and evidence record, stage-level evidence
IDs, separate documentation and observation timestamps, and suggested follow-ups.
CSV follows the same finding order and quotes spreadsheet-formula-leading text.
Markdown escapes supplied HTML and table/link syntax rather than executing it.

## Record contract

All packet values are strings, nulls, arrays or objects; JSON numeric values and
booleans have no accepted place in this schema. Duplicate keys, unknown fields,
invalid UTC dates, controls and invalid Unicode are rejected. Raw input is limited
to 2 MB, with at most 200 inventory items and 4,000 evidence records. Free text is
limited to 1,000 characters; identifiers to 80 simple letters/digits/dots/dashes/
underscores, beginning with a letter or digit.

Top-level fields are exactly `schema`, `assessment_id`, `as_of`, `evidence_mode`,
`items` and `evidence`. Schema is `uiowa.data-lifecycle/v1`. Timestamps use
ASCII digits in `YYYY-MM-DDTHH:MM:SSZ`; timezone offsets, non-ASCII digits and
date-only strings are not accepted. Canonical UTC strings preserve chronological
order when the evaluator selects the latest supplied observation.

### Each inventory item

| Field | Meaning |
|---|---|
| `id` | Stable identifier for **one separately retained copy**. |
| `group` | ESS, RIS or IAM exercise group. |
| `use_case` | TEST_DATA, DIAGNOSTIC_EXPORT or TROUBLESHOOTING_COPY. |
| `parent_id` | Source-copy ID, or null for a root/independently inventoried source. |
| `created_at` | Recorded creation time, no later than assessment `as_of`. |
| `owner` | Accountable organizational role, or null when not recorded. |
| `purpose` | Specific development/support purpose, or null when not recorded. |
| `classification` | PUBLIC, INTERNAL, SENSITIVE or UNKNOWN; an assessor label. |
| `location` | Controlled metadata locator, not credentials or a data export. |
| `retained_categories` | One to forty unique category labels, **not actual values**. |
| `retention_due_at` | Recorded review/disposition date, or null when unresolved. |

Copies cannot predate their sources, refer to absent parents or form cycles.
An item can legitimately have its own retention rationale after its source is
removed. Source disposal never disposes of another inventory item implicitly.

### Each evidence record

Fields are exactly `id`, `item_id`, `stage`, `basis`, `outcome`, `at`, `reference`,
`recorded_by` and `statement`. IDs must be unique. `item_id` must name an existing
copy. `at` lies between that copy's creation and the assessment instant.

Stages: classification, minimization, transfer, retention, disposal,
disposal_verification. Transfer evidence names the **destination copy**, not the
source; that copy must have a `parent_id`. Basis is DOCUMENTED or OBSERVED.
Outcome is SUPPORTED, GAP or UNKNOWN. These are facilitator-entered labels about
the supplied record, **not machine-certified truth**. `reference` locates the
controlled supporting record; `recorded_by` names a role; `statement` gives a
brief metadata-only account of what it establishes and its limits.

## Evidence interpretation

The latest observed timestamp determines a stage's effective observation. Equal
time, equal outcome records reinforce the same classification; different outcomes
at the same latest timestamp produce CONTRADICTORY. A later observation can
resolve an earlier conflict; all older IDs remain retained. A later UNKNOWN
observation cannot silently reuse an earlier success. Documentation is evaluated
separately and retained even when an observation exists. Documentation alone is
DOCUMENTED_ONLY or DOCUMENTED_GAP, never OBSERVED_SUPPORTED. Missing evidence is
UNKNOWN, not proof that the practice does not exist.

Classification, minimization and retention are always considered. Transfer is
considered for derived copies. Disposal and disposal verification are considered
when the supplied date has arrived or disposal-stage evidence exists. Coverage
counts describe these applicable evidence checks, **not maturity or risk scores**.
No automatic evidence-age threshold is invented; timestamps remain visible and
interviewers must assess whether a record represents current practice.

Disposal is supported only by a supported observed disposal record **and** a
supported observed verification record for that same copy, with verification at
or after the disposal timestamp. The state is deliberately named
`SUPPLIED_RECORDS_SUPPORT_DISPOSAL`, not a claim of actual deletion. A premature
verification is contradictory. An unresolved current disposal observation leaves
verification UNKNOWN rather than claiming that no earlier supporting disposal
record exists; the complete history is retained. Expiry without verified
disposition is a follow-up question, not a compliance violation: the date may
represent review, an exception may exist, and operational dependencies may justify
separate retention.

## Synthetic expected results

The fixture includes:

1. ESS source: observed classification/minimization/retention and a coherent
   disposal/verification pair.
2. ESS troubleshooting copy: the source's disposal does not cover the copy;
   ownership, date and transfer evidence remain unresolved, while a supplied
   observation identifies a minimization gap.
3. RIS diagnostic export: missing purpose/owner/date, unresolved classification,
   a written classification record, and contradictory minimization observations.
4. IAM diagnostic: disposal is reported, but its verification predates disposal,
   so it remains unverified and needs reconciliation.

Run the CLI for exact counts and machine-readable finding identifiers. This is a
teaching exercise; do not convert these invented outcomes into actual ESS/RIS/IAM
findings or an engagement-completion claim.

## Reproducibility and trust boundary

`assess(packet)` produces a deterministic report. Item order, evidence order and
category order do not change its semantic input digest. The report retains all
records in canonical identifier order. `report_sha256` hashes the report excluding
that digest field. `verify_report(packet, report)` independently recomputes the
entire report; updating hashes cannot rescue changed assessment semantics.

These hashes detect changes relative to supplied records. They do not establish
source authenticity, completeness, independent observation, currentness beyond the
selected instant, or resistance to malicious code inside the Python process.
Renderers accept a report object: use the assessor or verifier before presenting
an externally supplied report. Effort ranges are illustrative **team-day planning
assumptions**, not quotes, measured work, staffing commitments or report conclusions.

## Integration and attribution

Work order UIOWA-059; original operation `uiowa-059-oriel27-20260919` and
implementation by ZZ-ORIEL-27, retained in PR #16231 at
`85e86e534442916313a544d12ce5f71619e12ff0`. Recovery operation
`uiowa-059-recovery-yz-larch47-20260923` repairs chronology and diagnostic wording
and brings the usable component to main. The original test module remains in the
retained donor rather than being copied into this recovery. No new tests or CI.

This directory is independent of fixture-quality, component-maintenance,
service-identity, workbench and report-compiler work. The packet/report can be
consumed explicitly by a future integration; no automatic integration or new
workflow is claimed. No live execution, background polling, customer contact,
scheduling, vendor recommendation, payment or revenue action.
