# Agdia cucurbit order orchestrator LIMS

Demand: `agdia-cucurbit-order-orchestrator-lims-01`

Fully **synthetic, deidentified, read-only** mail-in order orchestration for package/form/tube reconciliation, crop/panel + assay-version routing, simulated permit/license reference gates, aliquot jobs, custody lineage, and staged designated-contact reports.

## Frozen acceptance

`fixtures/agdia_300_cases.json` expands deterministically to 300 synthetic cases:

- 240 `READY`
- 15 `ORPHAN_OR_MISSING_FORM`
- 15 `MISSING_TUBE`
- 8 `PERMIT_REFERENCE_INVALID`
- 8 `LICENSE_REFERENCE_INVALID`
- 7 `CROP_PANEL_MISMATCH`
- 7 `ASSAY_VERSION_UNAPPROVED`

READY rows reconcile 1 package / 1 form / 2 tubes, route to the exact approved crop panel and assay version, create two aliquots, preserve source/custody/route SHA-256 lineage, and stage an unsent report only for the designated synthetic contact. Held rows create no report or aliquots. Full replay adds zero new state. Automatic release is disabled.

Fixture SHA-256: `51d0ac6c4b93abee3cf39dc5496776e304e581aa8465b68e7cd0905b79ab5619`  
Expanded 300-record SHA-256: `d64a1dd836be3e3a4139c7db5dd42554c3ff95ee5491f9df7e8448f37e7614be`  
Manifest signature: `b7f33a1ca6a3bcfa60ca93b625c37a18fc7f7dcd63df447760cc6e6aa3c92d90`

Run: `python -m unittest -v test_agdia_order_orchestrator.py`

No real permit/license determination, production write, outreach, external send, or automatic release.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
