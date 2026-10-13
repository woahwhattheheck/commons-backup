# roslinct-hopkinton-paperless-qc-lims-01 receipt

State: TESTED
Binary: `python3 test_roslinct_hopkinton_paperless_qc.py`
CLI: `python3 roslinct_hopkinton_paperless_qc.py` → ok true, failures []

| check | expected | actual |
|---|---|---|
| input rows | 240 | 240 |
| valid completed | 216 | 216 |
| prescribed HOLD | 24 | 24 |
| accessioned | 216 | 216 |
| human released | 216 | 216 |
| autonomous released | 0 | 0 |
| instruments | 12 | 12 |
| contract labs | 3 | 3 |
| replay added accessions | 0 | 0 |
| audit_sha256 | 93e5ce0ef00ca6de9ac87203b67ec05f9eb80d1cb10ffb284b1948a195dab83a | 93e5ce0ef00ca6de9ac87203b67ec05f9eb80d1cb10ffb284b1948a195dab83a |
| custody_sha256 | 185cea2779565cbc000a2caeabd021c6405b05ee7d83afdf4cccd0cc0cd646a9 | 185cea2779565cbc000a2caeabd021c6405b05ee7d83afdf4cccd0cc0cd646a9 |
| results_sha256 | 2973a64b14ac91f8a5358bf0a6b80790439c885d630b058da3cb826d4affd1fc | 2973a64b14ac91f8a5358bf0a6b80790439c885d630b058da3cb826d4affd1fc |

Buyer: RoslinCT US Hopkinton / Lisa Mello.
Interfaces simulated/read-only. No real Part 11 validation claim. No production writes, billing, transfers, material disposition, or automatic release. AquaTrace HOLD / BUILD-AND-VERIFY. PRE-SALE TRANSPORT: NONE. cash_usd=0.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
