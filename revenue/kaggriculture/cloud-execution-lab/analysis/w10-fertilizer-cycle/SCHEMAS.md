# W10 machine-readable contracts

The W10 directory publishes four JSON Schema Draft 2020-12 documents:

- `trace.schema.json` — one control or fertilized observation trace;
- `certificate.schema.json` — one paired-trace certificate;
- `matrix.schema.json` — the explicit set of required seed/opponent pairs; and
- `matrix-result.schema.json` — the all-pairs admission result.

These schemas let a producer, recorder, review tool, or editor validate field names, primitive types, required fields, closed objects, identifier formats, array bounds, and output shapes without importing the Python checker.

## Structural validation is not certification

JSON Schema cannot express all W10 semantics. A structurally valid trace is only eligible to enter `realized_fertilizer.py`; it is not evidence by itself. The Python checker additionally enforces:

- fixed-order fail-closed validation;
- strictly increasing snapshot ticks;
- cumulative nondecreasing counters;
- an exact terminal horizon;
- carry, shed, and worker-budget bounds;
- action-accounting bounds;
- identical control/treatment identity and starting metrics;
- incremental `production -> harvest -> deposit -> sale` attribution;
- positive net cash inside the horizon;
- no added discard, protected-stock shortfall, or protected-obligation miss; and
- deterministic trace and certificate hashing.

Likewise, `matrix_runner.py` enforces unique pair IDs, unique trace paths, distinct comparison identities, resolved-path confinement, trace byte limits, all-required-pair evaluation, count reconciliation, and `ADMIT` only when every required pair certifies.

## Compatibility rule

The schema version is part of every document’s `schema` field. Producers must emit exactly the version they implement; consumers must fail closed on unknown versions. A schema update that changes required fields or semantics should receive a new schema URI and a new in-document version rather than silently broadening v1.

## Contract test

`test_schema_contract.py` locks the machine-readable documents to the runtime’s current field inventory and bounds. It also verifies closed roots, lowercase SHA-256 formats, exact decision enums, matrix path constraints, and complete result accounting.

Run it directly with:

```bash
python -m unittest -v \
  revenue/kaggriculture/cloud-execution-lab/analysis/w10-fertilizer-cycle/test_schema_contract.py
```

The path-scoped W10 matrix workflow discovers this test together with the certificate and matrix suites.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
