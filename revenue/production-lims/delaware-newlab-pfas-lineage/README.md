# Delaware new-lab PFAS and microbiology lineage LIMS

Demand: `delaware-newlab-pfas-lineage-lims-01`

This package is a **synthetic, read-only shadow** for the Delaware DNREC Environmental Laboratory new-lab transition. It preserves quote/request → accession → matrix/method/version → PFAS LC-MS/MS or molecular/microbiology → QC → staged-report lineage while retaining old/new-facility provenance.

It is not a production adapter and does not make a regulatory or public-health decision. No report is automatically released.

## Frozen acceptance contract

`fixtures/delaware_200_requests.json` deterministically expands to 200 synthetic requests:

- 150 `READY`
- 15 `MISSING_MATRIX_SDS_CUSTODY`
- 10 `DUPLICATE_CONTAINER`
- 10 `METHOD_MATRIX_MISMATCH`
- 10 `CALIBRATION_QC_FAIL`
- 5 `LEGACY_NEW_FACILITY_ID_COLLISION`

Held requests schedule no accession, analytical job, or report. READY requests preserve exact source, method, and value/unit/qualifier SHA-256 lineage into a `STAGED_HUMAN_REVIEW` report. A full second replay adds zero accessions, jobs, reports, holds, or events. The authoritative-state object is fingerprinted and remains unchanged.

Fixture SHA-256: `6df55cb90f4bd51883e68dbdde038e7cd83b52ea015321f9e3c238178464d1b3`  
Expanded 200-record SHA-256: `8ca2d239592c789a320abcd5b01c296573f75ab483b10493669ce49aa4ee8cf5`  
Manifest content-envelope signature: `2e0abd59d792a986f6aea9ca30c05f0ba71263d3809e9d5c75a0b9e7ff5c959d`

## Run

```bash
python -m unittest -v test_delaware_newlab_lineage.py
```

All adapters remain simulated/read-only. Production schemas, buyer-approved methods, facility identifiers, QC policy, de-identified golden round trips, and named release roles remain buyer-owned inputs.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
