# rosecity-olcc-metrc-sampling-lims-01 receipt

State: TESTED
Binary: `python3 test_rosecity_olcc_metrc_sampling.py` → 10/10 OK
CLI: `python3 rosecity_olcc_metrc_sampling.py` → ok true, failures []

| check | value |
|---|---|
| input rows | 100 |
| DISPATCH_READY | 75 |
| HOLD | 25 |
| missing Metrc transfer | 8 |
| batch-count mismatch | 7 |
| duplicate package IDs | 5 |
| unconfirmed appointments | 5 |
| HOLD dispatches | 0 |
| custody chains | 75 |
| accessions | 75 |
| emails sent | 0 |
| CoA released | 0 |
| replay added dispatches | 0 |
| manifest_sha256 | a15ea29c2fdfa6094fe8a20344df724a7b4b75e1ee07e0b11c8cdeeac4ad19ba |

Read-only adapters only. No Metrc/state write, compliance decision, outreach, prospect demo, email send, or automatic result/CoA release. HOLD / BUILD-AND-VERIFY. PRE-SALE TRANSPORT: NONE. cash_usd=0.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
