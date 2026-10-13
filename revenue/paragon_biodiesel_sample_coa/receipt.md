# paragon-biodiesel-sample-coa-lims-01 receipt

State: TESTED
Binary: `python3 test_paragon_biodiesel_sample_coa.py` → 10/10 OK
CLI: `python3 paragon_biodiesel_sample_coa.py` → ok true, failures []

| check | value |
|---|---|
| input rows | 120 |
| valid accessioned once | 100 |
| accessioned total | 105 (100 in-spec + 5 OOS) |
| HOLD | 20 |
| HOLD_INCOMPLETE_COC | 5 |
| HOLD_INCOMPLETE_SDS | 5 |
| HOLD_DUPLICATE_ID | 5 |
| HOLD_OOS | 5 |
| staged CoA / human released | 100 / 100 |
| duplicate accessions | 0 |
| golden_set_sha256 | 13b30045df03d9ac2a8493924bcd5da2a5f51486be77e6a2fb6d4bd109f14275 |
| audit_sha256 | 70e0875552b9024e42b0117cbcd63fe4d56e7b55277fe2ea700ccfaa9594e8da |
| replay added accessions | 0 |

Interfaces simulated. No autonomous certification or release. No production write. No outreach. AquaTrace HOLD / BUILD-AND-VERIFY. PRE-SALE TRANSPORT: NONE. cash_usd=0.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
