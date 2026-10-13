# weck-coc-preaccession-validator-lims-01 receipt

State: TESTED
Binary: `python3 test_weck_coc_preaccession_validator.py`
CLI: `python3 revenue/weck_coc_preaccession_validator/runner.py`

| check | expected | actual |
|---|---|---|
| input COCs | 400 | 400 |
| valid | 320 | 320 |
| exceptions | 80 | 80 |
| accessions | 320 | 320 |
| holds | 80 | 80 |
| orphan tests | 0 | 0 |
| duplicate accessions | 0 | 0 |
| autonomous released | 0 | 0 |
| human released | 320 | 320 |
| COA releasable | 320 | 320 |
| EDD releasable | 320 | 320 |
| production writes | 0 | 0 |
| audit_sha256 | 75c9c6ffa53e9c6cbaa025ad63254f6134ef9f9ba239d546e758c1c15476e5f3 | 75c9c6ffa53e9c6cbaa025ad63254f6134ef9f9ba239d546e758c1c15476e5f3 |

Buyer: Weck Laboratories / Agustin Pierri. Complement incumbent LIMS. Interfaces simulated. No PHI, production write, live reporting, billing, or automatic result release. HOLD / BUILD-AND-VERIFY. PRE-SALE TRANSPORT: NONE. cash_usd=0.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
