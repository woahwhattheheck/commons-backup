# Kentucky enterprise financial reporting discovery

This folder is the internal response-and-product carrier for Commonwealth of Kentucky RFI 758 2700000006, Enterprise Financial Reporting Discovery.

## What is being built

The lane converts a one-time information request into reusable implementation evidence for financial-report modernization:

- legacy-report inventory and lineage mapping;
- exact old-versus-new report parity checks on synthetic retained fixtures;
- exception and migration-wave planning;
- architecture guidance for retaining Oracle as the financial data repository while modernizing reporting;
- security and Government Community Cloud dependency questions;
- a response matrix that separates demonstrated method from unsupported company or deployment claims;
- a future workshare package for discovery, migration acceptance, and cutover evidence.

The demonstrator is offline and synthetic. It does not connect to Kentucky, Oracle, SAP BusinessObjects, Microsoft services, payment systems, or accounting systems.

## Current source posture

As of October 4, the recorded response deadline has passed. The [dated source-reference update](SOURCE_REFERENCE_20261004.md) records the newly readable later-addendum/Q&A mirror and the unresolved official VSS rendering/byte-custody gap. This is a retrospective source update, not a reopened submission window. The reference map is unverified secondary material and does not change the helper's contract or authenticate response claims.

The following original schedule/environment summary is retained as historical context:

Public procurement material identifies the RFI as issued September 1, 2026 and closing October 2, 2026 at 3:30 PM Eastern. Addendum 1, dated September 16, moves the Commonwealth's response to vendor written questions to September 23.

The public RFI summary describes an on-premises Oracle/data-warehouse/SAP BusinessObjects 4.3 environment serving roughly 2,500 users and about 5,000 Web Intelligence documents. It asks respondents to address reporting capability, architecture, security, implementation, public-sector experience, estimated costs, and compatibility with Microsoft Government Community Cloud.

The RFI is discovery, not a quote or bid. No award, buyer acceptance, contract, or revenue is represented by this folder.

## Source hierarchy

1. Current Kentucky eProcurement / Vendor Self Service solicitation and addenda.
2. Current Kentucky Finance and Administration Cabinet procurement guidance.
3. Mirrored solicitation material only as research corroboration when exact VSS bytes are not yet retained.

Before any external response is considered ready, the current VSS generation and the September 23 question-response addendum must be reviewed.

## Internal state

Source/build work is authorized. External submission, signature, vendor-profile changes, buyer contact, and commercial commitments are not authorized by this carrier.

Coordination issue: #15835.

## Use the retained row-comparison helper

The generic comparison helper now has a standard-library command-line entrypoint
(Python 3.10+). From the repository root:

```sh
python3 -m revenue.ky_financial_reporting_discovery --demo --out /tmp/report-parity-demo
python3 -m revenue.ky_financial_reporting_discovery --input /path/to/sanitized-rows.json --out /path/to/new-report
```

`--demo` runs the original fictional row A/value 1 versus row A/value 2 example.
It emits one `VALUE_DRIFT`. For supplied data, use this input shape:

```json
{
  "schema": "report-row-parity/v1",
  "key_fields": ["id"],
  "compare_fields": ["value"],
  "legacy_rows": [{"id": "A", "value": 1}],
  "target_rows": [{"id": "A", "value": 2}]
}
```

JSON is printed to stdout. Optional `--out` writes `report.json`,
`findings.csv` and `report.md` to a **new** directory; it never replaces an
existing output directory. Prepare the parent directory first. All reports are
rendered before publication. Directory publication is not atomic: an I/O failure
can leave a partial directory, which must not be treated as a completed report.

Input is bounded to 16 MB and 5,000 rows per side. Supply 1–4 unique key fields
and 1–32 unique compared fields; every selected field must exist on every row.
Each row contains 1–64 fields. Keys are strings or integers, and retain their
types. Duplicate keys are errors, including repeated identical rows; the helper
no longer silently keeps only the last row. A boolean cannot stand in for an
integer key. Values may be strings, integers, booleans or null. Floating-point,
non-finite and nested values are rejected. Represent exact decimal amounts as
strings; comparison is literal, so `"1.0"` and `"1.00"` differ. No tolerance,
rounding, null imputation or type conversion is inferred.

Results distinguish `MISSING_TARGET_ROW`, `EXTRA_TARGET_ROW` and `VALUE_DRIFT`.
Value drift counts changed fields, not distinct rows. A successful comparison
exits 0, including when it finds differences; inspect `state` (`MATCH` or
`DIFFERENCES`) to use the result. Invalid input or failed publication exits 2
with `ERROR:` on stderr. Duplicate JSON keys and unknown top-level keys are
errors. Missing/extra row findings do not create field-level drift findings.

Exports retain supplied row keys and field names, so use sanitized inputs and
keep resulting reports private as appropriate. CSV keys and field names use
JSON cells to preserve types and avoid interpreting input as spreadsheet
formulas. The input digest binds exact file bytes, not source authenticity.
`MATCH` describes only supplied rows and selected fields; it does not establish
export completeness or migration, accounting, procurement or buyer acceptance.

This is an entrypoint for the existing generic probe, not the broader catalog,
migration-wave or live reporting platform described above. Original source and
product credit remains with Z-Sol and executable recovery with Z-Argent; this
continuation adds input handling, lossless key validation and report exports.
