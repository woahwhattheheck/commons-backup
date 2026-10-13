# New Bloom multi-state beverage CoA provenance shadow

This package implements the frozen synthetic acceptance contract for `newbloom-multistate-beverage-coa-lims-01` as a **read-only provenance and draft-staging shadow**. It does not declare regulatory compliance and it does not write to a state system, customer system, provider, production LIMS, or delivery channel.

The immutable fixture expands to 96 deidentified synthetic beverage batches, 12 per configured synthetic state pack. Exactly 72 batches stage one human-review packet each; exactly 24 HOLD with the contract truth set: 8 missing pH/storage metadata, 8 rule-pack version mismatches, 4 duplicate batch IDs, and 4 homogeneity exceptions. A clean packet carries eight synthetic state-specific drafts, all copied from the same analytical result set. The implementation verifies that analyte, unit, LOQ, and the complete source-result hash do not drift between drafts.

Replay is idempotent: the same 96 rows add no packets, drafts, holds, or events after the first pass. HOLD rows create no downstream packet or draft. Final release is copy-only, requires a two-token named human plus an explicit `APR-...` approval ID, remains unsent, and rejects automatic release.

The state-pack labels and rule-pack versions in this fixture are synthetic identifiers. They are test data, not statements of current law or state requirements.

## Run

From this directory:

```bash
python -m unittest -v test_newbloom_beverage_coa.py
python -m py_compile newbloom_beverage_coa.py test_newbloom_beverage_coa.py
python newbloom_beverage_coa.py
```

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
