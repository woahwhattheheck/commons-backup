# savant-fe8-order-report-lims-01 receipt

State: TESTED
Binary: `python3 test_savant_fe8_order_report.py`
CLI: `python3 savant_fe8_order_report.py`

| check | expected | actual |
|---|---|---|
| input rows | 100 | 100 |
| accessioned once | 80 | 80 |
| held | 20 | 20 |
| HOLD codes | 5 MISSING_SDS + 5 MISSING_METADATA + 5 DUPLICATE_ID + 5 INVALID_METHOD | exact |
| scheduled | 80 | 80 |
| unscheduled holds | 20 | 20 |
| released reports (autonomous) | 0 | 0 |
| replay added accessions | 0 | 0 |
| fixture_sha256 | 2bcac0d66becddbd327a4f478480c77ef4f79305310ff3d7dde3adb2369a8c32 | match |
| audit_sha256 | 7181103bfe4b466c8472ab9d0fa82c10265e4a120c796aec843dd4be4ae08c57 | match |
| report_digest | a5853f7e35e396bdd9843053f3f45c14d4a340945996977db0b478921c0941fa | match |

Buyer: Savant Labs / Antonino Di Bartolo. Single-method FE8 TAF/SDS lane. Interfaces simulated. No production write, outreach, or automatic release. HOLD / BUILD-AND-VERIFY. PRE-SALE TRANSPORT: NONE. cash_usd=0.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
