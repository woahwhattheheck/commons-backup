# UNR biobank courier-to-freezer custody LIMS

Demand: `unr-biobank-courier-custody-lims-01`

This package is a **fully synthetic, deidentified, read-only shadow** for approved study/IRB/MTA reference → courier/package custody → receipt/temperature gate → deidentification check → specimen/aliquot genealogy → freezer position → controlled research-use authorization.

It contains no PHI-shaped fixture fields, does not perform clinical or diagnostic interpretation, and has no automatic research-use release path.

## Frozen acceptance contract

`fixtures/unr_120_shipments.json` deterministically expands to 120 synthetic/deidentified shipments:

- 90 `READY_FOR_STORAGE`
- 8 `IRB_MTA_REFERENCE_INVALID`
- 6 `CUSTODY_TEMPERATURE_FAIL`
- 6 `DUPLICATE_BARCODE`
- 5 `SPECIMEN_MANIFEST_MISMATCH`
- 5 `UNAPPROVED_TRANSPORT_ROUTE`

Held shipments create no specimen, aliquot, or freezer-position state. Each accepted parent specimen and its two synthetic aliquots maps exactly once to a unique freezer coordinate. Source, courier, custody, temperature, and position SHA-256 lineage is preserved. A full second replay adds zero specimens, aliquots, positions, holds, or events. Research-use availability requires a non-empty named human reviewer.

Fixture SHA-256: `3c9a5e3ec64fd7d26bf6fc1f1168b4fe962ec8589b2e681362e775ef26fed360`  
Expanded 120-record SHA-256: `7aea13dd195585087e686216defb56395170729cf59501ba1ab1d3c406f1694f`  
Manifest content-envelope signature: `c50b31526f037a2e365d66ed4556ceec0a481dfcb02ce75ed5004a17014618d9`

## Run

```bash
python -m unittest -v test_unr_biobank_custody.py
```

All adapters remain simulated/read-only. Real authority, institutional policy, approved routes, source schemas, deidentified golden round trips, role mapping, retention/deletion rules, and named operational release roles remain external inputs.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
