# MVTL NEMAGENE fertility/SCN pairing shadow

Demand: `mvtl-nemagene-pairing-release-lims-01`

Synthetic/read-only incumbent-LIMS augmentation for Minnesota Valley Testing Laboratories. It binds a synthetic SCN add-on job/result to the original soil/fertility accession, checks deterministic two-business-day SLA dates, preserves source/result lineage, and stages a combined report for named-human review.

## Frozen acceptance

- 500 synthetic soil orders: 400 valid and 100 HOLD.
- Exactly 250 of the 400 valid orders are fertility+SCN; the other 150 are fertility-only.
- The frozen truth set has 25 each `DUPLICATE_BARCODE`, `MISSING_ID`, `ADDON_SAMPLE_MISMATCH`, and `DIVERGENT_RECEIPT`.
- Every valid order creates one accession; every valid SCN result stays bound to the same original sample/fertility accession; zero orphan or duplicate SCN results.
- Signed receipt dates map deterministically to the fixture's two-business-day SLA due date.
- Every staged combined report preserves fertility/SCN result digests, SCN lineage hash when applicable, source hash, and a deterministic combined-result digest.
- Full replay adds zero state and leaves state/combined-manifest hashes unchanged.
- Named-human release is copy-only and unsent; automatic release is disabled.

Run `python -m unittest -v test_mvtl_nemagene_pairing.py`, `python -m py_compile ...`, and `python mvtl_nemagene_pairing.py`.

## Boundary

Synthetic/deidentified data and a read-only mock incumbent-LIMS snapshot only. No biological/diagnostic interpretation, live LIMS/state/provider/customer write, report send, outreach, spend, or autonomous release. The two-business-day rule and all identifiers are fixture assertions pending buyer/vendor golden validation.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
