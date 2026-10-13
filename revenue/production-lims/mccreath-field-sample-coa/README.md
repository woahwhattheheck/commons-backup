# McCreath field-sample-to-CoA reconciliation LIMS

Task: `mccreath-field-sample-coa-reconciliation-lims-01`

This bounded synthetic/read-only lane reconciles field inspection/sample/weight evidence,
shipment form/package identity, accession, one preparation split, ASTM/ISO method/version,
analytical result provenance, and a staged CoA. It does **not** write to a production LIMS,
contact a buyer/provider, make a compliance decision, or release a CoA automatically.

## Deterministic fixture

`fixtures/mccreath_100_jobs.json` contains exactly 100 synthetic jobs:

- 75 valid -> `READY`
- 10 -> `CUSTODY_WEIGHT_CONFLICT`
- 5 -> `DUPLICATE_CONTAINER`
- 5 -> `FORM_PACKAGE_MISMATCH`
- 5 -> `CONTRACT_SPEC_MISMATCH`

Fixture SHA-256: `b6d732ed06587b2cf14888909888b86bf0a0ab3ac87a637990d1efcc20772a10`

Every READY result carries an immutable golden identity over analyte, method/version,
value, unit, rounding rule, and synthetic source hash. The ledger requires exactly one
accession and one preparation split per READY job. Held jobs create neither.

## Run

```bash
python3 test_field_sample_coa.py
python3 field_sample_coa.py   --fixture fixtures/mccreath_100_jobs.json   --manifest fixtures/manifest.json   --verify
```

Acceptance requires 75 READY / 25 HOLD, exact hold-code counts, zero orphan splits or
duplicate accessions, result-identity hash equality, full 100-row replay with zero ledger
mutation, and all 75 CoAs remaining `STAGED_HUMAN_REVIEW` unless a non-empty named reviewer
and approval ID are explicitly supplied to `release_coa`.

PRE-SALE TRANSPORT: NONE.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
