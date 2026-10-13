# UIOWA-047 — Test-data readiness and maintenance

Offline, synthetic-only assessment kit for University of Iowa RFQ 18649 preparation.

The kit evaluates supplied evidence about accountable ownership, refresh timing,
interface/schema alignment, documented boundary-case coverage, cleanup/retirement,
retention rules and data origin/handling references. It does not inspect live
systems, ingest University data, determine regulatory compliance or convert
missing records into defects.

## Evidence states

**EVIDENCED** means the supplied record contains evidence for the particular check.
**OBSERVED_GAP** means supplied evidence conflicts with its own documented
expectation, such as a stale fixture against its declared cadence or a fixture
interface version that differs from the recorded current version. **UNKNOWN**
means evidence is absent or insufficient; it is not a failure or an implicit pass.

Cleanup applicability requires an explicit declaration. `cleanup_required: false`
records that cleanup is not required. `true` requires a usable verification date
on or before the assessment date. An omitted, null or non-boolean flag remains
UNKNOWN, including when a verification date is present. See
[evidence interpretation](EVIDENCE_SEMANTICS.md) for chronology and inventory rules.
These are evidence states, not regulatory or operational verdicts.

## Files and entry points

- `test_data_assessor.py` is the production CLI/library, despite its `test_` prefix.
- `catalog_from_csv.py` converts the editable `catalog_template.csv` to typed JSON.
- `schema/catalog.schema.json` describes the catalog's field contract.
- `fixtures/catalog.synthetic.json` and `synthetic_rehearsal.md` supply the original fictional ESS/RIS/IAM demonstration and its interpretation.
- `fixture_specifications.md`, `refresh_lifecycle.md` and `interview_guide.md` support discovery and evidence collection.

## Run

From this directory:

```sh
python3 test_data_assessor.py fixtures/catalog.synthetic.json
python3 test_data_assessor.py fixtures/catalog.synthetic.json --format json --output report.json
```

The default output is Markdown; JSON preserves the same checks and evidence states
for report tooling. A report writer should use the result as a question/evidence
organizer, not as an automatic University finding. Any actual finding still
requires source citations, service context and reviewer judgment.

Start from an edited copy of the CSV with a new JSON destination:

```sh
python3 catalog_from_csv.py catalog_template.csv --as-of 2026-09-19 --label 'Synthetic starter' --output catalog.new.json
python3 test_data_assessor.py catalog.new.json
```

[CSV intake](CSV_INTAKE.md) describes the exact format, source retention and
create-new-only save behavior. Blank evidence stays distinct from `[]`, false
and zero. The original starter and assessment semantics are unchanged.

## Catalog input boundaries

The JSON catalog must be an object with an exact `YYYY-MM-DD` `as_of` date and a
`datasets` array of objects. A malformed row is named by its zero-based index,
not silently dropped. An empty array is supported. Missing optional evidence in
a valid object remains UNKNOWN; these checks are not full JSON Schema enforcement.

Date fields do not accept timestamps, week dates or trailing text. An unusable
optional refresh or cleanup-verification date remains UNKNOWN; an unusable
required `as_of` rejects the catalog. Boolean values do not stand in for integer
day counts: a boolean cadence is unknown and a boolean retention duration follows
the invalid-supplied-value check. Actual integer zero-day retention is valid.

Input read/decoding errors and rejected catalog structures or required dates
produce a readable CLI diagnostic and exit 2 before a report is emitted or an
existing report is changed. The library raises `ValueError` for malformed catalog
structure. Exit 0 means a report was generated, not that all checks were evidenced.

## Preserve catalog and report files

The assessor's `--output` refuses source-catalog aliases and symbolic-link outputs.
It stages a new report before replacing a distinct regular report, so a staging
or encoding failure does not truncate the previous report. See
[report preservation](OUTPUT_PRESERVATION.md) for compatibility and filesystem
limits. The CSV importer has its separate create-new-only contract.

## Original three-service demonstration

ESS-REGISTRATION-BOUNDARIES is current, owned, aligned and complete for its
recorded boundary set. RIS-AWARD-SYNC is intentionally stale, on an older
interface version and missing two documented boundary cases. IAM-ROLE-TRANSITION
has aligned interfaces but unknown ownership, refresh, cleanup-verification and
retention evidence; its explicitly omitted required cases are an OBSERVED_GAP.

The demonstration shows evidenced mismatches and missing evidence without real
student, research or identity data. It remains the named deliverable from
[the original kit](https://github.com/woahwhattheheck/commons/pull/16122), not a
retained automated test suite.

## Assessment use and public-repository boundary

For each dataset, establish its purpose and service boundary; record the role
accountable for maintenance; capture evidence-backed refresh triggers and dates;
bind the fixture to its interface/schema version; document relevant boundary
cases; and record cleanup, retention, origin and handling context. Do not copy
sensitive values into this public repository.

All checked-in examples are fictional. Do not commit private University artifacts,
production-derived records, credentials, student/research/identity data or
proprietary source extracts here.
