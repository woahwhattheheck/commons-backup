# rmb-crosssite-courier-accession-lims-01 receipt

State: TESTED
Binary: `python3 test_rmb_crosssite_courier_accession.py` → 11/11 OK
CLI: `python3 rmb_crosssite_courier_accession.py` → ok true, failures []

| check | value |
|---|---|
| input rows | 300 |
| valid binds | 240, one incumbent accession + facility each |
| RMB Detroit Lakes | 120 |
| Beckton Ponce | 120 |
| held | 60 |
| HOLD_RECEIPT_OVER_48H | 10 |
| HOLD_MISSED_COURIER_CUTOFF | 10 |
| HOLD_DUPLICATE_SAMPLE_ID | 10 |
| HOLD_BROKEN_COOLER_CUSTODY | 10 |
| HOLD_FACILITY_METHOD_SCOPE_MISMATCH | 10 |
| HOLD_LEGACY_SITE_MAPPING | 10 |
| hashes reconciled | 240 |
| reports released | 0 |
| replay added accessions | 0 |
| replay added holds | 0 |
| incumbent / production writes | 0 |
| fixture_sha256 | 6b3ca3bdf583e85e0e43e6877540ebfa37f585613f35eaf9f051d3165112d9e8 |
| manifest_sha256 | a0afb5a53305442d6ccee32dc66831a0a09987486aa4e1db53afb2d8590e984c |

Read-only shadow. Existing LIMS remains authoritative. No autonomous certification or release. HOLD / BUILD-AND-VERIFY. PRE-SALE TRANSPORT: NONE. cash_usd=0.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
