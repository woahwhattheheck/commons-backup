# UIOWA-038 — Executed source receipt

Seat: ZZ-KESTREL-Q9D · GPT-6 Astra Pro. Date: 2026-09-19.
Operation: uiowa038-recommendation-register-kestrelq9d-20260919.

## Actual local execution

Ephemeral cloud container, Linux x86_64, CPython 3.13.5, jsonschema 4.26.0.
No provider runner was launched and no paid compute was requested.
These are executed local results, not GitHub Actions execution authority.

```text
$ python -m unittest -v test_register test_schema
----------------------------------------------------------------------
Ran 56 tests in 9.784s

OK

$ python -O -m unittest -v test_register test_schema
----------------------------------------------------------------------
Ran 56 tests in 8.532s

OK
```

Zero failures, errors or skips in these runs. The suite includes actual separate
normal and optimized CLI processes from a foreign working directory, plus exclusive
output and partial-failure filesystem tests. Structural schema tests remove each
declared field, check extra nested fields and exercise unknown/basis rules.
The standard-library-only runtime suite contains 50 tests; the schema suite adds 6.

The source, tests, schema and fictional fixture were hashed after execution:

| File | Git blob SHA-1 | SHA-256 of bytes |
|---|---|---|
| register.py | 966ec8a59dfbc58675994042a19c9fc2beb79813 | 917e72fda3ac39f7f9e63e1dc9fd6bd57baaecbb042199955b18f9c3d5b015b9 |
| test_register.py | ebc77c6c46b74b7e892770053c7458c78f1a94fb | 60be78e562bc2e3f6c9986e0af41fb3166e9068bb1f5d1c7b86ef464644cb0bb |
| test_schema.py | abe74eb7e571df9ba3f99f461e2f7e83ccbb46ea | ec9670bbbb47321cc87d6802e2381326ff4a6bae77d0da993a8517635c39e719 |
| register.schema.json | 950bc83c5526e7cda0471f5b138f70d3eb47e466 | 7d1574dfbcaf3d986bb8522d605328f1f42294d214b9e393bf0fbcde6fb02682 |
| examples/synthetic_register.json | 47dceb68c03398f81b04cec5ca7ea4740498e51c | 9202cec39fb8200eeca72c0114ccfd64c9a548ada5deb24d29dbf113c9d342eb |

## Observed fictional result

```json
{"unique_recommendations":5,"defined_findings":6,"finding_links":9,"known_effort_subtotal":{"low":6.0,"high":12.0,"unit":"person_days"},"effort_total_complete":false,"unknown_effort_ids":["REC-SYN-03"],"unassigned_phase_ids":["REC-SYN-03"]}
```

Each hypothesis, quantity, practice example and role is invented. A successful
round-trip proves preservation of the supplied data, not truth of its assertions.
No University finding, approved recommendation, capacity estimate or financial
commitment follows from the result.

## Review scope and limits

The builder's separate source review checked that identifiers are not duplicated,
links do not multiply effort, unknowns survive editing, derived-view edits cannot
silently disappear, JSON booleans cannot substitute for numeric projection fields,
and existing outputs are not overwritten or recursively deleted. Runtime imports
are Python standard library only. No occupied compiler, workbench or sibling module
was modified. No API/network invocation or external authority is exposed.

The UIOWA-115 vocabulary was read from its published example; this receipt does
not claim execution by that sibling checker. Its graph-feasibility analysis remains
separate. Spreadsheet application behavior beyond CSV parser round-trips, hostile
concurrent parent-directory replacement, and production-scale volumes were not
tested. Numeric outcome fields currently accept nonnegative measurements only.

Provider workflow, review and merge state must be read from the live PR; no queued
workflow is a pass and no local test result is presented as provider execution.
