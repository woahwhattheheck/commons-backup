# InfiniteCAL cross-state method parity (synthetic shadow)

Task: `infinitecal-crossstate-method-parity-lims-01`

This is a deterministic, read-only synthetic parity bridge for comparing California, Michigan, and New York method/rule-pack outputs without overwriting any source system. It is an internal build-and-verify artifact, not a compliance engine and not a state-system integration.

## Frozen acceptance

- 180 synthetic records: 60 per state, each state covering the same 20 blinded materials and three analytes per material.
- Exactly 150 `PARITY_CLEAN`.
- Exactly 12 `METHOD_VERSION_MISMATCH`.
- Exactly 9 `UNIT_ROUNDING_MISMATCH`.
- Exactly 6 `DUPLICATE_ACCESSION`.
- Exactly 3 `MISSING_SOURCE_FILE`.
- Zero cross-state sample swaps.
- Clean records retain canonical analyte/unit/LOQ hashes and immutable result hashes while preserving state rule-pack and method lineage.
- Replaying the full fixture against the same ledger adds zero processed records, accepted accessions, holds, events, or drafts.
- Clean output is only `STAGED_HUMAN_REVIEW`; release requires a non-empty named human reviewer.

## Boundaries

The fixture is synthetic. The adapter writes to no California, Michigan, New York, Tagleaf, LIMS, instrument, customer, or reporting system. It makes no compliance decision and performs no outreach, prospect demo, automated CoA/result release, payment, or spend action.

## Run

```bash
python3 revenue/production-lims/infinitecal-crossstate-method-parity/infinitecal_parity.py
python3 -m unittest revenue/production-lims/infinitecal-crossstate-method-parity/test_infinitecal_parity.py -v
```

The module validates the fixture SHA-256 from `fixtures/manifest.json` before processing.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
