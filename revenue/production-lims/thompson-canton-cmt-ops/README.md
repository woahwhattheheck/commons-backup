# Thompson & Lichtner Canton CMT gate — synthetic acceptance package

This additive package implements `thompson-canton-cmt-ops-lims-01` as a **synthetic, read-only intake → eligibility → schedule gate**. It does not connect to or mutate real staffing, accreditation, scheduling, LIMS, instrument, reporting, customer, or provider systems, and it makes no real hiring or accreditation claim.

## Frozen acceptance

- 100 deterministic synthetic jobs spanning concrete, aggregate, masonry, and enclosure materials.
- Exactly 80 `SCHEDULED`; exactly 20 `HOLD` (4 each incomplete request, method-revision mismatch, unqualified technician, unavailable equipment, expired calibration).
- Every scheduled job passes complete request, synthetic method/scope eligibility, technician qualification, equipment identity, calibration date, and collision-free slot validation exactly once.
- The package has **no laboratory-run path**: every scheduled record and result stub stays `NOT_RUN`.
- Exact retry is idempotent and zero-add; same-submission changed content fails closed without state mutation.
- Raw recipe, expanded fixture, worklist, result-stub ledger, staged-report ledger, and full audit-state SHA-256 digests are executable manifest gates.
- Reports stay `STAGED_PEER_REVIEW`; release is copy-only/unsent, requires a named human, rejects automation identities, and automatic release is disabled.

## Run

```bash
cd revenue/production-lims/thompson-canton-cmt-ops
python -m unittest -v test_thompson_canton_cmt.py
python -m py_compile thompson_canton_cmt.py test_thompson_canton_cmt.py
python thompson_canton_cmt.py fixtures/thompson_100_jobs.json fixtures/manifest.json
```

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
