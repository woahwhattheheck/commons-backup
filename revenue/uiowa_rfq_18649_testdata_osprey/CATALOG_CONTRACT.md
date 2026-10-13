# Catalog and bundle contract

The executable contract is `validate_catalog` in `fixture_lab.py`. This document
explains the contract rather than introducing a second independent validator.
Unrecognized fields and missing required fields are errors. Nullable fields
must be present with `null` when the information is unknown; omission is not a
substitute for an explicit unknown.

## Catalog root

| Field | Type and meaning |
|---|---|
| `schema` | Exactly `tjlabs.testdata.catalog.v1`. |
| `catalog_id` | Stable ID: starts with an ASCII letter, followed by letters, digits, `_`, or `-`; at most 80 characters. |
| `synthetic` | Literal JSON `true`; neither `1` nor the string `"true"`. This is a declaration, not a detector of real personal data. |
| `fixtures` | Array with 0–1,000 definitions; IDs unique across the catalog. An empty catalog reports `NOT_ASSESSED`. |

Input files and the canonical catalog are limited to 8 MiB. Parsed JSON nesting
is limited to 64 container levels. JSON must be valid
UTF-8, with no duplicate keys, non-finite numbers, or unpaired surrogate text.
Whitespace and original JSON-key order are not retained in canonical output.

## Required definition fields

| Field | Type | Interpretation |
|---|---|---|
| `id` | Stable ID | Logical fixture identifier; becomes the generated filename and prefix of each case ID. |
| `group` | `ESS`, `RIS`, or `IAM` | Fictional assessment context, not an organizational finding. |
| `service` | Nonempty string | Fictional service or behavior being represented. |
| `version` | Nonempty string | Author-assigned fixture-definition version; not automatically incremented. |
| `generator` | `term_window`, `funding_window`, or `role_transition` | Reference generator; the generator's own version is separate. |
| `purpose` | Nonempty string | Why the definition exists and what it is intended to exercise. |
| `owner_role` | Nonempty string or `null` | Proposed/recorded maintenance role; never a staffing commitment. |
| `last_refreshed` | `YYYY-MM-DD` or `null` | Recorded completion date, not a scheduled date. |
| `review_interval_days` | Integer 0–36,500 | Caller-supplied review assumption, not a policy recommendation. |
| `source_interface_version` | Nonempty string | Interface revision used to prepare the fixture. |
| `target_interface_version` | Nonempty string or `null` | Revision being considered in this assessment. |
| `required_boundaries` | Nonempty array | Unique names from `before`, `at_start`, `inside`, `at_end`, `after`. Order in this list does not reorder generated cases. |
| `maintenance_hours` | `{low, high}` or `null` | Proposed total maintenance effort range; integer hours 0–10,000, low ≤ high. |
| `retired_on` | `YYYY-MM-DD` or `null` | Effective retirement date for this definition; future dates do not make it retired at an earlier cut-off. |
| `cleanup_after_days` | Integer 0–36,500 | Caller-supplied interval following retirement. |
| `cleanup_evidence` | Nonempty string or `null` | Supplied cleanup or retention-disposition pointer; contents are not verified. |
| `refresh_evidence` | Nonempty string or `null` | Supplied completed-refresh pointer; contents are not verified. |
| `parameters` | `{start, end}` | ISO timestamps with explicit UTC offsets; start must precede end. |

Non-ID free-text fields are limited to 2,000 characters. An empty string is not
an unknown. Boolean values are rejected where an integer is required. A refresh
date after retirement is inconsistent with this version's lifecycle and is
rejected; represent a revived definition as a new version instead.

Timestamps are normalized to UTC. The generator works at Python datetime's
microsecond precision. An `inside` case requires a representable interior
instant; a one-microsecond interval may be used only without `inside`. `before`
and `after` must remain within the supported datetime range. Named-zone/DST
policy is not inferred from an offset.

## Maintenance findings

| Code | State | Meaning and next evidence |
|---|---|---|
| `OWNER_UNKNOWN` | unknown | Identify who maintains, reviews, and retires the fixture. |
| `TARGET_VERSION_UNKNOWN` | unknown | Establish the target interface revision. |
| `INTERFACE_REVIEW_REQUIRED` | follow_up | Compare interface semantics; a label difference alone proves nothing about breakage. |
| `REFRESH_DATE_UNKNOWN` | unknown | Obtain an actual completed-refresh record. |
| `FUTURE_REFRESH_RECORD` | inconsistent | Reconcile the date with the explicit assessment cut-off. |
| `REVIEW_OVERDUE` | follow_up | For an active fixture, age exceeds the supplied review interval. Review may justify no change. |
| `REFRESH_EVIDENCE_UNKNOWN` | unknown | A date alone does not provide the refresh evidence. |
| `EFFORT_UNKNOWN` | unknown | Estimate creation/refresh/checking/cleanup effort and assumptions. |
| `CLEANUP_UNVERIFIED` | unknown or follow_up | Retired fixture lacks a disposition pointer. Becomes follow_up when days since retirement exceed the interval. |
| `CLEANUP_RECORD_WITHOUT_EFFECTIVE_RETIREMENT` | inconsistent | Explain a cleanup pointer on an active definition or model a separate retired version. |
| `BOUNDARY_PLAN_PARTIAL` | follow_up | Explain omitted temporal boundaries and the remaining testing limitation. |

These are metadata diagnoses, not vulnerability findings, employee ratings,
application test failures, or maturity scores. Supplying a pointer resolves a
missing-pointer condition only; it does not demonstrate the referenced event.

## Version and byte identity

`version` identifies the fixture definition by the author's convention.
`definition_sha256` binds its exact canonical content. `generator_version`
identifies the reference implementation contract. `catalog_sha256` binds the
catalog used for the assessment; bundle catalogs are sorted by fixture ID.
Changing array order in an input catalog does not change a generated bundle.

A consumer should retain all of the following when relating an actual test run
to these inputs: fixture ID and version, definition digest, case ID, generator
version, bundle manifest digest, application revision, target environment,
actual observation, and run-evidence location. The current tool intentionally
does not fill the last four items.

## Bundle layout

```text
manifest.json
catalog.json
review.json
fixtures/
  ESS-TERM.json
  ...one member per fixture ID...
```

The manifest enumerates every member except itself, with its size and SHA-256.
The verifier's returned `manifest_sha256` identifies the manifest bytes. No
self-referential hash is implied. Additional files, missing files, unsupported
versions, noncanonical paths, duplicate paths, member symlinks, and
non-reproducible bytes are rejected. The verifier does not contact a provider,
resolve evidence links, or assert that the supplied catalog is authoritative.
