# BA Sciences multi-site stability intake shadow

Demand: `basciences-multisite-stability-intake-lims-01`

Synthetic/deidentified, read-only intake normalization across four posted form families: Micro, Chemistry, Water, and Stability. The product validates quote/PO/specification controls, synthetic storage/handling completeness, one-line/one-result mapping, three-site routing, result cardinality, and deterministic Stability pull schedules while retaining source-document provenance on every normalized field.

## Frozen acceptance

The compact signed generator expands deterministically to **220 synthetic intake records**:

- **180 READY**;
- **40 HOLD before testing**, allocated deterministically across every posted defect family:
  - 7 `EXPIRED_QUOTE`
  - 7 `QUOTE_PO_CONFLICT`
  - 7 `MISSING_CONTROLLED_OR_STORAGE_DATA`
  - 7 `ABSENT_SPECIFICATION`
  - 6 `AMBIGUOUS_RESULT_MAPPING`
  - 6 `INCORRECT_STABILITY_TOTALS`

Every READY record:

- creates exactly one accession and one staged-not-run job;
- uses the exact synthetic route pinned in the signed manifest for its form family;
- produces exactly the pinned result cardinality and one staged, unsent report;
- retains source document SHA-256 + source coordinate on every normalized field;
- if Stability, creates the signed four-pull schedule at offsets 0/30/90/180 days with two synthetic units per pull.

Every HOLD creates **zero accession, job, result, report, or pull-schedule state**. Full same-ledger replay adds zero state/events and preserves the state digest. A changed-content replay under an already-seen record ID fails before mutation.

Final report release is a copy-only, unsent operation requiring a non-reserved two-token human reviewer. Automatic release is disabled.

## Run

```bash
python -m unittest -v test_basciences_stability_intake.py
python -m py_compile basciences_stability_intake.py test_basciences_stability_intake.py
python basciences_stability_intake.py
```

## Boundary

Synthetic/deidentified fixtures and simulated/read-only state only. Synthetic route/method IDs are fixture assertions, not claims about buyer production configuration. No production LIMS, provider, customer, controlled-substance, regulatory, compliance, report-send, outreach, demo, payment, or spend action is performed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
