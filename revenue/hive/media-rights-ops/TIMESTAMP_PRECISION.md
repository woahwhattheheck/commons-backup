# Timestamp precision and consistency contract

The Content Rights & Usage-Window Operations Desk supports exact offset-aware timestamps through **microsecond precision** while preserving the existing whole-second canonical representation. This completes the broader temporal/read-consistency work requested in #15965 while retaining Z-Kestrel-Rights-7P9's #15973 parser hardening and the original product/export-custody lineage.

## Representable timestamps

`parse_time` / `norm_time` accept whole seconds and supplied fractional **seconds** with one through six digits. Values normalize to UTC. Whole seconds remain `YYYY-MM-DDTHH:MM:SSZ`; nonzero microseconds use six canonical digits.

Examples:

| Supplied value | Canonical result |
| --- | --- |
| `2026-09-18T12:00:00Z` | `2026-09-18T12:00:00Z` |
| `2026-09-18T14:00:00.1+02:00` | `2026-09-18T12:00:00.100000Z` |
| `2026-09-18T12:00:00.123456Z` | `2026-09-18T12:00:00.123456Z` |
| `2026-09-18T12:00:00.000000000Z` | `2026-09-18T12:00:00Z` |
| `2026-09-18.123456Z` | `2026-09-18T12:34:56Z` (dot is the ISO date/time separator) |
| `2026-09-18T12:00:00.1234567Z` | `RightsError` |
| `2026W38112.0000001+00:00` | `RightsError` |
| `2026-09-18T12:00:00+00:00:00.1` | `RightsError` |

The parser inspects the original fractional digits, not only the `datetime` result. This matters because CPython accepts some forms while silently discarding excess or offset precision. A dot/comma is exempted as a date/time separator only when the prefix is a complete ISO date, preserving the compact-week-date hostile found during #15973 review.

Fractional UTC-offset components are intentionally unsupported: they fail closed rather than expanding the stored-input contract. UTC normalization outside years 1..9999 remains a product-domain `RightsError`.

## Queue ordering

Persisted timestamps are canonical strings, but lexical ordering is not chronological when whole-second and fractional forms are mixed: `...00Z` and `...00.500000Z` place `Z` and `.` differently in text order. Retraction eligibility therefore no longer uses a SQL text comparison. The shared queue projector loads the candidate rows and compares `ends_at` and `revoked_at` as parsed instants.

Standalone `queues()` and exported `queues.json` use that same projector, so they cannot disagree merely because one path retained the old text predicate.

## Read generations

`evaluate()`, `queues()`, and `snapshot()` each hold one SQLite read transaction across their complete public projection. Under WAL, a supported concurrent writer may commit while that read is in progress, but the reader remains on one database generation instead of splicing pre-write and post-write rows.

The export path retains its existing stronger `BEGIN IMMEDIATE` connection guard and descriptor-relative filesystem publication/custody logic. Only its queue semantics delegate to the shared parsed-instant projector.

## Historical data and compatibility

Whole-second input, hashes, request replay, fixed fixture snapshot identity, and export semantics remain compatible. Existing historical receipts are never rewritten. If an older version discarded fractional digits before hashing or storage, those missing digits cannot be recovered from the ledger; any corrected record must come from separately confirmed original evidence.

## Validation

From this directory:

```sh
python -m unittest -q \
  test_rights_ops.py test_export_generation.py test_export_custody.py \
  test_timestamp_precision.py test_temporal_completion.py
python -O -m unittest -q \
  test_rights_ops.py test_export_generation.py test_export_custody.py \
  test_timestamp_precision.py test_temporal_completion.py
python -m py_compile rights_model.py rights_store.py rights_export.py rights_ops.py rights_http.py operator_rehearsal.py
```

The focused temporal tests include exact microsecond normalization, seventh-digit/compact-week rejection, fractional-offset refusal, replay identity, parsed retraction boundaries, and real two-connection WAL interleavings for both snapshot and queue readers. `operator_rehearsal.py` supplies the separate end-to-end CLI/readback exercise.
