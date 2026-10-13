# MVMTC aerospace fastener / additive-coupon evidence LIMS

Demand: `mvmtc-aero-fastener-evidence-lims-01`

This is a **synthetic, read-only shadow** for the Miami Valley Materials Testing Center build demand. It models the bounded evidence path requested in the queue:

`quote / PO -> sample + container accession -> synthetic A2LA-scope + method revision -> mechanical / chemical / metallography job -> QC -> staged evidence pack`

It does not connect to MVMTC systems, contact the buyer, make a materials-qualification decision, or release an evidence pack automatically. The fixture contains no controlled drawings and no weapon, vehicle, propulsion, or mission data.

## Frozen acceptance

`fixtures/mvmtc_100_lots.json` deterministically expands to 100 synthetic lots:

- 75 `READY`
- 8 `MISSING_PO_QUOTE_LINK`
- 5 `DUPLICATE_CONTAINER`
- 4 `METHOD_OUT_OF_SCOPE`
- 4 `CHEMISTRY_MATERIAL_MISMATCH`
- 4 `QC_FAIL`

HOLD rows create no job, worksheet, or evidence pack. Every READY row carries and preserves four lineage hashes: source, scope+method, specimen, and raw-value+unit. Evidence packs remain `STAGED_HUMAN_REVIEW` until a non-reserved named reviewer is supplied. Replaying the full frozen corpus adds zero lots, jobs, worksheets, evidence packs, holds, or events.

## Run

```bash
python revenue/production-lims/mvmtc-aero-fastener-evidence/test_mvmtc_fastener_evidence.py
python -m py_compile revenue/production-lims/mvmtc-aero-fastener-evidence/mvmtc_fastener_evidence.py revenue/production-lims/mvmtc-aero-fastener-evidence/test_mvmtc_fastener_evidence.py
python revenue/production-lims/mvmtc-aero-fastener-evidence/mvmtc_fastener_evidence.py
```

Only Python standard-library modules are used.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
