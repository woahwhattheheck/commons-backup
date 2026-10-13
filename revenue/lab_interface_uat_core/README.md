# Laboratory interface UAT evidence core

This package is a **buyer-neutral, synthetic interoperability test engine** for a
laboratory-interface acceptance workstream. It does not connect to Bluesquare,
ASLM, Africa CDC, DHIS2, a LIMS, an analyzer, or any production environment.

The engine binds an explicit versioned interface contract to synthetic source and
target laboratory records. It verifies deterministic code/unit mapping, exact
source-to-target field parity, event identity, revision/correction lineage,
idempotent retry behavior, and fail-closed handling for incomplete, conflicting,
unknown, or ambiguous evidence.

## Evidence contract

Each source event carries only synthetic identifiers plus an accession,
specimen type, test code, result value, unit, reference interval, result status,
site, revision, and correction predecessor. A target event must cite the exact
source event and the exact contract/mapping identity while preserving the
business fields required by the interface contract.

The engine:

- canonicalizes bounded JSON and rejects unknown fields;
- collapses exact retries but HOLDs a same-event-id changed payload;
- allows out-of-order arrival while requiring contiguous revision history;
- requires revision `n` to cite the exact revision `n-1` event;
- maps declared source test codes and units to target codes/units;
- quarantines unmapped codes/units and malformed/ambiguous values;
- detects missing and unexpected target records;
- detects any field-level source→target parity drift;
- emits a content-addressed PASS/HOLD receipt;
- verifies receipts by re-evaluating the bound evidence, not by trusting a
  self-hash.

## Validation

```bash
python -m unittest revenue.lab_interface_uat_core.test_engine -v
python -O -m unittest revenue.lab_interface_uat_core.test_engine -v
python -m revenue.lab_interface_uat_core.acceptance
```

The deterministic acceptance matrix executes 200 synthetic one-record interface
cases: 160 clean PASS and 40 deliberate HOLD cases covering missing target,
parity drift, same-ID conflict, broken correction lineage, and unmapped
terminology.

## Authority boundary

`AUTHORITY = INTERFACE_UAT_ONLY_NO_CLINICAL_OR_PRODUCTION_AUTHORITY`.

This code contains no real patient, specimen, or laboratory data. It makes no
diagnosis, clinical interpretation, reference-range judgment, release decision,
regulatory/compliance certification, or security certification. It does not
call a production LIMS/DHIS2/API, mutate a laboratory system, submit a proposal,
contact a buyer, or imply award/payment/revenue.
